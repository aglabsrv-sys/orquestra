"""Vigia de arquivos: avisa o painel quando algo muda no vault.

O watchdog chama `on_any_event` em outra thread. Nós só anotamos o caminho e
devolvemos o trabalho para o laço principal (asyncio), com um pequeno atraso
para juntar rajadas: um editor costuma gerar vários eventos para um único salvar.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

ATRASO = 0.35  # segundos
TRECHOS_IGNORADOS = ("/.git/", "/.obsidian/", "/.trash/", "/__pycache__/")


class Vigia(FileSystemEventHandler):
    def __init__(
        self,
        vault: Path,
        laco: asyncio.AbstractEventLoop,
        ao_mudar: Callable[[set[Path]], None],
        ao_reorganizar: Callable[[], None],
    ):
        self.vault = vault
        self.laco = laco
        self.ao_mudar = ao_mudar
        self.ao_reorganizar = ao_reorganizar
        self._pendentes: set[Path] = set()
        self._reorganizou = False
        self._timer: asyncio.TimerHandle | None = None
        self._observador = Observer()

    def iniciar(self) -> None:
        self._observador.schedule(self, str(self.vault), recursive=True)
        self._observador.daemon = True
        self._observador.start()

    def parar(self) -> None:
        self._observador.stop()
        self._observador.join(timeout=2)

    # ---- chamado pela thread do watchdog
    def on_any_event(self, evento) -> None:
        if evento.event_type in ("opened", "closed", "closed_no_write"):
            return
        caminhos = [str(evento.src_path)]
        if getattr(evento, "dest_path", None):
            caminhos.append(str(evento.dest_path))
        caminhos = [c for c in caminhos if not any(t in c.replace("\\", "/") + "/" for t in TRECHOS_IGNORADOS)]
        if not caminhos:
            return
        pasta_mexida = evento.is_directory and evento.event_type in ("moved", "deleted")
        if evento.is_directory and not pasta_mexida:
            return
        try:
            self.laco.call_soon_threadsafe(self._anotar, caminhos, pasta_mexida)
        except RuntimeError:
            pass  # o servidor está encerrando

    # ---- chamado no laço principal
    def _anotar(self, caminhos: list[str], pasta_mexida: bool) -> None:
        if pasta_mexida:
            self._reorganizou = True  # pasta renomeada ou apagada: refazemos o índice inteiro
        else:
            self._pendentes.update(Path(c) for c in caminhos)
        if self._timer:
            self._timer.cancel()
        self._timer = self.laco.call_later(ATRASO, self._despejar)

    def _despejar(self) -> None:
        self._timer = None
        pendentes, self._pendentes = self._pendentes, set()
        if self._reorganizou:
            self._reorganizou = False
            self.ao_reorganizar()
        elif pendentes:
            self.ao_mudar(pendentes)
