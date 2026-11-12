"""Leitura e escrita de notas markdown com frontmatter YAML.

Esta é a peça mais delicada do projeto: o "banco de dados" são arquivos que o
usuário também edita no Obsidian e que agentes de IA também alteram. Então:

- usamos ruamel.yaml em modo "round-trip", que preserva a ordem das chaves, os
  comentários e as aspas do frontmatter (o PyYAML reescreveria tudo);
- o corpo da nota nunca é reformatado;
- a escrita é atômica (grava num temporário e troca de uma vez), para nunca
  deixar um arquivo pela metade;
- cada nota tem uma "versão" (hash do conteúdo). Quem grava informa a versão
  que leu; se o arquivo mudou no disco nesse meio-tempo, a gravação é recusada.
"""

from __future__ import annotations

import datetime as dt
import io
import math
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.events import AliasEvent, CollectionEndEvent, CollectionStartEvent

from orquestra.armazenamento import ConflitoDeEscrita, gravar_bytes, pasta_local, versao
from orquestra.caminhos import caminho_no_vault


class Conflito(Exception):
    """O arquivo mudou no disco depois que foi lido."""


class FrontmatterInvalido(Exception):
    """O frontmatter não pôde ser lido; por segurança não reescrevemos o arquivo."""


# Marcador que diferencia "não confira a versão" de "a versão esperada é None".
_SEM_CONFERIR = object()
_leitores = threading.local()


def _yaml() -> YAML:
    y = YAML()  # modo round-trip (padrão do ruamel)
    y.preserve_quotes = True
    y.allow_unicode = True
    y.width = 4096  # não quebrar linhas longas
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def validar_aliases(texto: str) -> None:
    """ruamel round-trip pode representar autoalias como None; recuse antes disso."""
    if "&" not in texto or "*" not in texto:
        return
    pilha: list[str | None] = []
    ativos: set[str] = set()
    for evento in _yaml().parse(texto):
        if isinstance(evento, CollectionStartEvent):
            pilha.append(evento.anchor)
            if evento.anchor:
                ativos.add(evento.anchor)
        elif isinstance(evento, CollectionEndEvent):
            ancora = pilha.pop()
            if ancora:
                ativos.discard(ancora)
        elif isinstance(evento, AliasEvent) and evento.anchor in ativos:
            raise ValueError("Aliases YAML circulares não podem ser editados pelo painel.")


def _yaml_indice() -> YAML:
    """Leitor por thread; só usa C se seus escalares corresponderem ao YAML 1.2.

    Algumas versões do backend C tratam 052 como octal (YAML 1.1). Nesse caso
    usamos o SafeConstructor Python. Instâncias que falham não são reutilizadas.
    """
    leitor = getattr(_leitores, "seguro", None)
    if leitor is None:
        leitor = YAML(typ="safe")
        leitor.version = (1, 2)
        prova = "decimal: 052\noctal: 0o52\nsexagesimal: 12:34\ntexto: yes\nbooleano: true\nnumero: 1e2\ndata: 2026-11-11\n"
        esperado = simples(_yaml().load(prova))
        try:
            observado = simples(leitor.load(prova))
        except Exception:
            observado = None
        if observado != esperado or any(type(observado[k]) is not type(v) for k, v in esperado.items()):
            leitor = YAML(typ="safe", pure=True)
            leitor.version = (1, 2)
        _leitores.seguro = leitor
    return leitor


def _carregar_frontmatter(texto: str, *, somente_indice: bool) -> Any:
    # Tags, directives e merges podem ter tipos/ordem próprios do round-trip.
    # O caminho de edição sempre relê com RT, preservando comentários e aspas.
    if not somente_indice or "!" in texto or "%YAML" in texto or "<<:" in texto:
        return _yaml().load(texto)
    try:
        return _yaml_indice().load(texto)
    except Exception:
        if hasattr(_leitores, "seguro"):
            del _leitores.seguro
        return _yaml().load(texto)


def calcular_versao(dados: bytes) -> str:
    return versao(dados)


def separar(texto: str) -> tuple[str | None, str]:
    """Divide o texto em (frontmatter, corpo). Sem frontmatter, devolve (None, texto)."""
    if not texto.startswith("---"):
        return None, texto
    linhas = texto.split("\n")
    if linhas[0].strip() != "---":
        return None, texto
    for i in range(1, len(linhas)):
        if linhas[i].strip() in ("---", "..."):
            return "\n".join(linhas[1:i]), "\n".join(linhas[i + 1 :])
    return None, texto


def simples(valor: Any, *, _vistos: set[int] | None = None, _profundidade: int = 0, _orcamento: list[int] | None = None) -> Any:
    """Converte valores do YAML em tipos simples (para JSON e templates)."""
    _vistos = set() if _vistos is None else _vistos
    _orcamento = [10000] if _orcamento is None else _orcamento
    _orcamento[0] -= 1
    if _profundidade > 40 or _orcamento[0] < 0:
        raise ValueError("O frontmatter é complexo demais para o painel (limite de profundidade ou de valores).")
    if isinstance(valor, dt.datetime):
        return valor.isoformat(sep=" ", timespec="minutes")
    if isinstance(valor, dt.date):
        return valor.isoformat()
    if isinstance(valor, dict):
        if id(valor) in _vistos:
            raise ValueError("O frontmatter contém aliases YAML circulares.")
        _vistos.add(id(valor))
        try:
            return {str(k): simples(v, _vistos=_vistos, _profundidade=_profundidade + 1, _orcamento=_orcamento) for k, v in valor.items()}
        finally:
            _vistos.remove(id(valor))
    if isinstance(valor, (list, tuple)):
        if id(valor) in _vistos:
            raise ValueError("O frontmatter contém aliases YAML circulares.")
        _vistos.add(id(valor))
        try:
            return [simples(v, _vistos=_vistos, _profundidade=_profundidade + 1, _orcamento=_orcamento) for v in valor]
        finally:
            _vistos.remove(id(valor))
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, int):
        return int(valor)
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise ValueError("O frontmatter contém um número não finito, que não pode ser representado no painel.")
        return float(valor)
    return str(valor)


@dataclass
class Nota:
    caminho: Path  # caminho absoluto no disco
    rel: str  # caminho relativo ao vault, sempre com "/"
    meta: CommentedMap = field(default_factory=CommentedMap)
    corpo: str = ""
    versao: str = ""
    mtime: float = 0.0
    crlf: bool = False  # o arquivo usava quebras de linha do Windows
    erro: str | None = None  # frontmatter ilegível
    bom: bool = False
    _original: bytes | None = field(default=None, repr=False)
    _texto_original: str | None = field(default=None, repr=False)
    _cabecalho_original: str = field(default="", repr=False)
    _meta_original: str = field(default="", repr=False)
    vault: Path | None = field(default=None, repr=False)
    somente_indice: bool = field(default=False, repr=False)

    @property
    def titulo(self) -> str:
        t = self.meta.get("titulo")
        return str(t).strip() if t not in (None, "") else self.caminho.stem

    def campo(self, nome: str, padrao: Any = None) -> Any:
        if nome == "titulo":
            return self.titulo
        return simples(self.meta.get(nome, padrao))

    def campos(self) -> dict[str, Any]:
        return {str(k): simples(v) for k, v in self.meta.items()}


def ler_nota(caminho: Path, vault: Path, *, somente_indice: bool = False) -> Nota:
    caminho = caminho_no_vault(vault, caminho)
    bruto = caminho.read_bytes()
    erro = None
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("utf-8-sig", errors="replace")  # apenas visualização, nunca regrava
        erro = "O arquivo não está em UTF-8 válido. Converta uma cópia no editor antes de editar aqui."
    crlf = "\r\n" in texto
    texto = texto.replace("\r\n", "\n")
    fm, corpo = separar(texto)

    meta = CommentedMap()
    cabecalho = texto[: len(texto) - len(corpo)] if fm is not None else ""
    if fm is None and texto.split("\n", 1)[0].strip() == "---":
        erro = erro or "O frontmatter começou com --- mas não foi fechado. Corrija no editor antes de gravar."
    if fm is not None and fm.strip():
        try:
            if len(fm) > 256 * 1024:
                raise ValueError("O frontmatter excede o limite de 256 KiB do painel.")
            validar_aliases(fm)
            dados = _carregar_frontmatter(fm, somente_indice=somente_indice)
            if isinstance(dados, dict):
                meta = dados if isinstance(dados, CommentedMap) else CommentedMap(dados)
                simples(meta)  # valida ciclos/expansão antes de expor a templates e JSON
            elif dados is None and fm.strip() and not somente_indice:
                # YAML só de comentários não produz um mapa. Associe-os ao mapa
                # novo para que também sobrevivam quando a pessoa adicionar campos.
                meta.yaml_set_start_comment(fm)
            elif dados is not None:
                erro = erro or "O frontmatter precisa ser uma lista de campos no formato chave: valor."
        except Exception as e:  # YAML malformado: mostramos o aviso e não tocamos no arquivo
            erro = erro or "YAML inválido no frontmatter: " + str(e).strip().splitlines()[0]
    if erro:
        corpo = texto  # mostra o arquivo inteiro como está
        meta = CommentedMap()  # não encaminha estrutura parcial/circular a templates

    return Nota(
        caminho=caminho,
        rel=caminho.relative_to(vault).as_posix(),
        meta=meta,
        corpo=corpo,
        versao=calcular_versao(bruto),
        mtime=caminho.stat().st_mtime,
        crlf=crlf,
        erro=erro,
        bom=bruto.startswith(b"\xef\xbb\xbf"),
        _original=None if somente_indice else bruto,
        _texto_original=None if somente_indice else texto,
        _cabecalho_original="" if somente_indice else cabecalho,
        _meta_original="" if somente_indice or erro else _serializar_meta(meta),
        vault=vault,
        somente_indice=somente_indice,
    )


def _serializar_meta(meta: CommentedMap) -> str:
    saida = io.StringIO()
    _yaml().dump(meta, saida)
    return saida.getvalue()


def montar(nota: Nota) -> str:
    """Reutiliza o cabeçalho original quando somente o corpo mudou."""
    serializado = _serializar_meta(nota.meta)
    if nota._original is not None and serializado == nota._meta_original:
        cabecalho = nota._cabecalho_original
        if cabecalho and nota.corpo and not cabecalho.endswith("\n"):
            cabecalho += "\n"
        return cabecalho + nota.corpo
    if not nota.meta and not nota._cabecalho_original:
        return nota.corpo
    return "---\n" + serializado + "---\n" + nota.corpo


def _partes_originais(nota: Nota) -> tuple[str, str]:
    texto = nota._original.decode("utf-8-sig") if nota._original is not None else ""
    cabecalho = nota._cabecalho_original
    if not cabecalho:
        return "", texto
    if not cabecalho.endswith("\n"):
        return texto, ""  # delimitador final no fim do arquivo
    quantidade = cabecalho.count("\n")
    partes = texto.split("\n", quantidade)
    return "\n".join(partes[:-1]) + "\n", partes[-1]


def _bytes_da_nota(nota: Nota, texto: str) -> bytes:
    if nota._original is not None and texto == nota._texto_original:
        return nota._original
    cabecalho_bruto, corpo_bruto = _partes_originais(nota)
    corpo_original = (nota._texto_original or "")[len(nota._cabecalho_original):]
    if nota._original is not None and nota.corpo == corpo_original:
        # Uma propriedade não tem licença para normalizar quebras do corpo.
        cabecalho = texto[: len(texto) - len(nota.corpo)]
        quebra = "\r\n" if ("\r\n" in cabecalho_bruto or (not cabecalho_bruto and nota.crlf)) else "\n"
        resultado = cabecalho.replace("\n", quebra) + corpo_bruto
    elif nota._original is not None and _serializar_meta(nota.meta) == nota._meta_original:
        # Editar o corpo também preserva bytes do cabeçalho que não foi editado.
        quebra = "\r\n" if "\r\n" in corpo_bruto or (not corpo_bruto and nota.crlf) else "\n"
        if cabecalho_bruto and nota.corpo and not cabecalho_bruto.endswith("\n"):
            cabecalho_bruto += quebra
        resultado = cabecalho_bruto + nota.corpo.replace("\n", quebra)
    else:
        resultado = texto.replace("\n", "\r\n") if nota.crlf else texto
    dados = resultado.encode("utf-8")
    return b"\xef\xbb\xbf" + dados if nota.bom else dados


def gravar_nota(nota: Nota, versao_esperada: Any = _SEM_CONFERIR, criar: bool = False) -> Nota:
    """Publica uma nota com precondição e recuperação; criação é exclusiva."""
    if nota.somente_indice:
        raise FrontmatterInvalido("Releia a nota do disco antes de gravar; uma entrada do índice é somente leitura.")
    if nota.erro:
        raise FrontmatterInvalido(nota.erro)
    try:
        simples(nota.meta)
        if len(_serializar_meta(nota.meta)) > 256 * 1024:
            raise ValueError("O frontmatter excede o limite de 256 KiB do painel.")
    except ValueError as erro:
        raise FrontmatterInvalido(str(erro)) from erro

    texto = montar(nota)
    dados = _bytes_da_nota(nota, texto)
    if not criar and (versao_esperada is _SEM_CONFERIR or versao_esperada is None):
        raise Conflito("Informe a versão lida antes de editar esta nota.")
    def validar():
        if nota.vault is not None:
            caminho_no_vault(nota.vault, nota.caminho)
            if pasta_local().resolve().is_relative_to(nota.vault.resolve()):
                raise ValueError("ORQUESTRA_HOME precisa ficar fora do vault para manter a recuperação local privada.")
    try:
        gravar_bytes(nota.caminho, dados, esperado=versao_esperada, criar=criar,
                     validar=validar)
    except ConflitoDeEscrita as erro:
        raise Conflito(str(erro)) from erro
    nota.versao = calcular_versao(dados)
    nota.mtime = nota.caminho.stat().st_mtime
    nota._original = dados
    nota._texto_original = texto
    nota._cabecalho_original = texto[: len(texto) - len(nota.corpo)]
    nota._meta_original = _serializar_meta(nota.meta)
    return nota


_PROIBIDOS = re.compile(r'[\\/:*?"<>|#^\[\]\r\n\t]')


def nome_de_arquivo(titulo: str) -> str:
    """Transforma um título em nome de arquivo legível (com acentos e espaços).

    Mantemos o nome parecido com o título porque é assim que o Obsidian mostra as
    notas; só removemos o que o Windows, o macOS ou os links do Obsidian não aceitam.
    """
    nome = _PROIBIDOS.sub(" ", titulo)
    nome = re.sub(r"\s+", " ", nome).strip(" .")
    nome = nome[:80].rstrip(" .")
    while len(nome.encode("utf-8")) > 200:
        nome = nome[:-1]
    if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", nome, re.IGNORECASE):
        nome = "_" + nome
    return nome or "Sem título"


def caminho_livre(pasta: Path, titulo: str) -> Path:
    """Devolve um caminho .md que ainda não existe na pasta (acrescenta 2, 3...)."""
    base = nome_de_arquivo(titulo)
    caminho = pasta / f"{base}.md"
    n = 2
    while caminho.exists():
        caminho = pasta / f"{base} {n}.md"
        n += 1
    return caminho
