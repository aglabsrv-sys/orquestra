"""Tela de boas-vindas: escolher um vault que já existe ou criar um novo.

É um app pequeno e separado do painel, porque precisa funcionar antes de existir
qualquer vault. Ele mostra os cofres que o Obsidian desta máquina conhece, analisa
a pasta escolhida sem alterar nada, e só então prepara o vault (preparo.py) e pede
ao hospedeiro para abrir o painel em cima dele.

Estas rotas mexem em pastas fora do vault atual. Por isso só respondem a quem está
no próprio computador (endereço localhost): pelo celular, via Tailscale, a tela
aparece, mas não deixa escolher nem criar nada.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from orquestra import __version__, aparencia, preparo, temas
from orquestra import apresentacao as ap
from orquestra.config import lembrar_vault, definir_chave
from orquestra.modulos import rotulo
from orquestra.recursos import marca_estaticos
from orquestra.seguranca import CapabilityLocal, Protecao, canal_local

PASTA = Path(__file__).parent


class Recusa(Exception):
    def __init__(self, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.status = status


def _e_local(request: Request) -> bool:
    return canal_local(request)


def criar_boas_vindas(hospedeiro: Any) -> FastAPI:
    if not hasattr(hospedeiro, "capacidade"):
        hospedeiro.capacidade = CapabilityLocal()
    app = FastAPI(title="Orquestra", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.capacidade = hospedeiro.capacidade
    painel_app = getattr(hospedeiro, "painel_app", None)
    extras = painel_app.state.painel.config.hosts_permitidos if painel_app else []
    app.add_middleware(Protecao, hosts_extras=extras)
    app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")
    modelos = Jinja2Templates(directory=PASTA / "templates")
    modelos.env.globals.update(icone=ap.icone, rotulo=rotulo, nome_cena=temas.nome_cena)
    marca = marca_estaticos(PASTA / "static")

    @app.exception_handler(Recusa)
    async def recusa(request: Request, erro: Recusa):
        return JSONResponse({"erro": str(erro)}, status_code=erro.status)

    @app.exception_handler(preparo.PastaRecusada)
    async def pasta_recusada(request: Request, erro: preparo.PastaRecusada):
        return JSONResponse({"erro": str(erro)}, status_code=400)

    async def corpo(request: Request) -> dict[str, Any]:
        try:
            hospedeiro.capacidade.exigir(request)
        except ValueError as erro:
            raise Recusa(str(erro), 403) from None
        try:
            dados = await request.json()
        except ValueError:
            raise Recusa("O corpo da requisição não é um JSON válido.") from None
        if not isinstance(dados, dict):
            raise Recusa("Esperava um objeto JSON.")
        return dados

    # ------------------------------------------------------------ página

    @app.get("/boas-vindas", response_class=HTMLResponse)
    async def pagina(request: Request):
        lista_temas = temas.listar(preparo.MODELO)
        tema = lista_temas[0]
        local = _e_local(request)
        return modelos.TemplateResponse(
            request,
            "boasvindas.html",
            {
                "versao": __version__,
                "marca": marca,
                "tema": tema,
                "cenas": temas.CENAS,
                "visual": {"modos": aparencia.MODOS, "cantos": aparencia.CANTOS, "fontes": aparencia.FONTES, "nomes": aparencia.NOMES},
                "estilo": aparencia.estilo(tema, aparencia.Aparencia()),
                "temas": [{**t, "previa": temas.previa(t)} for t in lista_temas],
                "capa": temas.previa(tema),
                "perfis": [p for p in preparo.perfis().values() if p.id in ("essencial", "criador", "negocio")],
                "catalogo": [m for m in preparo.catalogo().values() if m.id != "agenda"],
                "cofres": await asyncio.to_thread(preparo.cofres_obsidian) if local else [],
                "vault_atual": str(hospedeiro.vault) if hospedeiro.painel_app else "",
                "pasta_nova": str(Path.home() / "Orquestra"),
                "erro": hospedeiro.erro_ao_abrir,
                "local": local,
            },
        )

    @app.get("/favicon.ico")
    async def favicon():
        return RedirectResponse("/static/icone.svg")

    # ------------------------------------------------------------ API

    @app.get("/api/local/capacidade")
    async def capacidade_local(request: Request):
        token = hospedeiro.capacidade.emitir(request)
        if token is None:
            raise Recusa("Abra o painel diretamente em localhost neste computador para autorizar operações locais.", 403)
        return JSONResponse({"token": token}, headers={"Cache-Control": "no-store"})

    @app.get("/api/local/painel")
    async def painel_local(request: Request):
        """Quem está nesta porta: usado por `orquestra status`, `parar` e `reiniciar`."""
        try:
            hospedeiro.capacidade.exigir(request)
        except ValueError as erro:
            raise Recusa(str(erro), 403) from None
        from orquestra import processo
        return JSONResponse({"app": "orquestra", "versao": __version__, "pid": os.getpid(), "segundo_plano": processo.em_segundo_plano(),
                             "vault": str(hospedeiro.vault or "")}, headers={"Cache-Control": "no-store"})

    @app.post("/api/local/encerrar")
    async def encerrar_local(request: Request):
        await corpo(request)
        if not hospedeiro.encerrar():
            raise Recusa("Este painel não foi iniciado pela linha de comando; feche-o por onde foi aberto.", 409)
        return {"ok": True}

    @app.post("/api/boas-vindas/analisar")
    async def analisar(request: Request):
        dados = await corpo(request)
        return await asyncio.to_thread(preparo.analisar, str(dados.get("caminho") or ""))

    @app.get("/api/boas-vindas/visual")
    async def previa_visual(tema: str = "brasa", modo: str = "escuro", destaque: str = ""):
        t = temas.carregar(preparo.MODELO, tema)
        return {"estilo": aparencia.estilo(t, aparencia.ler({"modo": modo, "destaque": destaque}))}

    @app.post("/api/boas-vindas/procurar")
    async def procurar(request: Request):
        """Abre a janela "escolher pasta" do sistema e devolve o caminho escolhido."""
        await corpo(request)
        escolhida = await asyncio.to_thread(preparo.escolher_pasta_no_sistema)
        if escolhida is None:
            raise Recusa("Não consegui abrir a janela de pastas neste sistema. Cole o caminho da pasta no campo.", 501)
        return {"caminho": escolhida}

    @app.post("/api/boas-vindas/concluir")
    async def concluir(request: Request):
        dados = await corpo(request)
        vault = preparo.conferir_pasta(str(dados.get("caminho") or ""))
        modo = str(dados.get("modo") or "")
        ja_e_vault = (vault / "orquestra.yaml").is_file()
        if modo == "novo" and vault.is_dir() and any(vault.iterdir()) and not ja_e_vault:
            raise Recusa("Essa pasta já tem arquivos. Para usá-la como está, volte e escolha “Já tenho um vault”; para criar do zero, indique uma pasta nova.")
        if modo == "existente" and not vault.is_dir():
            raise Recusa("Essa pasta não existe. Confira o caminho, ou volte e escolha “Criar um vault novo”.")
        if modo not in ("novo", "existente"):
            raise Recusa("Diga se o vault é novo ou se já existe.")

        if modo == "existente" and ja_e_vault:
            lembrar_vault(vault)
            await hospedeiro.abrir(vault)
            return {"ok": True, "reaberto": True, "avisos": []}

        disponiveis = preparo.catalogo()
        modulos = [str(m) for m in dados.get("modulos") or [] if str(m) in disponiveis]
        pastas = [
            {"pasta": str(p.get("pasta") or ""), "quadro": bool(p.get("quadro"))}
            for p in dados.get("pastas") or []
            if isinstance(p, dict) and p.get("pasta")
        ]
        try:
            visual = aparencia.validar(dados.get("aparencia") or {})
        except (ValueError, TypeError, AttributeError) as erro:
            raise Recusa("Confira as opções de aparência escolhidas.") from erro
        tema = str(dados.get("tema") or "")
        relatorio = await asyncio.to_thread(
            preparo.preparar,
            vault,
            modulos,
            bool(dados.get("exemplos")),
            str(dados.get("nome") or ""),
            tema if tema in {t["id"] for t in temas.listar(preparo.MODELO)} else None,
            bool(dados.get("backup")),
            pastas,
        )
        if visual:
            definir_chave(vault / "orquestra.yaml", "aparencia", visual)
        lembrar_vault(vault)
        await hospedeiro.abrir(vault)
        return {
            "ok": True,
            "vault": str(vault),
            "criados": len(relatorio.criados),
            "avisos": relatorio.avisos,
            "com_git": relatorio.com_git,
            "pediu_git": bool(dados.get("backup")),
        }

    # Sem vault aberto, qualquer outro endereço cai aqui: leva para a tela de boas-vindas.
    @app.get("/{resto:path}")
    async def qualquer(resto: str):
        return RedirectResponse("/boas-vindas", status_code=307)

    return app
