"""Importação e alterações de configuração compartilham uma fronteira de escrita."""

import asyncio
import importlib.util
import io
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from orquestra import automacoes, coletores
from orquestra.config import gravar_yaml, ler_yaml
from orquestra.painel import Painel


def test_remocao_em_outro_painel_aguarda_importacao_ja_iniciada(painel, monkeypatch):
    destino = painel.vault / "Projeto" / "Pesquisa"
    destino.mkdir(parents=True)
    instancia = automacoes.criar(painel, "radar/rss.py", "Projeto/Pesquisa")
    instancia = automacoes.autorizar(painel, instancia["id"], instancia["confianca"]["assinatura"])
    outro = Painel(painel.vault)
    importando, liberar, removendo, removida = (Event() for _ in range(4))
    importar = coletores.importar

    def importar_com_pausa(*args, **kwargs):
        importando.set()
        assert liberar.wait(5), "A coordenação da importação não foi liberada."
        return importar(*args, **kwargs)

    def remover():
        removendo.set()
        automacoes.remover(outro, instancia["id"])
        removida.set()

    monkeypatch.setattr(coletores, "importar", importar_com_pausa)
    with ThreadPoolExecutor(max_workers=2) as executor:
        gravacao = executor.submit(automacoes._concluir, painel, instancia,
                                   instancia["confianca"]["assinatura"],
                                   [{"id": "artigo:1", "titulo": "Uma referência"}], "")
        assert importando.wait(5)
        remocao = executor.submit(remover)
        try:
            assert removendo.wait(5)
            assert not removida.wait(.2), "Remoção terminou enquanto a importação ainda podia gravar."
        finally:
            liberar.set()
        assert gravacao.result(timeout=5)["novos"] == 1
        remocao.result(timeout=5)

    assert removida.is_set()
    assert automacoes.listar(outro) == []
    assert (destino / "Uma referência.md").is_file()


def test_edicao_antes_da_importacao_impede_gravar_resultado_antigo(painel):
    destino = painel.vault / "Pesquisa"
    destino.mkdir()
    instancia = automacoes.criar(painel, "radar/rss.py", "Pesquisa")
    instancia = automacoes.autorizar(painel, instancia["id"], instancia["confianca"]["assinatura"])
    automacoes.atualizar(painel, instancia["id"], "radar/rss.py", "Pesquisa",
                        {"feeds": ["https://example.test/outra-fonte"]})
    resultado = automacoes._concluir(painel, instancia, instancia["confianca"]["assinatura"],
                                     [{"id": "artigo:antigo", "titulo": "Resultado antigo"}], "")
    assert not resultado["ok"]
    assert "mudou" in resultado["erro"]
    assert not list(destino.glob("*.md"))


def test_coletas_em_paineis_com_indices_distintos_nao_duplicam_o_mesmo_item(painel):
    destino = painel.vault / "Pesquisa"
    destino.mkdir()
    instancia = automacoes.criar(painel, "radar/rss.py", "Pesquisa")
    instancia = automacoes.autorizar(painel, instancia["id"], instancia["confianca"]["assinatura"])
    outro = Painel(painel.vault)  # aberto antes de a primeira coleta escrever
    item = {"id": "rss:mesma-fonte", "titulo": "Uma referência"}
    primeira = automacoes._concluir(painel, instancia, instancia["confianca"]["assinatura"], [item], "")
    segunda = automacoes._concluir(outro, instancia, instancia["confianca"]["assinatura"], [item], "")
    assert primeira["novos"] == 1
    assert segunda["novos"] == 0 and segunda["repetidos"] == 1
    assert len(list(destino.glob("*.md"))) == 1


@pytest.mark.parametrize("pasta", ["radar", "tarefas", "numeros"])
def test_download_tem_limite_mesmo_sem_tamanho_confiavel(pasta, monkeypatch):
    monkeypatch.setenv("ORQUESTRA_CONFIG", "{}")
    # A importação do ajudante altera a preferência IPv4 só no processo coletor;
    # esta execução de teste deve devolver o resolvedor global ao final.
    monkeypatch.setattr(socket, "getaddrinfo", socket.getaddrinfo)
    caminho = Path(coletores.__file__).parent / "catalogo" / pasta / "maquina" / "coletores" / "_comum.py"
    spec = importlib.util.spec_from_file_location(f"ajudante_{pasta}", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    monkeypatch.setattr(modulo, "LIMITE_DOWNLOAD", 8)
    leituras = []

    class Resposta(io.BytesIO):
        headers = {"Content-Length": "1"}  # fonte pode mentir sobre o tamanho

        def read(self, tamanho=-1):
            assert tamanho > 0, "Uma fonte não pode provocar leitura ilimitada."
            leituras.append(tamanho)
            return super().read(tamanho)

    monkeypatch.setattr(modulo.urllib.request, "urlopen", lambda *args, **kwargs: Resposta(b"a" * 32))
    with pytest.raises(ValueError, match="limite de 8 MB"):
        modulo.baixar("https://example.test/feed")
    assert leituras == [9]
    monkeypatch.setattr(modulo.urllib.request, "urlopen", lambda *args, **kwargs: Resposta(b"a" * 8))
    assert modulo.baixar("https://example.test/feed") == b"a" * 8


@pytest.mark.parametrize("legado", [False, True])
def test_todas_fontes_falhando_nao_anunciam_sucesso_nem_expoem_url(painel, monkeypatch, legado):
    diagnostico = b"Falha em https://example.test/privado?token=teste-secreto: HTTP Error 503\n"
    monkeypatch.setattr(coletores, "_executar_limitado", lambda *args: (b"", diagnostico, 0, ""))
    if legado:
        modulo = painel.modulo("radar")
        coletor = next(c for c in modulo.coletores if c.script == "rss.py")
        resultado = painel.rodar_coletor_agora(modulo, coletor)
        ok, erro = resultado.ok, resultado.erro
    else:
        destino = painel.vault / "Pesquisa"
        destino.mkdir()
        instancia = automacoes.criar(painel, "radar/rss.py", "Pesquisa")
        automacoes.autorizar(painel, instancia["id"], instancia["confianca"]["assinatura"])
        resultado = asyncio.run(automacoes.rodar(painel, instancia["id"], previa=True))
        ok, erro = resultado["ok"], resultado["erro"]
    assert not ok
    assert "fontes" in erro and "teste-secreto" not in erro and "example.test" not in erro


def test_avisos_nao_invalidam_fonte_vazia_e_falha_parcial_preserva_itens(painel, monkeypatch):
    destino = painel.vault / "Pesquisa"
    destino.mkdir()
    instancia = automacoes.criar(painel, "radar/rss.py", "Pesquisa")
    automacoes.autorizar(painel, instancia["id"], instancia["confianca"]["assinatura"])
    monkeypatch.setattr(coletores, "_executar_limitado", lambda *args: (b"", b"warning: runtime\n", 0, ""))
    assert asyncio.run(automacoes.rodar(painel, instancia["id"], previa=True))["ok"]
    item = json.dumps({"id": "rss:1", "titulo": "Artigo"}).encode()
    monkeypatch.setattr(coletores, "_executar_limitado", lambda *args: (item, b"Falha em outra fonte\n", 0, ""))
    parcial = asyncio.run(automacoes.rodar(painel, instancia["id"], previa=True))
    assert parcial["ok"] and parcial["total"] == 1


def test_catalogo_stdlib_roda_sem_uv_e_metadados_futuros_preservam_uv(tmp_path, monkeypatch):
    script = tmp_path / "automacao.py"
    script.write_text('# /// script\n# requires-python = ">=3.11"\n# # Sem bibliotecas externas\n# dependencies = []\n# ///\nprint("ok")\n', encoding="utf-8")
    monkeypatch.setattr(automacoes.shutil, "which", lambda nome: None)
    assert automacoes._comando_catalogo(script) == [sys.executable, str(script)]
    script.write_text('# /// script\n# requires-python = ">=3.11"\n# dependencies = ["exemplo==1.0"]\n# ///\n', encoding="utf-8")
    with pytest.raises(automacoes.ErroAutomacao, match="precisa do uv"):
        automacoes._comando_catalogo(script)
    monkeypatch.setattr(automacoes.shutil, "which", lambda nome: "uv-test")
    assert automacoes._comando_catalogo(script) == ["uv-test", "run", "--quiet", "--no-project", "--script", str(script)]


def test_todo_catalogo_atual_usa_python_do_painel():
    for modulo, coletor in automacoes._definicoes().values():
        script = modulo.pasta / "maquina" / "coletores" / coletor.script
        assert automacoes._comando_catalogo(script) == [sys.executable, str(script)]


def test_coletor_com_nome_nativo_e_codigo_personalizado_nao_recebe_formulario_nativo(cliente, vault):
    script = vault / "radar" / "maquina" / "coletores" / "rss.py"
    script.write_text('raise SystemExit("script personalizado não deve ser executado")\n', encoding="utf-8")
    yaml = vault / "radar" / "_modulo.yaml"
    antes = yaml.read_bytes()
    catalogo = cliente.get("/api/automacoes/catalogo").json()
    existente = next(a for a in catalogo["legadas"] if a["legado"] == {"modulo": "radar", "script": "rss.py"})
    assert existente["codigo_nativo"] is False
    assert not existente["confianca"]["confiavel"] and not existente["atualizacao_disponivel"]
    pedido = {**existente["legado"], "versao": existente["versao"], "config": existente["config"]}
    for rota in ("prever", "editar"):
        resposta = cliente.post("/api/automacoes/legado/" + rota, json=pedido)
        assert resposta.status_code == 400 and "personalizado" in resposta.json()["erro"]
    assert yaml.read_bytes() == antes


def test_formulario_legado_usa_configuracao_atual_mesmo_com_indice_antigo(painel):
    modulo = painel.modulo("radar")
    caminho = modulo.pasta / "_modulo.yaml"
    antes = next(c for c in modulo.coletores if c.script == "rss.py").config["feeds"]
    dados = ler_yaml(caminho)
    nova_fonte = ["https://example.test/alteracao-externa.xml"]
    for coletor in dados["coletores"]:
        if coletor["script"] == "rss.py":
            coletor["config"]["feeds"] = nova_fonte
    gravar_yaml(caminho, dados)
    assert next(c for c in modulo.coletores if c.script == "rss.py").config["feeds"] == antes
    atual = automacoes._publica_legada(painel, "radar", "rss.py")
    assert atual["config"]["feeds"] == nova_fonte
    editada = automacoes.atualizar_legada(painel, "radar", "rss.py", atual["config"], nome="Nome novo", versao=atual["versao"])
    assert editada["config"]["feeds"] == nova_fonte


def test_formulario_rele_se_configuracao_mudar_durante_leitura(painel, monkeypatch):
    caminho = painel.modulo("radar").pasta / "_modulo.yaml"
    original = automacoes._definicao_legada
    chamadas = []

    def ler_e_alterar(*args):
        resultado = original(*args)
        chamadas.append(True)
        if len(chamadas) == 1:
            dados = ler_yaml(caminho)
            for coletor in dados["coletores"]:
                if coletor["script"] == "rss.py":
                    coletor["nome"] = "Alteração concorrente"
            gravar_yaml(caminho, dados)
        return resultado

    monkeypatch.setattr(automacoes, "_definicao_legada", ler_e_alterar)
    atual = automacoes._publica_legada(painel, "radar", "rss.py")
    assert atual["nome"] == "Alteração concorrente" and len(chamadas) == 2


def test_configuracao_importada_tem_leitura_limitada_sem_virar_lista_vazia(painel, monkeypatch):
    caminho = painel.vault / automacoes.ARQUIVO
    caminho.parent.mkdir(exist_ok=True)
    monkeypatch.setattr(automacoes, "LIMITE_CONFIGURACAO_BYTES", 64)
    caminho.write_bytes(b" " * 1000)
    leituras = []
    abrir = Path.open

    class LeituraLimitada:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, tamanho=-1):
            leituras.append(tamanho)
            assert 0 < tamanho <= 65
            return b" " * tamanho

    def abrir_config(p, *args, **kwargs):
        return LeituraLimitada() if p == caminho else abrir(p, *args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(Path, "open", abrir_config)
        with pytest.raises(automacoes.ErroAutomacao, match="limite de 32 MB"):
            automacoes.listar(painel)
    assert leituras == [65]
    caminho.write_text('{"versao":1,"instancias":[]}', encoding="utf-8")
    assert automacoes.listar(painel) == []
    caminho.write_text('{}', encoding="utf-8")
    with pytest.raises(automacoes.ErroAutomacao, match="formato desconhecido"):
        automacoes.listar(painel)
