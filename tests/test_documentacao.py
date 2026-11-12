"""Guias publicados precisam apontar para arquivos existentes e ferramentas reais."""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from orquestra.mcp_servidor import FERRAMENTAS


RAIZ = Path(__file__).parents[1]


def test_links_locais_dos_guias_e_readme_existem():
    arquivos = [RAIZ / nome for nome in ("README.md", "CONTRIBUTING.md", "SECURITY.md")]
    arquivos.extend((RAIZ / "docs").rglob("*.md"))
    ausentes = []
    for arquivo in arquivos:
        for bloco in MarkdownIt().parse(arquivo.read_text(encoding="utf-8")):
            for token in bloco.children or []:
                link = token.attrGet("href") if token.type == "link_open" else token.attrGet("src") if token.type == "image" else None
                if not link:
                    continue
                url = urlsplit(link)
                if url.scheme or url.netloc or not url.path:
                    continue
                relativo = unquote(url.path)
                destino = RAIZ / relativo.lstrip("/") if relativo.startswith("/") else arquivo.parent / relativo
                if not destino.exists():
                    ausentes.append(f"{arquivo.relative_to(RAIZ)}: {link}")
    assert not ausentes, "Links locais sem destino:\n" + "\n".join(ausentes)


def test_guia_mcp_documenta_todas_as_ferramentas_publicas():
    guia = (RAIZ / "docs" / "mcp.md").read_text(encoding="utf-8")
    documentadas = set(re.findall(r"^\|\s*`([a-z_]+)`\s*\|", guia, re.MULTILINE))
    assert documentadas == set(FERRAMENTAS)


def test_configuracao_json_do_cliente_mcp_e_copiavel():
    guia = (RAIZ / "docs" / "mcp.md").read_text(encoding="utf-8")
    exemplos = re.findall(r"```json\s*\n(.*?)\n```", guia, re.DOTALL)
    assert exemplos, "Mantenha um exemplo completo para clientes MCP locais."
    for exemplo in exemplos:
        servidor = json.loads(exemplo)["mcpServers"]["orquestra"]
        assert servidor["command"]
        argumentos = servidor["args"]
        assert "--directory" in argumentos and "--vault" in argumentos
        assert argumentos[argumentos.index("mcp") - 1] == "orquestra"
