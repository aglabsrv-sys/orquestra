"""Hospedeiro: o que o servidor web de fato executa.

O painel (servidor.py) é montado para um vault específico. Mas o programa precisa
abrir mesmo quando ainda não existe vault nenhum (primeira vez), e precisa trocar
de vault sem ser reiniciado. O hospedeiro resolve isso ficando na frente:

- sem vault, toda requisição vai para a tela de boas-vindas (boasvindas.py);
- com vault, vai para o painel desse vault; só `/boas-vindas` continua indo para a
  tela de boas-vindas, que é por onde se troca de vault.

Trocar de vault é encerrar o painel atual (vigia de arquivos e agendador) e montar
outro. As páginas abertas simplesmente passam a falar com o painel novo.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from orquestra import coletores
from orquestra.boasvindas import criar_boas_vindas
from orquestra.seguranca import CapabilityLocal
from orquestra.servidor import criar_app

ROTAS_DE_BOAS_VINDAS = ("/boas-vindas", "/api/boas-vindas", "/api/local/")
registro = logging.getLogger("orquestra.hospedeiro")


class Hospedeiro:
    def __init__(self, vault: Path | None, vigiar: bool = True, agendar: bool = True):
        self.vault = vault
        self.vigiar = vigiar
        self.agendar = agendar
        self.painel_app = None
        self._vida = None  # o "ciclo de vida" do painel atual (vigia + agendador)
        self._trava: asyncio.Lock | None = None
        self.erro_ao_abrir = ""
        self.capacidade = CapabilityLocal()
        self.boas_vindas = criar_boas_vindas(self)

    @property
    def painel(self):
        return self.painel_app.state.painel if self.painel_app else None

    # ------------------------------------------------------------ ASGI

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self._ciclo(receive, send)
        app = self.painel_app
        if app is None or scope.get("path", "").startswith(ROTAS_DE_BOAS_VINDAS):
            app = self.boas_vindas
        await app(scope, receive, send)

    async def _ciclo(self, receive, send) -> None:
        while True:
            mensagem = await receive()
            if mensagem["type"] == "lifespan.startup":
                if self.vault is not None:
                    try:
                        await self.abrir(self.vault)
                    except Exception as e:  # vault ilegível não pode impedir o programa de abrir
                        registro.exception("Não consegui abrir o vault %s", self.vault)
                        self.erro_ao_abrir = f"Não consegui abrir {self.vault}: {e}"
                        self.vault = None
                await send({"type": "lifespan.startup.complete"})
            elif mensagem["type"] == "lifespan.shutdown":
                await self.fechar()
                await send({"type": "lifespan.shutdown.complete"})
                return

    # ------------------------------------------------------------ troca de vault

    async def abrir(self, vault: Path) -> None:
        """Monta o painel de um vault, encerrando antes o que estiver aberto."""
        if self._trava is None:
            self._trava = asyncio.Lock()
        async with self._trava:
            app = await asyncio.to_thread(criar_app, vault, self.vigiar, self.agendar, hospedeiro=self)
            await self._encerrar_atual()
            vida = app.router.lifespan_context(app)
            await vida.__aenter__()
            self.painel_app, self._vida, self.vault = app, vida, vault
            self.boas_vindas = criar_boas_vindas(self)
            self.erro_ao_abrir = ""

    async def fechar(self) -> None:
        if self._trava is None:
            self._trava = asyncio.Lock()
        async with self._trava:
            await self._encerrar_atual()

    async def _encerrar_atual(self) -> None:
        if self.painel is not None:
            coletores.cancelar_execucoes(self.painel.vault)
        vida, self._vida, self.painel_app = self._vida, None, None
        if vida is not None:
            try:
                await vida.__aexit__(None, None, None)
            except Exception:
                registro.exception("Erro ao encerrar o painel anterior")
