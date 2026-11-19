"""Conclusão de tarefas e recorte do quadro, sem apagar o histórico do cofre."""

from __future__ import annotations

import datetime as dt
from typing import Any

from orquestra.modulos import Modulo
from orquestra.notas import Nota


def registrar_conclusao(modulo: Modulo, meta: dict[str, Any], anterior: Any = None) -> None:
    """Registra a transição real; editar texto de uma concluída não muda a data."""
    if modulo.id != "tarefas" or not modulo.tem_status:
        return
    estava = str(anterior or "") in modulo.concluidos
    terminou = str(meta.get(modulo.campo_status) or "") in modulo.concluidos
    if terminou and not estava:
        meta["concluido_em"] = dt.date.today()
    elif estava and not terminou:
        meta.pop("concluido_em", None)


def data_conclusao(nota: Nota) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(nota.campo("concluido_em") or "")[:10])
    except ValueError:
        return None


def recortar_quadro(itens: list[Nota], modulo: Modulo, hoje: dt.date, periodo: str) -> tuple[list[Nota], int]:
    inicio = hoje - dt.timedelta(days=hoje.weekday()) if periodo == "semana" else hoje
    fim = inicio + dt.timedelta(days=6) if periodo == "semana" else hoje
    abertos, concluidas = [], []
    for nota in itens:
        (concluidas if str(nota.campo(modulo.campo_status) or "") in modulo.concluidos else abertos).append(nota)
    visiveis = [n for n in concluidas if periodo == "todas" or (dia := data_conclusao(n)) is not None and inicio <= dia <= hoje]
    # As conclusões recentes vêm antes do histórico sem data, inclusive quando
    # uma coluna excede o limite de cartões exibidos pelo painel.
    visiveis.sort(key=lambda n: data_conclusao(n) or dt.date.min, reverse=True)
    if periodo != "todas":
        # Abertas de dias futuros ou sem data ficam em Todas; atrasadas continuam
        # visíveis, pois ainda precisam ser feitas.
        def no_periodo(nota: Nota) -> bool:
            try:
                dia = dt.date.fromisoformat(str(nota.campo(modulo.campo_data or "data") or "")[:10])
            except ValueError:
                return False
            return dia <= fim
        abertos = [n for n in abertos if no_periodo(n)]
    return [*abertos, *visiveis], len(concluidas) - len(visiveis)
