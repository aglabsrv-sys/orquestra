"""Cotas, pausas e concorrência sem consumir serviços externos."""

import asyncio
import io
import json
import os
import runpy
import socket
import subprocess
import sys
import time
import types
import urllib.error
from email.utils import formatdate
from pathlib import Path

import pytest

from orquestra import automacoes, coletores, limites_coleta as limites


@pytest.fixture
def relogio(monkeypatch):
    agora = [1_700_000_000.0]
    monkeypatch.setattr(limites, "_agora", lambda: agora[0])
    monkeypatch.setattr(limites.time, "sleep", lambda segundos: agora.__setitem__(0, agora[0] + segundos))
    monkeypatch.setattr(limites, "_chamadas", 0)
    return agora


@pytest.mark.parametrize("definicao,config", [
    ("radar/youtube_api.py", {"termos": [str(i) for i in range(26)]}),
    ("radar/youtube_api.py", {"maximo_por_termo": 51}),
    ("radar/rss.py", {"feeds": [f"https://example.test/{i}" for i in range(51)]}),
    ("radar/youtube_rss.py", {"canais": ["@exemplo", " @EXEMPLO "]}),
    ("radar/rss.py", {"feeds": [f"https://example.test/{i}" for i in range(21)], "maximo_por_feed": 100}),
])
def test_configuracoes_excessivas_sao_recusadas_antes_de_gravar(painel, definicao, config):
    antes = (painel.vault / automacoes.ARQUIVO).read_bytes() if (painel.vault / automacoes.ARQUIVO).exists() else None
    with pytest.raises(ValueError):
        automacoes.criar(painel, definicao, "radar/itens", config)
    assert ((painel.vault / automacoes.ARQUIVO).read_bytes() if antes is not None else None) == antes
    if antes is None:
        assert not (painel.vault / automacoes.ARQUIVO).exists()


@pytest.mark.parametrize("definicao,intervalo", [("radar/rss.py", "1m"), ("radar/youtube_api.py", "1h")])
def test_intervalos_minimos_tambem_valem_na_api_de_criacao(painel, definicao, intervalo):
    with pytest.raises(ValueError, match="intervalo de pelo menos"):
        automacoes.criar(painel, definicao, "radar/itens", a_cada=intervalo)
    assert automacoes._regra("1h", None, "radar/rss.py") == ("1h", None)
    assert automacoes._regra("6h", None, "radar/youtube_api.py") == ("6h", None)
    assert automacoes._regra("1m", None, "tarefas/recorrentes.py") == ("1m", None)


def test_execucao_repetida_tem_espera_apos_terminar_inclusive_falhas(relogio):
    with pytest.raises(RuntimeError), limites.execucao("instancia"):
        raise RuntimeError("falha simulada")
    with pytest.raises(limites.LimiteColeta, match="30s"):
        with limites.execucao("instancia"):
            pytest.fail("Não deveria iniciar")
    relogio[0] += 30
    with limites.execucao("instancia"):
        pass


def test_limite_simultaneo_e_liberacao_apos_encerramento(relogio):
    with limites.execucao("a"), limites.execucao("b"):
        with pytest.raises(limites.LimiteColeta, match="duas coletas"):
            with limites.execucao("c"):
                pytest.fail("Não deveria iniciar")
        with pytest.raises(limites.LimiteColeta, match="ainda está rodando"):
            with limites.execucao("a"):
                pytest.fail("Não deveria iniciar")
    with limites.execucao("c"):
        pass


def test_cota_github_e_compartilhada_e_libera_no_prazo(relogio):
    for i in range(55):
        limites._reservar(f"https://api.github.com/repos/exemplo/{i}")
    assert relogio[0] == 1_700_000_054
    with pytest.raises(limites.LimiteColeta, match="cota local"):
        limites._reservar("https://api.github.com/repos/outra/pasta")
    relogio[0] += 3600
    assert limites._reservar("https://api.github.com/repos/exemplo/novo") == "github"


def test_buscas_youtube_compartilham_cota_diaria_entre_chaves(relogio):
    for i in range(100):
        limites._reservar(f"https://www.googleapis.com/youtube/v3/search?q={i}&key=segredo-{i}")
    with pytest.raises(limites.LimiteColeta, match="cota local"):
        limites._reservar("https://www.googleapis.com/youtube/v3/search?key=outra-chave")
    gravado = (limites._pasta() / "estado.json").read_text()
    assert "segredo" not in gravado and "googleapis" not in gravado and "key=" not in gravado
    # Estatísticas do canal têm orçamento separado das buscas.
    assert limites._reservar("https://www.googleapis.com/youtube/v3/channels") == "youtube-api"


@pytest.mark.parametrize("tipo", ["segundos", "data", "reset-github", "cota-youtube"])
def test_bloqueio_persiste_e_impede_novas_consultas(relogio, monkeypatch, tipo):
    url = "https://api.github.com/repos/exemplo/privado?key=segredo-ficticio"
    headers = {"Retry-After": "3600"}
    codigo, corpo = 429, b""
    if tipo == "data":
        headers = {"Retry-After": formatdate(relogio[0] + 3600, usegmt=True)}
    if tipo == "reset-github":
        codigo, headers = 403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(relogio[0] + 3600)}
    if tipo == "cota-youtube":
        codigo, headers, corpo = 403, {}, b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}'
        url = "https://www.googleapis.com/youtube/v3/search?key=segredo-ficticio"
    erro = urllib.error.HTTPError(url, codigo, "recusado", headers, io.BytesIO(corpo))
    chamadas = []

    class Opener:
        def open(self, *args, **kwargs):
            chamadas.append(True)
            raise erro

    monkeypatch.setattr(limites.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(limites.LimiteColeta, match="pediu uma pausa"):
        limites.baixar(url)
    # Outra instância/reabertura lê o mesmo arquivo; não chega ao transporte.
    with pytest.raises(limites.LimiteColeta, match="serviço está em pausa"):
        limites.baixar(url)
    assert len(chamadas) == 1
    gravado = (limites._pasta() / "estado.json").read_text()
    assert "segredo-ficticio" not in gravado and "privado" not in gravado
    assert json.loads(gravado)["servicos"][limites._servico(url)[0]]["ate"] >= relogio[0] + (86400 if tipo == "cota-youtube" else 3600)


def test_redirecionamentos_e_total_por_coleta_tambem_consumem_cota(relogio):
    handler = limites._Redirecionamento()
    req = limites.urllib.request.Request("https://example.test/feed")
    handler.redirect_request(req, None, 302, "mover", {}, "https://api.github.com/repos/exemplo/repo")
    assert limites._chamadas == 1
    monkey = limites._chamadas
    limites._chamadas = 120
    try:
        with pytest.raises(limites.LimiteColeta, match="120 consultas"):
            limites._reservar("https://outra.test/feed")
    finally:
        limites._chamadas = monkey


@pytest.mark.parametrize("pasta,script,config", [
    ("radar", "youtube_rss.py", {"canais": ["UC" + str(i) * 22 for i in range(3)]}),
    ("numeros", "github_repo.py", {"repositorios": [{"repo": f"exemplo/{i}"} for i in range(3)]}),
])
def test_bloqueio_interrompe_laco_das_fontes(relogio, monkeypatch, pasta, script, config):
    monkeypatch.setenv("ORQUESTRA_CONFIG", json.dumps(config))
    monkeypatch.setattr(limites.time, "sleep", lambda _: None)
    caminho = Path(coletores.__file__).parent / "catalogo" / pasta / "maquina" / "coletores"
    monkeypatch.setattr(socket, "getaddrinfo", socket.getaddrinfo)
    ajudante = runpy.run_path(str(caminho / "_comum.py"))
    fake = types.ModuleType("_comum")
    fake.__dict__.update(ajudante)
    monkeypatch.setitem(sys.modules, "_comum", fake)
    chamadas = []

    class Opener:
        def open(self, req, **kwargs):
            chamadas.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 429, "bloqueado", {"Retry-After": "3600"}, None)

    monkeypatch.setattr(limites.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(SystemExit, match="pediu uma pausa"):
        runpy.run_path(str(caminho / script), run_name="__main__")
    assert len(chamadas) == 1


def test_api_execucao_e_previa_compartilham_espera(cliente, monkeypatch):
    instancia = automacoes.criar(cliente.painel, "radar/rss.py", "radar/itens")
    automacoes.autorizar(cliente.painel, instancia["id"], instancia["confianca"]["assinatura"])
    chamadas = []

    def processo(*args, **kwargs):
        chamadas.append(True)
        return b"", b"", 0, ""

    monkeypatch.setattr(coletores, "_executar_processo", processo)
    assert cliente.post("/api/automacoes/rodar", json={"id": instancia["id"], "previa": True}).status_code == 200
    resposta = cliente.post("/api/automacoes/rodar", json={"id": instancia["id"]})
    assert resposta.status_code == 429
    assert "Aguarde" in resposta.json()["erro"] and len(chamadas) == 1


def test_configuracao_antiga_com_frequencia_alta_nao_acessa_rede(painel, monkeypatch):
    instancia = automacoes.criar(painel, "radar/rss.py", "radar/itens")
    # Simula uma configuração criada antes dos novos limites e autorizada localmente.
    automacoes._alterar(painel, lambda lista: lista[0].update(a_cada="1m"))
    publica = automacoes.listar(painel)[0]
    automacoes.autorizar(painel, instancia["id"], publica["confianca"]["assinatura"])
    monkeypatch.setattr(coletores, "_executar_limitado", lambda *a: pytest.fail("Não pode executar"))
    resultado = asyncio.run(automacoes.rodar(painel, instancia["id"]))
    assert not resultado["ok"] and "pelo menos 1h" in resultado["erro"]
    assert automacoes.listar(painel)[0]["a_cada"] == "1m"


def test_limite_simultaneo_entre_processos(tmp_path):
    codigo = '''
import sys,time
from pathlib import Path
from orquestra import limites_coleta as limites
pasta=Path(sys.argv[1]); ident=sys.argv[2]
try:
    with limites.execucao(ident):
        (pasta/(ident+'.ok')).touch()
        inicio=time.monotonic()
        while not (pasta/'liberar').exists() and time.monotonic()-inicio<20:
            time.sleep(.02)
except limites.LimiteColeta:
    (pasta/(ident+'.bloqueada')).touch()
'''
    processos = [subprocess.Popen([sys.executable, "-c", codigo, str(tmp_path), str(i)], env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(4)]
    try:
        prazo = time.monotonic() + 20
        while len(list(tmp_path.glob("*.ok"))) + len(list(tmp_path.glob("*.bloqueada"))) < 4 and time.monotonic() < prazo:
            time.sleep(0.05)
        assert len(list(tmp_path.glob("*.ok"))) == 2
        assert len(list(tmp_path.glob("*.bloqueada"))) == 2
    finally:
        (tmp_path / "liberar").touch()
        for processo in processos:
            stdout, stderr = processo.communicate(timeout=10)
            assert processo.returncode == 0, (stdout, stderr)


def test_registro_corrompido_nao_reinicia_as_cotas():
    (limites._pasta() / "estado.json").write_text("invalido")
    with pytest.raises(ValueError, match="registro local de limites está inválido"):
        limites._reservar("https://example.test")


def test_cota_global_abrange_hosts_diferentes(relogio):
    with limites._estado() as estado:
        estado["servicos"]["total"] = {"usada": relogio[0], "chamadas": [relogio[0]] * 1000}
    with pytest.raises(limites.LimiteColeta, match="cota total"):
        limites._reservar("https://uma-nova-fonte.test/feed")


def test_pausa_sem_header_cresce_e_erros_de_permissao_nao_pausam(relogio):
    url = "https://api.github.com/repos/exemplo/repo"
    erro = urllib.error.HTTPError(url, 429, "recusado", {}, None)
    for espera in (60, 120, 240):
        with pytest.raises(limites.LimiteColeta, match=f"Aguarde {espera}s"):
            limites._pausar(url, erro)
        relogio[0] += espera
    assert limites._pausar(url, urllib.error.HTTPError(url, 403, "sem permissao", {}, None)) is None


def test_reserva_abandonada_expira_sem_sobrescrever_reserva_nova(relogio):
    antiga = limites.execucao("mesma-instancia")
    antiga.__enter__()
    relogio[0] += 211
    with limites.execucao("mesma-instancia"):
        antiga.__exit__(None, None, None)
        with pytest.raises(limites.LimiteColeta, match="ainda está rodando"):
            with limites.execucao("mesma-instancia"):
                pytest.fail("A reserva nova ainda pertence ao segundo processo")


def test_runtime_do_snapshot_funciona_sem_instalacao_python_do_app(tmp_path):
    pasta = tmp_path / "snapshot"
    pasta.mkdir()
    comum = Path(coletores.__file__).parent / "catalogo/radar/maquina/coletores/_comum.py"
    (pasta / "_comum.py").write_bytes(comum.read_bytes())
    (pasta / "sonda.py").write_text('import sys\nfrom _comum import emitir\nassert "orquestra" not in sys.modules\nemitir("teste:1", "Demonstração")\n', encoding="utf-8")
    ambiente = dict(os.environ, ORQUESTRA_CONFIG="{}")
    limites.preparar_snapshot(pasta, ambiente, "sonda")
    processo = subprocess.run([sys.executable, "-S", str(pasta / "sonda.py")], env=ambiente, capture_output=True, timeout=10)
    assert processo.returncode == 0, processo.stderr.decode("utf-8")
    assert json.loads(processo.stdout)["id"] == "teste:1"


def test_pausa_429_e_ritmo_abrangem_outros_recursos_da_mesma_api(relogio):
    busca = "https://www.googleapis.com/youtube/v3/search"
    canal = "https://www.googleapis.com/youtube/v3/channels"
    limites._reservar(busca)
    limites._reservar(canal)
    assert relogio[0] == 1_700_000_001
    with pytest.raises(limites.LimiteColeta):
        limites._pausar(busca, urllib.error.HTTPError(busca, 429, "recusado", {"Retry-After": "3600"}, None))
    with pytest.raises(limites.LimiteColeta, match="serviço está em pausa"):
        limites._reservar(canal)


@pytest.mark.parametrize("pasta,script", [("radar", "rss.py"), ("numeros", "youtube_canal.py")])
@pytest.mark.parametrize("personalizado", [False, True])
def test_atualizacao_dos_limites_preserva_configuracao_notas_e_codigo_proprio(painel, pasta, script, personalizado):
    modulo = painel.modulo(pasta)
    base = modulo.pasta / "maquina/coletores"
    fixtures = Path(__file__).parent / "fixtures"
    ajudante = (fixtures / "coletor-comum-antes-limites.txt").read_bytes()
    if personalizado:
        ajudante += b"\n# Minha personalizacao\n"
    (base / "_comum.py").write_bytes(ajudante)
    if pasta == "numeros":
        (base / script).write_bytes((fixtures / "youtube-canal-antes-limites.txt").read_bytes())
    antes = {p: p.read_bytes() for p in base.glob("*.py")}
    yaml = (modulo.pasta / "_modulo.yaml").read_bytes()
    notas = {n.rel: n.versao for n in painel.indice.notas.values()}
    automacoes.sincronizar_catalogo(painel)
    if personalizado:
        assert {p: p.read_bytes() for p in antes} == antes
    else:
        for nome in ("_comum.py", script):
            assert (base / nome).read_bytes() == (Path(automacoes.__file__).parent / "catalogo" / pasta / "maquina/coletores" / nome).read_bytes()
        assert automacoes._publica_legada(painel, pasta, script)["codigo_nativo"]
    assert (modulo.pasta / "_modulo.yaml").read_bytes() == yaml
    assert {n.rel: n.versao for n in painel.indice.notas.values()} == notas


def test_configuracao_conta_bytes_utf8_e_arquivo_excessivo_preserva_anterior(painel, monkeypatch):
    with pytest.raises(ValueError, match="muito grande"):
        limites.validar_config({"tarefas": [{"titulo": "🌱" * 26000}]})
    automacoes.criar(painel, "radar/rss.py", "radar/itens")
    caminho = painel.vault / automacoes.ARQUIVO
    anterior = caminho.read_bytes()
    monkeypatch.setattr(automacoes, "LIMITE_CONFIGURACAO_BYTES", len(anterior) + 1)
    with pytest.raises(ValueError, match="excedem 32 MB"):
        automacoes.criar(painel, "radar/rss.py", "radar/itens")
    assert caminho.read_bytes() == anterior
