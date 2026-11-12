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

from orquestra.aparencia import Aparencia
from orquestra.aparencia import ler as ler_aparencia
from orquestra.armazenamento import SEM_CONFERIR, gravar_bytes

PORTA_PADRAO = 8420


class ConfigInvalida(ValueError):
    """Configuração ilegível ou com estrutura diferente da esperada."""


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
    try:
        bruto = caminho.read_bytes()
    except FileNotFoundError:
        bruto = None
    try:
        texto = bruto.decode("utf-8-sig") if bruto is not None else ""
        from orquestra.notas import simples, validar_aliases

        validar_aliases(texto)
        dados = _yaml().load(texto)
        if dados is not None:
            simples(dados)
    except (UnicodeError, ValueError, TypeError) as erro:
        raise ConfigInvalida(f"Não consegui ler {caminho.name}: UTF-8 ou YAML inválido.") from erro
    except Exception as erro:
        from ruamel.yaml.error import YAMLError

        if isinstance(erro, YAMLError):
            raise ConfigInvalida(f"Não consegui ler {caminho.name}: YAML inválido.") from erro
        raise
    if dados is not None and not isinstance(dados, CommentedMap):
        raise ConfigInvalida(f"{caminho.name} precisa conter campos no formato chave: valor.")
    mapa = dados if isinstance(dados, CommentedMap) else CommentedMap()
    mapa._orq_original = bruto
    mapa._orq_caminho = str(caminho.resolve())
    mapa._orq_serializado = _serializar_yaml(mapa)
    mapa._orq_prefixo = texto if dados is None else ""
    return mapa


def _serializar_yaml(dados: Any) -> str:
    saida = io.StringIO()
    _yaml().dump(dados, saida)
    return saida.getvalue()


def gravar_yaml(caminho: Path, dados: Any, *, esperado: object = SEM_CONFERIR) -> None:
    """Atualiza somente a versão lida por ler_yaml; mapas novos exigem destino novo."""
    if not isinstance(dados, dict):
        raise ConfigInvalida("Uma configuração precisa ser um mapa de campos.")
    mesma_origem = getattr(dados, "_orq_caminho", None) == str(caminho.resolve())
    original = getattr(dados, "_orq_original", None) if mesma_origem else None
    if esperado is SEM_CONFERIR:
        esperado = original
    serializado = _serializar_yaml(dados)
    if mesma_origem and original is not None and serializado == dados._orq_serializado:
        bruto = original
    else:
        prefixo = getattr(dados, "_orq_prefixo", "") if mesma_origem else ""
        texto = (prefixo.rstrip("\r\n") + "\n" if prefixo.strip() else "") + serializado
        if original is not None and b"\r\n" in original:
            texto = texto.replace("\r\n", "\n").replace("\n", "\r\n")
        bruto = texto.encode("utf-8")
        if original is not None and original.startswith(b"\xef\xbb\xbf"):
            bruto = b"\xef\xbb\xbf" + bruto
    gravar_bytes(caminho, bruto, esperado=esperado)
    if isinstance(dados, CommentedMap):
        dados._orq_original = bruto
        dados._orq_caminho = str(caminho.resolve())
        dados._orq_serializado = serializado


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
    dock: list[str] = field(default_factory=list)  # áreas fixadas no dock; vazio = as primeiras
    hosts_permitidos: list[str] = field(default_factory=list)
    backup: ConfigBackup = field(default_factory=ConfigBackup)
    aparencia: Aparencia = field(default_factory=Aparencia)


def ler_config_painel(vault: Path) -> ConfigPainel:
    arquivo = vault / "orquestra.yaml"
    bruto = ler_yaml(arquivo)
    cfg = ConfigPainel()
    # Pasta que ainda não foi preparada (aberta direto com --vault): não fazemos commit
    # automático num repositório git que pode ser de outra coisa.
    cfg.backup.auto_commit = arquivo.is_file()
    for chave in ("nome", "tema", "captura"):
        if chave in bruto and not isinstance(bruto[chave], str):
            raise ConfigInvalida(f"orquestra.yaml: '{chave}' precisa ser texto.")
    cfg.nome = str(bruto.get("nome") or cfg.nome)
    cfg.tema = str(bruto.get("tema") or cfg.tema)
    cfg.captura = str(bruto.get("captura") or cfg.captura)
    porta = bruto.get("porta", cfg.porta)
    if isinstance(porta, bool) or not isinstance(porta, int) or not 1 <= porta <= 65535:
        raise ConfigInvalida("orquestra.yaml: 'porta' precisa ser um inteiro entre 1 e 65535.")
    cfg.porta = porta
    fixas = bruto.get("dock", [])
    if not isinstance(fixas, list) or any(not isinstance(f, str) for f in fixas):
        raise ConfigInvalida("orquestra.yaml: 'dock' precisa ser uma lista de nomes.")
    cfg.dock = list(fixas)
    hosts = bruto.get("hosts_permitidos", [])
    if not isinstance(hosts, list) or any(not isinstance(h, str) for h in hosts):
        raise ConfigInvalida("orquestra.yaml: 'hosts_permitidos' precisa ser uma lista de nomes.")
    cfg.hosts_permitidos = [h.lower() for h in hosts]
    if bruto.get("aparencia") is not None and not isinstance(bruto["aparencia"], dict):
        raise ConfigInvalida("orquestra.yaml: 'aparencia' precisa ser um mapa de opções.")
    cfg.aparencia = ler_aparencia(bruto.get("aparencia"))
    b = bruto.get("backup", {})
    if not isinstance(b, dict):
        raise ConfigInvalida("orquestra.yaml: 'backup' precisa ser um mapa de opções.")
    for chave in ("auto_commit", "push"):
        if chave in b and not isinstance(b[chave], bool):
            raise ConfigInvalida(f"orquestra.yaml: 'backup.{chave}' precisa ser true ou false.")
    cfg.backup.auto_commit = b.get("auto_commit", cfg.backup.auto_commit)
    cfg.backup.push = b.get("push", cfg.backup.push)
    horario = b.get("push_as", cfg.backup.push_as)
    import re

    if not isinstance(horario, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", horario):
        raise ConfigInvalida("orquestra.yaml: 'backup.push_as' precisa usar HH:MM (00:00 a 23:59).")
    cfg.backup.push_as = horario
    intervalo = b.get("intervalo_min", cfg.backup.intervalo_min)
    if isinstance(intervalo, bool) or not isinstance(intervalo, int) or intervalo < 1:
        raise ConfigInvalida("orquestra.yaml: 'backup.intervalo_min' precisa ser um inteiro positivo.")
    cfg.backup.intervalo_min = intervalo
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
