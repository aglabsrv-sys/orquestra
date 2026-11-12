"""Schema dos módulos: leitura do _modulo.yaml, conversão e validação de valores."""

from __future__ import annotations

import datetime as dt

import pytest

from orquestra.modulos import Campo, ValorInvalido, carregar_modulo, converter, descobrir, padroes, rotulo, validar


def test_descobre_os_modulos_do_modelo_na_ordem(vault):
    assert list(descobrir(vault)) == ["tarefas", "conteudo", "radar", "numeros", "entrada"]


def test_le_o_schema_de_tarefas(vault):
    m = carregar_modulo(vault / "tarefas")
    assert m.nome == "Tarefas"
    assert m.campos["status"].opcoes == ["a_fazer", "fazendo", "aguardando", "feito"]
    assert m.campos["status"].obrigatorio
    assert m.campo_data == "data"
    assert m.concluidos == ["feito"]
    assert m.decidir == ["aguardando"]
    assert [v.tipo for v in m.visoes] == ["kanban", "tabela"]
    assert m.acoes[0].definir == {"status": "feito"}
    assert m.avisos == []


def test_le_os_coletores_do_radar(vault):
    m = carregar_modulo(vault / "radar")
    scripts = {c.script: c for c in m.coletores}
    assert set(scripts) == {"youtube_rss.py", "rss.py", "google_trends.py", "youtube_api.py"}
    assert scripts["youtube_rss.py"].a_cada == "6h"
    assert scripts["google_trends.py"].diario_as == "07:00"
    assert scripts["youtube_api.py"].requer == ["YOUTUBE_API_KEY"]
    assert not any(c.ativo for c in m.coletores)  # nada roda sozinho sem o usuário ligar


def test_modulo_com_problemas_vira_aviso_e_nao_erro(tmp_path):
    pasta = tmp_path / "financas"
    pasta.mkdir()
    (pasta / "_modulo.yaml").write_text(
        "campos:\n  valor: {tipo: dinheiro}\n  tipo: {tipo: escolha}\nvisoes:\n  - {tipo: mapa}\n", encoding="utf-8"
    )
    m = carregar_modulo(pasta)
    assert m.nome == "Financas"
    assert m.campos["valor"].tipo == "texto"
    assert len(m.avisos) == 3
    assert m.visoes  # sempre sobra pelo menos uma visão


def test_converter_cada_tipo():
    assert converter(Campo("s", "escolha", ["a", "b"]), "a") == "a"
    assert converter(Campo("d", "data"), "2026-03-01") == dt.date(2026, 3, 1)
    assert converter(Campo("d", "data"), "hoje") == dt.date.today()
    assert converter(Campo("t", "lista"), "um, dois ,, tres") == ["um", "dois", "tres"]
    assert converter(Campo("n", "numero"), "3") == 3
    assert converter(Campo("n", "numero"), "2,5") == 2.5
    assert converter(Campo("b", "booleano"), "sim") is True
    assert converter(Campo("x", "texto"), "  oi  ") == "oi"


def test_valor_vazio_remove_o_campo():
    assert converter(Campo("d", "data"), "") is None
    assert converter(Campo("t", "lista"), "") is None
    assert converter(Campo("x", "texto"), None) is None


def test_converter_recusa_o_que_esta_fora_do_schema():
    with pytest.raises(ValorInvalido, match="não é uma opção"):
        converter(Campo("status", "escolha", ["a", "b"]), "c")
    with pytest.raises(ValorInvalido, match="AAAA-MM-DD"):
        converter(Campo("data", "data"), "15/01/2026")
    with pytest.raises(ValorInvalido, match="número"):
        converter(Campo("n", "numero"), "muito")


def test_padroes_de_uma_nota_nova(vault):
    m = carregar_modulo(vault / "tarefas")
    assert padroes(m) == {"status": "a_fazer", "prioridade": "media", "origem": "humano"}


def test_validar_aponta_o_que_esta_errado(vault):
    m = carregar_modulo(vault / "tarefas")
    assert validar(m, {"status": "a_fazer", "data": dt.date(2026, 1, 1), "tags": ["x"], "extra": "livre"}) == []
    problemas = validar(m, {"status": "inventado", "data": "amanhã", "tags": "solta"})
    assert len(problemas) == 3
    assert validar(m, {}) == ["Falta o campo obrigatório 'status'."]


def test_rotulo():
    assert rotulo("a_fazer") == "A fazer"
    assert rotulo("virou_ideia") == "Virou ideia"
