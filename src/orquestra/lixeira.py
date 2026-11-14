"""Exclusão explícita de notas, com restauração e limpeza por item."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from uuid import uuid4

from orquestra import armazenamento
from orquestra.caminhos import caminho_no_vault, ignorar
from orquestra.modulos import NOTAS_DE_CONTRATO
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
    if not isinstance(dados, dict) or not isinstance(dados.get("rel"), str) or not _nota_permitida(dados["rel"]):
        raise ValueError("Destino de restauração inválido.")
    caminho_no_vault(vault, dados["rel"])
    caminho_no_vault(vault, pasta / "nota.md")
    return pasta, dados


def listar(vault: Path) -> list[dict]:
    raiz = caminho_no_vault(vault, ".trash/orquestra")
    if not raiz.exists():
        return []
    resultado = []
    for pasta in raiz.iterdir():
        try:
            pasta, dados = _ler(vault, pasta.name)
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


def restaurar(vault: Path, identificador: str, versao: str) -> str:
    pasta, dados = _ler(vault, identificador)
    origem = caminho_no_vault(vault, pasta / "nota.md")
    destino = caminho_no_vault(vault, dados["rel"])
    if destino.exists():
        raise Conflito("Já existe uma nota no caminho original. Mova-a antes de restaurar; nada foi substituído.")
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
    pasta, _ = _ler(vault, identificador)
    nota = caminho_no_vault(vault, pasta / "nota.md")
    with armazenamento.trava(nota):
        caminho_no_vault(vault, nota)
        if armazenamento.versao(nota.read_bytes()) != versao:
            raise Conflito("O item da lixeira mudou. Atualize a página antes de excluir.")
        caminho_no_vault(vault, nota).unlink()
        _limpar_registro(vault, pasta)
