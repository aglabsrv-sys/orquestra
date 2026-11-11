"""Agendador interno: roda coletores e backups enquanto o painel está aberto.

Não usamos cron, Agendador de Tarefas nem launchd: é um laço simples dentro do
próprio servidor, que funciona igual em Windows, macOS e Linux. A cada volta ele
compara o relógio com a última execução; por isso, se o computador ficou
desligado, o que estava atrasado roda assim que o painel volta.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from orquestra import backup, coletores
from orquestra.painel import Painel

INTERVALO = 30  # segundos entre verificações
registro = logging.getLogger("orquestra.agenda")


def _quando(texto: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(texto) if texto else None
    except ValueError:
        return None


async def verificar(painel: Painel, agora: dt.datetime | None = None) -> None:
    agora = agora or dt.datetime.now()

    # ---- coletores
    for modulo in list(painel.indice.modulos.values()):
        for coletor in modulo.coletores:
            if not coletor.ativo:
                continue
            ultima = _quando(painel.ultima_coleta(modulo.id, coletor.script).get("ultima"))
            if coletores.devido(coletor, ultima, agora):
                resultado = await painel.rodar_coletor(modulo, coletor)
                if not resultado.ok:
                    registro.warning("Coletor %s/%s falhou: %s", modulo.id, coletor.script, resultado.erro)

    # ---- backup
    cfg = painel.config.backup
    if not backup.e_repositorio(painel.vault):
        return
    estado = painel.ler_estado().get("backup", {})
    if cfg.auto_commit:
        ultimo = _quando(estado.get("ultimo_commit"))
        if ultimo is None or (agora - ultimo).total_seconds() >= cfg.intervalo_min * 60:
            await asyncio.to_thread(painel.fazer_backup, False)
    if cfg.push:
        # Reaproveitamos a regra dos coletores: "uma vez por dia, a partir de tal hora".
        regra = coletores.ColetorDef(script="", nome="", diario_as=cfg.push_as)
        if coletores.devido(regra, _quando(estado.get("ultimo_push")), agora):
            await asyncio.to_thread(painel.fazer_backup, True)


async def laco(painel: Painel) -> None:
    await asyncio.sleep(5)  # deixa o servidor terminar de subir
    while True:
        try:
            await verificar(painel)
        except asyncio.CancelledError:
            raise
        except Exception:  # um erro aqui não pode derrubar o painel
            registro.exception("Erro no agendador")
        await asyncio.sleep(INTERVALO)
