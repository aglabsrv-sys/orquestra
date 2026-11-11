"""Canal de eventos entre o servidor e as páginas abertas (Server-Sent Events).

Quando um arquivo muda no disco, o servidor publica um evento e cada aba aberta
decide se precisa se atualizar. É o que faz uma edição no Obsidian aparecer no
painel sem apertar F5.
"""

from __future__ import annotations

import asyncio


class Eventos:
    def __init__(self) -> None:
        self._filas: set[asyncio.Queue] = set()

    def assinar(self) -> asyncio.Queue:
        fila: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._filas.add(fila)
        return fila

    def cancelar(self, fila: asyncio.Queue) -> None:
        self._filas.discard(fila)

    def publicar(self, evento: dict) -> None:
        for fila in list(self._filas):
            try:
                fila.put_nowait(evento)
            except asyncio.QueueFull:
                pass  # aba travada: ela se atualiza quando voltar
