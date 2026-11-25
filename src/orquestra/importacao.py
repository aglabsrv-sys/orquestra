"""Cópia explícita de documentos para uma pasta do cofre, sem sobrescrever."""
from __future__ import annotations

import re
from pathlib import Path

from orquestra import apoios, armazenamento
from orquestra.caminhos import ignorar
from orquestra.modulos import NOTAS_DE_CONTRATO
from orquestra.painel import NaoEncontrado, Recusado

LIMITE_ARQUIVO = 20 * 1024 * 1024
EXT_DOCUMENTOS = {".pdf", ".txt", ".csv", ".tsv", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".zip"}
EXT_IMPORTAVEIS = EXT_DOCUMENTOS | {".md", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif", ".bmp", ".ico", ".mp4", ".webm", ".html", ".htm"}


def copiar(painel, destino: str, nome: str, dados: bytes, vinculo: str = "") -> dict:
    if (not nome or len(nome.encode("utf-8")) > 220 or re.search(r'[<>:"/\\|?*\x00-\x1f]', nome)
            or nome.startswith((".", "_")) or nome.endswith((".", " ")) or nome.casefold() in NOTAS_DE_CONTRATO
            or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", nome, re.I)):
        raise Recusado("Este nome de arquivo é reservado ou contém caracteres inválidos.")
    if Path(nome).suffix.lower() not in EXT_IMPORTAVEIS:
        raise Recusado("Use uma nota Markdown, imagem, vídeo, HTML, PDF, documento de escritório, texto ou ZIP.")
    if len(dados) > LIMITE_ARQUIVO:
        raise Recusado("Cada arquivo pode ter até 20 MB.")
    with painel._trava:
        pasta = painel.caminho_seguro(destino)
        if (destino and ignorar(destino + "/x.md") or any(p.startswith((".", "_")) or p.casefold() in ("maquina", "arquivo") for p in destino.split("/") if p)):
            raise Recusado("Escolha uma pasta de notas, fora das configurações e dos arquivos arquivados.")
        if vinculo:
            area = painel.indice.modulo_de(vinculo)
            if not area or area.id not in ("projetos", "estudos"):
                raise NaoEncontrado(vinculo)
            raiz = apoios.dentro(painel, area, vinculo)["diretorio"]
            if destino != raiz and not destino.startswith(raiz + "/"):
                raise Recusado("O destino não pertence à pasta aberta.")
        elif not pasta.is_dir():
            raise NaoEncontrado(destino)
        caminho = painel.caminho_seguro(pasta / nome)
        numero = 2
        while caminho.exists():
            caminho = painel.caminho_seguro(pasta / f"{Path(nome).stem} {numero}{Path(nome).suffix}")
            numero += 1
        armazenamento.gravar_bytes(caminho, dados, criar=True, validar=lambda: painel.caminho_seguro(caminho))
        painel.apos_escrita(caminho, "painel")
        return {"rel": caminho.relative_to(painel.vault).as_posix(), "nome": caminho.name, "renomeado": caminho.name != nome}
