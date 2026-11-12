"""Visão de gráfico: a evolução de cada campo numérico de um módulo ao longo dos dias.

Cada número ganha o seu próprio quadro (valor atual, variação no período e uma
linha do tempo). Não misturamos números diferentes num gráfico só: seguidores e
receita têm escalas que não se comparam, e dois eixos no mesmo gráfico enganam.

A geometria da linha é calculada aqui e vai pronta no HTML, como SVG. O navegador
só cuida do que é interação: a linha-guia e o valor sob o ponteiro.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from orquestra.indice import Indice
from orquestra.modulos import Modulo, Visao
from orquestra.notas import Nota

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Área de desenho, em unidades do viewBox do SVG.
LARGURA, ALTURA = 320, 120
MARGEM_ESQ, MARGEM_DIR, MARGEM_TOPO, MARGEM_BASE = 6, 10, 10, 8

_DATA_NO_NOME = re.compile(r"\d{4}-\d{2}-\d{2}")


def numero(valor: float, compacto: bool = False) -> str:
    """Número no formato brasileiro: 1.284 · 12,9 mil · 4,2 mi · 119,90."""
    if compacto and abs(valor) >= 1_000_000:
        return f"{valor / 1_000_000:.1f}".replace(".", ",").removesuffix(",0") + " mi"
    if compacto and abs(valor) >= 10_000:
        return f"{valor / 1_000:.1f}".replace(".", ",").removesuffix(",0") + " mil"
    if float(valor).is_integer():
        return f"{int(valor):,}".replace(",", ".")
    return f"{valor:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def dia_curto(dia: dt.date, com_ano: bool = False) -> str:
    texto = f"{dia.day} {MESES[dia.month - 1]}"
    return f"{texto} {dia.year}" if com_ano else texto


def _dia_da_nota(nota: Nota, campo_dia: str | None) -> dt.date | None:
    """A data de um registro: o campo de data do módulo ou, na falta dele, o nome do arquivo."""
    valor = nota.meta.get(campo_dia) if campo_dia else None
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    for texto in (str(valor or ""), nota.caminho.stem):
        achado = _DATA_NO_NOME.search(texto)
        if achado:
            try:
                return dt.date.fromisoformat(achado.group(0))
            except ValueError:
                pass
    return None


def campo_do_dia(modulo: Modulo) -> str | None:
    return modulo.campo_data or next((c.nome for c in modulo.campos.values() if c.tipo == "data"), None)


def montar(indice: Indice, modulo: Modulo, visao: Visao, hoje: dt.date) -> list[dict[str, Any]]:
    """Um quadro por campo numérico, com os pontos dos últimos `visao.dias` dias."""
    nomes = [c for c in (visao.campos or modulo.campos_numericos) if c in modulo.campos_numericos]
    campo_dia = campo_do_dia(modulo)
    inicio = hoje - dt.timedelta(days=visao.dias - 1)

    por_campo: dict[str, dict[dt.date, float]] = {n: {} for n in nomes}
    for nota in indice.notas_em(modulo.id, "itens"):
        dia = _dia_da_nota(nota, campo_dia)
        if dia is None or dia < inicio or dia > hoje:
            continue
        for nome in nomes:
            valor = nota.meta.get(nome)
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                continue
            # Vários registros no mesmo dia (lançamentos, por exemplo) somam.
            por_campo[nome][dia] = por_campo[nome].get(dia, 0.0) + float(valor)

    quadros = []
    for nome in nomes:
        pontos = sorted(por_campo[nome].items())
        quadros.append(_quadro(nome, modulo.campos[nome].rotulo, pontos, inicio, hoje, visao.dias))
    return quadros


def _quadro(nome: str, rotulo: str, pontos: list[tuple[dt.date, float]], inicio: dt.date, hoje: dt.date, dias: int) -> dict[str, Any]:
    quadro: dict[str, Any] = {"campo": nome, "rotulo": rotulo, "dias": dias, "vazio": not pontos, "pontos": []}
    if not pontos:
        return quadro

    valores = [v for _, v in pontos]
    minimo, maximo = min(valores), max(valores)
    if minimo == maximo:  # linha reta: abre espaço para ela ficar no meio do quadro
        folga = abs(minimo) * 0.1 or 1.0
        minimo, maximo = minimo - folga, maximo + folga
    area_x = LARGURA - MARGEM_ESQ - MARGEM_DIR
    area_y = ALTURA - MARGEM_TOPO - MARGEM_BASE
    # O eixo começa no primeiro registro, não no começo da janela: quem começou a
    # anotar há uma semana vê a semana inteira, e não uma linha espremida no canto.
    inicio = max(inicio, pontos[0][0])
    total_dias = max((hoje - inicio).days, 1)

    def x(dia: dt.date) -> float:
        return round(MARGEM_ESQ + area_x * (dia - inicio).days / total_dias, 1)

    def y(valor: float) -> float:
        return round(MARGEM_TOPO + area_y * (1 - (valor - minimo) / (maximo - minimo)), 1)

    coordenadas = [(x(d), y(v)) for d, v in pontos]
    linha = " ".join(f"{'M' if i == 0 else 'L'}{px} {py}" for i, (px, py) in enumerate(coordenadas))
    base = ALTURA - MARGEM_BASE
    area = f"{linha} L{coordenadas[-1][0]} {base} L{coordenadas[0][0]} {base} Z" if len(coordenadas) > 1 else ""

    primeiro_dia, primeiro = pontos[0]
    ultimo_dia, ultimo = pontos[-1]
    variacao = ultimo - primeiro
    quadro.update(
        {
            "linha": linha,
            "area": area,
            "fim": {"x": coordenadas[-1][0], "y": coordenadas[-1][1]},
            "atual": numero(ultimo, compacto=True),
            "atual_exato": numero(ultimo),
            "quando": "hoje" if ultimo_dia == hoje else dia_curto(ultimo_dia, ultimo_dia.year != hoje.year),
            "variacao": None,
            "minimo": numero(min(valores), compacto=True),
            "maximo": numero(max(valores), compacto=True),
            "de": dia_curto(primeiro_dia),
            "ate": dia_curto(ultimo_dia),
            "pontos": [
                {"x": px, "y": py, "dia": dia_curto(d, d.year != hoje.year), "valor": numero(v)}
                for (d, v), (px, py) in zip(pontos, coordenadas)
            ],
        }
    )
    if len(pontos) > 1:
        sinal = "+" if variacao > 0 else ("−" if variacao < 0 else "")
        quadro["variacao"] = {
            "texto": f"{sinal}{numero(abs(variacao), compacto=True)}",
            "direcao": "sobe" if variacao > 0 else ("desce" if variacao < 0 else "igual"),
            "desde": dia_curto(primeiro_dia),
        }
    return quadro
