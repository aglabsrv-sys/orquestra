"""Mede navegação em um vault sintético descartável, sem rede ou dados pessoais.

Uso: uv run --frozen python scripts/medir_desempenho.py --notas 10000
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import statistics
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from orquestra import preparo
from orquestra.servidor import criar_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notas", type=int, default=1000)
    parser.add_argument("--amostras", type=int, default=7)
    args = parser.parse_args()
    if not 1 <= args.notas <= 100_000 or not 3 <= args.amostras <= 50:
        parser.error("Use de 1 a 100000 notas e de 3 a 50 amostras.")
    with tempfile.TemporaryDirectory(prefix="orquestra-benchmark-") as temporario:
        raiz = Path(temporario)
        os.environ["ORQUESTRA_HOME"] = str(raiz / "home")
        vault = preparo.preparar(raiz / "vault", ["tarefas"], exemplos=False, com_backup=False).vault
        texto = f"---\nstatus: a_fazer\nprioridade: media\ndata: {dt.date.today()}\norigem: humano\n---\n\n"
        texto += "Nota sintética para medir navegação. " * 24 + "\n"
        for numero in range(args.notas):
            (vault / "tarefas/itens" / f"Nota {numero:06}.md").write_text(texto, encoding="utf-8")
        inicio = time.perf_counter()
        app = criar_app(vault, vigiar=False, agendar=False)
        resultado = {"python": platform.python_version(), "sistema": platform.system(), "notas": args.notas,
                     "bytes_por_nota": len(texto.encode()), "amostras": args.amostras,
                     "carga_ms": round((time.perf_counter() - inicio) * 1000, 2), "rotas": {}}
        with TestClient(app, base_url="http://localhost") as cliente:
            for rota in ("/", "/m/tarefas?aba=v1", "/m/tarefas", "/api/resumo", "/buscar?q=sintética"):
                cliente.get(rota).raise_for_status()  # aquecimento fora das amostras
                tempos = []
                for _ in range(args.amostras):
                    inicio = time.perf_counter()
                    resposta = cliente.get(rota)
                    resposta.raise_for_status()
                    tempos.append((time.perf_counter() - inicio) * 1000)
                resultado["rotas"][rota] = {"mediana_ms": round(statistics.median(tempos), 2),
                                             "maximo_ms": round(max(tempos), 2), "bytes": len(resposta.content)}
        print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
