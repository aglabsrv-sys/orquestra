"""Retoma o painel fora do terminal, após a resposta de ativação chegar à página."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from orquestra import cli, processo


def retomar(vault: Path, porta: int, pid: int) -> None:
    # Não interromper a requisição HTTP que acabou de preparar esta retomada.
    time.sleep(1)
    atual = processo.consultar(porta)
    if atual:
        if pid == 0:
            return  # outra abertura ganhou a porta; não reiniciar uma instância nova
        if atual.get("pid") != pid or Path(atual.get("vault") or "").resolve() != vault.resolve():
            raise RuntimeError("O painel ou cofre mudou; a instância atual foi preservada.")
        processo.parar(porta, pid_esperado=pid)
    elif processo.vivo(pid):
        raise RuntimeError("O painel anterior ainda não responde; a retomada foi cancelada sem encerrá-lo.")
    cli.main(["iniciar", "--vault", str(vault), "--porta", str(porta)])


if __name__ == "__main__":
    retomar(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
