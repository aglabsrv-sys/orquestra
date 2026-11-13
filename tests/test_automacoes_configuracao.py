"""Configuração amigável preserva identidades, notas e código personalizado."""

import hashlib
import os
from pathlib import Path

import pytest

from orquestra import automacoes, confianca
from orquestra.config import ler_yaml


def legado(painel, modulo="radar", script="rss.py"):
    return next(a for a in automacoes.legadas(painel) if a["legado"] == {"modulo": modulo, "script": script})


def test_catalogo_explica_personalizacao_e_legados_estao_prontos(painel):
    catalogo = automacoes.catalogo()
    assert all(a["ajuda"] for a in catalogo)
    assert "termos" in next(a["ajuda"] for a in catalogo if a["id"] == "radar/youtube_api.py")
    assert legado(painel)["confianca"]["confiavel"]
    assert not legado(painel)["atualizacao_disponivel"]


def test_editar_fontes_legadas_preserva_notas_codigo_e_demais_coletores(painel):
    atual = legado(painel)
    modulo = painel.modulo("radar")
    caminho = modulo.pasta / "_modulo.yaml"
    original = ler_yaml(caminho)
    codigo = (modulo.pasta / "maquina/coletores/rss.py").read_bytes()
    notas = {n.rel: n.versao for n in painel.indice.notas.values()}
    config = {**atual["config"], "feeds": ["https://example.test/pesquisa.atom"]}
    resultado = automacoes.atualizar_legada(painel, "radar", "rss.py", config, nome="Pesquisa do projeto", a_cada="30m", versao=atual["versao"])
    assert resultado["config"]["feeds"] == config["feeds"] and resultado["a_cada"] == "30m"
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
