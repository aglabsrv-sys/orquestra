"""O dock chama atenção para pendências, sem contar o estoque de arquivos."""

import datetime as dt

from orquestra.apresentacao import montar_dock
from orquestra.indice import espera_decisao


def test_itens_abertos_sem_prazo_nem_decisao_nao_viram_notificacao(painel):
    modulo = painel.criar_modulo("Referências", "nota", com_quadro=True)
    painel.criar_nota(modulo.id, "Uma referência para consultar", campos={"status": "a_fazer"})
    assert painel.indice.resumo(modulo).abertos == 1
    item = next(m for m in montar_dock(painel, "inicio", dt.date.today())["modulos"] if m["id"] == modulo.id)
    assert item["selo"] == 0


def test_concluir_uma_nota_com_pergunta_remove_a_pendencia(cliente):
    painel = cliente.painel
    modulo = painel.modulo("tarefas")
    nota = painel.criar_nota(modulo.id, "Aprovação encerrada", campos={"status": "aguardando", "pergunta": "Podemos concluir?"})
    antes = cliente.get("/api/resumo").json()["decidir"]
    assert espera_decisao(nota, modulo)
    nota = painel.editar_nota(nota.rel, nota.versao, campos={"status": "feito"})
    assert not espera_decisao(nota, modulo)
    assert cliente.get("/api/resumo").json()["decidir"] == antes - 1
    assert "Aprovação encerrada" not in cliente.get("/decidir").text


def test_entrada_mantem_decisoes_quando_capturas_sao_desligadas(cliente):
    cliente.painel.desligar_modulo("entrada")
    legado = cliente.get("/decidir?modulo=conteudo", follow_redirects=False)
    assert legado.status_code == 303
    assert legado.headers["location"] == "/entrada?modulo=conteudo&aba=decisoes"
    pagina = cliente.get("/m/entrada")
    assert pagina.status_code == 200 and "Para decidir" in pagina.text
    assert not pagina.context["tem_capturas"]
    assert pagina.context["dock"]["entrada"]["selo"] == cliente.get("/api/resumo").json()["decidir"]
    assert pagina.context["dock"]["entrada"]["ativo"]


def test_responder_pergunta_mantem_item_cujo_status_ainda_exige_decisao(cliente):
    painel = cliente.painel
    nota = painel.criar_nota("tarefas", "Revisão de pauta", {"status": "aguardando"})
    nota = painel.editar_nota(nota.rel, nota.versao, campos={"pergunta": "Pode revisar?"})
    resposta = cliente.put("/api/notas/" + nota.rel, json={
        "versao": nota.versao, "campos": {"resposta": "Sim.", "pergunta": ""},
    })
    assert resposta.status_code == 200
    assert resposta.json()["decisao_pendente"]
    fila = cliente.get("/entrada", params={"aba": "decisoes", "nota": nota.rel})
    assert "Revisão de pauta" in fila.text and "Pode revisar?" not in fila.text

