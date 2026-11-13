"""Painel em execução: registro, consulta e encerramento por outro terminal."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from orquestra import cli, processo
from orquestra.hospedeiro import Hospedeiro


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path / "home"))
    hospedeiro = Hospedeiro(None, vigiar=False, agendar=False)
    with TestClient(hospedeiro, base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        yield hospedeiro, cliente


def test_registro_guarda_e_so_apaga_a_propria_instancia(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path))
    processo.registrar(8425, tmp_path / "vault")
    dados = processo.ler()
    assert dados["pid"] == os.getpid() and dados["porta"] == 8425 and dados["vault"].endswith("vault")
    processo.esquecer(os.getpid() + 1)  # outra instância não apaga o registro desta
    assert processo.ler() is not None
    processo.esquecer(os.getpid())
    assert processo.ler() is None


def test_registro_corrompido_e_ignorado(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path))
    (tmp_path / "painel.json").write_text("{nao é json", encoding="utf-8")
    assert processo.ler() is None
    assert processo.vivo(os.getpid()) and not processo.vivo(0)


def test_painel_local_exige_credencial_e_se_identifica(local):
    _, cliente = local
    assert cliente.get("/api/local/painel").status_code == 403
    token = cliente.get("/api/local/capacidade").json()["token"]
    dados = cliente.get("/api/local/painel", headers={"X-Orquestra-Local": token}).json()
    assert dados["app"] == "orquestra" and dados["pid"] == os.getpid()


def test_encerrar_fecha_o_servidor_somente_com_credencial(local):
    hospedeiro, cliente = local
    hospedeiro.servidor = SimpleNamespace(should_exit=False)
    assert cliente.post("/api/local/encerrar", json={}).status_code == 403
    assert hospedeiro.servidor.should_exit is False
    token = cliente.get("/api/local/capacidade").json()["token"]
    assert cliente.post("/api/local/encerrar", json={}, headers={"X-Orquestra-Local": token}).status_code == 200
    assert hospedeiro.servidor.should_exit is True


def test_encerrar_sem_servidor_da_linha_de_comando_explica(local):
    hospedeiro, cliente = local
    token = cliente.get("/api/local/capacidade").json()["token"]
    resposta = cliente.post("/api/local/encerrar", json={}, headers={"X-Orquestra-Local": token})
    assert resposta.status_code == 409 and "linha de comando" in resposta.json()["erro"]


def test_parar_sem_painel_rodando_avisa(monkeypatch, capsys):
    monkeypatch.setattr(processo, "localizar", lambda porta=None: None)
    cli._main(["parar"])
    assert "não estava rodando" in capsys.readouterr().out


def test_registro_de_processo_que_nao_responde_pede_forcar(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path))
    monkeypatch.setattr(processo, "localizar", lambda porta=None: {"pid": 4242, "porta": 8425, "respondendo": False})
    with pytest.raises(RuntimeError, match="--forcar"):
        processo.parar()
    encerrados = []
    monkeypatch.setattr(processo, "_forcar", encerrados.append)
    monkeypatch.setattr(processo, "vivo", lambda pid: False)
    assert processo.parar(forcar=True)["porta"] == 8425 and encerrados == [4242]


def test_iniciar_com_orquestra_ja_aberto_orienta_reiniciar(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_porta_livre", lambda porta: False)
    monkeypatch.setattr(processo, "consultar", lambda porta: {"app": "orquestra", "vault": "meu vault"})
    monkeypatch.setattr(cli, "localizar_vault", lambda v=None: None)
    with pytest.raises(SystemExit, match="orquestra reiniciar"):
        cli._main(["iniciar", "--porta", "8425"])
