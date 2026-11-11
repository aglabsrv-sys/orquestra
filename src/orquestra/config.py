"""Configuração: onde fica o vault, opções do painel e segredos.

Há dois lugares de configuração, de propósito separados:

- `~/.orquestra/` (fora do vault): caminho do vault e o arquivo `.env` com chaves
  de API. Segredos nunca ficam dentro do vault, porque o vault vai para backup.
- `orquestra.yaml` (dentro do vault): nome do painel, tema, porta, backup. Fica no
  vault para que você ou um agente possam ajustar só editando o arquivo.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

PORTA_PADRAO = 8420


def pasta_app() -> Path:
    return Path(os.environ.get("ORQUESTRA_HOME") or (Path.home() / ".orquestra"))


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.allow_unicode = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def ler_yaml(caminho: Path) -> CommentedMap:
    """Lê um YAML preservando comentários. Arquivo ausente ou vazio vira mapa vazio."""
    if not caminho.is_file():
        return CommentedMap()
    dados = _yaml().load(caminho.read_text(encoding="utf-8-sig"))
    return dados if isinstance(dados, CommentedMap) else CommentedMap()


def gravar_yaml(caminho: Path, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    saida = io.StringIO()
    _yaml().dump(dados, saida)
    temporario = caminho.with_name(f".{caminho.name}.orq-tmp")
    temporario.write_text(saida.getvalue(), encoding="utf-8")
    os.replace(temporario, caminho)


def definir_chave(caminho: Path, chave: str, valor: Any) -> None:
    """Altera uma única chave de um YAML sem mexer no resto do arquivo."""
    dados = ler_yaml(caminho)
    dados[chave] = valor
    gravar_yaml(caminho, dados)


# ---------------------------------------------------------------- vault


def localizar_vault(explicito: str | None = None) -> Path | None:
    """Ordem: argumento --vault, variável ORQUESTRA_VAULT, ~/.orquestra/config.yaml."""
    candidato = explicito or os.environ.get("ORQUESTRA_VAULT")
    if not candidato:
        candidato = ler_yaml(pasta_app() / "config.yaml").get("vault")
    if not candidato:
        return None
    return Path(str(candidato)).expanduser().resolve()


def lembrar_vault(vault: Path) -> None:
    definir_chave(pasta_app() / "config.yaml", "vault", str(vault))


# ---------------------------------------------------------------- painel


@dataclass
class ConfigBackup:
    auto_commit: bool = True
    intervalo_min: int = 30
    push: bool = False
    push_as: str = "03:00"


@dataclass
class ConfigPainel:
    nome: str = "Orquestra"
    tema: str = "brasa"
    porta: int = PORTA_PADRAO
    captura: str = "entrada"  # módulo que recebe a captura rápida
    hosts_permitidos: list[str] = field(default_factory=list)
    backup: ConfigBackup = field(default_factory=ConfigBackup)


def ler_config_painel(vault: Path) -> ConfigPainel:
    bruto = ler_yaml(vault / "orquestra.yaml")
    cfg = ConfigPainel()
    cfg.nome = str(bruto.get("nome") or cfg.nome)
    cfg.tema = str(bruto.get("tema") or cfg.tema)
    cfg.captura = str(bruto.get("captura") or cfg.captura)
    try:
        cfg.porta = int(bruto.get("porta") or cfg.porta)
    except (TypeError, ValueError):
        pass
    hosts = bruto.get("hosts_permitidos") or []
    if isinstance(hosts, list):
        cfg.hosts_permitidos = [str(h).lower() for h in hosts]
    b = bruto.get("backup") or {}
    if isinstance(b, dict):
        cfg.backup.auto_commit = bool(b.get("auto_commit", cfg.backup.auto_commit))
        cfg.backup.push = bool(b.get("push", cfg.backup.push))
        cfg.backup.push_as = str(b.get("push_as") or cfg.backup.push_as)
        try:
            cfg.backup.intervalo_min = max(1, int(b.get("intervalo_min") or cfg.backup.intervalo_min))
        except (TypeError, ValueError):
            pass
    return cfg


# ---------------------------------------------------------------- segredos


def carregar_env() -> dict[str, str]:
    """Lê ~/.orquestra/.env (linhas CHAVE=valor). Usado só pelos coletores."""
    caminho = pasta_app() / ".env"
    segredos: dict[str, str] = {}
    if not caminho.is_file():
        return segredos
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.strip().strip('"').strip("'")
        if chave.strip() and valor:
            segredos[chave.strip()] = valor
    return segredos
