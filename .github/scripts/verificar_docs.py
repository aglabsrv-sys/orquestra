"""Confere links e imagens locais dos guias, sem rede ou dependências extras."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


LINKS = re.compile(r"!?\[[^\]\n]*\]\((?:<([^>\n]+)>|([^\s)]+))(?:\s+['\"][^\n]*?['\"])?\)")


def verificar(raiz: Path) -> tuple[int, list[str]]:
    documentos = sorted([*raiz.glob("*.md"), *(raiz / "docs").rglob("*.md")])
    erros = []
    for documento in documentos:
        relativo = documento.relative_to(raiz).as_posix()
        try:
            texto = documento.read_text(encoding="utf-8")
        except UnicodeError:
            erros.append(f"{relativo}: não está em UTF-8")
            continue
        for link in LINKS.finditer(texto):
            destino = urlsplit(link.group(1) or link.group(2))
            if destino.scheme or destino.netloc or not destino.path:
                continue
            caminho = unquote(destino.path)
            alvo = (raiz / caminho.lstrip("/") if caminho.startswith("/") else documento.parent / caminho).resolve()
            linha = texto.count("\n", 0, link.start()) + 1
            if not alvo.is_relative_to(raiz) or not alvo.exists():
                erros.append(f"{relativo}:{linha}: destino local ausente ou fora do repositório: {caminho}")
    return len(documentos), erros


if __name__ == "__main__":
    quantidade, erros = verificar(Path(__file__).resolve().parents[2])
    if erros:
        print("\n".join(erros))
        raise SystemExit(1)
    print(f"Links e imagens locais: OK ({quantidade} documentos).")
