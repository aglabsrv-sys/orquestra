"""Conclusão e histórico de tarefas, sempre em notas fictícias."""

import datetime as dt
from types import SimpleNamespace

from orquestra import tarefas
from orquestra.config import gravar_yaml, ler_yaml


def test_concluir_reabrir_e_conflito_preservam_nota(cliente):
    nota = cliente.painel.criar_nota("tarefas", "Revisar contrato fictício", {"status": "fazendo"}, "Texto a preservar.")
    resposta = cliente.put("/api/notas/" + nota.rel, json={"versao": nota.versao, "campos": {"status": "feito"}})
    assert resposta.status_code == 200
    concluida = cliente.painel.nota(nota.rel)
    assert str(concluida.campo("concluido_em")) == dt.date.today().isoformat()
    assert concluida.corpo == nota.corpo
    assert cliente.put("/api/notas/" + nota.rel, json={"versao": nota.versao, "campos": {"status": "a_fazer"}}).status_code == 409
    editada = cliente.painel.editar_nota(nota.rel, concluida.versao, campos={"concluido_em": "2026-01-01"}, corpo="Texto revisto.")
    assert str(editada.campo("concluido_em")) == "2026-01-01"
    reaberta = cliente.painel.editar_nota(nota.rel, editada.versao, campos={"status": "fazendo"})
    assert reaberta.campo("concluido_em") is None
    assert reaberta.corpo == "Texto revisto."


def test_quadro_recorta_pela_conclusao_preserva_abertas_e_historico(cliente):
    hoje = dt.date.today()
    painel = cliente.painel
    ocultas_antes = cliente.get("/m/tarefas?aba=v0").context["concluidas_ocultas"]
    atrasada = painel.criar_nota("tarefas", "Aberta atrasada", {"data": "2020-01-01"})
    aberta = painel.criar_nota("tarefas", "Aberta futura", {"data": (hoje + dt.timedelta(days=30)).isoformat()})
    sem_prazo = painel.criar_nota("tarefas", "Aberta sem data", {})
    atual = painel.criar_nota("tarefas", "Concluída hoje", {"status": "feito", "data": "2020-01-01"})
    antiga = painel.criar_nota("tarefas", "Concluída antiga", {"status": "feito"})
    painel.editar_nota(antiga.rel, antiga.versao, campos={"concluido_em": "2020-01-01"})
    sem_data = painel.criar_nota("tarefas", "Concluída sem data", {"status": "feito"})
    painel.editar_nota(sem_data.rel, sem_data.versao, campos={"concluido_em": None})
    resposta = cliente.get("/m/tarefas?aba=v0")
    cartoes = [c["rel"] for col in resposta.context["colunas"] for c in col["cartoes"]]
    assert atual.rel in cartoes and atrasada.rel in cartoes
    assert not {antiga.rel, sem_data.rel, aberta.rel, sem_prazo.rel} & set(cartoes)
    lista_hoje = cliente.get("/m/tarefas?aba=v1")
    assert not {aberta.rel, sem_prazo.rel, antiga.rel} & {l["cartao"]["rel"] for l in lista_hoje.context["linhas"]}
    assert resposta.context["concluidas_ocultas"] == ocultas_antes + 2
    assert resposta.context["resumo"].abertos >= 1
    todas = cliente.get("/m/tarefas?aba=v0&concluidas=todas")
    concluidas = next(c for c in todas.context["colunas"] if c["concluida"])
    assert concluidas["cartoes"][0]["rel"] == atual.rel
    assert {antiga.rel, sem_data.rel}.issubset({c["rel"] for c in concluidas["cartoes"]})
    lista = cliente.get("/m/tarefas?aba=v1&concluidas=todas")
    assert {antiga.rel, sem_data.rel, aberta.rel, sem_prazo.rel}.issubset({l["cartao"]["rel"] for l in lista.context["linhas"]})
    # A virada do dia remove a conclusão de ontem apenas do recorte diário.
    itens = painel.indice.itens("tarefas")
    amanha, _ = tarefas.recortar_quadro(itens, painel.modulo("tarefas"), hoje + dt.timedelta(days=1), "hoje")
    assert atual.rel not in {n.rel for n in amanha} and atrasada.rel in {n.rel for n in amanha}


def test_semana_comeca_na_segunda_e_nao_inclui_futuro(cliente, monkeypatch):
    hoje = dt.date(2026, 11, 18)
    painel = cliente.painel
    for titulo, dia in (("Segunda", "2026-11-16"), ("Domingo", "2026-11-15"), ("Futura", "2026-11-19")):
        nota = painel.criar_nota("tarefas", titulo, {"status": "feito"})
        painel.editar_nota(nota.rel, nota.versao, campos={"concluido_em": dia})
    visiveis, _ = tarefas.recortar_quadro(painel.indice.itens("tarefas"), painel.modulo("tarefas"), hoje, "semana")
    assert "Segunda" in {n.titulo for n in visiveis}
    assert not {"Domingo", "Futura"} & {n.titulo for n in visiveis}
    class DataFixa(dt.date):
        @classmethod
        def today(cls):
            return hoje
    monkeypatch.setattr(tarefas, "dt", SimpleNamespace(date=DataFixa, timedelta=dt.timedelta))
    nota = painel.criar_nota("tarefas", "Concluída pela regra", {"status": "feito"})
    assert str(nota.campo("concluido_em")) == hoje.isoformat()


def test_periodo_filtra_abertas_e_conclusoes_na_lista_e_quadro(cliente):
    painel = cliente.painel
    hoje = dt.date.today()
    hoje_nota = painel.criar_nota("tarefas", "Dia atual", {"data": hoje.isoformat()})
    fora = painel.criar_nota("tarefas", "Outra semana", {"data": (hoje + dt.timedelta(days=14)).isoformat()})
    sem_dia = painel.criar_nota("tarefas", "Sem agendamento", {"data": None})
    ontem = painel.criar_nota("tarefas", "Terminada ontem", {"status": "feito"})
    painel.editar_nota(ontem.rel, ontem.versao, campos={"concluido_em": (hoje - dt.timedelta(days=1)).isoformat()})
    for aba in ("v0", "v1"):
        pagina = cliente.get(f"/m/tarefas?aba={aba}&concluidas=hoje")
        assert hoje_nota.titulo in pagina.text
        assert all(n.titulo not in pagina.text for n in (fora, sem_dia, ontem))
        assert 'aria-label="Período das tarefas"' in pagina.text
        todas = cliente.get(f"/m/tarefas?aba={aba}&concluidas=todas")
        assert all(n.titulo in todas.text for n in (hoje_nota, fora, sem_dia, ontem))
    fim = hoje + dt.timedelta(days=6-hoje.weekday())
    domingo = painel.criar_nota("tarefas", "Fim da semana", {"data": fim.isoformat()})
    assert domingo.titulo in cliente.get("/m/tarefas?aba=v1&concluidas=semana").text


def test_lista_conclui_tarefas_e_outras_areas_preservam_selecao(cliente):
    pagina = cliente.get("/m/tarefas?aba=v1")
    assert "data-tarefa-conclusao" in pagina.text
    assert "data-lote-item" not in pagina.text and "data-lote-todos" not in pagina.text
    cliente.painel.adicionar_modulo("projetos")
    projeto = cliente.painel.criar_nota("projetos", "Projeto fictício", {"status": "concluido"})
    assert projeto.campo("concluido_em") is None
    # Em Projetos, a Lista mostra pastas; a seleção em lote segue nas demais áreas.
    pagina = cliente.get("/m/projetos?aba=v1")
    assert "lista-pastas" in pagina.text and "data-tarefa-conclusao" not in pagina.text
    assert "tarefas-periodos" not in cliente.get("/m/projetos?aba=v0").text
    if "notas" not in cliente.painel.indice.modulos:
        cliente.painel.adicionar_modulo("notas")
    cliente.painel.criar_nota("notas", "Nota fictícia", {})
    pagina = cliente.get("/m/notas?aba=" + next(f"v{i}" for i, v in enumerate(cliente.painel.modulo("notas").visoes) if v.tipo == "tabela"))
    assert "data-lote-item" in pagina.text and "data-tarefa-conclusao" not in pagina.text


def test_conclusao_respeita_campo_e_opcoes_personalizados(cliente, vault):
    caminho = vault / "tarefas/_modulo.yaml"
    config = ler_yaml(caminho)
    config["campos"]["situacao"] = {"tipo": "escolha", "opcoes": ["pendente", "resolvida"], "padrao": "pendente"}
    config["status"] = {"campo": "situacao", "concluidos": ["resolvida"]}
    config["visoes"][0]["agrupar_por"] = "situacao"
    gravar_yaml(caminho, config)
    cliente.painel.recarregar_config()
    nota = cliente.painel.criar_nota("tarefas", "Tarefa personalizada", {"situacao": "resolvida"})
    assert str(nota.campo("concluido_em")) == dt.date.today().isoformat()
    pagina = cliente.get("/m/tarefas?aba=v1")
    assert 'data-campo="situacao"' in pagina.text and 'data-concluir="resolvida"' in pagina.text
    assert 'data-reabrir="pendente"' in pagina.text
