"""Temas e capas.

Um tema é uma pasta em `_orquestra/temas/<nome>/` com um `tema.yaml` que define:

- `cores`: as cores da interface;
- `paletas`: conjuntos de cores usados pelas capas em pixel art;
- `capas`: qual cena e qual paleta cada módulo usa.

Tudo isso fica no vault de propósito: você (ou um agente com acesso à pasta)
troca cores e capas editando um arquivo, e atualizar o app nunca desfaz isso.

Uma capa pode ser uma cena desenhada pelo navegador (pixel art procedural, ver
static/js/cenas.js) ou um arquivo de imagem/vídeo do vault.
"""

from __future__ import annotations

import re
import zlib
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import quote

from orquestra.config import ler_yaml
from orquestra.notas import simples

PASTA_TEMAS = "_orquestra/temas"
CENAS = ["janela", "cidade", "montanhas", "mar", "floresta", "espaco"]
EXT_VIDEO = {".mp4", ".webm"}

CORES_PADRAO = {
    "fundo": "#130c09",
    "superficie": "#1e1410",
    "superficie_alta": "#2a1c16",
    "borda": "#3b2a22",
    "texto": "#f6ebe3",
    "texto_suave": "#b59f92",
    "destaque": "#f4b183",
    "sobre_destaque": "#2a1608",
    "alerta": "#ff7a59",
    "ok": "#9bd49b",
}


def _tema_embutido() -> dict[str, Any]:
    """Tema Brasa que vem junto com o app; usado quando o vault não tem temas."""
    caminho = resources.files("orquestra") / "modelo_vault" / PASTA_TEMAS / "brasa" / "tema.yaml"
    with resources.as_file(caminho) as arquivo:
        return _normalizar("brasa", simples(dict(ler_yaml(Path(arquivo)))))


_COR_HEX = re.compile(r"#[0-9a-fA-F]{3,8}")


def _normalizar(tema_id: str, bruto: dict[str, Any]) -> dict[str, Any]:
    cores = dict(CORES_PADRAO)
    # Só aceitamos cores em hexadecimal: elas entram direto no CSS da página.
    cores.update(
        {k: str(v) for k, v in (bruto.get("cores") or {}).items() if k in CORES_PADRAO and _COR_HEX.fullmatch(str(v))}
    )
    return {
        "id": tema_id,
        "nome": str(bruto.get("nome") or tema_id.capitalize()),
        "descricao": str(bruto.get("descricao") or ""),
        "cores": cores,
        "paletas": {k: v for k, v in (bruto.get("paletas") or {}).items() if isinstance(v, dict)},
        "capas": dict(bruto.get("capas") or {}),
    }


def listar(vault: Path) -> list[dict[str, Any]]:
    pasta = vault / PASTA_TEMAS
    temas = []
    if pasta.is_dir():
        for sub in sorted(pasta.iterdir()):
            if (sub / "tema.yaml").is_file():
                try:
                    temas.append(_normalizar(sub.name, simples(dict(ler_yaml(sub / "tema.yaml")))))
                except Exception:
                    continue  # tema com YAML quebrado não derruba o painel
    return temas or [_tema_embutido()]


def carregar(vault: Path, tema_id: str) -> dict[str, Any]:
    temas = listar(vault)
    for tema in temas:
        if tema["id"] == tema_id:
            return tema
    return temas[0]


def resolver_capa(tema: dict[str, Any], alvo: str, propria: Any = None) -> dict[str, Any]:
    """Decide a capa de um módulo.

    Prioridade: `capa` do próprio módulo (escolha do usuário) > `capas` do tema >
    uma cena escolhida de forma estável a partir do nome do módulo.
    """
    spec = propria if propria else tema["capas"].get(alvo)
    semente = zlib.crc32(alvo.encode("utf-8"))

    if isinstance(spec, str) and spec.strip():
        caminho = spec.strip()
        url = caminho if caminho.startswith(("http://", "https://")) else "/arquivo/" + quote(caminho)
        tipo = "video" if Path(caminho).suffix.lower() in EXT_VIDEO else "imagem"
        return {"tipo": tipo, "url": url}

    cena = paleta = None
    if isinstance(spec, dict):
        cena, paleta = spec.get("cena"), spec.get("paleta")
    if cena not in CENAS:
        cena = CENAS[semente % len(CENAS)]

    paletas = tema["paletas"]
    if isinstance(paleta, dict):
        cores = paleta
    elif paleta in paletas:
        cores = paletas[paleta]
    elif paletas:
        cores = list(paletas.values())[semente % len(paletas)]
    else:
        cores = {}
    return {"tipo": "cena", "cena": cena, "paleta": cores, "semente": semente % 100000}
