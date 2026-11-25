"""Atualização real entre repositórios locais, incluindo cópia e conflitos de caminhos."""
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

from orquestra import atualizacao_git as g


def git(pasta, *args):
    return subprocess.check_output(["git", *args], cwd=pasta).decode("utf-8").strip()


@pytest.fixture
def repos(tmp_path, monkeypatch):
    remoto = tmp_path / "origem"
    remoto.mkdir()
    git(remoto, "init", "-b", "main")
    git(remoto, "config", "user.name", "Teste")
    git(remoto, "config", "user.email", "teste@localhost")
    git(remoto, "config", "core.autocrlf", "false")
    (remoto / ".gitattributes").write_text("* text eol=lf\n", newline="\n")
    (remoto / "pyproject.toml").write_text("# exemplo\n")
    (remoto / ".gitignore").write_text("ignorado.txt\n.venv/\n")
    (remoto / "código com espaço.txt").write_text("original\n", encoding="utf-8")
    (remoto / "excluido.txt").write_text("original\n")
    git(remoto, "add", ".")
    git(remoto, "commit", "-m", "Inicial")
    copia = tmp_path / "instalação com espaço"
    git(tmp_path, "-c", "core.autocrlf=false", "clone", str(remoto), str(copia))
    git(copia, "config", "core.autocrlf", "false")
    monkeypatch.setattr(g, "REMOTOS", {str(remoto)})
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path / "dados"))
    (remoto / "nova-versao.txt").write_text("nova versão\n", encoding="utf-8")
    git(remoto, "add", ".")
    git(remoto, "commit", "-m", "Nova versão")
    return g.Instalacao(copia), remoto


def abrir_copia(instalacao, resultado):
    return zipfile.ZipFile(instalacao.copias / (resultado["copia"]["id"] + ".zip"))


def test_extras_e_vault_interno_sem_colisao_nao_bloqueiam_nem_entram_na_copia(repos):
    instalacao, _ = repos
    (instalacao.raiz / "extra.txt").write_bytes(b"pessoal")
    vault = instalacao.raiz / "Meu vault"
    vault.mkdir()
    (vault / "nota.md").write_bytes(b"minha nota")
    resultado = instalacao.atualizar(vault=vault)
    assert resultado["mudou"] and resultado["copia"] is None
    assert (vault / "nota.md").read_bytes() == b"minha nota"
    assert (instalacao.raiz / "extra.txt").read_bytes() == b"pessoal"


def test_guarda_edicoes_indice_exclusoes_binarios_e_colisoes_sem_reaplicar(repos):
    instalacao, _ = repos
    raiz = instalacao.raiz
    nome = "código com espaço.txt"
    (raiz / nome).write_bytes(b"edicao no indice\n")
    git(raiz, "add", nome)
    (raiz / nome).write_bytes(b"edicao posterior\x00\xff")
    (raiz / "excluido.txt").unlink()
    (raiz / "nova-versao.txt").write_bytes(b"arquivo pessoal conflitante")
    (raiz / "extra-sem-conflito.txt").write_bytes(b"preservado no lugar")
    resultado = instalacao.atualizar(preservar=True)
    assert (raiz / nome).read_text() == "original\n"
    assert (raiz / "nova-versao.txt").read_text(encoding="utf-8") == "nova versão\n"
    assert (raiz / "excluido.txt").exists()
    assert not instalacao.alterados()
    assert (raiz / "extra-sem-conflito.txt").read_bytes() == b"preservado no lugar"
    with abrir_copia(instalacao, resultado) as copia:
        assert copia.read("arquivos/" + nome) == b"edicao posterior\x00\xff"
        assert copia.read("arquivos/nova-versao.txt") == b"arquivo pessoal conflitante"
        manifesto = json.loads(copia.read("manifesto.json"))
        assert any(a["tipo"] == "excluido" for a in manifesto["arquivos"])
        assert b"edicao no indice" in copia.read("preparadas.patch")
    assert git(raiz, "rev-parse", "refs/orquestra/atualizacoes/" + resultado["copia"]["id"])


def test_exige_confirmacao_antes_de_mover_edicoes(repos):
    instalacao, _ = repos
    alvo = instalacao.raiz / "pyproject.toml"
    alvo.write_bytes(b"alteracao pessoal")
    with pytest.raises(RuntimeError, match="Guardar cópia"):
        instalacao.atualizar()
    assert alvo.read_bytes() == b"alteracao pessoal"


def test_colisao_ignorada_e_diretorio_no_lugar_de_arquivo(repos):
    instalacao, remoto = repos
    (remoto / "ignorado.txt").write_text("oficial")
    git(remoto, "add", "-f", "ignorado.txt")
    git(remoto, "commit", "-m", "Arquivo distribuído")
    (instalacao.raiz / "ignorado.txt").write_bytes(b"pessoal ignorado")
    diretorio = instalacao.raiz / "nova-versao.txt"
    diretorio.mkdir()
    (diretorio / "meu arquivo.md").write_bytes(b"conteudo")
    resultado = instalacao.atualizar(preservar=True)
    with abrir_copia(instalacao, resultado) as copia:
        assert copia.read("arquivos/ignorado.txt") == b"pessoal ignorado"
        assert copia.read("arquivos/nova-versao.txt/meu arquivo.md") == b"conteudo"
    assert diretorio.is_file()


def test_colisao_arquivo_no_lugar_de_pasta(repos):
    instalacao, remoto = repos
    (remoto / "pasta").mkdir()
    (remoto / "pasta/novo.txt").write_text("oficial")
    git(remoto, "add", ".")
    git(remoto, "commit", "-m", "Pasta nova")
    (instalacao.raiz / "pasta").write_bytes(b"arquivo pessoal")
    resultado = instalacao.atualizar(preservar=True)
    with abrir_copia(instalacao, resultado) as copia:
        assert copia.read("arquivos/pasta") == b"arquivo pessoal"
    assert (instalacao.raiz / "pasta/novo.txt").is_file()


def test_renomeacao_preparada_e_nome_parecido_com_pathspec(repos):
    instalacao, _ = repos
    git(instalacao.raiz, "mv", "excluido.txt", "[pessoal].txt")
    resultado = instalacao.atualizar(preservar=True)
    with abrir_copia(instalacao, resultado) as copia:
        assert copia.read("arquivos/[pessoal].txt") == b"original\n"
    assert (instalacao.raiz / "excluido.txt").exists()


def test_revisao_mudou_nao_move_arquivos(repos):
    instalacao, _ = repos
    (instalacao.raiz / "pyproject.toml").write_bytes(b"pessoal")
    with pytest.raises(RuntimeError, match="publicada"):
        instalacao.atualizar("a" * 40, preservar=True)
    assert (instalacao.raiz / "pyproject.toml").read_bytes() == b"pessoal"


def test_vault_colidindo_fica_intacto(repos):
    instalacao, _ = repos
    vault = instalacao.raiz / "nova-versao.txt"
    vault.mkdir()
    (vault / "nota.md").write_bytes(b"nota")
    with pytest.raises(RuntimeError, match="vault"):
        instalacao.atualizar(preservar=True, vault=vault)
    assert (vault / "nota.md").read_bytes() == b"nota"


def test_recuperacao_reconhece_vault_fechado_sem_registro(repos):
    instalacao, _ = repos
    vault = instalacao.raiz / "nova-versao.txt"
    vault.mkdir()
    (vault / "orquestra.yaml").write_text("nome: Exemplo\n")
    (vault / "nota.md").write_bytes(b"nota")
    with pytest.raises(RuntimeError, match="vault"):
        instalacao.atualizar(preservar=True)
    assert (vault / "nota.md").read_bytes() == b"nota"


def test_commits_divergentes_nao_sao_descartados(repos):
    instalacao, _ = repos
    git(instalacao.raiz, "config", "user.name", "Teste")
    git(instalacao.raiz, "config", "user.email", "teste@localhost")
    (instalacao.raiz / "local.txt").write_bytes(b"commit pessoal")
    git(instalacao.raiz, "add", ".")
    git(instalacao.raiz, "commit", "-m", "Personalizado")
    antes = git(instalacao.raiz, "rev-parse", "HEAD")
    with pytest.raises(RuntimeError, match="commits próprios"):
        instalacao.atualizar(preservar=True)
    assert git(instalacao.raiz, "rev-parse", "HEAD") == antes


def test_falha_na_copia_nao_limpa_edicoes(repos, monkeypatch):
    instalacao, _ = repos
    (instalacao.raiz / "pyproject.toml").write_bytes(b"pessoal")
    monkeypatch.setattr(g.zipfile, "ZipFile", lambda *a, **k: (_ for _ in ()).throw(OSError("sem espaço")))
    with pytest.raises(OSError):
        instalacao.atualizar(preservar=True)
    assert (instalacao.raiz / "pyproject.toml").read_bytes() == b"pessoal"


def test_trava_impede_duas_atualizacoes(repos):
    instalacao, _ = repos
    with instalacao.trava():
        with pytest.raises(RuntimeError, match="andamento"):
            instalacao.atualizar(preservar=True)


def test_recusa_outro_repositorio(repos, monkeypatch):
    instalacao, _ = repos
    monkeypatch.setattr(g, "REMOTOS", {"https://outro.invalid"})
    with pytest.raises(RuntimeError, match="oficial"):
        instalacao.atualizar(preservar=True)


def test_recusa_copias_dentro_do_vault_antes_de_escrever(repos):
    instalacao, _ = repos
    vault = instalacao.copias.parent.parent
    with pytest.raises(RuntimeError, match="fora do aplicativo e do vault"):
        instalacao.atualizar(preservar=True, vault=vault)
    assert not instalacao.copias.exists()


def test_recuperador_roda_fora_do_pacote(tmp_path):
    fonte = Path(g.__file__).resolve()
    resultado = subprocess.run([__import__("sys").executable, "-I", str(fonte), "--help"], cwd=tmp_path, capture_output=True)
    assert resultado.returncode == 0
    assert b"--aplicativo" in resultado.stdout


def test_tentar_novamente_mantem_acesso_a_copia(repos, monkeypatch):
    instalacao, _ = repos
    (instalacao.raiz / "pyproject.toml").write_bytes(b"pessoal")
    original = instalacao.git
    def falhar_merge(*args, **kwargs):
        if args[:1] == ("merge",):
            raise RuntimeError("merge interrompido")
        return original(*args, **kwargs)
    monkeypatch.setattr(instalacao, "git", falhar_merge)
    with pytest.raises(RuntimeError, match="guardadas"):
        instalacao.atualizar(preservar=True)
    copia = instalacao.ler_estado()["copia"]
    monkeypatch.setattr(instalacao, "git", original)
    assert instalacao.atualizar(preservar=True)["copia"] == copia
    assert (instalacao.copias / (copia["id"] + ".zip")).exists()


def test_dependencias_preparam_fora_do_ambiente_em_uso_e_aplicam_offline(tmp_path, monkeypatch):
    deps = g.Dependencias(tmp_path / "app", "uv", tmp_path / "copias")
    chamadas = []
    monkeypatch.setattr(deps, "sincronizar", lambda ambiente, **opcoes: chamadas.append((ambiente, opcoes)))
    deps.preparar()
    if os.name == "nt":
        assert Path(chamadas[0][0]["UV_PROJECT_ENVIRONMENT"]).parent == deps.copias
        assert chamadas[0][0] != deps.ambiente
    assert deps.concluir() == deps.ambiente
    if os.name == "nt":
        assert chamadas[-1] == (deps.ambiente, {"offline": True})
    deps.limpar()
    assert not deps.preparado or not deps.preparado.exists()


def test_executavel_ainda_ocupado_retoma_com_dependencias_preparadas(tmp_path, monkeypatch):
    preparado = tmp_path / "copias/ambiente-teste"
    preparado.mkdir(parents=True)
    deps = g.Dependencias(tmp_path / "app", "uv", preparado.parent, preparado=preparado)
    monkeypatch.setattr(deps, "sincronizar", lambda *a, **k: (_ for _ in ()).throw(OSError(32, "executável em uso")))
    ambiente = deps.concluir()
    assert ambiente["UV_PROJECT_ENVIRONMENT"] == str(preparado)
    deps.limpar()
    assert preparado.exists()


def test_limpeza_de_ambiente_nao_atravessa_pasta_de_atualizacoes(tmp_path):
    externo = tmp_path / "pessoal/ambiente-exemplo"
    externo.mkdir(parents=True)
    nota = externo / "nota.md"
    nota.write_bytes(b"pessoal")
    deps = g.Dependencias(tmp_path / "app", "uv", tmp_path / "copias", preparado=externo)
    deps.limpar()
    assert nota.read_bytes() == b"pessoal"
