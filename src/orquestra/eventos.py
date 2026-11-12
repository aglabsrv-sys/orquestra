"""Canal de eventos entre o servidor e as páginas abertas (Server-Sent Events).

Quando um arquivo muda no disco, o servidor publica um evento e cada aba aberta
decide se precisa se atualizar. É o que faz uma edição no Obsidian aparecer no
painel sem apertar F5.
"""

from __future__ import annotations

import asyncio
import threading


class Eventos:
    def __init__(self) -> None:
        self._filas: dict[asyncio.Queue, asyncio.AbstractEventLoop | None] = {}
        self._trava = threading.Lock()

    def assinar(self) -> asyncio.Queue:
        fila: asyncio.Queue = asyncio.Queue(maxsize=200)
        try:
            laco = asyncio.get_running_loop()
        except RuntimeError:
            laco = None
        with self._trava:
            self._filas[fila] = laco
        return fila

    def cancelar(self, fila: asyncio.Queue) -> None:
        with self._trava:
            self._filas.pop(fila, None)

    def publicar(self, evento: dict) -> None:
        with self._trava:
            assinantes = list(self._filas.items())
        for fila, laco in assinantes:
            if laco is not None:
                try:
                    laco.call_soon_threadsafe(self._entregar, fila, evento)
                except RuntimeError:
                    self.cancelar(fila)
            else:
                self._entregar(fila, evento)

    def _entregar(self, fila: asyncio.Queue, evento: dict) -> None:
        try:
            fila.put_nowait(evento)
        except asyncio.QueueFull:
            while not fila.empty():
                fila.get_nowait()
            # Não afirmar que a aba está atualizada depois de perder eventos.
            fila.put_nowait({"tipo": "config", "ressincronizar": True})
