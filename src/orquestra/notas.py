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
import hashlib
import io
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


class Conflito(Exception):
    """O arquivo mudou no disco depois que foi lido."""


class FrontmatterInvalido(Exception):
    """O frontmatter não pôde ser lido; por segurança não reescrevemos o arquivo."""


# Marcador que diferencia "não confira a versão" de "a versão esperada é None".
_SEM_CONFERIR = object()


def _yaml() -> YAML:
    y = YAML()  # modo round-trip (padrão do ruamel)
    y.preserve_quotes = True
    y.allow_unicode = True
    y.width = 4096  # não quebrar linhas longas
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def calcular_versao(dados: bytes) -> str:
    return hashlib.sha1(dados).hexdigest()[:12]


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


def simples(valor: Any) -> Any:
    """Converte valores do YAML em tipos simples (para JSON e templates)."""
    if isinstance(valor, dt.datetime):
        return valor.isoformat(sep=" ", timespec="minutes")
    if isinstance(valor, dt.date):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {str(k): simples(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [simples(v) for v in valor]
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, int):
        return int(valor)
    if isinstance(valor, float):
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


def ler_nota(caminho: Path, vault: Path) -> Nota:
    bruto = caminho.read_bytes()
    texto = bruto.decode("utf-8-sig", errors="replace")
    crlf = "\r\n" in texto
    texto = texto.replace("\r\n", "\n")
    fm, corpo = separar(texto)

    meta = CommentedMap()
    erro = None
    if fm is not None and fm.strip():
        try:
            dados = _yaml().load(fm)
            if isinstance(dados, CommentedMap):
                meta = dados
            elif dados is not None:
                erro = "O frontmatter precisa ser uma lista de campos no formato chave: valor."
        except Exception as e:  # YAML malformado: mostramos o aviso e não tocamos no arquivo
            erro = "YAML inválido no frontmatter: " + str(e).strip().splitlines()[0]
    if erro:
        corpo = texto  # mostra o arquivo inteiro como está

    return Nota(
        caminho=caminho,
        rel=caminho.relative_to(vault).as_posix(),
        meta=meta,
        corpo=corpo,
        versao=calcular_versao(bruto),
        mtime=caminho.stat().st_mtime,
        crlf=crlf,
        erro=erro,
    )


def montar(nota: Nota) -> str:
    """Remonta o texto do arquivo a partir do frontmatter e do corpo."""
    if not nota.meta:
        return nota.corpo
    saida = io.StringIO()
    _yaml().dump(nota.meta, saida)
    return "---\n" + saida.getvalue() + "---\n" + nota.corpo


def gravar_nota(nota: Nota, versao_esperada: Any = _SEM_CONFERIR, criar: bool = False) -> Nota:
    """Grava a nota no disco de forma atômica.

    - `versao_esperada`: versão que o chamador leu. Se o arquivo no disco estiver
      diferente, levanta `Conflito` e nada é gravado.
    - `criar=True`: falha se o arquivo já existir (nunca sobrescreve).
    """
    if nota.erro:
        raise FrontmatterInvalido(nota.erro)

    texto = montar(nota)
    if nota.crlf:
        texto = texto.replace("\n", "\r\n")
    dados = texto.encode("utf-8")

    caminho = nota.caminho
    if caminho.exists():
        if criar:
            raise FileExistsError(str(caminho))
        if versao_esperada is not _SEM_CONFERIR:
            if calcular_versao(caminho.read_bytes()) != versao_esperada:
                raise Conflito(nota.rel)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    temporario = caminho.with_name(f".{caminho.name}.orq-tmp")
    temporario.write_bytes(dados)
    for tentativa in range(6):
        try:
            os.replace(temporario, caminho)
            break
        except PermissionError:
            # No Windows outro programa pode estar com o arquivo aberto por um instante.
            if tentativa == 5:
                temporario.unlink(missing_ok=True)
                raise
            time.sleep(0.08 * (tentativa + 1))

    nota.versao = calcular_versao(dados)
    nota.mtime = caminho.stat().st_mtime
    return nota


_PROIBIDOS = re.compile(r'[\\/:*?"<>|#^\[\]\r\n\t]')


def nome_de_arquivo(titulo: str) -> str:
    """Transforma um título em nome de arquivo legível (com acentos e espaços).

    Mantemos o nome parecido com o título porque é assim que o Obsidian mostra as
    notas; só removemos o que o Windows, o macOS ou os links do Obsidian não aceitam.
    """
    nome = _PROIBIDOS.sub(" ", titulo)
    nome = re.sub(r"\s+", " ", nome).strip(" .")
    return (nome[:80].rstrip(" .")) or "Sem título"


def caminho_livre(pasta: Path, titulo: str) -> Path:
    """Devolve um caminho .md que ainda não existe na pasta (acrescenta 2, 3...)."""
    base = nome_de_arquivo(titulo)
    caminho = pasta / f"{base}.md"
    n = 2
    while caminho.exists():
        caminho = pasta / f"{base} {n}.md"
        n += 1
    return caminho
