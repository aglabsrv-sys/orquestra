"""Preparação comum dos testes: cada teste ganha um vault novo, copiado do modelo."""

from __future__ import annotations

from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from orquestra import backup, cli
from orquestra.painel import Painel
from orquestra.servidor import criar_app


@pytest.fixture
def avancar_coletas(monkeypatch):
    """Avança somente o relógio das cotas em jornadas com execuções consecutivas."""
    from orquestra import limites_coleta
    agora = [time.time()]
    monkeypatch.setattr(limites_coleta, "_agora", lambda: agora[0])

    def avancar():
        agora[0] += 31
    return avancar


@pytest.fixture(autouse=True)
def configuracao_isolada(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Inclusive testes de baixo nível guardam locks/recuperação somente no temporário."""
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path_factory.mktemp("orquestra-home-")))
    monkeypatch.delenv("ORQUESTRA_VAULT", raising=False)


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Nada dos testes pode tocar a configuração real do usuário (~/.orquestra).
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ORQUESTRA_VAULT", raising=False)
    # Sem git nos testes: é lento e não é o que está sendo testado aqui.
    monkeypatch.setattr(backup, "iniciar", lambda vault: False)
    return cli.criar_vault(tmp_path / "vault")


@pytest.fixture
def painel(vault: Path) -> Painel:
    return Painel(vault)


@pytest.fixture
def cliente(vault: Path):
    app = criar_app(vault, vigiar=False, agendar=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        c.painel = app.state.painel  # atalho para os testes olharem o estado
        yield c
