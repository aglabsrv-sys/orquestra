"""Prazos continuam pendentes e panoramas grandes podem ser consultados até o fim."""

from __future__ import annotations

import datetime as dt

from orquestra.mcp_servidor import Ferramentas


def test_panorama_mantem_tarefas_com_horario_ou_data_fim_nos_atrasados(vault):
    ontem = dt.date.today() - dt.timedelta(days=1)
    anteontem = ontem - dt.timedelta(days=1)
    itens = {
        "Prazo com horario": f'data: {ontem}\nhora: "09:00"\n',
        "Prazo com termino": f"data: {anteontem}\ndata_fim: {ontem}\n",
        "Compromisso encerrado": f"data: {anteontem}\ndata_fim: {ontem}\ncategoria: Compromisso\n",
    }
    caminhos = {}
    for titulo, campos in itens.items():
        caminho = vault / "tarefas" / "itens" / f"{titulo}.md"
        caminho.write_text(f"---\nstatus: a_fazer\n{campos}---\n", encoding="utf-8")
        caminhos[titulo] = caminho.relative_to(vault).as_posix()

    panorama = Ferramentas(vault).panorama(area="tarefas", limite=100)
    atrasados = {item["caminho"] for item in panorama["grupos"]["atrasados"]["itens"]}
    assert caminhos["Prazo com horario"] in atrasados
    assert caminhos["Prazo com termino"] in atrasados
    assert caminhos["Compromisso encerrado"] not in atrasados
    for grupo in ("hoje", "proximos"):
        assert not set(caminhos.values()) & {
            item["caminho"] for item in panorama["grupos"][grupo]["itens"]
        }


def test_panorama_pagina_mais_de_cem_atrasados_da_mesma_area(vault):
    area = vault / "fila"
    itens = area / "itens"
    itens.mkdir(parents=True)
    (area / "_modulo.yaml").write_text(
        "nome: Fila\n"
        "campos:\n"
        "  status:\n"
        "    tipo: escolha\n"
        "    opcoes: [pendente, feito]\n"
        "  data:\n"
        "    tipo: data\n"
        "campo_data: data\n"
        "status:\n"
        "  concluidos: [feito]\n",
        encoding="utf-8",
    )
    ontem = dt.date.today() - dt.timedelta(days=1)
    esperados = [f"fila/itens/Pendente {numero:03}.md" for numero in range(105)]
    for rel in esperados:
        (vault / rel).write_text(f"---\nstatus: pendente\ndata: {ontem}\n---\n", encoding="utf-8")

    ferramentas = Ferramentas(vault)
    primeira = ferramentas.panorama(area="fila", limite=100)["grupos"]["atrasados"]
    assert primeira["total"] == 105
    assert len(primeira["itens"]) == 100 and primeira["limitado"]
    assert primeira["proximo_deslocamento"] == 100

    segunda = ferramentas.panorama(
        area="fila", limite=100, deslocamento=primeira["proximo_deslocamento"],
    )["grupos"]["atrasados"]
    assert segunda["total"] == 105 and len(segunda["itens"]) == 5
    assert segunda["proximo_deslocamento"] is None
    recebidos = [item["caminho"] for item in primeira["itens"] + segunda["itens"]]
    assert recebidos == esperados
