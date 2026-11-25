"""Atualização real entre repositórios locais, incluindo sincronização e proteção do vault."""
import os
import subprocess
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


def test_extras_e_vault_interno_sem_colisao_ficam_no_lugar(repos):
    instalacao, _ = repos
    (instalacao.raiz / "extra.txt").write_bytes(b"pessoal")
    vault = instalacao.raiz / "Meu vault"
    vault.mkdir()
    (vault / "nota.md").write_bytes(b"minha nota")
    resultado = instalacao.atualizar(vault=vault)
    assert resultado["mudou"]
    assert (vault / "nota.md").read_bytes() == b"minha nota"
    assert (instalacao.raiz / "extra.txt").read_bytes() == b"pessoal"


def test_sincroniza_edicoes_indice_exclusoes_binarios_sem_copias(repos):
    instalacao, _ = repos
    raiz = instalacao.raiz
    nome = "código com espaço.txt"
    (raiz / nome).write_bytes(b"edicao no indice\n")
    git(raiz, "add", nome)
    (raiz / nome).write_bytes(b"edicao posterior\x00\xff")
    (raiz / "excluido.txt").unlink()
    (raiz / "nova-versao.txt").write_bytes(b"conflito")
    (raiz / "extra-sem-conflito.txt").write_bytes(b"preservado")
    resultado = instalacao.atualizar()
    assert git(raiz, "rev-parse", "HEAD") == resultado["revisao"]
    assert (raiz / nome).read_text() == "original\n"
    assert (raiz / "nova-versao.txt").read_text(encoding="utf-8") == "nova versão\n"
    assert (raiz / "excluido.txt").exists()
    assert not instalacao.alterados()
    assert (raiz / "extra-sem-conflito.txt").read_bytes() == b"preservado"
    assert not list(instalacao.pasta.glob("*.zip"))
    assert not git(raiz, "for-each-ref", "--format=%(refname)", "refs/stash", "refs/orquestra/atualizacoes")


def test_sincroniza_tambem_quando_a_revisao_ja_e_a_mais_recente(repos):
    instalacao, _ = repos
    instalacao.atualizar()
    alvo = instalacao.raiz / "pyproject.toml"
    alvo.write_bytes(b"alteracao local")
    assert not instalacao.atualizar()["mudou"]
    assert alvo.read_bytes() == b"# exemplo\n"


def test_sincroniza_colisoes_ignoradas_e_pastas_no_lugar_de_arquivo(repos):
    instalacao, remoto = repos
    (remoto / "ignorado.txt").write_text("oficial")
    git(remoto, "add", "-f", "ignorado.txt")
    git(remoto, "commit", "-m", "Arquivo distribuído")
    (instalacao.raiz / "ignorado.txt").write_bytes(b"local")
    diretorio = instalacao.raiz / "nova-versao.txt"
    diretorio.mkdir()
    (diretorio / "arquivo.txt").write_bytes(b"local")
    instalacao.atualizar()
    assert diretorio.is_file()
    assert (instalacao.raiz / "ignorado.txt").read_text() == "oficial"


def test_sincroniza_arquivo_no_lugar_de_pasta(repos):
    instalacao, remoto = repos
    (remoto / "pasta").mkdir()
    (remoto / "pasta/novo.txt").write_text("oficial")
    git(remoto, "add", ".")
    git(remoto, "commit", "-m", "Pasta nova")
    (instalacao.raiz / "pasta").write_bytes(b"local")
    instalacao.atualizar()
    assert (instalacao.raiz / "pasta/novo.txt").is_file()


def test_sincroniza_renomeacao_preparada_com_nome_especial(repos):
    instalacao, _ = repos
    git(instalacao.raiz, "mv", "excluido.txt", "[local].txt")
    instalacao.atualizar()
    assert (instalacao.raiz / "excluido.txt").exists()
    assert not (instalacao.raiz / "[local].txt").exists()


def test_revisao_mudou_nao_altera_arquivos(repos):
    instalacao, _ = repos
    (instalacao.raiz / "pyproject.toml").write_bytes(b"local")
    with pytest.raises(RuntimeError, match="publicada"):
        instalacao.atualizar("a" * 40)
    assert (instalacao.raiz / "pyproject.toml").read_bytes() == b"local"


@pytest.mark.parametrize("reconhecido", [True, False])
def test_vault_colidindo_fica_intacto(repos, reconhecido):
    instalacao, _ = repos
    vault = instalacao.raiz / "nova-versao.txt"
    vault.mkdir()
    (vault / "orquestra.yaml").write_text("nome: Exemplo\n")
    (vault / "nota.md").write_bytes(b"nota")
    with pytest.raises(RuntimeError, match="vault"):
        instalacao.atualizar(vault=vault if reconhecido else None)
    assert (vault / "nota.md").read_bytes() == b"nota"


def test_vault_aninhado_em_diretorio_que_seria_substituido_fica_intacto(repos):
    instalacao, _ = repos
    vault = instalacao.raiz / "nova-versao.txt/subpasta/Vault"
    vault.mkdir(parents=True)
    (vault / "orquestra.yaml").write_text("nome: Exemplo\n")
    (vault / "nota.md").write_bytes(b"nota")
    with pytest.raises(RuntimeError, match="vault"):
        instalacao.atualizar()
    assert (vault / "nota.md").read_bytes() == b"nota"


def test_caminhos_novos_tambem_conferem_o_vault_antes_de_sincronizar(repos):
    instalacao, _ = repos
    antes = git(instalacao.raiz, "rev-parse", "HEAD")
    with pytest.raises(RuntimeError, match="vault"):
        instalacao.atualizar(vault=instalacao.raiz)
    assert git(instalacao.raiz, "rev-parse", "HEAD") == antes
    assert not (instalacao.raiz / "nova-versao.txt").exists()


def test_commits_divergentes_nao_sao_descartados(repos):
    instalacao, _ = repos
    git(instalacao.raiz, "config", "user.name", "Teste")
    git(instalacao.raiz, "config", "user.email", "teste@localhost")
    (instalacao.raiz / "local.txt").write_bytes(b"commit local")
    git(instalacao.raiz, "add", ".")
    git(instalacao.raiz, "commit", "-m", "Personalizado")
    antes = git(instalacao.raiz, "rev-parse", "HEAD")
    with pytest.raises(RuntimeError, match="commits próprios"):
        instalacao.atualizar()
    assert git(instalacao.raiz, "rev-parse", "HEAD") == antes


def test_trava_impede_duas_atualizacoes(repos):
    instalacao, _ = repos
    with instalacao.trava():
        with pytest.raises(RuntimeError, match="andamento"):
            instalacao.atualizar()


@pytest.mark.skipif(os.name != "nt", reason="Trava de região obrigatória no Windows")
def test_atualizador_nao_escreve_em_trava_vazia_ocupada(repos):
    import msvcrt

    instalacao, _ = repos
    instalacao.pasta.mkdir(parents=True)
    with (instalacao.pasta / "operacao.lock").open("w+b", buffering=0) as arquivo:
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            with pytest.raises(RuntimeError, match="andamento"):
                instalacao.atualizar()
        finally:
            msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)


def test_recusa_outro_repositorio(repos, monkeypatch):
    instalacao, _ = repos
    monkeypatch.setattr(g, "REMOTOS", {"https://outro.invalid"})
    with pytest.raises(RuntimeError, match="oficial"):
        instalacao.atualizar()


def test_recusa_dados_dentro_do_vault_antes_de_escrever(repos):
    instalacao, _ = repos
    vault = instalacao.pasta.parent.parent
    with pytest.raises(RuntimeError, match="fora do aplicativo e do vault"):
        instalacao.atualizar(vault=vault)
    assert not instalacao.pasta.exists()


def test_recuperador_roda_fora_do_pacote(tmp_path):
    fonte = Path(g.__file__).resolve()
    resultado = subprocess.run([__import__("sys").executable, "-I", str(fonte), "--help"], cwd=tmp_path, capture_output=True)
    assert resultado.returncode == 0
    assert b"--aplicativo" in resultado.stdout


def test_dependencias_preparam_fora_do_ambiente_em_uso_e_aplicam_offline(tmp_path, monkeypatch):
    deps = g.Dependencias(tmp_path / "app", "uv", tmp_path / "copias")
    chamadas = []
    monkeypatch.setattr(deps, "sincronizar", lambda ambiente, **opcoes: chamadas.append((ambiente, opcoes)))
    deps.preparar()
    if os.name == "nt":
        assert Path(chamadas[0][0]["UV_PROJECT_ENVIRONMENT"]).parent == deps.pasta
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
