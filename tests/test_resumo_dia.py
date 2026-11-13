"""O resumo usa datas e estados reais, sem inventar histórico de atividade."""
import datetime as dt
from types import SimpleNamespace

from orquestra import automacoes, calendario, coletores, diario
from orquestra.apresentacao import url_nota
from orquestra.indice import Indice
from orquestra.modulos import Campo, Modulo
from orquestra.notas import Nota


HOJE = dt.date(2030, 5, 16)


def contexto(tmp_path):
    indice = Indice(tmp_path)
    indice.modulos = {
        "tarefas": Modulo("tarefas", tmp_path / "tarefas", "Tarefas", campo_data="data",
            campos={"status": Campo("status", "escolha", ["aberto", "aguardando", "feito"])},
            concluidos=["feito"], decidir=["aguardando"]),
        "notas": Modulo("notas", tmp_path / "notas", "Notas", campo_data="data"),
    }
    return SimpleNamespace(vault=tmp_path, indice=indice)


def adicionar(painel, pasta, titulo, **meta):
    rel = f"{pasta}/itens/{titulo}.md"
    nota = Nota(painel.vault / rel, rel, meta={"titulo": titulo, **meta})
    painel.indice.notas[rel] = nota
    painel.indice._reindexar()
    return nota


def titulos(resumo, grupo):
    return {item["titulo"] for item in resumo[grupo]}


def test_pendencias_exigem_status_e_concluidos_nao_voltam_para_decidir(tmp_path):
    painel = contexto(tmp_path)
    adicionar(painel, "tarefas", "Vencida", data="2030-05-15", status="aberto")
    adicionar(painel, "tarefas", "Prazo hoje", data=HOJE, status="aberto")
    adicionar(painel, "tarefas", "Concluída", data=HOJE, status="feito", pergunta="Ainda aprova?")
    adicionar(painel, "tarefas", "Aprovar", status="aguardando")
    adicionar(painel, "notas", "Nota antiga", data="2030-05-15")
    adicionar(painel, "notas", "Nota de hoje", data=HOJE)
    r = diario.resumo_dia(painel, HOJE, HOJE)
    assert titulos(r, "itens") == {"Prazo hoje", "Nota de hoje"}
    assert titulos(r, "atrasados") == {"Vencida"}
    assert titulos(r, "decisoes") == {"Aprovar"}


def test_dia_historico_mostra_estado_atual_e_nunca_pendencias_de_hoje(tmp_path):
    painel = contexto(tmp_path)
    ontem = HOJE - dt.timedelta(days=1)
    adicionar(painel, "tarefas", "Concluída depois", data=ontem, status="feito")
    adicionar(painel, "tarefas", "Antes de ontem", data="2030-05-14", status="aberto")
    adicionar(painel, "tarefas", "Pendente agora", status="aguardando")
    r = diario.resumo_dia(painel, ontem, HOJE)
    assert titulos(r, "itens") == {"Concluída depois"}
    assert r["itens"][0]["concluido"] and r["historico"]
    assert not r["atrasados"] and not r["decisoes"]
    assert r["anterior"] == "/dia/2030-05-14" and r["proximo"] == "/dia/2030-05-16"


def test_compromisso_multidia_e_fim_exclusivo_sem_virar_tarefa_atrasada(tmp_path):
    painel = contexto(tmp_path)
    adicionar(painel, "tarefas", "Turno encerrado", status="aberto", data="2030-05-15",
              data_fim="2030-05-16", hora="23:00", hora_fim="00:00")
    adicionar(painel, "tarefas", "Encontro em andamento", status="aberto", data="2030-05-15",
              data_fim="2030-05-16", hora="23:00", hora_fim="10:00")
    adicionar(painel, "tarefas", "Às nove", status="aberto", data=HOJE, hora="09:00", hora_fim="10:00")
    r = diario.resumo_dia(painel, HOJE, HOJE)
    assert titulos(r, "itens") == {"Encontro em andamento", "Às nove"}
    assert not r["atrasados"]


def test_atividade_vem_do_registro_e_agrupa_gravacoes_sem_inventar_eventos(tmp_path):
    painel = contexto(tmp_path)
    nota = adicionar(painel, "tarefas", "Documento", status="aberto")
    nota.mtime = dt.datetime(2030, 5, 16, 10).timestamp()
    assert not diario.resumo_dia(painel, HOJE, HOJE)["atividade"]
    pasta = tmp_path / diario.PASTA_REGISTRO
    pasta.mkdir(parents=True)
    (pasta / f"{HOJE}.md").write_text(
        f"- 09:00:00 | criado | {nota.rel} | | painel\n"
        f"- 10:00:00 | editado | {nota.rel} | status: aberto | agente\n"
        "- 11:00:00 | removido | notas/itens/Removida.md | | externo\n", encoding="utf-8")
    r = diario.resumo_dia(painel, HOJE, HOJE)
    assert r["totais"]["atividade"] == 3 and r["totais"]["arquivos"] == 2
    assert r["atividade"][0]["titulo"] == "Removida" and not r["atividade"][0]["url"]
    assert r["atividade"][1]["quantidade"] == 2 and r["atividade"][1]["hora"] == "10:00:00"
    assert not diario.resumo_dia(painel, HOJE - dt.timedelta(days=1), HOJE)["atividade"]


def test_habitos_usam_confirmacoes_da_data_sem_sugerir_instalacao(tmp_path):
    painel = contexto(tmp_path)
    assert not diario.resumo_dia(painel, HOJE, HOJE)["habitos"]
    painel.indice.modulos["habitos"] = Modulo("habitos", tmp_path / "habitos", "Hábitos",
        campos={"registros": Campo("registros", "lista")})
    adicionar(painel, "habitos", "Ler", registros=[HOJE.isoformat()], meta_semanal=3)
    assert diario.resumo_dia(painel, HOJE, HOJE)["totais"]["habitos_feitos"] == 1
    r = diario.resumo_dia(painel, HOJE - dt.timedelta(days=1), HOJE)
    assert r["totais"]["habitos_feitos"] == 0 and r["habitos"][0]["semana"] == 0
    assert not diario.resumo_dia(painel, HOJE + dt.timedelta(days=1), HOJE)["habitos"]


def test_pagina_dia_preserva_navegacao_e_escapa_conteudo(cliente):
    hoje = dt.date.today()
    nota = cliente.painel.criar_nota("tarefas", "<script>doMal()</script>", {"data": hoje.isoformat()})
    pagina = cliente.get(f"/dia/{hoje}")
    assert pagina.status_code == 200, pagina.text
    assert "dia-pagina" in pagina.text and "grade-cartoes" not in pagina.text
    assert f'href="/dia/{hoje - dt.timedelta(days=1)}"' in pagina.text
    assert "<script>doMal()</script>" not in pagina.text and "&lt;script&gt;doMal()&lt;/script&gt;" in pagina.text
    assert url_nota(nota.rel) in pagina.text


def test_tarefas_independentes_entram_no_resumo_e_agenda_com_data_mapeada(painel):
    destino = painel.vault / "Projetos" / "Rotinas"
    destino.mkdir(parents=True)
    for _ in range(2):
        automacoes.criar(painel, "tarefas/recorrentes.py", "Projetos/Rotinas", mapeamento={"data": "prazo"})
    contrato = automacoes.destinos_tarefas(painel)[0]
    coletor = next(c for c in painel.modulo("tarefas").coletores if c.script == "recorrentes.py")
    notas, _ = coletores.importar(painel.indice, contrato["modulo"], coletor,
        [{"id": "teste:rotina", "titulo": "Rotina independente", "prazo": HOJE.isoformat()}], escopo_pasta=True)
    for nota in notas:
        painel.apos_escrita(nota.caminho, "coletor:recorrentes")
    (destino / "Nota comum.md").write_text("---\ndata: 2030-05-16\nprazo: 2030-05-16\n---\nAnotação", encoding="utf-8")
    painel.indice.sincronizar()
    resumo = diario.resumo_dia(painel, HOJE, HOJE)
    assert [i["titulo"] for i in resumo["itens"]] == ["Rotina independente"]
    assert not any(i["rel"] == notas[0].rel for grupo in ("atrasados", "decisoes") for i in resumo[grupo])
    eventos = calendario.montar(painel, HOJE, "dia")["eventos"]
    assert [e["titulo"] for e in eventos] == ["Rotina independente"]
    assert not eventos[0]["editavel"] and eventos[0]["url"] == url_nota(notas[0].rel)


def test_ical_independente_preserva_hora_e_modulo_existente_nao_duplica(cliente):
    painel = cliente.painel
    destino = painel.vault / "Compromissos"
    destino.mkdir()
    automacoes.criar(painel, "tarefas/agenda_ics.py", "Compromissos")
    contrato = automacoes.destinos_tarefas(painel)[0]
    coletor = next(c for c in painel.modulo("tarefas").coletores if c.script == "agenda_ics.py")
    notas, _ = coletores.importar(painel.indice, contrato["modulo"], coletor,
        [{"id": "agenda:reuniao", "titulo": "09:30 Reunião importada", "data": HOJE.isoformat()}], escopo_pasta=True)
    for nota in notas:
        painel.apos_escrita(nota.caminho, "coletor:agenda_ics")
    automacoes.criar(painel, "tarefas/recorrentes.py", "tarefas/itens")
    tarefa = painel.criar_nota("tarefas", "Tarefa no módulo", {"data": HOJE.isoformat(), "status": "feito"})
    resumo = diario.resumo_dia(painel, HOJE, HOJE)
    reuniao = next(i for i in resumo["itens"] if i["rel"] == notas[0].rel)
    assert reuniao["hora"] == "09:30" and reuniao["tipo"] == "compromisso"
    assert not any(i["rel"] == tarefa.rel for i in resumo["itens"])
    fontes = calendario.fontes(painel)
    assert sum(n.rel == tarefa.rel for _, notas_fonte in fontes for n in notas_fonte) == 1
    for visao in calendario.VISOES:
        pagina = cliente.get(f"/agenda/{HOJE}?visao={visao}")
        assert pagina.status_code == 200, pagina.text
        assert f'href="{url_nota(notas[0].rel)}"' in pagina.text
        assert f'data-evento="{notas[0].rel}"' not in pagina.text
