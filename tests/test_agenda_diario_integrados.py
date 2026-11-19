"""Regressões de duplicação entre áreas e consultas coerentes entre painel e MCP."""

import datetime as dt
from urllib.parse import parse_qs, urlsplit

import pytest

from orquestra import calendario, diario, preparo
from orquestra.mcp_servidor import ErroDeFerramenta, Ferramentas


@pytest.mark.parametrize("primeira,segunda", [("tarefas", "agenda"), ("agenda", "tarefas")])
def test_mcp_recusa_copia_de_tarefa_datada_em_outra_area(vault, primeira, segunda):
    preparo.adicionar_modulo(vault, "agenda", exemplos=False)
    mcp = Ferramentas(vault)
    campos = {"data": "2026-11-19"}
    original = mcp.criar_item(primeira, "Planejar a semana", campos)
    antes = {p: p.read_bytes() for p in vault.rglob("*.md")}
    with pytest.raises(ErroDeFerramenta, match="já aparece na agenda local"):
        mcp.criar_item(segunda, "PLANEJAR  a semana", campos)
    assert {p: p.read_bytes() for p in vault.rglob("*.md")} == antes
    assert sum(i["caminho"] == original["caminho"] for i in mcp.agenda("2026-11-19")) == 1
    distinta = mcp.criar_item(segunda, "Planejar a semana", campos, permitir_duplicata=True)
    assert distinta["caminho"] != original["caminho"]


def test_diagnostico_e_agenda_mostram_copias_sem_apagar_ou_ocultar(cliente):
    painel = cliente.painel
    tarefa = painel.criar_nota("tarefas", "Preparar encontro", {"data": "2026-11-19"})
    painel.salvar_evento_agenda({"titulo": tarefa.titulo, "data": "2026-11-19", "dia_inteiro": True})
    # Mesmo título em outra data é outro compromisso, não candidato.
    painel.salvar_evento_agenda({"titulo": tarefa.titulo, "data": "2026-11-20", "dia_inteiro": True})
    cal = calendario.montar(painel, dt.date(2026, 11, 19))
    assert len(calendario.duplicatas(cal["eventos"])) == 1
    assert len([e for e in cal["eventos"] if e["data"] == "2026-11-19" and e["titulo"] == tarefa.titulo]) == 2
    assert any(e["data"] == "2026-11-20" and e["modulo"] == "agenda" for e in cal["eventos"])
    html = cliente.get("/agenda/2026-11-19").text
    assert "cal-conexoes" not in html
    assert "cal-duplicatas" not in html
    mcp = Ferramentas(painel.vault)
    achados = mcp.revisar_organizacao("tarefas")["achados"]["itens"]
    duplicata = next(a for a in achados if a["tipo"] == "possivel_duplicata_agenda")
    assert tarefa.rel in duplicata["caminhos"] and len(duplicata["caminhos"]) == 2


def test_conexoes_distinguem_area_sem_data_habitos_e_ical_sem_rede(vault, monkeypatch):
    from orquestra import agenda_externa, segredos

    def rede_proibida(*args):
        raise AssertionError("Esta consulta não pode acessar a rede")

    monkeypatch.setattr(agenda_externa, "baixar", rede_proibida)
    preparo.adicionar_modulo(vault, "notas", exemplos=False)
    preparo.adicionar_modulo(vault, "habitos", exemplos=False)
    mcp = Ferramentas(vault)
    estado = mcp.conexoes_agenda()
    assert estado["agenda_local"] and estado["agenda_externa_configurada"] is False
    areas = {a["id"]: a for a in estado["areas"]}
    assert areas["tarefas"]["campo_data"] == "data"
    assert areas["notas"]["campo_data"] == areas["habitos"]["campo_data"] == ""
    assert "não crie outra nota" in mcp.regras()
    chave = agenda_externa.Assinatura(vault).chave
    segredos.salvar(vault, chave, "https://example.test/privado.ics")
    estado = mcp.conexoes_agenda()
    assert estado["agenda_externa_configurada"] is True and "privado" not in str(estado)


def test_mcp_e_resumo_concordam_em_intervalos_meia_noite_e_atrasos(cliente):
    painel = cliente.painel
    hoje = dt.date.today()
    ontem = hoje - dt.timedelta(days=1)
    amanha = hoje + dt.timedelta(days=1)
    viagem = painel.salvar_evento_agenda({"titulo": "Viagem", "data": str(ontem), "data_fim": str(amanha), "dia_inteiro": True})
    encerrado = painel.salvar_evento_agenda({"titulo": "Termina à meia-noite", "data": str(ontem),
                                           "data_fim": str(hoje), "hora": "23:00", "hora_fim": "00:00"})
    prazo = painel.criar_nota("tarefas", "Prazo ainda pendente", {"data": str(ontem)})
    painel.editar_nota(prazo.rel, prazo.versao, campos={"hora": "09:00"})
    mcp = Ferramentas(painel.vault)
    consulta = {i["caminho"]: i for i in mcp.agenda()}
    assert viagem.rel in consulta and not consulta[viagem.rel]["atrasado"]
    assert encerrado.rel not in consulta
    assert consulta[prazo.rel]["atrasado"]
    resumo = diario.resumo_dia(painel, hoje)
    assert viagem.rel not in {i["rel"] for i in resumo["itens"]}
    assert encerrado.rel not in {i["rel"] for i in resumo["itens"]}
    assert prazo.rel in {i["rel"] for i in resumo["atrasados"]}


def registro_extenso(vault, total=181):
    caminho = vault / diario.PASTA_REGISTRO / f"{dt.date.today()}.md"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("# Registro sintético\n" + "".join(
        f"- 10:{i // 60:02}:{i % 60:02} | editado | tarefas/itens/Nota {i}.md | Revisão {i} | agente:mcp\n"
        for i in range(total)), encoding="utf-8")
    return caminho


def test_diario_pagina_sem_perder_registros_e_preserva_filtros(cliente):
    caminho = registro_extenso(cliente.painel.vault)
    original = caminho.read_bytes()
    consulta = diario.consultar_registro(cliente.painel.vault, dt.date.today())
    assert consulta["total"] == consulta["encontradas"] == 181
    assert len(consulta["entradas"]) == 80 and consulta["paginas"] == 3
    pagina = cliente.get("/ajustes/atividade").text
    assert pagina.count('class="diario-evento"') == 80
    segunda = cliente.get("/diario?pagina=2").text
    assert segunda.count('class="diario-evento"') == 80
    assert diario.consultar_registro(cliente.painel.vault, dt.date.today(), pagina=999)["pagina"] == 3
    filtro = diario.consultar_registro(cliente.painel.vault, dt.date.today(), q="revisao", autor="agente:mcp", tipo="editado")
    params = parse_qs(urlsplit(filtro["proximo"]).query)
    assert params["q"] == ["revisao"] and params["autor"] == ["agente:mcp"] and params["tipo"] == ["editado"]
    assert caminho.read_bytes() == original


def test_diario_busca_acentos_nao_injeta_html_e_mcp_le_sem_escrever(cliente):
    caminho = registro_extenso(cliente.painel.vault, 1)
    original = caminho.read_bytes()
    pagina = cliente.get("/diario", params={"q": "REVISAO"})
    assert pagina.status_code == 200 and pagina.text.count('class="diario-evento"') == 1
    assert "Nenhuma atividade corresponde" in cliente.get("/diario?q=inexistente").text
    assert '<script>alert(1)</script>' not in cliente.get("/diario", params={"q": "<script>alert(1)</script>"}).text
    mcp = Ferramentas(cliente.painel.vault)
    assert mcp.diario_dia()["total"] == 1
    assert mcp.diario_dia()["entradas"][0]["autor"] == "agente:mcp"
    assert caminho.read_bytes() == original
    with pytest.raises(ErroDeFerramenta, match="AAAA-MM-DD"):
        mcp.diario_dia("ontem")
    assert cliente.get("/ajustes/atividade?dia=0001-01-01").status_code == 200


def test_anotacao_diaria_reaproveita_a_mesma_nota_e_separa_o_registro(cliente):
    hoje = dt.date.today()
    rota = f"/api/diario/anotacao/{hoje}"
    assert 'id="diario-escrever"' in cliente.get(f"/diario?dia={hoje}").text
    assert cliente.post(rota, json={}, headers={"X-Orquestra-Vault": "outro-cofre"}).status_code == 409
    primeira = cliente.post(rota, json={})
    assert primeira.status_code == 200
    url = primeira.json()["url"]
    rel = diario.caminho_anotacao(hoje)
    nota = cliente.painel.nota(rel)
    resposta = cliente.put("/api/notas/" + rel, json={"versao": nota.versao, "corpo": "**Anotação pessoal**"})
    assert resposta.status_code == 200
    assert cliente.post(rota, json={}).json()["url"] == url
    assert list((cliente.painel.vault / diario.PASTA_ANOTACOES).glob("*.md")) == [nota.caminho]
    assert 'data-iniciar-edicao' in cliente.get(url + "?editar=1").text
    assert f'href="/diario?dia={hoje}"' in cliente.get(url).text
    pagina = cliente.get("/diario").text
    assert "<strong>Anotação pessoal</strong>" in pagina and "diario-evento" not in pagina
    assert "diario-evento" in cliente.get("/ajustes/atividade").text
    assert "Atividade observada" not in cliente.get(f"/dia/{hoje}").text
