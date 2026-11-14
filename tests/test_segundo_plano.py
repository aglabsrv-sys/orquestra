"""Retomada independente do terminal, sem tocar a inicialização real da pessoa."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from orquestra import autostart, cli, preparo, processo
from orquestra.servidor import criar_app
from orquestra.seguranca import CapabilityLocal


def test_porta_com_servidor_ativo_nao_e_considerada_livre():
    with socket.socket() as servidor:
        if os.name != "nt":
            servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind(("127.0.0.1", 0))
        servidor.listen()
        assert not cli._porta_livre(servidor.getsockname()[1])


@pytest.mark.skipif(os.name == "nt", reason="Reutilização de TIME_WAIT específica de sockets Unix")
def test_porta_em_time_wait_pode_reabrir_apos_encerrar_servidor():
    with socket.socket() as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind(("127.0.0.1", 0))
        porta = servidor.getsockname()[1]
        servidor.listen()
        with socket.create_connection(("127.0.0.1", porta)) as cliente:
            conexao, _ = servidor.accept()
            conexao.close()  # o lado servidor encerra primeiro e entra em TIME_WAIT
            assert cliente.recv(1) == b""
    assert cli._porta_livre(porta)


def test_retomada_nao_encerra_outra_instancia(monkeypatch):
    monkeypatch.setattr(processo, "localizar", lambda porta: {"pid": 456, "respondendo": True})
    with pytest.raises(RuntimeError, match="preservada"):
        processo.parar(8421, pid_esperado=123)


def test_destacar_nao_herda_terminal_e_nao_duplica_pedido(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(processo, "_retomada", None)
    monkeypatch.setattr(processo, "vivo", lambda pid: True)
    chamadas = []
    def abrir(args, **opcoes):
        chamadas.append((args, opcoes))
        return SimpleNamespace(pid=987)
    monkeypatch.setattr(processo.subprocess, "Popen", abrir)
    assert processo.destacar(tmp_path / "cofre", 8421, 123) == 987
    assert processo.destacar(tmp_path / "cofre", 8421, 123) == 987
    assert len(chamadas) == 1
    _, opcoes = chamadas[0]
    assert opcoes["close_fds"] and opcoes["stdin"] == subprocess.DEVNULL
    assert opcoes["env"]["ORQUESTRA_EM_SEGUNDO_PLANO"] == "1"
    if sys.platform == "win32":
        assert opcoes["creationflags"] & subprocess.DETACHED_PROCESS
        assert opcoes["creationflags"] & subprocess.CREATE_BREAKAWAY_FROM_JOB
    else:
        assert opcoes["start_new_session"]


def test_inicio_automatico_ja_ativo_tambem_libera_nova_abertura(tmp_path, monkeypatch):
    cofre = tmp_path / "cofre"
    cofre.mkdir()
    monkeypatch.setattr(cli, "_porta_livre", lambda porta: True)
    monkeypatch.setattr(autostart, "resumo", lambda vault: {"ativo": True})
    monkeypatch.setattr(processo, "em_segundo_plano", lambda: False)
    chamadas = []
    monkeypatch.setattr(processo, "destacar", lambda *args: chamadas.append(args))
    cli._main(["iniciar", "--vault", str(cofre), "--porta", "8421"])
    assert chamadas == [(cofre.resolve(), 8421, 0)]


def test_api_aplicar_agora_preserva_capacidade_e_so_anuncia_transicao(vault, monkeypatch):
    host = SimpleNamespace(servidor=SimpleNamespace(config=SimpleNamespace(port=8421)), capacidade=CapabilityLocal())
    monkeypatch.setattr(autostart, "resumo", lambda vault: {"ativo": True, "estado": "ativo", "presente": True})
    monkeypatch.setattr(autostart, "executar", lambda *args: None)
    monkeypatch.setattr(processo, "em_segundo_plano", lambda: False)
    chamadas = []
    monkeypatch.setattr(processo, "destacar", lambda *args: chamadas.append(args))
    app = criar_app(vault, vigiar=False, agendar=False, hospedeiro=host)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        assert cliente.post("/api/autostart", json={"acao": "ativar"}).status_code == 403
        # A capacidade é compartilhada com o hospedeiro em uma instância real.
        headers = {"X-Orquestra-Local": host.capacidade.token}
        estado = cliente.get("/api/autostart", headers=headers).json()
        assert estado["precisa_aplicar"] and not estado["segundo_plano"]
        resposta = cliente.post("/api/autostart", headers=headers, json={"acao": "ativar"})
        assert resposta.status_code == 200 and resposta.json()["reiniciando"]
        assert resposta.json()["mensagem"] != "Pronto"
        assert chamadas == [(vault, 8421, os.getpid())]


def test_ativar_transfere_servidor_e_sobrevive_ao_terminal_original(tmp_path, monkeypatch):
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("uv indisponível para a jornada real de terminal")
    home = tmp_path / "home"
    monkeypatch.setenv("ORQUESTRA_HOME", str(home))
    cofre = preparo.preparar(tmp_path / "Cofre de teste", [], exemplos=False, com_backup=False).vault
    ambiente = {**os.environ, "ORQUESTRA_HOME": str(home), "APPDATA": str(tmp_path / "appdata")}
    if sys.platform != "win32":
        ambiente["HOME"] = str(tmp_path / "perfil")
        (tmp_path / "perfil").mkdir()
    ambiente.pop("ORQUESTRA_EM_SEGUNDO_PLANO", None)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    from orquestra.config import gravar_yaml, ler_yaml
    configuracao = ler_yaml(cofre / "orquestra.yaml")
    configuracao["porta"] = porta
    gravar_yaml(cofre / "orquestra.yaml", configuracao)
    base = f"http://127.0.0.1:{porta}"
    def pedido(rota, dados=None):
        headers = {"Content-Type": "application/json"}
        if rota != "/api/local/capacidade":
            headers["X-Orquestra-Local"] = pedido("/api/local/capacidade")["token"]
        req = urllib.request.Request(base + rota, data=json.dumps(dados).encode() if dados is not None else None, headers=headers)
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.load(r)
    opcoes = {}
    if sys.platform == "win32":
        inicio = subprocess.STARTUPINFO()
        inicio.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        inicio.wShowWindow = 0
        opcoes = {"creationflags": subprocess.CREATE_NEW_CONSOLE, "startupinfo": inicio}
    # O driver representa o terminal/uv original e termina quando seu painel sai.
    driver = "import subprocess,sys; sys.exit(subprocess.call(sys.argv[1:]))"
    with (tmp_path / "terminal.log").open("wb") as log:
        terminal = subprocess.Popen([sys.executable, "-c", driver, uv, "run", "--frozen", "orquestra", "iniciar", "--vault", str(cofre), "--porta", str(porta)],
                                    cwd=Path(__file__).resolve().parents[1], env=ambiente, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **opcoes)
        try:
            antigo = None
            for _ in range(100):
                try:
                    antigo = pedido("/api/local/painel")
                    break
                except OSError:
                    time.sleep(.1)
            assert antigo and not antigo["segundo_plano"]
            assert pedido("/api/autostart", {"acao": "ativar"})["reiniciando"]
            novo = None
            for _ in range(150):
                try:
                    atual = pedido("/api/local/painel")
                    if atual["pid"] != antigo["pid"] and atual["segundo_plano"]:
                        novo = atual
                        break
                except OSError:
                    pass
                time.sleep(.1)
            if not novo:
                diagnostico = []
                for arquivo in (home / "painel.log", tmp_path / "terminal.log"):
                    if arquivo.exists():
                        diagnostico.append(arquivo.name + ":\n" + arquivo.read_text(encoding="utf-8", errors="replace")[-6000:])
                pytest.fail("O painel não retomou em segundo plano\n" + "\n".join(diagnostico))
            terminal.wait(timeout=10)
            assert pedido("/api/local/painel")["pid"] == novo["pid"]
            assert pedido("/api/autostart")["segundo_plano"]
            assert pedido("/api/autostart")["ativo"]
        finally:
            try:
                pedido("/api/local/encerrar", {})
            except OSError:
                pass
            if terminal.poll() is None:
                terminal.terminate()
            terminal.wait(timeout=10)
            for _ in range(100):
                if processo.consultar(porta) is None:
                    break
                time.sleep(.1)
            subprocess.run([sys.executable, "-m", "orquestra", "autostart", "desativar"], env=ambiente,
                           capture_output=True, timeout=20)
