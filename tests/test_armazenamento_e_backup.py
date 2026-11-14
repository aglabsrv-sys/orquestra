"""Fronteiras reais: concorrência de processos, bytes e snapshots Git restauráveis."""

from __future__ import annotations

import plistlib
import os
import json
import shlex
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from orquestra import armazenamento as ar, autostart, backup, config, doctor
from orquestra import preparo
from orquestra.notas import FrontmatterInvalido, gravar_nota, ler_nota


@pytest.fixture(autouse=True)
def casa_isolada(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path_factory.mktemp("armazenamento-estado-local-")))


def test_criar_exclusivo_nao_sobrescreve_e_nao_deixa_temporarios(tmp_path):
    nota = tmp_path / "nota.md"
    ar.gravar_bytes(nota, b"primeiro", criar=True)
    with pytest.raises(FileExistsError):
        ar.gravar_bytes(nota, b"segundo", criar=True)
    assert nota.read_bytes() == b"primeiro"
    assert not list(tmp_path.glob("*.orq-tmp"))


def test_update_exige_precondicao_e_nao_ressuscita_removida(tmp_path):
    nota = tmp_path / "nota.md"
    nota.write_bytes(b"antiga")
    with pytest.raises(ar.ConflitoDeEscrita):
        ar.gravar_bytes(nota, b"nova")
    nota.unlink()
    with pytest.raises(ar.ConflitoDeEscrita):
        ar.gravar_bytes(nota, b"nova", esperado=b"antiga")
    assert not nota.exists()


def test_duas_escritas_processos_reais_so_uma_vence(tmp_path):
    nota = tmp_path / "nota.md"
    nota.write_bytes(b"original")
    porta = tmp_path / "pode-gravar"
    codigo = """
import sys,time
from pathlib import Path
from orquestra.armazenamento import gravar_bytes, ConflitoDeEscrita
nota,porta=Path(sys.argv[1]),Path(sys.argv[2])
limite=time.monotonic()+10
while not porta.exists():
    if time.monotonic()>limite: raise RuntimeError('barreira nao liberada')
    time.sleep(.01)
try:
    gravar_bytes(nota,sys.argv[3].encode(),esperado=b'original')
    print('feito')
except ConflitoDeEscrita:
    print('conflito')
"""
    processos = [subprocess.Popen([sys.executable, "-c", codigo, str(nota), str(porta), valor],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for valor in ("A", "B")]
    try:
        porta.touch()
        resultados = [p.communicate(timeout=20) for p in processos]
    finally:
        for p in processos:
            if p.poll() is None:
                p.kill()
                p.wait()
    assert all(p.returncode == 0 for p in processos), resultados
    assert sorted(saida.strip() for saida, _ in resultados) == ["conflito", "feito"]
    assert nota.read_bytes() in (b"A", b"B")


def test_read_modify_write_serializado_entre_processos(tmp_path):
    estado = tmp_path / "contador"
    estado.write_bytes(b"0")
    codigo = """
import sys,time
from pathlib import Path
from orquestra.armazenamento import atualizar_bytes
def incrementar(antes):
    time.sleep(.015)
    return str(int(antes)+1).encode()
for _ in range(8): atualizar_bytes(Path(sys.argv[1]),incrementar,backup=False)
"""
    processos = [subprocess.Popen([sys.executable, "-c", codigo, str(estado)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    try:
        resultados = [p.communicate(timeout=20) for p in processos]
    finally:
        for p in processos:
            if p.poll() is None:
                p.kill()
                p.wait()
    assert all(p.returncode == 0 for p in processos), resultados
    assert estado.read_bytes() == b"16"


def test_edicao_externa_na_ultima_janela_fica_na_recuperacao(tmp_path, monkeypatch):
    nota = tmp_path / "nota.md"
    nota.write_bytes(b"original")
    real = ar._trocar_com_captura
    def interferir(temporario, destino):
        destino.write_bytes(b"edicao externa depois do ultimo check")
        return real(temporario, destino)
    monkeypatch.setattr(ar, "_trocar_com_captura", interferir)
    with pytest.raises(ar.ConflitoDeEscrita):
        ar.gravar_bytes(nota, b"proposta", esperado=b"original")
    recuperacoes = ar.listar_recuperacoes(nota)
    anteriores = [ar.ler_recuperacao(nota, r["id"]) for r in recuperacoes if r["tem_anterior"]]
    assert b"original" in anteriores
    assert b"edicao externa depois do ultimo check" in anteriores
    assert nota.read_bytes() == b"proposta"
    assert not list(tmp_path.glob("*.orq-tmp"))


def test_criacao_concorrente_no_instante_da_publicacao_nao_substitui(tmp_path, monkeypatch):
    nota = tmp_path / "nota.md"
    real = ar._renomear_exclusivo
    def interferir(origem, destino):
        Path(destino).write_bytes(b"criada por outro programa")
        return real(origem, destino)
    monkeypatch.setattr(ar, "_renomear_exclusivo", interferir)
    with pytest.raises(FileExistsError):
        ar.gravar_bytes(nota, b"proposta", criar=True)
    assert nota.read_bytes() == b"criada por outro programa"


def test_mover_recusa_colisao_e_preserva_arquivo_efetivamente_movido(tmp_path, monkeypatch):
    origem, destino = tmp_path / "origem.md", tmp_path / "arquivo" / "nota.md"
    origem.write_bytes(b"original")
    destino.parent.mkdir()
    destino.write_bytes(b"preexistente")
    with pytest.raises(FileExistsError):
        ar.mover_seguro(origem, destino, esperado=b"original")
    assert origem.read_bytes() == b"original"
    assert destino.read_bytes() == b"preexistente"
    destino.unlink()
    real = ar._renomear_exclusivo
    def interferir(inicio, fim):
        inicio.write_bytes(b"outra edicao")
        real(inicio, fim)
    monkeypatch.setattr(ar, "_renomear_exclusivo", interferir)
    with pytest.raises(ar.ConflitoDeEscrita):
        ar.mover_seguro(origem, destino, esperado=b"original")
    assert destino.read_bytes() == b"outra edicao"
    assert any(ar.ler_recuperacao(destino, r["id"]) == b"outra edicao" for r in ar.listar_recuperacoes(destino))


@pytest.mark.parametrize("bruto", [
    b"\xef\xbb\xbf---\r\n# comentario sem campos\r\n---\r\ncorpo\r\n",
    b"---\n# comentario sem campos\n...\ncorpo\n",
    b"\xef\xbb\xbfsem frontmatter\r\nsegunda linha\n",
    b"---\nstatus: antigo\n...",
])
def test_roundtrip_sem_edicao_preserva_bytes_e_mtime(tmp_path, bruto):
    caminho = tmp_path / "nota.md"
    caminho.write_bytes(bruto)
    antes = caminho.stat().st_mtime_ns
    nota = ler_nota(caminho, tmp_path)
    gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_bytes() == bruto
    assert caminho.stat().st_mtime_ns == antes


def test_comentario_sem_campos_e_bom_sobrevivem_edicao_de_corpo(tmp_path):
    caminho = tmp_path / "nota.md"
    caminho.write_bytes(b"\xef\xbb\xbf---\r\n# comentario\r\n---\r\ncorpo\r\n")
    nota = ler_nota(caminho, tmp_path)
    nota.corpo = "novo\n"
    gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_bytes() == b"\xef\xbb\xbf---\r\n# comentario\r\n---\r\nnovo\r\n"


def test_editar_metadata_preserva_bytes_do_corpo_com_quebras_mistas(tmp_path):
    caminho = tmp_path / "nota.md"
    corpo = b"primeira\r\nsegunda\nterceira\r\n"
    caminho.write_bytes(b"\xef\xbb\xbf---\nstatus: antes\n---\n" + corpo)
    nota = ler_nota(caminho, tmp_path)
    nota.meta["status"] = "depois"
    gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_bytes() == b"\xef\xbb\xbf---\nstatus: depois\n---\n" + corpo


def test_editar_corpo_preserva_cabecalho_com_quebras_mistas(tmp_path):
    caminho = tmp_path / "nota.md"
    cabecalho = b"---\r\n# comentario\nstatus: antes\r\n...\n"
    caminho.write_bytes(cabecalho + b"corpo antigo\n")
    nota = ler_nota(caminho, tmp_path)
    nota.corpo = "corpo novo\n"
    gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_bytes() == cabecalho + b"corpo novo\n"


def test_adicionar_campos_preserva_comentario_de_frontmatter_vazio(tmp_path):
    caminho = tmp_path / "nota.md"
    caminho.write_bytes(b"---\n# comentario original\n---\ncorpo\n")
    nota = ler_nota(caminho, tmp_path)
    for valor in ("um", "dois"):
        nota.meta["campo"] = valor
        gravar_nota(nota, versao_esperada=nota.versao)
        assert "# comentario original" in caminho.read_text(encoding="utf-8")
    assert ler_nota(caminho, tmp_path).campo("campo") == "dois"


@pytest.mark.parametrize("bruto", [b"---\nstatus: antigo\n---\nbyte \xe9\n", b"---\nstatus: nao fechado\n"])
def test_encoding_ou_delimitador_invalido_travam_sem_alterar(tmp_path, bruto):
    caminho = tmp_path / "nota.md"
    caminho.write_bytes(bruto)
    nota = ler_nota(caminho, tmp_path)
    assert nota.erro
    nota.meta["status"] = "novo"
    with pytest.raises(FrontmatterInvalido):
        gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_bytes() == bruto


def test_fastpath_indice_equivale_na_leitura_e_nao_pode_gravar(tmp_path):
    caminho = tmp_path / "nota.md"
    caminho.write_text('---\ntitulo: "Título"\ndata: 2026-11-11\nfeito: true\ntags: [um, dois]\n---\n# Corpo\n', encoding="utf-8")
    normal, indice = ler_nota(caminho, tmp_path), ler_nota(caminho, tmp_path, somente_indice=True)
    assert (indice.campos(), indice.corpo, indice.versao, indice.erro, indice.titulo) == (
        normal.campos(), normal.corpo, normal.versao, normal.erro, normal.titulo)
    assert indice._original is None and not indice._meta_original
    with pytest.raises(FrontmatterInvalido, match="índice"):
        gravar_nota(indice, versao_esperada=indice.versao)


def test_autoalias_yaml_trava_sem_deixar_estrutura_recursiva(tmp_path):
    caminho = tmp_path / "nota.md"
    bruto = b"---\na: &a [*a]\n---\ncorpo\n"
    caminho.write_bytes(bruto)
    nota = ler_nota(caminho, tmp_path)
    assert nota.erro and "circulares" in nota.erro
    assert nota.campos() == {}
    with pytest.raises(FrontmatterInvalido):
        gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_bytes() == bruto


@pytest.mark.parametrize("valor", ["a" * (257 * 1024), float("nan"), list(range(10001))])
def test_escrita_recusa_metadata_que_reader_nao_conseguiria_reabrir(tmp_path, valor):
    caminho = tmp_path / "nota.md"
    original = b"---\nstatus: original\n---\ncorpo\n"
    caminho.write_bytes(original)
    nota = ler_nota(caminho, tmp_path)
    nota.meta["campo"] = valor
    with pytest.raises(FrontmatterInvalido):
        gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_bytes() == original


@pytest.mark.parametrize("frontmatter", [
    "decimal: 052\noctal: 0o52\ntexto: yes\nbooleano: true\nnumero: 1e2\ndata: 2026-11-11\nhora: 12:34",
    'custom: !meutipo "valor"\ntexto: !!str 42\nconjunto: !!set {um: null, dois: null}',
    'base: &base {status: fazendo, tags: [um, dois]}\nregistro: {<<: *base, status: feito}',
    'tags: &tags [um, dois]\nrepetidas: *tags',
    'status: um\nstatus: dois',
    'numero: .nan',
])
def test_leitor_seguro_e_roundtrip_concordam_nas_extensoes_yaml(tmp_path, frontmatter):
    caminho = tmp_path / "nota.md"
    caminho.write_text("---\n" + frontmatter + "\n---\ncorpo\n", encoding="utf-8")
    normal, indice = ler_nota(caminho, tmp_path), ler_nota(caminho, tmp_path, somente_indice=True)
    assert (indice.campos(), indice.corpo, indice.versao, bool(indice.erro), indice.titulo) == (
        normal.campos(), normal.corpo, normal.versao, bool(normal.erro), normal.titulo)


def test_leitor_seguro_equivale_ao_roundtrip_em_todas_notas_do_catalogo():
    for caminho in preparo.CATALOGO.rglob("*.md"):
        normal = ler_nota(caminho, preparo.CATALOGO)
        indice = ler_nota(caminho, preparo.CATALOGO, somente_indice=True)
        assert (indice.campos(), indice.corpo, indice.versao, bool(indice.erro), indice.titulo) == (
            normal.campos(), normal.corpo, normal.versao, bool(normal.erro), normal.titulo), caminho


def test_config_detecta_conflito_preserva_comentario_e_recusa_raiz_lista(tmp_path):
    caminho = tmp_path / "config.yaml"
    caminho.write_bytes(b"\xef\xbb\xbf# comentario\r\n")
    mapa = config.ler_yaml(caminho)
    mapa["nome"] = "Novo"
    config.gravar_yaml(caminho, mapa)
    assert caminho.read_bytes().startswith(b"\xef\xbb\xbf# comentario\r\n")
    outro = config.ler_yaml(caminho)
    caminho.write_text("nome: Externo\n", encoding="utf-8")
    outro["nome"] = "Meu"
    with pytest.raises(ar.ConflitoDeEscrita):
        config.gravar_yaml(caminho, outro)
    assert "Externo" in caminho.read_text(encoding="utf-8")
    caminho.write_text("[um, dois]\n", encoding="utf-8")
    with pytest.raises(config.ConfigInvalida):
        config.ler_yaml(caminho)


@pytest.mark.parametrize("texto", ["porta: 0", "porta: 65536", "porta: true", "backup: []", "dock: 12",
                                         "backup: {push: 'false'}", "backup: {push_as: '26:00'}"])
def test_config_painel_rejeita_tipos_e_portas_invalidos(tmp_path, texto):
    (tmp_path / "orquestra.yaml").write_text(texto, encoding="utf-8")
    with pytest.raises(config.ConfigInvalida):
        config.ler_config_painel(tmp_path)


@pytest.fixture
def repo(tmp_path):
    if not backup.git_disponivel():
        pytest.skip("Git indisponível")
    pasta = tmp_path / "vault"
    pasta.mkdir()
    assert backup.iniciar(pasta)
    for chave, valor in (("user.name", "Teste"), ("user.email", "teste@localhost"), ("core.autocrlf", "false")):
        assert backup.git(pasta, "config", chave, valor).returncode == 0
    return pasta


def aprovar(repo):
    backup.autorizar(repo, backup.resumo(repo)["assinatura"])


def test_git_snapshot_restauro_preservam_staging_head_e_bytes(repo):
    nota = repo / "nota.md"
    nota.write_bytes(b"primeira\r\n")
    assert backup.git(repo, "add", "--", ".").returncode == 0
    assert backup.git(repo, "commit", "-m", "commit do usuario").returncode == 0
    head = backup.git(repo, "rev-parse", "HEAD").stdout
    nota.write_bytes(b"staging\r\n")
    assert backup.git(repo, "add", "nota.md").returncode == 0
    nota.write_bytes(b"trabalho posterior\r\n")
    (repo / "nova.md").write_bytes("acentos: ação\r\n".encode())
    indice = (repo / ".git" / "index").read_bytes()
    aprovar(repo)
    assert backup.commit(repo) == "feito"
    assert (repo / ".git" / "index").read_bytes() == indice
    assert backup.git(repo, "rev-parse", "HEAD").stdout == head
    assert backup.git(repo, "show", ":nota.md", texto=False).stdout == b"staging\r\n"
    assert backup.git(repo, "show", backup.REF_BACKUP + ":nota.md", texto=False).stdout == b"trabalho posterior\r\n"
    assert backup.git(repo, "rev-list", "--parents", "-1", backup.REF_BACKUP).stdout.split() == [
        backup.git(repo, "rev-parse", backup.REF_BACKUP).stdout.strip()
    ], "primeiro snapshot não deve herdar histórico anterior do usuário"
    assert backup.commit(repo) == "nada"
    restaurada = backup.restaurar_arquivo(repo, "nova.md", esperado=None, destino="copia.md")
    assert restaurada.read_bytes() == "acentos: ação\r\n".encode()


def test_git_ignores_mesclados_idempotentes_e_segredo_rastreado_bloqueia(repo):
    ignorar = repo / ".gitignore"
    ignorar.write_text("*.meu\n", encoding="utf-8")
    backup.iniciar(repo)
    primeiro = ignorar.read_bytes()
    backup.iniciar(repo)
    assert ignorar.read_bytes() == primeiro
    assert "*.meu" in primeiro.decode()
    segredo = repo / ".env.local"
    segredo.write_text("TOKEN=marcador-sintetico\n", encoding="utf-8")
    assert backup.git(repo, "check-ignore", ".env.local").returncode == 0
    assert backup.git(repo, "add", "-f", ".env.local").returncode == 0
    aprovar(repo)
    assert backup.commit(repo).startswith("erro: Há arquivos de segredo")


def test_backup_independente_funciona_sem_usar_index_lock_do_usuario(repo):
    aprovar(repo)
    (repo / "nota.md").write_bytes(b"precisa de backup")
    lock = repo / ".git" / "index.lock"
    lock.write_bytes(b"outro comando do usuario")
    assert backup.commit(repo) == "feito"
    assert lock.read_bytes() == b"outro comando do usuario"
    assert backup.git(repo, "show", backup.REF_BACKUP + ":nota.md", texto=False).stdout == b"precisa de backup"


def test_backup_falha_de_indice_nao_vira_nada(repo, monkeypatch):
    aprovar(repo)
    (repo / "nota.md").write_bytes(b"nova")
    real = backup.git
    def falhar(vault, *args, **kwargs):
        if args and args[0] == "update-index":
            return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"erro sintetico")
        return real(vault, *args, **kwargs)
    monkeypatch.setattr(backup, "git", falhar)
    assert backup.commit(repo).startswith("erro:")
    assert real(repo, "rev-parse", "--verify", backup.REF_BACKUP).returncode != 0


def test_backup_recusa_config_nao_autorizada_e_nao_executa_filtro(repo, tmp_path):
    marcador = tmp_path / "filtro-executou"
    assert backup.git(repo, "config", "filter.teste.clean", f'python -c "open({str(marcador)!r}, \'w\').write(\'executou\')"').returncode == 0
    (repo / ".gitattributes").write_text("*.md filter=teste\n", encoding="utf-8")
    (repo / "nota.md").write_bytes(b"bytes originais\r\n")
    assert backup.commit(repo).startswith("erro:")
    assert not marcador.exists()
    aprovar(repo)
    assert backup.commit(repo) == "feito"
    assert not marcador.exists(), "snapshot deve usar --no-filters mesmo após autorização"
    assert backup.git(repo, "show", backup.REF_BACKUP + ":nota.md", texto=False).stdout == b"bytes originais\r\n"
    (repo / ".gitattributes").write_text("*.md filter=outro\n", encoding="utf-8")
    assert not backup.resumo(repo)["confiavel"]


def test_git_push_real_para_bare_exige_novo_aceite_e_nao_altera_upstream(repo, tmp_path):
    (repo / "nota.md").write_bytes(b"snapshot remoto")
    aprovar(repo)
    assert backup.commit(repo) == "feito"
    remoto = tmp_path / "remoto.git"
    assert subprocess.run(["git", "init", "--bare", str(remoto)], capture_output=True).returncode == 0
    assert backup.git(repo, "remote", "add", "origin", str(remoto)).returncode == 0
    assert backup.push(repo).startswith("erro:")
    aprovar(repo)
    assert backup.push(repo) == "feito"
    r = subprocess.run(["git", f"--git-dir={remoto}", "show", f"refs/heads/{backup.BRANCH_REMOTO}:nota.md"], capture_output=True)
    assert r.returncode == 0 and r.stdout == b"snapshot remoto"
    assert backup.git(repo, "config", "branch.main.remote").returncode == 1


def _historico_com_segredo(repo, nome=".env"):
    caminho = repo / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"TOKEN=valor-sintetico-sem-acesso-externo\n")
    assert backup.git(repo, "add", "-f", "--", nome).returncode == 0
    assert backup.git(repo, "commit", "-m", "Segredo fictício antigo").returncode == 0
    assert backup.git(repo, "rm", "--", nome).returncode == 0
    assert backup.git(repo, "commit", "-m", "Remove segredo fictício").returncode == 0
    return backup.git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.mark.parametrize("nome", [".env", "sub/.env.production", ".ENV.local", "chave.pem", "segredos/secrets.json"])
def test_historico_backup_contaminado_bloqueia_snapshot_e_envio(repo, tmp_path, nome):
    revisao = _historico_com_segredo(repo, nome)
    assert backup.git(repo, "update-ref", backup.REF_BACKUP, revisao).returncode == 0
    remoto = tmp_path / "remoto.git"
    assert subprocess.run(["git", "init", "--bare", str(remoto)], capture_output=True).returncode == 0
    assert backup.git(repo, "remote", "add", "origin", str(remoto)).returncode == 0
    aprovar(repo)
    assert "histórico do backup contém arquivos de segredo" in backup.commit(repo)
    assert "histórico do backup contém arquivos de segredo" in backup.push(repo)
    assert backup.git(repo, "rev-parse", backup.REF_BACKUP).stdout.strip() == revisao
    assert subprocess.run(["git", f"--git-dir={remoto}", "show-ref"], capture_output=True).returncode == 1


def test_historico_do_usuario_nao_e_herdado_no_primeiro_snapshot(repo):
    _historico_com_segredo(repo)
    (repo / "nota.md").write_bytes(b"nota sem segredo")
    aprovar(repo)
    assert backup.commit(repo) == "feito"
    assert len(backup.git(repo, "rev-list", backup.REF_BACKUP).stdout.splitlines()) == 1
    backup._conferir_historico(repo, backup.git(repo, "rev-parse", backup.REF_BACKUP).stdout.strip())


def test_historico_confere_tambem_o_segundo_pai_de_merge(repo):
    (repo / "nota.md").write_bytes(b"raiz")
    assert backup.git(repo, "add", ".").returncode == 0
    assert backup.git(repo, "commit", "-m", "Raiz limpa").returncode == 0
    raiz = backup.git(repo, "rev-parse", "HEAD").stdout.strip()
    assert backup.git(repo, "checkout", "-b", "ramo-com-segredo").returncode == 0
    outro = _historico_com_segredo(repo)
    arvore = backup.git(repo, "rev-parse", raiz + "^{tree}").stdout.strip()
    merge = backup.git(repo, "commit-tree", arvore, "-p", raiz, "-p", outro, "-m", "Merge com árvore limpa").stdout.strip()
    assert backup.git(repo, "update-ref", backup.REF_BACKUP, merge).returncode == 0
    aprovar(repo)
    assert "histórico do backup contém arquivos de segredo" in backup.commit(repo)


def test_envio_fixa_hash_validado_mesmo_se_referencia_mudar(repo, tmp_path, monkeypatch):
    (repo / "nota.md").write_bytes(b"snapshot seguro")
    aprovar(repo)
    assert backup.commit(repo) == "feito"
    seguro = backup.git(repo, "rev-parse", backup.REF_BACKUP).stdout.strip()
    contaminado = _historico_com_segredo(repo)
    remoto = tmp_path / "remoto.git"
    assert subprocess.run(["git", "init", "--bare", str(remoto)], capture_output=True).returncode == 0
    assert backup.git(repo, "remote", "add", "origin", str(remoto)).returncode == 0
    aprovar(repo)
    real = backup.git

    def trocar_antes_de_enviar(vault, *args, **kwargs):
        if args[0] == "push":
            assert real(repo, "update-ref", backup.REF_BACKUP, contaminado).returncode == 0
            assert real(repo, "update-ref", "refs/heads/" + seguro, contaminado).returncode == 0
        return real(vault, *args, **kwargs)

    monkeypatch.setattr(backup, "git", trocar_antes_de_enviar)
    assert backup.push(repo) == "feito"
    enviado = subprocess.run(["git", f"--git-dir={remoto}", "rev-parse", backup.BRANCH_REMOTO], capture_output=True)
    assert enviado.returncode == 0 and enviado.stdout.strip().decode() == seguro


@pytest.mark.parametrize("falha", ["git", "saida_incompleta"])
def test_envio_nao_prossegue_se_historico_nao_puder_ser_verificado(repo, monkeypatch, falha):
    (repo / "nota.md").write_bytes(b"snapshot seguro")
    aprovar(repo)
    assert backup.commit(repo) == "feito"
    real = backup.git

    def falhar(vault, *args, **kwargs):
        assert args[0] != "push", "não deve iniciar envio depois de uma verificação incompleta"
        if args[0] == "log":
            return subprocess.CompletedProcess(args, 1 if falha == "git" else 0, stdout=b"incompleto", stderr=b"")
        return real(vault, *args, **kwargs)

    monkeypatch.setattr(backup, "git", falhar)
    assert backup.push(repo).startswith("erro:")


def test_envio_e_restauracao_em_clone_descartavel_preservam_bytes_sem_env(repo, tmp_path):
    from orquestra import segredos

    original = "\ufeffNota sintética com acentuação.\r\n".encode("utf-8")
    (repo / "nota.md").write_bytes(original)
    (repo / ".env").write_bytes(b"TOKEN=segredo-ficticio-do-vault\n")
    (repo / ".env.example").write_bytes(b"TOKEN=\n")
    segredos.salvar(repo, "CHAVE_SINTETICA", "segredo-ficticio-local")
    aprovar(repo)
    assert backup.commit(repo) == "feito"
    primeira = backup.git(repo, "rev-parse", backup.REF_BACKUP).stdout.strip()
    (repo / "nota.md").write_bytes(b"versao posterior")
    assert backup.commit(repo) == "feito"
    remoto = tmp_path / "remoto.git"
    assert subprocess.run(["git", "init", "--bare", str(remoto)], capture_output=True).returncode == 0
    assert backup.git(repo, "remote", "add", "origin", str(remoto)).returncode == 0
    aprovar(repo)
    assert backup.push(repo) == "feito"
    clone = tmp_path / "restauracao"
    assert subprocess.run(["git", "clone", "--branch", backup.BRANCH_REMOTO, str(remoto), str(clone)], capture_output=True).returncode == 0
    assert (clone / "nota.md").read_bytes() == b"versao posterior"
    assert not (clone / ".env").exists()
    assert not (clone / ".env.local").exists()
    assert (clone / ".env.example").read_text(encoding="utf-8") == "TOKEN=\n"
    backup._conferir_historico(clone, "HEAD")
    aprovar(clone)
    copia = backup.restaurar_arquivo(clone, "nota.md", revisao=primeira, esperado=None, destino="recuperada.md")
    assert copia.read_bytes() == original
    assert (clone / "nota.md").read_bytes() == b"versao posterior"


def _vincular_metadado(origem: Path, externo: Path) -> None:
    origem.parent.mkdir(parents=True, exist_ok=True)
    if origem.is_file():
        origem.unlink()
    assert not origem.exists()
    if os.name == "nt":
        # Junction funciona sem administrador, inclusive nos Windows em que criar
        # um symlink de arquivo exige Developer Mode. Git nunca deve chegar a lê-la.
        r = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(origem), str(externo)], capture_output=True)
        assert r.returncode == 0, "Não foi possível preparar junction sintética"
    else:
        origem.symlink_to(externo, target_is_directory=externo.is_dir())


@pytest.mark.parametrize("relativo", ["refs/orquestra", "objects/aa", "index", "info/exclude"])
def test_git_recusa_metadata_vinculada_antes_de_iniciar_subprocesso(repo, tmp_path, monkeypatch, relativo):
    externo = tmp_path / "externo"
    externo.mkdir()
    marcador = externo / "sentinela"
    marcador.write_bytes(b"conteudo externo nao pode ser lido ou alterado")
    _vincular_metadado(repo / ".git" / relativo, externo)
    leitura_real = Path.read_bytes
    def ler_somente_interno(caminho):
        if caminho.resolve().is_relative_to(externo):
            pytest.fail("Nenhum conteúdo de metadado externo pode ser lido")
        return leitura_real(caminho)
    monkeypatch.setattr(Path, "read_bytes", ler_somente_interno)
    monkeypatch.setattr(backup.subprocess, "run", lambda *a, **k: pytest.fail("Git não pode iniciar com metadata vinculada"))
    with pytest.raises(ValueError):
        backup.git(repo, "update-ref", backup.REF_BACKUP, "a" * 40)
    assert not backup.resumo(repo)["confiavel"]
    assert leitura_real(marcador) == b"conteudo externo nao pode ser lido ou alterado"
    assert sorted(p.name for p in externo.iterdir()) == ["sentinela"]


@pytest.mark.parametrize("relativo", ["objects/info/alternates", "objects/info/http-alternates", "commondir", "config.worktree"])
def test_git_recusa_redirecionadores_de_metadados_sem_executar_ou_ler_destino(repo, tmp_path, monkeypatch, relativo):
    externo = tmp_path / "objetos-externos"
    externo.mkdir()
    redirecionador = repo / ".git" / relativo
    redirecionador.parent.mkdir(parents=True, exist_ok=True)
    redirecionador.write_text(str(externo), encoding="utf-8")
    leitura_real = Path.read_bytes
    def ler(caminho):
        if caminho == redirecionador:
            pytest.fail("O tamanho basta para recusar um redirector não vazio")
        return leitura_real(caminho)
    monkeypatch.setattr(Path, "read_bytes", ler)
    monkeypatch.setattr(backup.subprocess, "run", lambda *a, **k: pytest.fail("Git não pode iniciar com alternates/worktree"))
    with pytest.raises(ValueError):
        backup.git(repo, "status", "--porcelain")
    assert list(externo.iterdir()) == []


def test_git_cache_da_operacao_nao_reutiliza_decisao_apos_junction(repo, tmp_path, monkeypatch):
    externo = tmp_path / "refs-externas"
    externo.mkdir()
    preparado = tmp_path / "junction-preparada"
    _vincular_metadado(preparado, externo)
    with backup._operacao_git(repo):
        backup.git(repo, "rev-parse", "--verify", "HEAD")
        preparado.rename(repo / ".git" / "refs" / "orquestra")
        monkeypatch.setattr(backup.subprocess, "run", lambda *a, **k: pytest.fail("A decisão antiga não autoriza uma junction nova"))
        with pytest.raises(ValueError):
            backup.git(repo, "update-ref", backup.REF_BACKUP, "a" * 40)
    assert list(externo.iterdir()) == []


def test_git_recheca_ref_critica_depois_da_varredura(repo, tmp_path, monkeypatch):
    externo = tmp_path / "refs-externas"
    externo.mkdir()
    preparado = tmp_path / "junction-preparada"
    _vincular_metadado(preparado, externo)
    real = backup._validar_arvore_git
    def trocar(vault, **kwargs):
        resultado = real(vault, **kwargs)
        preparado.rename(repo / ".git" / "refs" / "orquestra")
        return resultado
    monkeypatch.setattr(backup, "_validar_arvore_git", trocar)
    monkeypatch.setattr(backup.subprocess, "run", lambda *a, **k: pytest.fail("A referência precisa ser revalidada antes do Git"))
    with pytest.raises(ValueError):
        backup.git(repo, "update-ref", backup.REF_BACKUP, "a" * 40)
    assert list(externo.iterdir()) == []


def test_git_recusa_arquivo_git_de_worktree_e_nao_muda_ignore(tmp_path, monkeypatch):
    repo = tmp_path / "vault"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: ../externo\n", encoding="utf-8")
    (repo / ".gitignore").write_bytes(b"regra original\n")
    monkeypatch.setattr(backup.subprocess, "run", lambda *a, **k: pytest.fail("Git vinculado não deve ser iniciado"))
    with pytest.raises(ValueError):
        backup.iniciar(repo)
    assert (repo / ".gitignore").read_bytes() == b"regra original\n"


def test_git_ambiente_minimo_exclui_segredos_e_controles_herdados(repo, monkeypatch):
    for nome in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "YOUTUBE_API_KEY", "DATABASE_URL", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(nome, "marcador-sintetico")
    monkeypatch.setenv("GIT_SSH_COMMAND", "comando que nao deve ser herdado")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "3")
    monkeypatch.setenv("SSH_AUTH_SOCK", "socket-do-agente-ssh")
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.exemplo:443")
    observado = {}
    def observar(args, **kwargs):
        observado.update(kwargs["env"])
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    monkeypatch.setattr(backup.subprocess, "run", observar)
    backup.git(repo, "status", "--porcelain")
    assert not any(nome in observado for nome in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "YOUTUBE_API_KEY", "DATABASE_URL", "AWS_SECRET_ACCESS_KEY", "GIT_SSH_COMMAND", "GIT_CONFIG_COUNT"))
    assert observado["SSH_AUTH_SOCK"] == "socket-do-agente-ssh"
    assert observado["HTTPS_PROXY"] == "https://proxy.exemplo:443"
    assert observado["GIT_NO_LAZY_FETCH"] == observado["GIT_NO_REPLACE_OBJECTS"] == "1"


@pytest.mark.parametrize("protocolo,host,autenticado", [
    ("https", "github.com", True),
    ("https", "outro.example.test", False),
    ("https", "github.com.example.test", False),
    ("http", "github.com", False),
])
def test_push_usa_so_helper_oficial_no_host_github_sem_config_global(repo, monkeypatch, protocolo, host, autenticado):
    # O envio é substituído por credential fill local: não abre rede nem consulta
    # a conta real. O Python representa um gh de teste e só escreve dados fictícios.
    (repo / "auth").write_text(
        "import sys\n"
        "assert sys.argv[1:] == ['git-credential', 'get']\n"
        "assert 'host=github.com' in sys.stdin.read()\n"
        "print('username=usuario-teste\\npassword=token-sintetico\\n')\n",
        encoding="utf-8",
    )
    assert backup.git(repo, "config", "credential.helper", "!exit 99").returncode == 0
    executar = subprocess.run
    localizar = backup.shutil.which
    monkeypatch.setattr(backup.shutil, "which", lambda nome: sys.executable if nome == "gh" else localizar(nome))

    def preencher(args, **kwargs):
        assert args[-3:] == ["push", "origin", "ref-teste"]
        assert kwargs["env"]["GIT_CONFIG_GLOBAL"] == os.devnull
        assert "credential.helper=" in args and "core.fsmonitor=false" in args
        kwargs["input"] = f"protocol={protocolo}\nhost={host}\n\n"
        return executar([*args[:-3], "credential", "fill"], **kwargs)

    monkeypatch.setattr(backup.subprocess, "run", preencher)
    resultado = backup.git(repo, "push", "origin", "ref-teste")
    assert (resultado.returncode == 0) is autenticado
    assert ("password=token-sintetico" in resultado.stdout) is autenticado


@pytest.mark.parametrize("endereco,esperado", [
    ("https://usuario-secreto:senha-secreta@github.com/org/repo.git?access_token=token-secreto#fragmento-secreto", "https://github.com/org/repo.git"),
    ("ssh://usuario-secreto:senha-secreta@[::1]:2222/org/repo.git?token=token-secreto#fragmento-secreto", "ssh://[::1]:2222/org/repo.git"),
    ("usuario-secreto:senha-secreta@github.com:org/repo.git?token=token-secreto#fragmento-secreto", "github.com:org/repo.git"),
    ("ext::comando senha-secreta?token=token-secreto", "[destino personalizado; consulte a configuração local]"),
    ("https://host:senha-secreta/repo.git", "[destino personalizado; consulte a configuração local]"),
])
def test_resumo_git_nao_exibe_credenciais_do_remoto_ou_pushurl(repo, endereco, esperado):
    backup.git(repo, "config", "remote.origin.url", endereco)
    backup.git(repo, "config", "remote.origin.pushurl", endereco)
    resumo = backup.resumo(repo)
    assert resumo["assinatura"]
    assert all(r["destino"] == esperado for r in resumo["remotos"])
    visivel = json.dumps(resumo, ensure_ascii=False)
    assert not any(valor in visivel for valor in ("usuario-secreto", "senha-secreta", "token-secreto", "fragmento-secreto"))
    backup.git(repo, "config", "remote.origin.url", endereco + "outro")
    assert backup.resumo(repo)["assinatura"] != resumo["assinatura"], "a assinatura usa os bytes reais, não o resumo redigido"


def test_doctor_preserva_arquivo_com_antigo_nome_fixo(tmp_path, monkeypatch):
    existente = tmp_path / ".orquestra-teste.orq-tmp"
    existente.write_bytes(b"conteudo preexistente")
    monkeypatch.setattr(doctor, "verificar_acesso", lambda porta: [])
    doctor.verificar_vault(tmp_path)
    assert existente.read_bytes() == b"conteudo preexistente"
    assert list(tmp_path.glob(".orquestra-teste-*.orq-tmp")) == []


def test_plist_mac_valido_com_metacaracteres_e_falha_launchctl(tmp_path, monkeypatch):
    # Simula somente o autostart: armazenamento precisa usar as primitivas do
    # sistema real, inclusive quando este teste de plist roda em Linux.
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="darwin", executable=sys.executable))
    monkeypatch.setattr(autostart, "_comando", lambda vault: ["/Python & teste/python", "-m", "orquestra", str(vault)])
    vault = tmp_path / 'P&D "acentos ação"'
    assert plistlib.loads(autostart._conteudo(vault).encode())["ProgramArguments"][-1] == str(vault)
    arquivo = tmp_path / "agente.plist"
    monkeypatch.setattr(autostart, "_arquivo", lambda: arquivo)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1))
    with pytest.raises(RuntimeError, match="não ativou"):
        autostart.executar("ativar", vault)
    assert arquivo.exists()
    with pytest.raises(RuntimeError, match="preservado"):
        autostart.executar("desativar", vault)
    assert arquivo.exists()


def test_desktop_linux_escapa_exec_sem_field_codes(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="linux", executable=sys.executable))
    partes = ["/path com espaço/python", "-m", "orquestra", 'P&D com "aspas" $variavel `cmd` 100% \\fim']
    monkeypatch.setattr(autostart, "_comando", lambda vault: partes)
    exec_linha = next(l[5:] for l in autostart._conteudo(tmp_path).splitlines() if l.startswith("Exec="))
    # Primeiro parser Desktop Entry desfaz \\; parser de argumentos desfaz aspas.
    decodificado = exec_linha.replace("\\\\", "\\")
    tokens = shlex.split(decodificado)
    # shlex não expande variáveis nem field codes; remove apenas escapes de shell.
    tokens = [t.replace("\\$", "$").replace("\\`", "`").replace("%%", "%") for t in tokens]
    assert tokens == partes
