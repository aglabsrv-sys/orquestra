"""Referências locais compartilhadas pelo leitor, grafo e diagnóstico do cofre.

Somente lê o índice. Nenhum link é reescrito e nenhuma URL externa é consultada.
"""
from __future__ import annotations

import posixpath
import re
import unicodedata
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.rules_inline import image, link

from orquestra.caminhos import CaminhoInseguro, caminho_no_vault, ignorar

if TYPE_CHECKING:
    from orquestra.indice import Indice


@dataclass
class _Lote:
    indice: object
    caminhos: dict[str, Path | None]
    arquivos: dict[str, bool]


_lote: ContextVar[_Lote | None] = ContextVar("orquestra_vinculos_lote", default=None)


@contextmanager
def resolver_em_lote(indice: Indice):
    """Reutiliza validações só nesta operação; nunca entre requisições.

    A verificação trabalha sobre o espelho em memória. Servir ou escrever um
    arquivo continua exigindo sua própria validação imediatamente antes do I/O.
    ContextVar mantém os lotes de requisições concorrentes independentes.
    """
    atual = _lote.get()
    if atual is not None and atual.indice is indice:
        yield
        return
    token = _lote.set(_Lote(indice, {}, {}))
    try:
        yield
    finally:
        _lote.reset(token)


def _caminho_validado(indice: Indice, rel: str) -> Path:
    lote = _lote.get()
    cache = lote.caminhos if lote is not None and lote.indice is indice else None
    if cache is not None and rel in cache:
        caminho = cache[rel]
        if caminho is None:
            raise CaminhoInseguro("O destino não está disponível dentro do cofre.")
        return caminho
    try:
        caminho = caminho_no_vault(indice.vault, rel)
    except (CaminhoInseguro, OSError):
        if cache is not None:
            cache[rel] = None
        raise
    if cache is not None:
        cache[rel] = caminho
    return caminho


def _arquivo_existente(indice: Indice, rel: str) -> bool:
    lote = _lote.get()
    cache = lote.arquivos if lote is not None and lote.indice is indice else None
    if cache is not None and rel in cache:
        return cache[rel]
    existe = _caminho_validado(indice, rel).is_file()
    if cache is not None:
        cache[rel] = existe
    return existe


@dataclass(frozen=True)
class Referencia:
    alvo: str
    texto: str = ""
    linha: int = 1
    tipo: str = "wiki"
    embutido: bool = False


@dataclass(frozen=True)
class Resolucao:
    estado: str
    rel: str = ""
    fragmento: str = ""
    candidatos: tuple[str, ...] = ()


def normalizar_ancora(texto: str) -> str:
    texto = unicodedata.normalize("NFC", unquote(texto)).strip().casefold()
    if texto.startswith("^"):
        return "bloco-" + texto[1:]
    texto = re.sub(r"[^\w\s-]", "", texto, flags=re.UNICODE)
    return re.sub(r"[\s_]+", "-", texto).strip("-")


def _wiki(state, silent):
    inicio = state.pos
    embutido = state.src.startswith("![[", inicio)
    prefixo = 3 if embutido else 2
    if not embutido and not state.src.startswith("[[", inicio):
        return False
    fim = state.src.find("]]", inicio + prefixo)
    if fim < 0:
        return False
    conteudo = state.src[inicio + prefixo:fim]
    alvo, _, rotulo = conteudo.partition("|")
    alvo = alvo.strip()
    if not alvo or "[[" in conteudo:
        return False
    if not silent:
        token = state.push("wikilink", "", 0)
        token.content = rotulo.strip() or alvo
        token.meta = {"alvo": alvo, "embutido": embutido, "inicio": inicio, "multilinha": "\n" in conteudo,
                      "fonte": state.src[inicio:fim + 2]}
    state.pos = fim + 2
    return True


def _com_posicao(regra):
    def executar(state, silent):
        inicio, quantidade = state.pos, len(state.tokens)
        resultado = regra(state, silent)
        if resultado and not silent:
            for token in state.tokens[quantidade:]:
                if token.type in {"link_open", "image"}:
                    token.meta["inicio"] = inicio
        return resultado
    return executar


def markdown_local() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable(["table", "strikethrough"])
    md.inline.ruler.before("link", "wikilink", _wiki)
    md.inline.ruler.at("link", _com_posicao(link))
    md.inline.ruler.at("image", _com_posicao(image))
    return md


_md = markdown_local()


def externo(alvo: str) -> bool:
    # Não analisamos hosts: uma URL inválida em uma nota não pode derrubar o índice.
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", alvo) or alvo.startswith("//"))


def extrair_referencias(texto: str) -> list[Referencia]:
    """Usa o parser Markdown: exemplos em código e escapes ficam de fora."""
    resultado = []
    for bloco in _md.parse(texto):
        if bloco.type != "inline":
            continue
        for token in bloco.children or []:
            if token.type == "wikilink":
                alvo = token.meta["alvo"]
                tipo, embutido = "wiki", token.meta["embutido"]
            elif token.type in {"link_open", "image"}:
                alvo = token.attrGet("href" if token.type == "link_open" else "src") or ""
                tipo, embutido = "markdown", token.type == "image"
            else:
                continue
            if not alvo or externo(alvo):
                continue
            linha = (bloco.map or [0])[0] + bloco.content[:token.meta.get("inicio", 0)].count("\n") + 1
            resultado.append(Referencia(alvo, token.content or alvo, linha, tipo, embutido))
    return resultado


def ancoras(texto: str) -> set[str]:
    resultado = set()
    pilha: list[tuple[int, str]] = []
    tokens = _md.parse(texto)
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and i + 1 < len(tokens):
            inline = tokens[i + 1]
            titulo = "".join(t.content for t in inline.children or [] if t.type not in {"html_inline", "link_open", "link_close"})
            normal = normalizar_ancora(titulo)
            resultado.add(normal)
            nivel = int(token.tag[1:])
            while pilha and pilha[-1][0] >= nivel:
                pilha.pop()
            pilha.append((nivel, normal))
            resultado.add("#".join(p[1] for p in pilha))
        if token.type == "inline":
            # IDs dentro de código inline não são destinos de bloco.
            visivel = "".join(t.content for t in token.children or [] if t.type == "text")
            for bloco in re.findall(r"(?:^|\s)\^([A-Za-z0-9-]+)(?=\s*$)", visivel, re.MULTILINE):
                resultado.add("bloco-" + bloco.casefold())
    return resultado


def _inventario(indice: Indice):
    versao = getattr(indice, "revisao", 0)
    cache = getattr(indice, "_inventario_vinculos", None)
    if cache and cache[0] == versao:
        return cache[1:]
    arquivos = set(getattr(indice, "arquivos", ())) | set(indice.notas)
    por_caminho: dict[str, set[str]] = {}
    por_nome: dict[str, set[str]] = {}
    for rel in arquivos:
        por_caminho.setdefault(rel.casefold(), set()).add(rel)
        nome = posixpath.basename(rel)
        chaves = {nome.casefold()}
        if rel.lower().endswith(".md"):
            chaves.add(nome[:-3].casefold())
        for chave in chaves:
            por_nome.setdefault(chave, set()).add(rel)
    for rel, nota in list(indice.notas.items()):
        aliases = nota.meta.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        if isinstance(aliases, list):
            for alias in aliases:
                por_nome.setdefault(str(alias).strip().casefold(), set()).add(rel)
    indice._inventario_vinculos = (versao, por_caminho, por_nome)
    return por_caminho, por_nome


def resolver_referencia(indice: Indice, referencia: Referencia | str, origem: str = "", *, tipo: str = "wiki") -> Resolucao:
    if isinstance(referencia, str):
        referencia = Referencia(referencia, tipo=tipo)
    bruto = referencia.alvo.strip()
    if externo(bruto):
        return Resolucao("externo")
    alvo, separador, fragmento = bruto.partition("#")
    # Separar o fragmento antes de decodificar preserva '%23' em nomes de arquivo.
    alvo = unquote(alvo.split("?", 1)[0]).replace("\\", "/").strip()
    if any(ord(c) < 32 for c in alvo) or ":" in alvo:
        return Resolucao("bloqueado")
    caminhos, nomes = _inventario(indice)

    def seguro(rel):
        try:
            return not ignorar(rel) and _arquivo_existente(indice, rel)
        except (CaminhoInseguro, OSError):
            return False

    if not alvo:
        candidatos = {origem} if origem in indice.notas else set()
    else:
        relativo = posixpath.normpath(posixpath.join(posixpath.dirname(origem), alvo))
        raiz = posixpath.normpath(alvo.lstrip("/"))
        if relativo == ".." or relativo.startswith("../") or (alvo.startswith("/") and raiz.startswith("../")):
            return Resolucao("bloqueado")
        explicito_relativo = alvo.startswith(("./", "../"))
        if referencia.tipo == "markdown" or explicito_relativo:
            opcoes = [relativo] if not alvo.startswith("/") else [raiz]
        else:
            opcoes = list(dict.fromkeys([relativo, raiz]))
        candidatos = set()
        for opcao in opcoes:
            if ignorar(opcao):
                return Resolucao("bloqueado")
            try:
                _caminho_validado(indice, opcao)
            except (CaminhoInseguro, OSError):
                return Resolucao("bloqueado")
            variantes = [opcao] + ([] if posixpath.splitext(opcao)[1] else [opcao + ".md"])
            for variante in variantes:
                try:
                    _caminho_validado(indice, variante)
                except (CaminhoInseguro, OSError):
                    return Resolucao("bloqueado")
                candidatos = caminhos.get(variante.casefold(), set())
                if candidatos:
                    break
            if candidatos:
                break
        if not candidatos and referencia.tipo == "wiki" and not explicito_relativo and not alvo.startswith("/"):
            if "/" not in alvo:
                candidatos = nomes.get(alvo.casefold(), set())
            else:
                variantes = [raiz.casefold()] + ([] if posixpath.splitext(raiz)[1] else [(raiz + ".md").casefold()])
                candidatos = {rel for chave, valores in caminhos.items() if any(chave.endswith("/" + v) for v in variantes) for rel in valores}
    candidatos = {r for r in candidatos if seguro(r)}
    if len(candidatos) > 1:
        return Resolucao("ambiguo", candidatos=tuple(sorted(candidatos)))
    if not candidatos:
        # Uma referência a uma nota futura é uma prática normal de escrita.
        extensao = posixpath.splitext(alvo)[1].lower()
        return Resolucao("futuro" if extensao in {"", ".md"} else "ausente")
    rel = next(iter(candidatos))
    if separador and fragmento and rel in indice.notas:
        normal = "#".join(normalizar_ancora(p) for p in fragmento.split("#"))
        nota = indice.notas.get(rel)
        if nota is None:
            return Resolucao("futuro")
        cache = getattr(indice, "_ancoras_vinculos", {})
        existente = cache.get(rel)
        if not existente or existente[0] != nota.versao:
            existente = (nota.versao, ancoras(nota.corpo))
            cache[rel] = existente
            indice._ancoras_vinculos = cache
        if normal not in existente[1]:
            return Resolucao("ancora_ausente", rel, normal)
        return Resolucao("valido", rel, normal.split("#")[-1])
    return Resolucao("valido", rel)


def referencias_da_nota(indice: Indice, rel: str) -> list[Referencia]:
    nota = indice.notas.get(rel)
    if nota is None:
        return []
    cache = getattr(indice, "_referencias_vinculos", {})
    existente = cache.get(rel)
    if not existente or existente[0] != nota.versao:
        existente = (nota.versao, extrair_referencias(nota.corpo))
        cache[rel] = existente
        indice._referencias_vinculos = cache
    return existente[1]


def verificar_links(indice: Indice, pasta: str = "", limite: int = 1000, *, filtro: str = "todos") -> dict:
    """Relatório factual; referências futuras ficam separadas das revisões."""
    with resolver_em_lote(indice):
        return _verificar_links(indice, pasta, limite, filtro=filtro)


def _verificar_links(indice: Indice, pasta: str, limite: int, *, filtro: str) -> dict:
    pasta = pasta.strip("/")
    limite = max(1, min(5000, limite))
    if filtro not in {"todos", "revisao", "futuro"}:
        filtro = "todos"
    if pasta:
        caminho_no_vault(indice.vault, pasta)
        if ignorar(pasta):
            raise CaminhoInseguro("Essa pasta não participa da verificação de links.")
    resumo = Counter({c: 0 for c in ("valido", "futuro", "ausente", "ambiguo", "ancora_ausente", "bloqueado")})
    revisoes, futuras = [], []
    total, notas = 0, 0
    for rel in sorted(indice.notas):
        if pasta and rel != pasta and not rel.startswith(pasta + "/"):
            continue
        notas += 1
        for ref in referencias_da_nota(indice, rel):
            resolucao = resolver_referencia(indice, ref, rel)
            if resolucao.estado == "externo":
                continue
            resumo[resolucao.estado] += 1
            total += 1
            if resolucao.estado != "valido":
                grupo = futuras if resolucao.estado == "futuro" else revisoes
                if len(grupo) < limite:
                    grupo.append({"origem": rel, **asdict(ref), **asdict(resolucao)})
    resumo["revisao"] = sum(resumo[c] for c in ("ausente", "ambiguo", "ancora_ausente", "bloqueado"))
    grupo = revisoes if filtro == "revisao" else futuras if filtro == "futuro" else revisoes + futuras
    ocorrencias = grupo[:limite]
    quantidade = resumo[filtro] if filtro != "todos" else total - resumo["valido"]
    return {"pasta": pasta, "filtro": filtro, "notas": notas, "total": total, "resumo": dict(resumo), "ocorrencias": ocorrencias, "limitado": len(ocorrencias) < quantidade}
