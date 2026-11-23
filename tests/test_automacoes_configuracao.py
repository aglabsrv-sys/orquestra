"""Configuração amigável preserva identidades, notas e código personalizado."""

import hashlib
import os
from pathlib import Path

import pytest

from orquestra import automacoes, confianca
from orquestra.config import gravar_yaml, ler_yaml
from orquestra.painel import Painel


def legado(painel, modulo="radar", script="rss.py"):
    return next(a for a in automacoes.legadas(painel) if a["legado"] == {"modulo": modulo, "script": script})


def test_catalogo_explica_personalizacao_e_legados_estao_prontos(painel):
    catalogo = automacoes.catalogo()
    assert all(a["ajuda"] for a in catalogo)
    assert "termos" in next(a["ajuda"] for a in catalogo if a["id"] == "radar/youtube_api.py")
    assert legado(painel)["confianca"]["confiavel"]
    assert not legado(painel)["atualizacao_disponivel"]


@pytest.mark.parametrize("personalizado", [False, True])
def test_remover_original_preserva_notas_codigo_e_demais_configuracoes(painel, personalizado):
    modulo = painel.modulo("radar")
    arquivo = modulo.pasta / "_modulo.yaml"
    script = modulo.pasta / "maquina/coletores/rss.py"
    if personalizado:
        script.write_bytes(script.read_bytes() + b"\n# Personalizacao preservada\n")
    atual = legado(painel)
    original = ler_yaml(arquivo)
    preservados = {p: p.read_bytes() for p in modulo.pasta.rglob("*") if p.is_file() and p != arquivo}
    automacoes.remover_legada(painel, "radar", "rss.py", versao=atual["versao"])
    depois = ler_yaml(arquivo)
    assert depois["coletores"] == [c for c in original["coletores"] if c["script"] != "rss.py"]
    assert {k: v for k, v in depois.items() if k != "coletores"} == {k: v for k, v in original.items() if k != "coletores"}
    assert all(p.read_bytes() == conteudo for p, conteudo in preservados.items())
    reaberto = Painel(painel.vault)
    automacoes.sincronizar_catalogo(reaberto)
    assert all(c.script != "rss.py" for c in reaberto.modulo("radar").coletores)
    assert "radar/rss.py" not in {a["id"] for a in automacoes.contexto(reaberto, reaberto.modulo("radar"))["automacoes_instaladas"]}
    adicionada = automacoes.criar(reaberto, "radar/rss.py", "radar/itens")
    assert adicionada["destino"] == "radar/itens"


def test_remocao_original_recusa_versao_antiga_e_execucao_em_andamento(painel):
    atual = legado(painel)
    arquivo = painel.modulo("radar").pasta / "_modulo.yaml"
    arquivo.write_bytes(arquivo.read_bytes() + b"\n# Alteracao externa\n")
    antes = arquivo.read_bytes()
    with pytest.raises(automacoes.ErroAutomacao, match="mudaram"):
        automacoes.remover_legada(painel, "radar", "rss.py", versao=atual["versao"])
    atual = legado(painel)
    painel.rodando.add("radar/rss.py")
    try:
        with pytest.raises(automacoes.ErroAutomacao, match="terminar"):
            automacoes.remover_legada(painel, "radar", "rss.py", versao=atual["versao"])
    finally:
        painel.rodando.discard("radar/rss.py")
    assert arquivo.read_bytes() == antes


def test_remocao_recusa_alteracao_externa_antes_da_leitura(painel, monkeypatch):
    atual = legado(painel)
    arquivo = painel.modulo("radar").pasta / "_modulo.yaml"
    conteudo = arquivo.read_bytes() + b"\n# Outra pessoa editou esta configuracao\n"
    ler_original = automacoes.ler_yaml

    def ler_apos_edicao(caminho):
        arquivo.write_bytes(conteudo)
        return ler_original(caminho)

    monkeypatch.setattr(automacoes, "ler_yaml", ler_apos_edicao)
    with pytest.raises(automacoes.ErroAutomacao, match="mudaram"):
        automacoes.remover_legada(painel, "radar", "rss.py", versao=atual["versao"])
    assert arquivo.read_bytes() == conteudo


def test_editar_fontes_legadas_preserva_notas_codigo_e_demais_coletores(painel):
    atual = legado(painel)
    modulo = painel.modulo("radar")
    caminho = modulo.pasta / "_modulo.yaml"
    original = ler_yaml(caminho)
    codigo = (modulo.pasta / "maquina/coletores/rss.py").read_bytes()
    notas = {n.rel: n.versao for n in painel.indice.notas.values()}
    config = {**atual["config"], "feeds": ["https://example.test/pesquisa.atom"]}
    resultado = automacoes.atualizar_legada(painel, "radar", "rss.py", config, nome="Pesquisa do projeto", a_cada="1h", versao=atual["versao"])
    assert resultado["config"]["feeds"] == config["feeds"] and resultado["a_cada"] == "1h"
    assert resultado["destino"] == atual["destino"] and resultado["id"] == atual["id"]
    assert not resultado["ativo"] and not resultado["confianca"]["confiavel"]
    depois = ler_yaml(caminho)
    for antes, agora in zip(original["coletores"], depois["coletores"]):
        if antes["script"] != "rss.py":
            assert antes == agora
    assert (modulo.pasta / "maquina/coletores/rss.py").read_bytes() == codigo
    assert {n.rel: n.versao for n in painel.indice.notas.values()} == notas
    confianca.autorizar(painel.vault, *painel.coletor("radar", "rss.py"), resultado["confianca"]["assinatura"])
    assert legado(painel)["confianca"]["confiavel"]


def test_edicao_legada_recusa_configuracao_desatualizada_e_execucao_em_andamento(painel):
    atual = legado(painel)
    caminho = painel.modulo("radar").pasta / "_modulo.yaml"
    caminho.write_text(caminho.read_text(encoding="utf-8") + "\n# Alteração externa\n", encoding="utf-8")
    with pytest.raises(automacoes.ErroAutomacao, match="mudaram"):
        automacoes.atualizar_legada(painel, "radar", "rss.py", atual["config"], versao=atual["versao"])
    atual = legado(painel)
    painel.rodando.add("radar/rss.py")
    with pytest.raises(automacoes.ErroAutomacao, match="terminar"):
        automacoes.atualizar_legada(painel, "radar", "rss.py", atual["config"], versao=atual["versao"])


def test_formulario_legado_preserva_configuracoes_proprias_sem_permitir_injetar_opcoes(painel):
    atual = legado(painel)
    with pytest.raises(automacoes.ErroAutomacao, match="personalizada"):
        automacoes.prever_legada(painel, "radar", "rss.py", {**atual["config"], "comando": "não permitido"})
    assert legado(painel)["versao"] == atual["versao"]


@pytest.mark.parametrize("crlf", [False, True])
def test_atualizar_nativo_antigo_e_explicito_e_preserva_configuracao(painel, crlf):
    modulo = painel.modulo("radar")
    helper = modulo.pasta / "maquina/coletores/_comum.py"
    antigo = (Path(__file__).parent / "fixtures/coletor-comum-040.txt").read_bytes()
    assert hashlib.sha256(antigo).hexdigest() == automacoes._HELPER_DISTRIBUIDO_ANTERIOR
    helper.write_bytes(antigo.replace(b"\n", b"\r\n") if crlf else antigo)
    antes = legado(painel)
    assert antes["atualizacao_disponivel"] and not antes["confianca"]["confiavel"]
    yaml = (modulo.pasta / "_modulo.yaml").read_bytes()
    notas = {n.rel: n.versao for n in painel.indice.notas.values()}
    depois = automacoes.atualizar_codigo_legado(painel, "radar", "rss.py", versao=antes["versao"], assinatura=antes["confianca"]["assinatura"])
    assert not depois["atualizacao_disponivel"] and depois["confianca"]["confiavel"]
    assert (modulo.pasta / "_modulo.yaml").read_bytes() == yaml
    assert {n.rel: n.versao for n in painel.indice.notas.values()} == notas
    assert helper.read_bytes() == (Path(automacoes.__file__).parent / "catalogo/radar/maquina/coletores/_comum.py").read_bytes()
    assert list((Path(os.environ['ORQUESTRA_HOME']) / 'recuperacao').rglob('*.antes'))


@pytest.mark.parametrize("personalizado", [False, True])
def test_atualizacao_recorrentes_reconhece_original_e_preserva_codigo_proprio(painel, personalizado):
    modulo = painel.modulo("tarefas")
    script = modulo.pasta / "maquina/coletores/recorrentes.py"
    antigo = (Path(__file__).parent / "fixtures/recorrentes-040.txt").read_bytes()
    assert hashlib.sha256(antigo.replace(b"\r\n", b"\n")).hexdigest() == automacoes._RECORRENTES_DISTRIBUIDO_ANTERIOR
    script.write_bytes(antigo + (b"\n# Personalizado\n" if personalizado else b""))
    antes = automacoes._publica_legada(painel, "tarefas", "recorrentes.py")
    assert antes["atualizacao_disponivel"] is not personalizado
    yaml = (modulo.pasta / "_modulo.yaml").read_bytes()
    if personalizado:
        with pytest.raises(automacoes.ErroAutomacao, match="código próprio"):
            automacoes.atualizar_codigo_legado(painel, "tarefas", "recorrentes.py", versao=antes["versao"], assinatura=antes["confianca"]["assinatura"])
        assert script.read_bytes() == antigo + b"\n# Personalizado\n"
    else:
        depois = automacoes.atualizar_codigo_legado(painel, "tarefas", "recorrentes.py", versao=antes["versao"], assinatura=antes["confianca"]["assinatura"])
        assert not depois["atualizacao_disponivel"]
        assert script.read_bytes() == (Path(automacoes.__file__).parent / "catalogo/tarefas/maquina/coletores/recorrentes.py").read_bytes()
    assert (modulo.pasta / "_modulo.yaml").read_bytes() == yaml


def test_updater_nunca_substitui_codigo_personalizado(painel):
    modulo = painel.modulo("radar")
    script = modulo.pasta / "maquina/coletores/rss.py"
    script.write_bytes(script.read_bytes() + b"\n# Minha personalizacao\n")
    atual = legado(painel)
    assert not atual["atualizacao_disponivel"]
    antes = script.read_bytes()
    with pytest.raises(automacoes.ErroAutomacao, match="código próprio"):
        automacoes.atualizar_codigo_legado(painel, "radar", "rss.py", versao=atual["versao"], assinatura=atual["confianca"]["assinatura"])
    assert script.read_bytes() == antes


@pytest.mark.parametrize("personalizado", [False, True])
@pytest.mark.parametrize("revogado", [False, True])
def test_abrir_versao_nova_incorpora_originais_sem_fluxo_separado(painel, personalizado, revogado):
    from fastapi.testclient import TestClient
    from orquestra import confianca
    from orquestra.servidor import criar_app

    modulo = painel.modulo("tarefas")
    coletor = next(c for c in modulo.coletores if c.script == "recorrentes.py")
    script = modulo.pasta / "maquina/coletores/recorrentes.py"
    antigo = (Path(__file__).parent / "fixtures/recorrentes-040.txt").read_bytes()
    anterior = antigo + (b"\n# Personalizado\n" if personalizado else b"")
    script.write_bytes(anterior)
    if revogado:
        confianca.revogar(painel.vault, modulo, coletor)
    configuracao = (modulo.pasta / "_modulo.yaml").read_bytes()
    notas = {p: p.read_bytes() for p in modulo.pasta_itens.glob("*.md")}
    app = criar_app(painel.vault, vigiar=False, agendar=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        pagina = cliente.get("/ajustes/automacoes")
        assert pagina.status_code == 200
        assert "Atualizar automação" not in pagina.text
        assert 'id="automacao-atualizar"' not in pagina.text
    atual = legado(app.state.painel, "tarefas", "recorrentes.py")
    assert not atual["ativo"]
    if personalizado:
        assert script.read_bytes() == anterior
    else:
        assert not atual["atualizacao_disponivel"] and atual["codigo_nativo"]
        if revogado:
            assert not atual["confianca"]["confiavel"]
        assert script.read_bytes() == (Path(automacoes.__file__).parent / "catalogo/tarefas/maquina/coletores/recorrentes.py").read_bytes()
    assert (modulo.pasta / "_modulo.yaml").read_bytes() == configuracao
    assert {p: p.read_bytes() for p in modulo.pasta_itens.glob("*.md")} == notas
    arquivos = {p: p.read_bytes() for p in (modulo.pasta / "maquina/coletores").glob("*.py")}
    automacoes.sincronizar_catalogo(app.state.painel)
    assert {p: p.read_bytes() for p in arquivos} == arquivos


@pytest.mark.parametrize("revogado", [False, True])
def test_atualizacao_youtube_preserva_config_antiga_e_revogacao(painel, revogado):
    modulo = painel.modulo("radar")
    script = modulo.pasta / "maquina/coletores/youtube_rss.py"
    antigo = (Path(__file__).parent / "fixtures/youtube-rss-040.txt").read_bytes()
    assert hashlib.sha256(antigo.replace(b"\r\n", b"\n")).hexdigest() == automacoes._YOUTUBE_RSS_DISTRIBUIDO_ANTERIOR
    script.write_bytes(antigo)
    arquivo = modulo.pasta / "_modulo.yaml"
    dados = ler_yaml(arquivo)
    for c in dados["coletores"]:
        if c["script"] == "youtube_rss.py":
            c["config"].pop("titulos_contem", None)
    gravar_yaml(arquivo, dados)
    painel.recarregar_config()
    modulo, coletor = painel.coletor("radar", "youtube_rss.py")
    if revogado:
        confianca.revogar(painel.vault, modulo, coletor)
    antes = arquivo.read_bytes()
    automacoes.sincronizar_catalogo(painel)
    assert arquivo.read_bytes() == antes
    atual = legado(painel, "radar", "youtube_rss.py")
    assert atual["codigo_nativo"] and not atual["atualizacao_disponivel"]
    assert atual["confianca"]["confiavel"] is not revogado
    # Um filtro preenchido continua sendo uma mudança de configuração.
    coletor.config["titulos_contem"] = ["python"]
    assert not confianca.resumo(painel.vault, modulo, coletor)["confiavel"]
