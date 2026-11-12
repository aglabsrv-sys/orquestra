"""Coletores (agendamento, importação) e o diário de mudanças."""

from __future__ import annotations

import datetime as dt
import shutil

from orquestra import coletores, confianca, diario
from orquestra.modulos import ColetorDef
from orquestra.notas import ler_nota

COLETOR_FALSO = '''
import json, os
config = json.loads(os.environ["ORQUESTRA_CONFIG"])
print("uma linha qualquer que não é JSON")
for i in range(config["quantos"]):
    print(json.dumps({"id": f"teste:{i}", "titulo": f"Item {i}: com dois-pontos", "fonte": "teste",
                      "link": "https://exemplo.com/" + str(i), "publicado_em": "2026-01-0" + str(i + 1),
                      "status": "inventado", "campo_livre": "ok", "corpo": "Resumo " + str(i)}, ensure_ascii=False))
'''


def instalar_coletor_falso(painel, monkeypatch, quantos=3):
    # Sem uv nos testes: o script roda com o mesmo Python, sem baixar nada.
    monkeypatch.setattr(shutil, "which", lambda nome: None)
    modulo = painel.modulo("radar")
    (modulo.pasta / "maquina/coletores/falso.py").write_text(COLETOR_FALSO, encoding="utf-8")
    coletor = ColetorDef(script="falso.py", nome="Falso", config={"quantos": quantos})
    modulo.coletores.append(coletor)
    autorizar_coletor(painel, modulo, coletor)
    return modulo, coletor


def autorizar_coletor(painel, modulo, coletor):
    """Cada versão sintética é aprovada explicitamente, como no fluxo local."""
    revisao = confianca.resumo(painel.vault, modulo, coletor)
    assert revisao["assinatura"] and not revisao.get("erro")
    confianca.autorizar(painel.vault, modulo, coletor, revisao["assinatura"])


# ---------------------------------------------------------------- agendamento


def test_intervalos():
    assert coletores.intervalo_em_segundos("30m") == 1800
    assert coletores.intervalo_em_segundos("6h") == 21600
    assert coletores.intervalo_em_segundos("1d") == 86400
    assert coletores.intervalo_em_segundos("logo") is None
    assert coletores.intervalo_em_segundos(None) is None


def test_devido_por_intervalo():
    c = ColetorDef(script="x.py", nome="x", a_cada="6h")
    agora = dt.datetime(2026, 1, 10, 12, 0)
    assert coletores.devido(c, None, agora)
    assert not coletores.devido(c, agora - dt.timedelta(hours=5), agora)
    assert coletores.devido(c, agora - dt.timedelta(hours=7), agora)


def test_devido_por_horario_recupera_o_que_perdeu():
    c = ColetorDef(script="x.py", nome="x", diario_as="07:00")
    dia = dt.datetime(2026, 1, 10)
    # Já rodou hoje às 7h05: só amanhã.
    assert not coletores.devido(c, dia.replace(hour=7, minute=5), dia.replace(hour=15))
    # Rodou ontem e hoje ainda são 6h: espera.
    assert not coletores.devido(c, dia.replace(hour=7, minute=5) - dt.timedelta(days=1), dia.replace(hour=6))
    # Rodou ontem e hoje já passou das 7h: roda.
    assert coletores.devido(c, dia.replace(hour=7, minute=5) - dt.timedelta(days=1), dia.replace(hour=7, minute=1))
    # O computador ficou desligado dois dias e voltou de madrugada: roda o que perdeu.
    assert coletores.devido(c, dia - dt.timedelta(days=2), dia.replace(hour=3))


# ---------------------------------------------------------------- execução


def test_coletor_vira_notas_e_nao_duplica(painel, monkeypatch):
    modulo, coletor = instalar_coletor_falso(painel, monkeypatch)

    primeira = painel.rodar_coletor_agora(modulo, coletor)
    assert (primeira.ok, primeira.novos, primeira.repetidos) == (True, 3, 0)

    nota = ler_nota(modulo.pasta_itens / "Item 0 com dois-pontos.md", painel.vault)
    assert nota.titulo == "Item 0: com dois-pontos"
    assert nota.campo("origem") == "coletor"
    assert nota.campo("coletor") == "falso"
    assert nota.campo("id_externo") == "teste:0"
    assert nota.campo("status") == "novo"  # "inventado" não existe no schema: fica o padrão
    assert nota.campo("publicado_em") == "2026-01-01"
    assert nota.campo("campo_livre") == "ok"
    assert nota.corpo.strip() == "Resumo 0"

    segunda = painel.rodar_coletor_agora(modulo, coletor)
    assert (segunda.novos, segunda.repetidos) == (0, 3)
    assert painel.ultima_coleta("radar", "falso.py")["repetidos"] == 3


def test_item_arquivado_nao_volta(painel, monkeypatch):
    modulo, coletor = instalar_coletor_falso(painel, monkeypatch, quantos=1)
    painel.rodar_coletor_agora(modulo, coletor)
    painel.arquivar("radar/itens/Item 0 com dois-pontos.md")
    assert painel.rodar_coletor_agora(modulo, coletor).novos == 0


def test_script_com_erro_vira_mensagem(painel, monkeypatch):
    modulo, coletor = instalar_coletor_falso(painel, monkeypatch)
    (modulo.pasta / "maquina/coletores/falso.py").write_text("raise SystemExit('a fonte está fora do ar')", encoding="utf-8")
    autorizar_coletor(painel, modulo, coletor)
    resultado = painel.rodar_coletor_agora(modulo, coletor)
    assert not resultado.ok
    assert "fora do ar" in resultado.erro
    assert painel.ultima_coleta("radar", "falso.py")["ok"] is False


def test_script_que_nao_existe(painel):
    modulo = painel.modulo("radar")
    resultado = painel.rodar_coletor_agora(modulo, ColetorDef(script="sumiu.py", nome="x"))
    assert not resultado.ok and "não encontrado" in resultado.erro


# ---------------------------------------------------------------- diário


def test_mudanca_feita_por_fora_entra_no_diario(painel):
    rel = "tarefas/itens/Renovar o domínio do site.md"
    caminho = painel.vault / rel
    # Simula um agente editando o arquivo direto no disco.
    caminho.write_text(caminho.read_text(encoding="utf-8").replace("status: a_fazer", "status: feito") + "\nPago.\n", encoding="utf-8")
    painel.ao_mudar_arquivos({caminho})

    entrada = diario.ler_registro(painel.vault, dt.date.today())[0]
    assert (entrada.tipo, entrada.rel, entrada.autor) == ("editado", rel, "externo")
    assert "status: a_fazer → feito" in entrada.detalhe
    assert "texto: +2 −0 linhas" in entrada.detalhe  # a linha em branco e "Pago."
    assert painel.nota(rel).campo("status") == "feito"  # o índice acompanhou


def test_a_mesma_mudanca_nao_e_registrada_duas_vezes(painel):
    nota = painel.criar_nota("tarefas", "Tarefa pelo painel")
    painel.ao_mudar_arquivos({nota.caminho})  # o vigia avisa da gravação que o próprio painel fez
    entradas = [e for e in diario.ler_registro(painel.vault, dt.date.today()) if e.rel == nota.rel]
    assert [(e.tipo, e.autor) for e in entradas] == [("criado", "painel")]


def test_arquivo_removido_por_fora(painel):
    rel = "tarefas/itens/Renovar o domínio do site.md"
    (painel.vault / rel).unlink()
    painel.ao_mudar_arquivos({painel.vault / rel})
    assert rel not in painel.indice.notas
    assert diario.ler_registro(painel.vault, dt.date.today())[0].tipo == "removido"


def test_mudar_o_modulo_yaml_recarrega_o_schema(painel):
    caminho = painel.vault / "tarefas/_modulo.yaml"
    caminho.write_text(caminho.read_text(encoding="utf-8").replace("nome: Tarefas", "nome: Afazeres"), encoding="utf-8")
    painel.ao_mudar_arquivos({caminho})
    assert painel.modulo("tarefas").nome == "Afazeres"


def test_o_registro_do_diario_nao_gera_registro(painel):
    painel.criar_nota("tarefas", "Qualquer")
    registro = painel.vault / diario.PASTA_REGISTRO / f"{dt.date.today()}.md"
    antes = registro.read_text(encoding="utf-8")
    painel.ao_mudar_arquivos({registro})
    assert registro.read_text(encoding="utf-8") == antes


def test_sessoes_dos_agentes_aparecem_no_diario(painel):
    assert "agente de exemplo" in diario.ler_sessoes(painel.vault, dt.date.today())
    assert dt.date.today() in diario.dias_com_registro(painel.vault)
