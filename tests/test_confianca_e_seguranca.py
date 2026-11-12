"""Regressões dos limites de confiança: dados importados não autorizam código."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from orquestra import coletores, confianca
from orquestra.boasvindas import criar_boas_vindas
from orquestra.hospedeiro import Hospedeiro
from orquestra.mcp_servidor import ErroDeFerramenta, Ferramentas
from orquestra.modulos import Campo, ColetorDef, Modulo
from orquestra.indice import Indice
from orquestra.notas import gravar_nota, ler_nota
from orquestra.seguranca import CapabilityLocal, Protecao, canal_local, host_permitido


@pytest.fixture
def codigo(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ORQUESTRA_VAULT", raising=False)
    monkeypatch.setattr(coletores.shutil, "which", lambda nome: None)
    vault = tmp_path / "vault"
    pasta = vault / "tarefas" / "maquina" / "coletores"
    pasta.mkdir(parents=True)
    script = pasta / "teste.py"
    script.write_text('print(\'{"id":"teste:1","titulo":"Código aprovado"}\')', encoding="utf-8")
    modulo = Modulo(id="tarefas", pasta=vault / "tarefas", nome="Tarefas")
    coletor = ColetorDef(script="teste.py", nome="Teste", ativo=True)
    return vault, modulo, coletor, script


def aprovar(vault, modulo, coletor):
    estado = confianca.resumo(vault, modulo, coletor)
    return confianca.autorizar(vault, modulo, coletor, estado["assinatura"])


def test_vault_importado_nao_executa_antes_de_aceite(codigo, monkeypatch):
    vault, modulo, coletor, _ = codigo
    monkeypatch.setattr(coletores.subprocess, "Popen", lambda *a, **kw: pytest.fail("Não pode iniciar processo sem aceite"))
    itens, erro = coletores.rodar_script(vault, modulo, coletor)
    assert itens == [] and "não foi autorizado" in erro


def test_aceite_local_executa_e_revogacao_bloqueia(codigo):
    vault, modulo, coletor, _ = codigo
    aprovado = aprovar(vault, modulo, coletor)
    assert aprovado["confiavel"]
    assert aprovado["arquivos"] == ["teste.py"]
    itens, erro = coletores.rodar_script(vault, modulo, coletor)
    assert not erro and itens[0]["titulo"] == "Código aprovado"
    assert not list(vault.rglob("confianca*.json"))
    confianca.revogar(vault, modulo, coletor)
    assert not confianca.resumo(vault, modulo, coletor)["confiavel"]


@pytest.mark.parametrize("mudanca", ["script", "auxiliar", "config", "requer"])
def test_alteracao_revoga_hash_e_aceite_obsoleto_e_recusado(codigo, mudanca):
    vault, modulo, coletor, script = codigo
    auxiliar = script.with_name("_comum.py")
    auxiliar.write_text("VALOR = 1\n", encoding="utf-8")
    assinatura = aprovar(vault, modulo, coletor)["assinatura"]
    if mudanca == "script":
        script.write_text(script.read_text() + "\n# outra versão\n", encoding="utf-8")
    elif mudanca == "auxiliar":
        auxiliar.write_text("VALOR = 2\n", encoding="utf-8")
    elif mudanca == "config":
        coletor.config["termo"] = "outro"
    else:
        coletor.requer = ["CHAVE_AUTORIZADA"]
    assert not confianca.resumo(vault, modulo, coletor)["confiavel"]
    with pytest.raises(ValueError, match="mudou"):
        confianca.autorizar(vault, modulo, coletor, assinatura)
    assert "não foi autorizado" in coletores.rodar_script(vault, modulo, coletor)[1]


def test_aceite_nao_viaja_com_copia_do_vault(codigo, tmp_path):
    vault, modulo, coletor, _ = codigo
    aprovar(vault, modulo, coletor)
    outro = tmp_path / "vault-copiado"
    shutil.copytree(vault, outro)
    copiado = Modulo(id="tarefas", pasta=outro / "tarefas", nome="Tarefas")
    assert not confianca.resumo(outro, copiado, coletor)["confiavel"]


@pytest.mark.parametrize("nome", ["../fora.py", "/tmp/fora.py", "C:\\fora.py", "teste.txt", ".oculto.py", "sub/../../fora.py", "C:fora.py"])
def test_script_precisa_ser_python_local_sem_traversal(codigo, nome):
    vault, modulo, coletor, _ = codigo
    coletor.script = nome
    assert not confianca.resumo(vault, modulo, coletor)["confiavel"]
    assert coletores.rodar_script(vault, modulo, coletor)[0] == []


def test_execucao_recebe_so_chaves_declaradas_e_nao_herda_pythonpath(codigo, tmp_path, monkeypatch):
    vault, modulo, coletor, script = codigo
    casa = tmp_path / "home"
    casa.mkdir()
    (casa / ".env").write_text("CHAVE_AUTORIZADA=fixture-permitida\nOUTRA_CHAVE=fixture-privada\n", encoding="utf-8")
    monkeypatch.setenv("TOKEN_DO_PROCESSO", "fixture-token-pai")
    monkeypatch.setenv("PYTHONPATH", "/nao/deve/ser/herdado")
    coletor.requer = ["CHAVE_AUTORIZADA"]
    script.write_text('import os, json\nprint(json.dumps({"id":"x","titulo":"teste","campos":{"permitida":bool(os.getenv("CHAVE_AUTORIZADA")),"outra":bool(os.getenv("OUTRA_CHAVE")),"pai":bool(os.getenv("TOKEN_DO_PROCESSO")),"pythonpath":bool(os.getenv("PYTHONPATH"))}}))', encoding="utf-8")
    aprovar(vault, modulo, coletor)
    itens, erro = coletores.rodar_script(vault, modulo, coletor)
    assert not erro
    assert itens[0]["campos"] == {"permitida": True, "outra": False, "pai": False, "pythonpath": False}


@pytest.mark.parametrize("canal", ["stdout", "stderr"])
def test_credenciais_nao_voltam_na_saida(codigo, tmp_path, canal):
    vault, modulo, coletor, script = codigo
    casa = tmp_path / "home"
    casa.mkdir()
    (casa / ".env").write_text("CHAVE=fake-sensitive-fixture\n", encoding="utf-8")
    coletor.requer = ["CHAVE"]
    if canal == "stdout":
        script.write_text('import os,json\nprint(json.dumps({"id":"x","titulo":os.environ["CHAVE"]}))', encoding="utf-8")
    else:
        script.write_text('import os,sys\nsys.exit(os.environ["CHAVE"])', encoding="utf-8")
    aprovar(vault, modulo, coletor)
    itens, erro = coletores.rodar_script(vault, modulo, coletor)
    assert "fake-sensitive-fixture" not in json.dumps([itens, erro])
    assert "segredo omitido" in json.dumps([itens, erro])


def test_snapshot_executa_bytes_aprovados_mesmo_se_original_muda(codigo, monkeypatch):
    vault, modulo, coletor, script = codigo
    aprovar(vault, modulo, coletor)
    executar = coletores._executar_limitado

    def trocar_antes_de_iniciar(*args):
        script.write_text('raise SystemExit("codigo trocado")', encoding="utf-8")
        return executar(*args)

    monkeypatch.setattr(coletores, "_executar_limitado", trocar_antes_de_iniciar)
    itens, erro = coletores.rodar_script(vault, modulo, coletor)
    assert not erro and itens[0]["titulo"] == "Código aprovado"
    assert not confianca.resumo(vault, modulo, coletor)["confiavel"]


def test_snapshot_le_auxiliares_sem_carregar_pycache_do_vault(codigo):
    vault, modulo, coletor, script = codigo
    script.with_name("_comum.py").write_text('TITULO = "Auxiliar aprovado"', encoding="utf-8")
    cache = script.parent / "__pycache__"
    cache.mkdir()
    (cache / "nao-aprovado.pyc").write_bytes(b"nao e codigo executavel")
    script.write_text('from _comum import TITULO\nimport json\nprint(json.dumps({"id":"x","titulo":TITULO}))', encoding="utf-8")
    estado = aprovar(vault, modulo, coletor)
    assert not any("__pycache__" in p for p in estado["arquivos"])
    itens, erro = coletores.rodar_script(vault, modulo, coletor)
    assert not erro and itens[0]["titulo"] == "Auxiliar aprovado"


def test_fechar_vault_interrompe_coletor_sem_esperar_timeout(codigo, tmp_path):
    vault, modulo, coletor, script = codigo
    iniciado = tmp_path / "iniciado.txt"
    script.write_text(f"import time\nfrom pathlib import Path\nPath({str(iniciado)!r}).write_text('iniciado')\ntime.sleep(10)\n", encoding="utf-8")
    aprovar(vault, modulo, coletor)
    with ThreadPoolExecutor() as executor:
        futuro = executor.submit(coletores.rodar_script, vault, modulo, coletor)
        limite = time.monotonic() + 3
        while not iniciado.exists() and time.monotonic() < limite:
            time.sleep(0.02)
        assert iniciado.exists()
        coletores.cancelar_execucoes(vault)
        itens, erro = futuro.result(timeout=3)
    assert itens == [] and "vault foi fechado" in erro


def test_saida_excessiva_e_interrompida_sem_importacao_parcial(codigo, monkeypatch):
    vault, modulo, coletor, script = codigo
    script.write_text('print("x" * 10000)', encoding="utf-8")
    aprovar(vault, modulo, coletor)
    monkeypatch.setattr(coletores, "LIMITE_SAIDA", 512)
    itens, erro = coletores.rodar_script(vault, modulo, coletor)
    assert itens == [] and "excedeu" in erro


def test_timeout_encerra_tambem_processo_filho(codigo, tmp_path, monkeypatch):
    vault, modulo, coletor, script = codigo
    marcador = tmp_path / "filho-nao-deve-concluir.txt"
    filho = f"import time; from pathlib import Path; time.sleep(1); Path({str(marcador)!r}).write_text('sobreviveu')"
    script.write_text(f"import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', {filho!r}])\ntime.sleep(10)\n", encoding="utf-8")
    aprovar(vault, modulo, coletor)
    monkeypatch.setattr(coletores, "TEMPO_LIMITE", 0.3)
    itens, erro = coletores.rodar_script(vault, modulo, coletor)
    assert itens == [] and "interrompido" in erro
    time.sleep(1.1)
    assert not marcador.exists()


def test_coletor_sem_agenda_nao_e_automatico_e_horario_invalido_nao_quebra():
    agora = dt.datetime(2026, 11, 11, 12)
    assert not coletores.devido(ColetorDef(script="x.py", nome="Manual"), None, agora)
    assert not coletores.devido(ColetorDef(script="x.py", nome="Inválido", diario_as="99:99"), None, agora)


def test_coleta_completa_vazio_preserva_manual_e_rastreia_so_o_que_preencheu(codigo):
    vault, modulo, coletor, _ = codigo
    modulo.campos = {nome: Campo(nome, tipo="numero") for nome in ("inscritos", "seguidores")}
    modulo.campos["origem"] = Campo("origem")
    modulo.pasta_itens.mkdir()
    caminho = modulo.pasta_itens / "Hoje.md"
    caminho.write_text("---\norigem: humano\nseguidores: 42\n---\nMeu texto original.\n", encoding="utf-8")
    indice = Indice(vault)
    indice.carregar()

    def coletar(inscritos):
        item = {"id": "numeros:hoje", "titulo": "Hoje", "atualizar": True,
                "campos": {"inscritos": inscritos, "seguidores": 999, "origem": "coletor"}}
        resultado = coletores.importar(indice, modulo, coletor, [item])
        for nota in resultado[0]:
            indice.atualizar(nota.caminho)
        return resultado

    criadas, repetidos = coletar(100)
    assert len(criadas) == 1 and repetidos == 0
    nota = ler_nota(caminho, vault)
    assert nota.meta["origem"] == "humano" and nota.meta["seguidores"] == 42
    assert nota.meta["inscritos"] == 100 and nota.corpo == "Meu texto original.\n"
    assert nota.meta["_orquestra_coleta"]["tarefas/teste.py"] == {"inscritos": 100}
    assert len(list(modulo.pasta_itens.glob("*.md"))) == 1

    assert len(coletar(110)[0]) == 1
    nota = ler_nota(caminho, vault)
    assert nota.meta["inscritos"] == 110 and nota.meta["seguidores"] == 42
    nota.meta["inscritos"] = 321  # edição humana posterior, no mesmo arquivo
    gravar_nota(nota, versao_esperada=nota.versao)
    indice.atualizar(caminho)
    assert coletar(120) == ([], 1)
    depois = ler_nota(caminho, vault)
    assert depois.meta["inscritos"] == 321 and depois.meta["seguidores"] == 42
    assert depois.meta["_orquestra_coleta"]["tarefas/teste.py"]["inscritos"] == 110
    assert len(list(modulo.pasta_itens.glob("*.md"))) == 1


def test_coleta_de_origem_coletor_ainda_atualiza_normalmente(codigo):
    vault, modulo, coletor, _ = codigo
    modulo.campos = {"valor": Campo("valor", tipo="numero")}
    modulo.pasta_itens.mkdir()
    caminho = modulo.pasta_itens / "Fonte.md"
    caminho.write_text("---\norigem: coletor\nvalor: 10\n---\n", encoding="utf-8")
    indice = Indice(vault)
    indice.carregar()
    criadas, repetidos = coletores.importar(indice, modulo, coletor, [{"id": "fonte", "titulo": "Fonte", "atualizar": True, "campos": {"valor": 20}}])
    assert len(criadas) == 1 and repetidos == 0
    assert ler_nota(caminho, vault).meta["valor"] == 20


def pedido_local(peer="127.0.0.1", **headers):
    cabecalhos = {"host": "localhost:8420", **headers}
    return Request({"type": "http", "scheme": "http", "method": "GET", "path": "/", "query_string": b"", "client": (peer, 1234), "server": ("127.0.0.1", 8420), "headers": [(k.encode(), v.encode()) for k, v in cabecalhos.items()]})


def test_capability_exige_peer_loopback_e_nao_confia_host_ou_proxy():
    capacidade = CapabilityLocal()
    local = pedido_local()
    assert canal_local(local) and capacidade.emitir(local) == capacidade.token
    for remoto in (pedido_local(peer="100.101.102.103"), pedido_local(**{"x-forwarded-for": "127.0.0.1"}), pedido_local(**{"tailscale-user-login": "teste"}), pedido_local(**{"sec-fetch-site": "cross-site"}), pedido_local(origin="null")):
        assert capacidade.emitir(remoto) is None
        with pytest.raises(ValueError):
            capacidade.exigir(remoto)
    with pytest.raises(ValueError):
        capacidade.exigir(local)
    capacidade.exigir(pedido_local(**{"x-orquestra-local": capacidade.token}))
    assert CapabilityLocal().token != capacidade.token


def test_onboarding_exige_capability_mesmo_com_host_local(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path / "home"))
    vault = tmp_path / "vault"
    vault.mkdir()
    app = criar_boas_vindas(Hospedeiro(None, False, False))
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 1234)) as cliente:
        assert cliente.post("/api/boas-vindas/analisar", json={"caminho": str(vault)}).status_code == 403
        bootstrap = cliente.get("/api/local/capacidade")
        assert bootstrap.status_code == 200 and bootstrap.headers["cache-control"] == "no-store"
        headers = {"X-Orquestra-Local": bootstrap.json()["token"]}
        assert cliente.post("/api/boas-vindas/analisar", json={"caminho": str(vault)}, headers=headers).status_code == 200
        assert cliente.get("/api/local/capacidade", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403
    with TestClient(app, base_url="http://localhost", client=("100.101.102.103", 1234)) as remoto:
        assert remoto.get("/api/local/capacidade").status_code == 403
        assert remoto.post("/api/boas-vindas/analisar", json={"caminho": str(vault)}, headers=headers).status_code == 403


@pytest.fixture
def protegido():
    app = FastAPI()
    app.add_middleware(Protecao, hosts_extras=["painel.tail123.ts.net", "outro.local"])

    @app.post("/salvar")
    async def salvar(request: Request):
        return {"dados": await request.json()}

    return app


@pytest.mark.parametrize("origin", ["null", "https://localhost", "http://localhost:9999", "http://outro.local", "http://localhost@evil.example", "http://localhost/path"])
def test_origem_completa_precisa_ser_a_mesma(protegido, origin):
    with TestClient(protegido, base_url="http://localhost") as c:
        assert c.post("/salvar", json={}, headers={"Origin": origin, "X-Forwarded-Host": origin.removeprefix("http://")}).status_code == 403


def test_hosts_exatos_json_valido_limite_e_cabecalhos(protegido):
    assert not host_permitido("qualquer.ts.net")
    assert host_permitido("painel.tail123.ts.net", ["painel.tail123.ts.net"])
    assert not host_permitido("localhost:invalida")
    with TestClient(protegido, base_url="http://localhost") as c:
        ok = c.post("/salvar", json={"x": 1}, headers={"Origin": "http://localhost"})
        assert ok.status_code == 200 and ok.headers["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in ok.headers["content-security-policy"]
        assert c.post("/salvar", content="{}", headers={"Content-Type": "application/jsonfake"}).status_code == 415
        assert c.post("/salvar", content=b"x" * (2 * 1024 * 1024 + 1), headers={"Content-Type": "application/json"}).status_code == 413


def test_mcp_nao_edita_contrato_ou_reescreve_nota_fora_da_area(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path / "home"))
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "AGENTS.md").write_text("Regras sintéticas", encoding="utf-8")
    (vault / "nota.md").write_text("---\norigem: agente\n---\nTexto original\n", encoding="utf-8")
    mcp = Ferramentas(vault)
    assert "Regras sintéticas" in mcp.regras()
    with pytest.raises(ErroDeFerramenta, match="reservado"):
        mcp.atualizar_item("AGENTS.md", acrescentar="injetar instruções")
    with pytest.raises(ErroDeFerramenta, match="não pode ser substituído"):
        mcp.atualizar_item("nota.md", novo_texto="substituído")
    assert "Texto original" in (vault / "nota.md").read_text()
    assert mcp.buscar("Regras sintéticas") == []
