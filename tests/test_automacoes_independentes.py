"""Destino, confiança e identidade das automações fora dos módulos prontos."""

import asyncio
import datetime as dt
import json

import pytest

from orquestra import automacoes, coletores
from orquestra.notas import gravar_nota, ler_nota
from orquestra.painel import Painel


def pasta(painel, nome="Clientes/Acme/Pesquisa"):
    destino = painel.vault / nome
    destino.mkdir(parents=True, exist_ok=True)
    return nome


def instalar(painel, definicao="radar/rss.py", destino=None, config=None, **kwargs):
    instancia = automacoes.criar(painel, definicao, destino or pasta(painel), config, **kwargs)
    return automacoes.autorizar(painel, instancia["id"], instancia["confianca"]["assinatura"])


def executar(painel, instancia, previa=False):
    return asyncio.run(automacoes.rodar(painel, instancia["id"], previa))


def simular(monkeypatch, itens, capturar=None):
    def rodar(comando, pasta, ambiente, cancelamento):
        if capturar is not None:
            capturar.update(ambiente)
        return ("\n".join(json.dumps(i) for i in itens)).encode(), b"", 0, ""
    monkeypatch.setattr(coletores, "_executar_limitado", rodar)


def test_catalogo_independe_dos_modulos_e_previa_nao_escreve(painel):
    painel.indice.modulos.clear()
    assert len(automacoes.catalogo()) == 9
    destino = pasta(painel)
    antes = set(painel.vault.rglob("*"))
    previa = automacoes.prever(painel, "radar/rss.py", destino, {"feeds": ["https://example.test/feed"]})
    assert previa["destino"] == destino
    assert "status" not in previa["exemplo"]["campos"]
    assert any(c["tipo"] == "lista" for c in previa["campos"])
    assert set(painel.vault.rglob("*")) == antes


def test_instancia_persiste_sem_instalar_modulo_e_remocao_preserva_notas(painel, monkeypatch):
    instancia = instalar(painel)
    simular(monkeypatch, [{"id": "rss:1", "titulo": "Artigo", "tags": ["pesquisa"], "link": "https://example.test/1"}])
    assert executar(painel, instancia)["novos"] == 1
    destino = painel.vault / instancia["destino"]
    assert not (destino / "_modulo.yaml").exists()
    nota = ler_nota(destino / "Artigo.md", painel.vault)
    assert nota.meta["tags"] == ["pesquisa"]
    assert "status" not in nota.meta
    reaberto = Painel(painel.vault)
    assert automacoes.listar(reaberto)[0]["id"] == instancia["id"]
    assert automacoes.listar(reaberto)[0]["confianca"]["confiavel"]
    automacoes.remover(reaberto, instancia["id"])
    assert automacoes.listar(reaberto) == []
    assert (destino / "Artigo.md").exists()


def test_execucao_previa_nao_grava_e_destinos_deduplicam_independentemente(painel, monkeypatch):
    a = instalar(painel)
    simular(monkeypatch, [{"id": "rss:mesmo", "titulo": "Artigo"}])
    assert executar(painel, a, previa=True)["total"] == 1
    assert not list((painel.vault / a["destino"]).glob("*.md"))
    assert executar(painel, a)["novos"] == 1
    assert executar(painel, a)["repetidos"] == 1
    b = instalar(painel, destino=pasta(painel, "Outro/Pesquisa"))
    assert executar(painel, b)["novos"] == 1
    c = instalar(painel, destino=a["destino"])
    assert executar(painel, c)["repetidos"] == 1


def test_autorizacao_exige_versao_local_e_cobre_destino_config_e_mapeamento(painel):
    a = automacoes.criar(painel, "radar/rss.py", pasta(painel))
    assert not a["confianca"]["confiavel"]
    assert not executar(painel, a)["ok"]
    with pytest.raises(automacoes.ErroAutomacao, match="Autorize"):
        automacoes.ativar(painel, a["id"], True)
    with pytest.raises(automacoes.ErroAutomacao, match="mudou"):
        automacoes.autorizar(painel, a["id"], "0" * 64)
    a = automacoes.autorizar(painel, a["id"], a["confianca"]["assinatura"])
    arquivo = painel.vault / automacoes.ARQUIVO
    original = arquivo.read_text(encoding="utf-8")
    for chave, valor in [("destino", pasta(painel, "Outra")), ("config", {"feeds": [], "maximo_por_feed": 1}), ("mapeamento", {"link": "url"})]:
        bruto = json.loads(original)
        bruto["instancias"][0][chave] = valor
        arquivo.write_text(json.dumps(bruto), encoding="utf-8")
        assert not automacoes.listar(painel)[0]["confianca"]["confiavel"]


def test_metricas_agregam_campos_preservam_edicao_manual_e_recusam_colisoes(painel, monkeypatch):
    destino = pasta(painel)
    a = instalar(painel, "numeros/cotacoes.py", destino, {"moedas": {"dolar": "USD-BRL"}})
    hoje = dt.date.today().isoformat()
    item = {"id": "numeros:" + hoje, "titulo": hoje, "atualizar": True, "campos": {"dia": hoje, "dolar": 5}}
    simular(monkeypatch, [item])
    assert executar(painel, a)["novos"] == 1
    item["campos"]["dolar"] = 6
    assert executar(painel, a)["novos"] == 1
    caminho = painel.vault / destino / (hoje + ".md")
    nota = ler_nota(caminho, painel.vault)
    assert nota.meta["dolar"] == 6
    nota.meta["dolar"] = 42
    gravar_nota(nota, versao_esperada=nota.versao)
    painel.apos_escrita(caminho, "painel")
    item["campos"]["dolar"] = 7
    assert executar(painel, a)["repetidos"] == 1
    assert ler_nota(caminho, painel.vault).meta["dolar"] == 42
    with pytest.raises(automacoes.ErroAutomacao, match="já preenche"):
        automacoes.criar(painel, "numeros/cotacoes.py", destino, {"moedas": {"dolar": "EUR-BRL"}})
    b = instalar(painel, "numeros/cotacoes.py", destino, {"moedas": {"euro": "EUR-BRL"}})
    simular(monkeypatch, [{**item, "campos": {"dia": hoje, "euro": 8}}])
    assert executar(painel, b)["novos"] == 1
    assert len(list(caminho.parent.glob("*.md"))) == 1
    nota = ler_nota(caminho, painel.vault)
    assert nota.meta["dolar"] == 42 and nota.meta["euro"] == 8


def test_mapeamento_tem_tipos_e_evitar_perda_de_campos(painel, monkeypatch):
    destino = pasta(painel)
    with pytest.raises(automacoes.ErroAutomacao, match="dois valores"):
        automacoes.prever(painel, "numeros/cotacoes.py", destino, mapeamento={"dolar": "dia"})
    with pytest.raises(automacoes.ErroAutomacao, match="não produz"):
        automacoes.prever(painel, "radar/rss.py", destino, mapeamento={"nao_existe": "outro"})
    a = instalar(painel, destino=destino, mapeamento={"tags": "assuntos"})
    simular(monkeypatch, [{"id": "rss:1", "titulo": "Artigo", "tags": ["tema"]}])
    assert executar(painel, a)["ok"]
    nota = ler_nota(painel.vault / destino / "Artigo.md", painel.vault)
    assert nota.meta["assuntos"] == ["tema"] and "tags" not in nota.meta


@pytest.mark.parametrize("destino", ["../fora", ".obsidian", "_orquestra", "nao-existe", "C:/outro/vault"])
def test_destino_recusa_traversal_internos_e_ausentes(painel, destino):
    with pytest.raises(ValueError):
        automacoes.criar(painel, "radar/rss.py", destino)


def test_segredo_ical_e_declarado_sem_herdar_outros_segredos(painel, monkeypatch):
    monkeypatch.setenv("AGENDA_PESSOAL", "https://example.test/secret.ics")
    monkeypatch.setenv("SEGREDO_NAO_DECLARADO", "nao-passar")
    a = instalar(painel, "tarefas/agenda_ics.py", config={"agendas": [{"nome": "Pessoal", "variavel": "AGENDA_PESSOAL"}]})
    assert a["confianca"]["requer"] == ["AGENDA_PESSOAL"]
    ambiente = {}
    simular(monkeypatch, [], ambiente)
    assert executar(painel, a)["ok"]
    assert ambiente["AGENDA_PESSOAL"].startswith("https://")
    assert "SEGREDO_NAO_DECLARADO" not in ambiente


def test_agenda_independente_respeita_pausa_horario_e_ultima_execucao(painel, monkeypatch):
    a = instalar(painel, "tarefas/recorrentes.py", config={"tarefas": []}, diario_as="10:00")
    chamadas = []
    async def rodar(painel, identificador, previa=False):
        chamadas.append(identificador)
        painel.gravar_estado("automacoes", identificador, {"ultima": "2026-11-13T10:01:00"})
        return {"ok": True}
    monkeypatch.setattr(automacoes, "rodar", rodar)
    asyncio.run(automacoes.verificar(painel, dt.datetime(2026, 11, 13, 11)))
    assert chamadas == []
    automacoes.ativar(painel, a["id"], True)
    asyncio.run(automacoes.verificar(painel, dt.datetime(2026, 11, 13, 9)))
    assert chamadas == []
    asyncio.run(automacoes.verificar(painel, dt.datetime(2026, 11, 13, 10, 1)))
    asyncio.run(automacoes.verificar(painel, dt.datetime(2026, 11, 13, 11)))
    assert chamadas == [a["id"]]


def test_editar_mantem_id_pausa_e_requer_novo_aceite_quando_muda(painel):
    destino = pasta(painel)
    a = instalar(painel, "numeros/cotacoes.py", destino)
    automacoes.ativar(painel, a["id"], True)
    assert automacoes.prever(painel, a["definicao"], destino, ignorar_id=a["id"])["destino"] == destino
    b = automacoes.atualizar(painel, a["id"], a["definicao"], destino, diario_as="12:30")
    assert b["id"] == a["id"] and not b["ativo"]
    assert not b["confianca"]["confiavel"]
    assert len(automacoes.listar(painel)) == 1
    with pytest.raises(automacoes.ErroAutomacao, match="mudou"):
        automacoes.autorizar(painel, b["id"], a["confianca"]["assinatura"])


def test_numeros_da_mesma_instancia_nao_podem_usar_mesmo_campo(painel):
    with pytest.raises(automacoes.ErroAutomacao, match="mesmo campo"):
        automacoes.prever(painel, "numeros/youtube_canal.py", pasta(painel), {
            "campo_inscritos": "total", "campo_visualizacoes": "total",
        })


def test_regra_recorrente_preserva_tipos_extras(painel, monkeypatch):
    a = instalar(painel, "tarefas/recorrentes.py", config={"tarefas": [
        {"titulo": "Medir", "quando": "todo dia", "estimativa": 2, "urgente": True, "tags": ["rotina"]},
    ]})
    simular(monkeypatch, [{"id": "regra:1", "titulo": "Medir", "estimativa": 2, "urgente": True, "tags": ["rotina"]}])
    assert executar(painel, a)["ok"]
    nota = ler_nota(painel.vault / a["destino"] / "Medir.md", painel.vault)
    assert nota.meta["estimativa"] == 2 and nota.meta["urgente"] is True
    assert nota.meta["tags"] == ["rotina"]


def test_configuracao_truncada_nao_bloqueia_backup_git(painel, monkeypatch):
    from orquestra import agenda, backup
    caminho = painel.vault / automacoes.ARQUIVO
    caminho.parent.mkdir(exist_ok=True)
    caminho.write_text('{"versao":', encoding="utf-8")
    painel.config.backup.auto_commit = True
    painel.mudou_desde_o_backup = True
    monkeypatch.setattr(backup, "e_repositorio", lambda vault: True)
    monkeypatch.setattr(backup, "resumo", lambda vault: {"confiavel": True})
    chamadas = []
    monkeypatch.setattr(painel, "fazer_backup", lambda enviar: chamadas.append(enviar))
    asyncio.run(agenda.verificar(painel))
    assert chamadas == [False]


def test_recriar_mesma_fonte_retoma_metricas_sem_apagar_edicoes_manuais(painel, monkeypatch):
    destino = pasta(painel)
    a = instalar(painel, "numeros/cotacoes.py", destino)
    hoje = dt.date.today().isoformat()
    item = {"id": "numeros:" + hoje, "titulo": hoje, "atualizar": True, "campos": {"dia": hoje, "dolar": 5}}
    simular(monkeypatch, [item])
    assert executar(painel, a)["novos"] == 1
    automacoes.remover(painel, a["id"])
    b = instalar(painel, "numeros/cotacoes.py", destino)
    item["campos"]["dolar"] = 6
    assert executar(painel, b)["novos"] == 1
    caminho = painel.vault / destino / (hoje + ".md")
    nota = ler_nota(caminho, painel.vault)
    assert nota.meta["dolar"] == 6
    nota.meta["dolar"] = 42
    gravar_nota(nota, versao_esperada=nota.versao)
    painel.apos_escrita(caminho, "painel")
    automacoes.remover(painel, b["id"])
    c = instalar(painel, "numeros/cotacoes.py", destino)
    item["campos"]["dolar"] = 7
    assert executar(painel, c)["ok"]
    assert ler_nota(caminho, painel.vault).meta["dolar"] == 42
    assert len(list(caminho.parent.glob("*.md"))) == 1


def test_metricas_independentes_nao_disputam_campo_com_coletor_legado_ativo(painel):
    painel.definir_coletor_ativo("numeros", "cotacoes.py", True)
    modulo = painel.modulo("numeros")
    destino = modulo.pasta_itens.relative_to(painel.vault).as_posix()
    with pytest.raises(automacoes.ErroAutomacao, match="ativa da pasta"):
        automacoes.prever(painel, "numeros/cotacoes.py", destino)


def test_destino_raiz_do_cofre_deduplica_sem_afetar_subpastas(painel, monkeypatch):
    a = instalar(painel, destino=".")
    simular(monkeypatch, [{"id": "rss:raiz", "titulo": "Artigo na raiz"}])
    assert executar(painel, a)["novos"] == 1
    assert executar(painel, a)["repetidos"] == 1
    assert (painel.vault / "Artigo na raiz.md").exists()


def test_erro_de_fonte_ical_nao_expoe_endereco_privado(painel, monkeypatch):
    endereco = "https://example.test/ical/token-privado/basic.ics"
    a = instalar(painel, "tarefas/agenda_ics.py", config={"agendas": [{"nome": "Pessoal", "url": endereco}]})
    monkeypatch.setattr(coletores, "_executar_limitado", lambda *args: (b"", ("Falha em " + endereco).encode(), 1, ""))
    resultado = executar(painel, a)
    assert not resultado["ok"] and endereco not in resultado["erro"]
    assert "[segredo omitido]" in resultado["erro"]
