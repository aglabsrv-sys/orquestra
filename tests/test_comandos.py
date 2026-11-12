"""Comandos reais em processos e pastas descartáveis, sem provedores externos."""

import json
import os
import socket
import subprocess
import sys
from types import SimpleNamespace
import time
import urllib.request

import pytest

from orquestra import autostart, cli, doctor, preparo


@pytest.fixture
def comando(tmp_path):
    env = os.environ.copy()
    env.pop("ORQUESTRA_VAULT", None)
    env["ORQUESTRA_HOME"] = str(tmp_path / "configuração local")
    env["APPDATA"] = str(tmp_path / "appdata descartável")

    def executar(*argumentos):
        return subprocess.run(
            [sys.executable, "-m", "orquestra", *map(str, argumentos)],
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    executar.env = env
    return executar


@pytest.fixture
def cofre_cli(tmp_path):
    vault = tmp_path / "Meu cofre com espaços e acentuação"
    preparo.preparar(vault, ["tarefas", "entrada"], exemplos=False, com_backup=False)
    return vault


@pytest.mark.parametrize("subcomando", [
    "criar", "init", "adotar", "iniciar", "mcp", "doctor", "diagnostico", "coletar", "backup", "confiar", "autostart",
])
def test_ajuda_de_cada_comando_funciona_sem_vault(comando, subcomando):
    resultado = comando(subcomando, "--help")
    assert resultado.returncode == 0
    assert "usage:" in resultado.stdout
    assert "Traceback" not in resultado.stderr


def test_versao_e_ajuda_principal_sem_vault(comando):
    assert comando("--help").returncode == 0
    resultado = comando("--version")
    assert resultado.returncode == 0
    assert resultado.stdout.startswith("orquestra ")


def test_init_e_adotar_por_subprocesso_preservam_notas(comando, tmp_path):
    novo = tmp_path / "Novo cofre com acentuação"
    criado = comando("init", novo, "--perfil", "essencial", "--sem-exemplos")
    assert criado.returncode == 0, criado.stderr
    assert (novo / "orquestra.yaml").is_file()
    assert "Inicie o painel:  orquestra" in criado.stdout
    repetido = comando("criar", novo)
    assert repetido.returncode == 0
    assert "Já existe" in repetido.stdout

    existente = tmp_path / "Notas existentes"
    (existente / "Projetos").mkdir(parents=True)
    nota = existente / "Projetos" / "Minha nota.md"
    bruto = b"\xef\xbb\xbf---\r\ntitulo: Minha nota # meu comentario\r\n---\r\nTexto meu.\r\n"
    nota.write_bytes(bruto)
    adotado = comando("adotar", existente, "--pastas", "Projetos", "--modulos", "entrada")
    assert adotado.returncode == 0, adotado.stderr
    assert nota.read_bytes() == bruto
    assert (existente / "Projetos" / "_modulo.yaml").is_file()


def test_vault_antes_ou_depois_do_subcomando(comando, cofre_cli):
    antes = comando("--vault", cofre_cli, "confiar", "backup")
    depois = comando("confiar", "backup", "--vault", cofre_cli)
    assert antes.returncode == depois.returncode == 0
    assert antes.stdout == depois.stdout
    revisao = json.loads(antes.stdout[:antes.stdout.rfind("}") + 1])
    assert revisao["confiavel"] is False


def test_coletar_modulo_inexistente_ou_falha_nao_retornam_sucesso(comando, cofre_cli):
    desconhecido = comando("coletar", "nao-existe", "--vault", cofre_cli)
    assert desconhecido.returncode == 1
    assert "não existe" in desconhecido.stderr
    # Uma alteração local deixa de corresponder ao catálogo e exige aprovação.
    # Todos os auxiliares entram na assinatura: nenhum provedor deve ser chamado.
    script = cofre_cli / "tarefas/maquina/coletores/recorrentes.py"
    script.write_bytes(script.read_bytes() + b"\n# revisao local pendente\n")
    recusado = comando("coletar", "tarefas", "--vault", cofre_cli)
    assert recusado.returncode == 1
    assert "falhou:" in recusado.stdout
    assert "Traceback" not in recusado.stderr
    nenhum = comando("coletar", "entrada", "--vault", cofre_cli)
    assert nenhum.returncode == 0
    assert "Nenhum coletor" in nenhum.stdout


def test_confiar_coletor_desconhecido_mostra_orientacao_sem_traceback(comando, cofre_cli):
    for modulo, script in (("inexistente", "script.py"), ("tarefas", "inexistente.py")):
        resultado = comando("confiar", "coletor", modulo, script, "--vault", cofre_cli)
        assert resultado.returncode == 1
        assert "não existe" in resultado.stderr
        assert "Traceback" not in resultado.stderr


def test_confiar_recusa_opcoes_contraditorias_e_argumentos_ignorados(comando, cofre_cli):
    for extras in (("--revogar", "--assinatura", "abc"), ("modulo-ignorado", "script-ignorado.py")):
        resultado = comando("confiar", "backup", *extras, "--vault", cofre_cli)
        assert resultado.returncode == 2
        assert "Traceback" not in resultado.stderr


def test_vault_vazio_ou_destino_ambiguo_e_recusado_antes_de_gravar(comando, tmp_path):
    for argumentos in (("coletar", "--vault", "   "), ("mcp", "--vault", ""), ("--vault", tmp_path / "Não criar", "criar")):
        resultado = comando(*argumentos)
        assert resultado.returncode == 2
        assert "Traceback" not in resultado.stderr
    assert not (tmp_path / "Não criar").exists()


def test_backup_cli_requer_assinatura_e_faz_snapshot_sem_remoto(comando, cofre_cli):
    primeiro = comando("backup", "--vault", cofre_cli)
    assert primeiro.returncode == 1
    assert (cofre_cli / ".git").is_dir()
    revisao = comando("confiar", "backup", "--vault", cofre_cli)
    dados = json.loads(revisao.stdout[:revisao.stdout.rfind("}") + 1])
    aprovado = comando("confiar", "backup", "--assinatura", dados["assinatura"], "--vault", cofre_cli)
    assert aprovado.returncode == 0
    local = comando("backup", "--vault", cofre_cli)
    assert local.returncode == 0
    assert "Commit feito." in local.stdout
    envio = comando("backup", "--enviar", "--vault", cofre_cli)
    assert envio.returncode == 1
    assert "Não há repositório remoto" in envio.stdout
    assert "Traceback" not in envio.stderr


def test_coletar_script_local_revisado_e_revogar_por_cli(comando, cofre_cli):
    arquivo = cofre_cli / "entrada" / "_modulo.yaml"
    with arquivo.open("a", encoding="utf-8") as destino:
        destino.write("\ncoletores:\n  - script: exemplo_local.py\n    nome: Exemplo local\n    ativo: false\n")
    pasta = cofre_cli / "entrada" / "maquina" / "coletores"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "exemplo_local.py").write_text("print('[]')\n", encoding="utf-8")
    base = ("confiar", "coletor", "entrada", "exemplo_local.py")
    revisao = comando(*base, "--vault", cofre_cli)
    dados = json.loads(revisao.stdout[:revisao.stdout.rfind("}") + 1])
    assert comando(*base, "--assinatura", dados["assinatura"], "--vault", cofre_cli).returncode == 0
    coleta = comando("coletar", "entrada", "--vault", cofre_cli)
    assert coleta.returncode == 0
    assert "0 novos, 0 já conhecidos" in coleta.stdout
    assert comando(*base, "--revogar", "--vault", cofre_cli).returncode == 0
    assert comando("coletar", "entrada", "--vault", cofre_cli).returncode == 1


def test_autostart_status_e_desativar_dispensam_vault(comando, monkeypatch, tmp_path, capsys):
    comando.env["HOME"] = str(tmp_path)
    comando.env["USERPROFILE"] = str(tmp_path)
    assert comando("autostart", "status").returncode == 0
    arquivo = tmp_path / "inicialização simulada" / "orquestra.desktop"
    monkeypatch.setattr(autostart, "_arquivo", lambda: arquivo)
    # Simula apenas o arquivo; nenhum serviço de login é iniciado ou alterado.
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="linux", executable=sys.executable))
    monkeypatch.delenv("ORQUESTRA_VAULT", raising=False)
    perdido = tmp_path / "vault que não existe mais"
    arquivo.parent.mkdir()
    arquivo.write_text("registro antigo", encoding="utf-8")
    cli.main(["autostart", "status", "--vault", str(perdido)])
    assert "ligado" in capsys.readouterr().out
    cli.main(["autostart", "desativar", "--vault", str(perdido)])
    assert not arquivo.exists()
    assert "desligado" in capsys.readouterr().out


def test_doctor_relata_script_ausente_e_captura_desligada(cofre_cli, monkeypatch):
    script = cofre_cli / "tarefas" / "maquina" / "coletores" / "recorrentes.py"
    script.unlink()
    arquivo = cofre_cli / "orquestra.yaml"
    arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("captura: entrada", "captura: ''"), encoding="utf-8")
    monkeypatch.setattr(doctor, "verificar_acesso", lambda porta: [])
    itens = doctor.verificar_vault(cofre_cli)
    assert any(i.estado == "erro" and "recorrentes.py" in i.titulo for i in itens)
    assert any("Backup" in i.titulo or "histórico" in i.titulo for i in itens)
    assert not any("Módulo de captura ''" in i.titulo for i in itens)
    assert any("sem autorização local" in i.titulo for i in itens)


def test_doctor_nao_da_sucesso_para_configuracao_invalida(cofre_cli, monkeypatch):
    (cofre_cli / "orquestra.yaml").write_text("nome: [quebrado\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "verificar_acesso", lambda porta: [])
    itens = doctor.verificar_vault(cofre_cli)
    assert any(i.estado == "erro" and "configuração" in i.titulo for i in itens)


@pytest.mark.parametrize("backend,aponta", [
    ("http://127.0.0.1:18420", False),
    ("http://127.0.0.1:8420", True),
    ("http://localhost:8420/painel", True),
    ("http://[::1]:8420", True),
    ("http://outro-servidor:8420", False),
])
def test_doctor_confere_porta_exata_sem_promessa_de_acesso(monkeypatch, backend, aponta):
    class Conexao:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, valor):
            pass

        def connect_ex(self, endereco):
            return 0

    monkeypatch.setattr(doctor.socket, "socket", lambda *args: Conexao())
    monkeypatch.setattr(doctor, "localizar_tailscale", lambda: "tailscale")
    estado = json.dumps({"BackendState": "Running", "Self": {"DNSName": "pc-teste.tail-exemplo.ts.net."}})
    monkeypatch.setattr(doctor, "_rodar", lambda *args: (0, estado if "--json" in args else f"|-- proxy {backend}\n"))
    itens = doctor.verificar_acesso(8420)
    assert itens[0].titulo.startswith("Porta local aberta")
    assert "não confirma" in itens[0].detalhe
    assert any(i.titulo == "Tailscale Serve aponta para a porta local 8420" for i in itens) is aponta
    assert not any(i.titulo.startswith("Acesso pelo celular:") for i in itens)


def test_iniciar_cli_responde_na_porta_local_configurada(comando, cofre_cli):
    with socket.socket() as livre:
        livre.bind(("127.0.0.1", 0))
        porta = livre.getsockname()[1]
    processo = subprocess.Popen(
        [sys.executable, "-m", "orquestra", "iniciar", "--vault", str(cofre_cli), "--porta", str(porta)],
        env=comando.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        limite = time.monotonic() + 15
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=1) as resposta:
                    assert resposta.status == 200
                    assert "Tarefas" in resposta.read().decode("utf-8")
                break
            except OSError:
                if processo.poll() is not None or time.monotonic() >= limite:
                    pytest.fail("O comando iniciar não respondeu na porta local dentro do prazo.")
                time.sleep(0.1)
    finally:
        processo.terminate()
        processo.communicate(timeout=10)
