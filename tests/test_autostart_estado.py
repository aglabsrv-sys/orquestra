"""Estado de inicialização por cofre; todas as alterações usam pasta temporária."""
from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from orquestra import autostart


@pytest.fixture(params=["win32", "linux", "darwin"])
def inicializacao(request, tmp_path, monkeypatch):
    arquivo = tmp_path / "inicializacao"
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform=request.param, executable=sys.executable))
    monkeypatch.setattr(autostart, "_arquivo", lambda: arquivo)
    monkeypatch.setattr(autostart.subprocess, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 0))
    return arquivo, tmp_path / "Cofre com espaço e ação"


def test_estado_e_ativacao_idempotente_por_cofre(inicializacao):
    arquivo, vault = inicializacao
    desligado = autostart.resumo(vault)
    assert desligado["estado"] == "desligado" and not desligado["presente"]
    assert not arquivo.exists()
    autostart.executar("ativar", vault)
    assert autostart.resumo(vault) == {"presente": True, "ativo": True, "neste_cofre": True,
                                      "estado": "ativo", "descricao": "Ativado para este cofre."}
    antes = arquivo.read_bytes(), arquivo.stat().st_mtime_ns
    assert "já está ligado" in autostart.executar("ativar", vault)
    assert (arquivo.read_bytes(), arquivo.stat().st_mtime_ns) == antes
    autostart.executar("desativar")
    assert autostart.resumo(vault)["estado"] == "desligado"
    assert "já estava desligado" in autostart.executar("desativar")


def test_estado_distingue_outro_cofre_sem_expor_caminho(inicializacao):
    arquivo, vault = inicializacao
    autostart.executar("ativar", vault)
    estado = autostart.resumo(vault.parent / "Outro cofre")
    assert estado["presente"] and not estado["ativo"] and not estado["neste_cofre"]
    assert estado["estado"] == "outro_cofre"
    assert str(arquivo) not in str(estado) and str(vault) not in str(estado)


def test_arquivo_desconhecido_nao_e_mostrado_como_ativo(inicializacao):
    arquivo, vault = inicializacao
    arquivo.write_text("arquivo diferente", encoding="utf-8")
    estado = autostart.resumo(vault)
    assert estado["presente"] and not estado["ativo"]
    assert estado["estado"] == "revisar"


def test_executavel_removido_permite_reparar_inicializacao(inicializacao, monkeypatch):
    arquivo, vault = inicializacao
    executavel = vault.parent / "instalacao-antiga" / "python.exe"
    monkeypatch.setattr(autostart, "_comando", lambda destino: [str(executavel), "-m", "orquestra", "iniciar", "--vault", str(destino)])
    arquivo.write_text(autostart._conteudo(vault), encoding="utf-8")
    estado = autostart.resumo(vault)
    assert estado["presente"] and not estado["ativo"] and estado["estado"] == "revisar"


def test_macos_arquivo_presente_sem_agente_carregado(tmp_path, monkeypatch):
    arquivo, vault = tmp_path / "agente.plist", tmp_path / "vault"
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="darwin", executable=sys.executable))
    monkeypatch.setattr(autostart, "_arquivo", lambda: arquivo)
    arquivo.write_text(autostart._conteudo(vault), encoding="utf-8")
    monkeypatch.setattr(autostart.subprocess, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 1))
    estado = autostart.resumo(vault)
    assert estado["neste_cofre"] and not estado["ativo"] and estado["estado"] == "pendente"


def test_macos_falha_ao_descarregar_preserva_configuracao(tmp_path, monkeypatch):
    arquivo, vault = tmp_path / "agente.plist", tmp_path / "vault"
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="darwin", executable=sys.executable))
    monkeypatch.setattr(autostart, "_arquivo", lambda: arquivo)
    arquivo.write_text(autostart._conteudo(vault), encoding="utf-8")
    antes = arquivo.read_bytes()
    monkeypatch.setattr(autostart.subprocess, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 0 if args[1] == "list" else 1))
    with pytest.raises(RuntimeError, match="preservada"):
        autostart.executar("ativar", vault.parent / "outro")
    assert arquivo.read_bytes() == antes


def test_api_inicializacao_confirma_estado_sem_expor_arquivo(cliente, tmp_path, monkeypatch):
    arquivo = tmp_path / "Inicializar" / "Orquestra.vbs"
    monkeypatch.setattr(autostart, "_arquivo", lambda: arquivo)
    # A API é a mesma em todo sistema. Fixar uma plataforma sem serviço do sistema evita
    # que o teste registre um agente de verdade no launchctl do macOS da CI.
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="win32", executable=sys.executable))
    assert cliente.get("/api/autostart").status_code == 403
    assert cliente.post("/api/autostart", json={"acao": "ativar"}).status_code == 403
    headers = {"X-Orquestra-Local": cliente.get("/api/local/capacidade").json()["token"]}
    assert not cliente.get("/api/autostart", headers=headers).json()["ativo"]
    ativo = cliente.post("/api/autostart", headers=headers, json={"acao": "ativar"})
    assert ativo.status_code == 200 and ativo.json()["ativo"]
    assert ativo.json()["mensagem"] == "Pronto"
    assert str(arquivo) not in ativo.text and "Arquivo criado" not in ativo.text
    desligado = cliente.post("/api/autostart", headers=headers, json={"acao": "desativar"})
    assert desligado.status_code == 200 and not desligado.json()["presente"]


def test_referencia_youtube_e_olho_nao_criam_segredo(cliente, vault):
    from orquestra import segredos
    caminho = segredos.arquivo(vault)
    antes = caminho.read_bytes() if caminho.exists() else None
    pagina = cliente.get("/ajustes/variaveis")
    assert pagina.status_code == 200 and "<code>YOUTUBE_API_KEY</code>" in pagina.text
    assert 'id="variavel-revelar" type="button"' in pagina.text
    assert 'class="segredo-valor"' in pagina.text and 'class="segredo-olho"' in pagina.text
    assert "developers.google.com/youtube/data/guides/authentication" in pagina.text
    assert segredos.nomes(vault) == []
    assert (caminho.read_bytes() if caminho.exists() else None) == antes


def test_windows_oferece_reparar_lancador_antigo_utf8(tmp_path, monkeypatch):
    arquivo = tmp_path / "Orquestra.vbs"
    vault = tmp_path / "Cofre com ação"
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="win32", executable=sys.executable))
    monkeypatch.setattr(autostart, "_arquivo", lambda: arquivo)
    arquivo.write_text(autostart._conteudo(vault), encoding="utf-8")
    assert autostart.resumo(vault)["estado"] == "revisar"
    autostart.executar("ativar", vault)
    assert arquivo.read_bytes().startswith(b"\xff\xfe")
    assert autostart.resumo(vault)["ativo"]
