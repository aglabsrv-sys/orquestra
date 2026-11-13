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

