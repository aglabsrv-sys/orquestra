# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: tarefas que se repetem (todo dia, toda sexta, todo dia 5...).

Não busca nada na internet: só olha o calendário. Rodando uma vez por dia, ele cria
a tarefa de hoje para cada regra que cai hoje. É a automação mais simples que
existe, e dispensa lembrar de recriar a mesma tarefa toda semana.

Configuração (em tarefas/_modulo.yaml):

    tarefas:
      - titulo: Revisar a semana
        quando: sexta            # veja as opções abaixo
        prioridade: alta         # opcional: qualquer campo do módulo
      - titulo: Pagar o aluguel
        quando: dia 5

Opções de `quando`:
    todo dia | dia util | fim de semana
    segunda, terca, quarta, quinta, sexta, sabado, domingo  (pode juntar: "segunda, quinta")
    dia 5  (dia do mês; "dia 31" em mês curto cai no último dia)
"""

import calendar
import datetime
import unicodedata

from _comum import CONFIG, avisar, emitir

DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def simples(texto: str) -> str:
    """'Terça-feira' -> 'terca-feira': sem acento e em minúsculas, para comparar."""
    sem = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in sem if not unicodedata.combining(c)).lower().strip()


def cai_hoje(quando: str, hoje: datetime.date) -> bool | None:
    """True/False se a regra cai hoje; None se não entendi a regra."""
    regra = simples(quando)
    if regra in ("todo dia", "todos os dias", "diario", "diaria"):
        return True
    if regra in ("dia util", "dias uteis"):
        return hoje.weekday() < 5
    if regra in ("fim de semana", "fins de semana"):
        return hoje.weekday() >= 5
    if regra.startswith("dia "):
        try:
            dia = int(regra[4:])
        except ValueError:
            return None
        ultimo = calendar.monthrange(hoje.year, hoje.month)[1]
        return hoje.day == min(dia, ultimo)
    partes = [p.strip().removesuffix("-feira") for p in regra.replace(" e ", ",").split(",") if p.strip()]
    if partes and all(p in DIAS for p in partes):
        return DIAS[hoje.weekday()] in partes
    return None


def main() -> None:
    hoje = datetime.date.today()
    for regra in CONFIG.get("tarefas") or []:
        if not isinstance(regra, dict) or not regra.get("titulo") or not regra.get("quando"):
            continue
        cai = cai_hoje(str(regra["quando"]), hoje)
        if cai is None:
            avisar(f"Não entendi 'quando: {regra['quando']}' da tarefa '{regra['titulo']}'.")
            continue
        if not cai:
            continue
        titulo = str(regra["titulo"]).strip()
        campos = {k: v for k, v in regra.items() if k not in ("titulo", "quando", "corpo")}
        campos.setdefault("tags", ["recorrente"])
        emitir(
            id=f"recorrente:{simples(titulo)}:{hoje.isoformat()}",
            titulo=f"{titulo} - {hoje.day} {MESES[hoje.month - 1]}",
            corpo=str(regra.get("corpo") or ""),
            data=hoje.isoformat(),
            **campos,
        )


if __name__ == "__main__":
    main()
