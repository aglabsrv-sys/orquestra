"""Observação por metadados, com uma única varredura podada e lotes limitados.

Um PollingObserverVFS evita um emitter/thread por pasta e permite excluir árvores
antes de enumerá-las nas três plataformas. Não lê o conteúdo das notas: compara
os metadados a cada 750 ms; o índice relê apenas os arquivos alterados.
"""
from __future__ import annotations

import asyncio
import logging
import os
import stat
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserverVFS
from orquestra.caminhos import CaminhoInseguro, caminho_no_vault, ignorar

ATRASO = 0.35
ESPERA_MAXIMA = 1.5
LIMITE_LOTE = 1000
INTERVALO_POLL = 0.75
registro = logging.getLogger(__name__)


class Vigia(FileSystemEventHandler):
    def __init__(self, vault: Path, laco: asyncio.AbstractEventLoop,
                 ao_mudar: Callable[[set[Path]], None], ao_reorganizar: Callable[[], None]):
        self.vault = vault.resolve()
        self.laco = laco
        self.ao_mudar = ao_mudar
        self.ao_reorganizar = ao_reorganizar
        self._pendentes: set[Path] = set()
        self._reorganizou = False
        self._timer: asyncio.TimerHandle | None = None
        self._primeiro: float | None = None
        # DirectorySnapshot pede stat(path) depois de listdir: reutilizamos o
        # resultado de DirEntry, sem uma segunda consulta por arquivo.
        self._stats: dict[str, os.stat_result] = {}
        self._observador = PollingObserverVFS(self._stat, self._listar, polling_interval=INTERVALO_POLL)
        self._vigiados: dict[Path, object] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orquestra-vigia")
        self._trabalho: Future | None = None
        self._fechando = False

    def _listar(self, pasta: str | None):
        if self._fechando or pasta is None:
            return
        try:
            base = caminho_no_vault(self.vault, Path(pasta))
        except (CaminhoInseguro, OSError):
            return
        with os.scandir(base) as entradas:
            for entrada in entradas:
                caminho = Path(entrada.path)
                rel = caminho.relative_to(self.vault).as_posix()
                if ignorar(rel, configuracao=True) or ":" in entrada.name or any(ord(c) < 32 for c in entrada.name):
                    continue
                try:
                    info = entrada.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    continue
                if stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode):
                    self._stats[entrada.path] = info
                    yield entrada

    def _stat(self, caminho: str) -> os.stat_result:
        if Path(caminho) == self.vault:
            self._stats.clear()  # também elimina sobras de uma varredura interrompida
        conhecida = self._stats.pop(caminho, None)
        if conhecida is not None:
            return conhecida
        return caminho_no_vault(self.vault, Path(caminho)).stat(follow_symlinks=False)

    def _ajustar_observacao(self) -> None:
        if self._fechando:
            return
        if not self._vigiados:
            self._vigiados[self.vault] = self._observador.schedule(self, str(self.vault), recursive=True)

    def iniciar(self) -> None:
        self._ajustar_observacao()
        self._observador.daemon = True
        self._observador.start()

    def parar(self) -> None:
        self._fechando = True
        self._observador.stop()
        if self._observador.ident is not None:
            self._observador.join(timeout=3)
        if self._timer:
            try:
                self.laco.call_soon_threadsafe(self._timer.cancel)
            except RuntimeError:
                pass
        self._executor.shutdown(wait=True, cancel_futures=True)

    def on_any_event(self, evento) -> None:
        if self._fechando or evento.event_type in ("opened", "closed", "closed_no_write"):
            return
        caminhos = []
        invalidou_caminho = False
        for texto in (evento.src_path, getattr(evento, "dest_path", "")):
            if not texto:
                continue
            try:
                alvo = caminho_no_vault(self.vault, Path(texto))
                rel = alvo.relative_to(self.vault).as_posix()
                if not ignorar(rel, configuracao=True):
                    caminhos.append(str(alvo))
            except (CaminhoInseguro, OSError):
                # Uma pasta/nota antes legítima pode ter virado link entre dois
                # snapshots. Não seguimos o novo alvo, mas precisamos retirar
                # do índice os itens antigos que a exclusão representa.
                try:
                    rel = Path(texto).relative_to(self.vault).as_posix()
                except ValueError:
                    continue
                if evento.event_type in ("deleted", "moved") and not ignorar(rel, configuracao=True):
                    invalidou_caminho = True
        if not caminhos and not invalidou_caminho:
            return
        reorganizou = invalidou_caminho or evento.is_directory and evento.event_type in ("created", "moved", "deleted")
        if evento.is_directory and not reorganizou:
            return
        try:
            self.laco.call_soon_threadsafe(self._anotar, caminhos, reorganizou)
        except RuntimeError:
            pass

    def _anotar(self, caminhos: list[str], pasta_mexida: bool) -> None:
        if self._fechando:
            return
        agora = self.laco.time()
        if self._primeiro is None:
            self._primeiro = agora
        self._reorganizou |= pasta_mexida
        self._pendentes.update(Path(c) for c in caminhos)
        if len(self._pendentes) > LIMITE_LOTE:
            self._reorganizou = True
            self._pendentes.clear()
        if self._timer:
            self._timer.cancel()
        espera = max(0, min(ATRASO, ESPERA_MAXIMA - (agora - self._primeiro)))
        self._timer = self.laco.call_later(espera, self._despejar)

    def _despejar(self) -> None:
        self._timer = None
        if self._fechando:
            return
        if self._trabalho is not None and not self._trabalho.done():
            self._timer = self.laco.call_later(ATRASO, self._despejar)
            return
        self._primeiro = None
        caminhos, self._pendentes = self._pendentes, set()
        reorganizou, self._reorganizou = self._reorganizou, False
        self._trabalho = self._executor.submit(self._processar, caminhos, reorganizou)

    def _processar(self, caminhos: set[Path], reorganizou: bool) -> None:
        try:
            if self._fechando:
                return
            if reorganizou:
                self.ao_reorganizar()
            elif caminhos:
                self.ao_mudar(caminhos)
        except Exception:
            registro.exception("Não foi possível atualizar o índice. O próximo lote tentará novamente.")
