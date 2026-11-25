"""Exclusão explícita, com restauração e limpeza por item."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from orquestra import armazenamento
from orquestra.caminhos import caminho_no_vault, eh_link, ignorar
from orquestra.modulos import ARQUIVO_DESLIGADO, ARQUIVO_MODULO, NOTAS_DE_CONTRATO
from orquestra.notas import Conflito


def _nota_permitida(rel: str) -> bool:
    caminho = Path(rel.replace("\\", "/"))
    partes = rel.replace("\\", "/").split("/")
    return (not any(p in ("", ".", "..") or ":" in p for p in partes)
            and not ignorar(rel) and caminho.suffix.lower() == ".md"
            and caminho.name.lower() not in NOTAS_DE_CONTRATO
            and not any(p.startswith("_") or p.lower() == "maquina" for p in partes))


def pode_excluir(painel, rel: str) -> bool:
    return _nota_permitida(rel) and painel.indice.zona_de(rel) not in ("maquina",)


def _pasta_permitida(rel: str) -> bool:
    partes = rel.split("/")
    return (bool(rel) and rel.casefold() != "diario" and "\\" not in rel and not ignorar(rel + "/x.md")
            and not any(not p or p.startswith((".", "_")) or ":" in p or p.casefold() == "maquina" for p in partes))


def pode_excluir_pasta(vault: Path, rel: str) -> tuple[bool, str]:
    if not _pasta_permitida(rel):
        return False, "Esta pasta é protegida."
    try:
        conferir_pasta(caminho_no_vault(vault, rel))
    except ValueError as erro:
        return False, str(erro)
    return True, ""


def versao_pasta(pasta: Path) -> str:
    """Inclui alterações em notas e subpastas, sem ler anexos inteiros ou seguir links."""
    resumo = hashlib.sha256()
    pendentes = [pasta]
    while pendentes:
        atual = pendentes.pop()
        link = eh_link(atual)
        info = atual.lstat()
        resumo.update(json.dumps((atual.relative_to(pasta).as_posix(), info.st_mode, info.st_dev, info.st_ino,
                                 info.st_size, info.st_mtime_ns, info.st_ctime_ns, link), ensure_ascii=False).encode("utf-8"))
        if not link and atual.is_dir():
            pendentes.extend(sorted(atual.iterdir(), key=lambda p: p.name))
    return resumo.hexdigest()


def conferir_pasta(pasta: Path) -> None:
    """Valida a árvore sem atravessar links ou mover configurações e instruções."""
    protegidos = NOTAS_DE_CONTRATO | {ARQUIVO_MODULO, ARQUIVO_DESLIGADO, "orquestra.yaml"}
    pilha = [pasta]
    while pilha:
        atual = pilha.pop()
        for filho in atual.iterdir():
            if eh_link(filho) or filho.name.startswith((".", "_")) or filho.name.casefold() in protegidos | {"maquina"}:
                raise ValueError("Esta pasta contém configurações, instruções ou links protegidos.")
            if filho.is_dir():
                pilha.append(filho)


def _pasta(vault: Path, identificador: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", identificador):
        raise ValueError("Item da lixeira inválido.")
    return caminho_no_vault(vault, f".trash/orquestra/{identificador}")


def _ler(vault: Path, identificador: str) -> tuple[Path, dict]:
    pasta = _pasta(vault, identificador)
    registro = caminho_no_vault(vault, pasta / "registro.json")
    if registro.stat().st_size > 16384:
        raise ValueError("Registro da lixeira inválido.")
    dados = json.loads(registro.read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or not isinstance(dados.get("rel"), str):
        raise ValueError("Destino de restauração inválido.")
    pasta_real = dados.get("tipo") == "pasta"
    if not (_pasta_permitida(dados["rel"]) if pasta_real else _nota_permitida(dados["rel"])):
        raise ValueError("Destino de restauração inválido.")
    caminho_no_vault(vault, dados["rel"])
    caminho_no_vault(vault, pasta / ("pasta" if pasta_real else "nota.md"))
    return pasta, dados


def listar(vault: Path) -> list[dict]:
    raiz = caminho_no_vault(vault, ".trash/orquestra")
    if not raiz.exists():
        return []
    resultado = []
    for pasta in raiz.iterdir():
        try:
            pasta, dados = _ler(vault, pasta.name)
            if dados.get("tipo") == "pasta":
                destino = caminho_no_vault(vault, pasta / "pasta")
                if destino.is_dir():
                    resultado.append({**dados, "id": pasta.name, "versao": versao_pasta(destino)})
                continue
            nota = caminho_no_vault(vault, pasta / "nota.md")
            if nota.is_file():
                resultado.append({**dados, "id": pasta.name, "versao": armazenamento.versao(nota.read_bytes())})
        except (OSError, ValueError, TypeError):
            continue
    return sorted(resultado, key=lambda d: str(d.get("excluido_em", "")), reverse=True)


def excluir(vault: Path, rel: str, versao: str, titulo: str) -> str:
    if not _nota_permitida(rel):
        raise ValueError("Este arquivo é protegido contra exclusão.")
    identificador = uuid4().hex
    pasta = _pasta(vault, identificador)
    origem = caminho_no_vault(vault, rel)
    destino = caminho_no_vault(vault, pasta / "nota.md")
    dados = {"rel": rel, "titulo": titulo, "excluido_em": dt.datetime.now().isoformat(timespec="seconds")}
    registro = caminho_no_vault(vault, pasta / "registro.json")
    armazenamento.gravar_bytes(registro, json.dumps(dados, ensure_ascii=False).encode("utf-8"), criar=True,
                              validar=lambda: caminho_no_vault(vault, registro))
    try:
        armazenamento.mover_seguro(origem, destino, esperado=versao,
                                  validar=lambda: (caminho_no_vault(vault, origem), caminho_no_vault(vault, destino)))
    except (OSError, ValueError, armazenamento.ConflitoDeEscrita):
        if not caminho_no_vault(vault, destino).exists():
            _limpar_registro(vault, pasta)
        raise
    return identificador


def excluir_pasta(vault: Path, rel: str, versao: str, titulo: str) -> str:
    if not _pasta_permitida(rel):
        raise ValueError("Esta pasta é protegida contra exclusão.")
    identificador = uuid4().hex
    pasta = _pasta(vault, identificador)
    origem = caminho_no_vault(vault, rel)
    destino = caminho_no_vault(vault, pasta / "pasta")
    registro = caminho_no_vault(vault, pasta / "registro.json")
    dados = {"rel": rel, "titulo": titulo, "tipo": "pasta", "excluido_em": dt.datetime.now().isoformat(timespec="seconds")}
    armazenamento.gravar_bytes(registro, json.dumps(dados, ensure_ascii=False).encode("utf-8"), criar=True,
                              validar=lambda: caminho_no_vault(vault, registro))
    try:
        mover_pasta(vault, origem, destino, versao)
    except (OSError, ValueError, Conflito):
        if not caminho_no_vault(vault, destino).exists():
            _limpar_registro(vault, pasta)
        raise
    return identificador


def mover_pasta(vault: Path, origem: Path, destino: Path, versao: str) -> None:
    conferir_pasta(caminho_no_vault(vault, origem))

    def validar():
        caminho_no_vault(vault, destino)
        if versao_pasta(caminho_no_vault(vault, origem)) != versao:
            raise Conflito("A pasta mudou no disco. Reabra os ajustes antes de continuar.")

    armazenamento.mover_diretorio(origem, destino, validar=validar)


def restaurar(vault: Path, identificador: str, versao: str) -> str:
    pasta, dados = _ler(vault, identificador)
    pasta_real = dados.get("tipo") == "pasta"
    origem = caminho_no_vault(vault, pasta / ("pasta" if pasta_real else "nota.md"))
    destino = caminho_no_vault(vault, dados["rel"])
    if destino.exists():
        raise Conflito("Já existe um arquivo ou pasta no caminho original. Mova-o antes de restaurar.")
    if pasta_real:
        mover_pasta(vault, origem, destino, versao)
    else:
        armazenamento.mover_seguro(origem, destino, esperado=versao,
                                   validar=lambda: (caminho_no_vault(vault, origem), caminho_no_vault(vault, destino)))
    _limpar_registro(vault, pasta)
    return dados["rel"]


def _limpar_registro(vault: Path, pasta: Path) -> None:
    caminho_no_vault(vault, pasta / "registro.json").unlink(missing_ok=True)
    try:
        caminho_no_vault(vault, pasta).rmdir()  # nunca apaga outros arquivos
    except OSError:
        pass


def apagar(vault: Path, identificador: str, versao: str) -> None:
    pasta, dados = _ler(vault, identificador)
    if dados.get("tipo") == "pasta":
        destino = caminho_no_vault(vault, pasta / "pasta")
        with armazenamento.trava(destino):
            conferir_pasta(caminho_no_vault(vault, destino))
            if versao_pasta(destino) != versao:
                raise Conflito("A pasta na lixeira mudou. Atualize a página antes de excluir.")
            shutil.rmtree(caminho_no_vault(vault, destino))
            _limpar_registro(vault, pasta)
        return
    nota = caminho_no_vault(vault, pasta / "nota.md")
    with armazenamento.trava(nota):
        caminho_no_vault(vault, nota)
        if armazenamento.versao(nota.read_bytes()) != versao:
            raise Conflito("O item da lixeira mudou. Atualize a página antes de excluir.")
        caminho_no_vault(vault, nota).unlink()
        _limpar_registro(vault, pasta)
