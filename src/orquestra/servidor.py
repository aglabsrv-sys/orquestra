"""Servidor web do painel (FastAPI).

Páginas são HTML renderizado no servidor (templates Jinja). As alterações são
feitas por uma pequena API JSON em /api, chamada pelo JavaScript da página.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from orquestra import __version__, agenda, backup, diario, temas
from orquestra import apresentacao as ap
from orquestra.indice import EXT_MIDIA, data_de, espera_decisao
from orquestra.modulos import ValorInvalido, padroes, rotulo, validar
from orquestra.notas import Conflito, FrontmatterInvalido, simples
from orquestra.painel import NaoEncontrado, Painel, Recusado
from orquestra.seguranca import Protecao
from orquestra.vigia import Vigia

PASTA = Path(__file__).parent
LIMITE_POR_COLUNA = 80


def criar_app(vault: Path, vigiar: bool = True, agendar: bool = True) -> FastAPI:
    painel = Painel(vault)

    @asynccontextmanager
    async def vida(app: FastAPI):
        vigia = tarefa = None
        if vigiar:
            vigia = Vigia(painel.vault, asyncio.get_running_loop(), painel.ao_mudar_arquivos, painel.recarregar_tudo)
            vigia.iniciar()
        if agendar:
            tarefa = asyncio.create_task(agenda.laco(painel))
        yield
        if tarefa:
            tarefa.cancel()
        if vigia:
            vigia.parar()

    app = FastAPI(title="Orquestra", lifespan=vida, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.painel = painel
    app.add_middleware(Protecao, hosts_extras=painel.config.hosts_permitidos)
    app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")

    modelos = Jinja2Templates(directory=PASTA / "templates")
    modelos.env.globals.update(icone=ap.icone, rotulo=rotulo, url_nota=ap.url_nota)
    # Muda sempre que um arquivo de static/ muda, para o navegador não usar CSS/JS antigo.
    marca = str(int(max(p.stat().st_mtime for p in (PASTA / "static").rglob("*") if p.is_file())))

    def pagina(request: Request, nome: str, ativo: str, status: int = 200, **extra: Any) -> HTMLResponse:
        hoje = dt.date.today()
        contexto = {
            "cfg": painel.config,
            "tema": painel.tema,
            "versao": __version__,
            "marca": marca,
            "hoje": hoje,
            "hoje_longo": ap.data_longa(hoje),
            "dock": ap.montar_dock(painel, ativo, hoje),
            "ativo": ativo,
            "modulo_captura": painel.indice.modulos.get(painel.config.captura),
            **extra,
        }
        return modelos.TemplateResponse(request, nome, contexto, status_code=status)

    # ------------------------------------------------------------ erros

    def quer_json(request: Request) -> bool:
        return request.url.path.startswith("/api/")

    @app.exception_handler(NaoEncontrado)
    async def nao_encontrado(request: Request, erro: NaoEncontrado):
        if quer_json(request):
            return JSONResponse({"erro": "Não encontrei: " + str(erro)}, status_code=404)
        return pagina(request, "erro.html", "", 404, titulo="Não encontrei", mensagem=f"Não existe nada em “{erro}”.")

    @app.exception_handler(Conflito)
    async def conflito(request: Request, erro: Conflito):
        return JSONResponse(
            {"erro": "Este arquivo mudou no disco depois que você abriu. Recarregue para ver a versão nova.", "conflito": True},
            status_code=409,
        )

    @app.exception_handler(ValorInvalido)
    @app.exception_handler(Recusado)
    @app.exception_handler(FrontmatterInvalido)
    async def recusado(request: Request, erro: Exception):
        return JSONResponse({"erro": str(erro)}, status_code=400)

    @app.exception_handler(FileExistsError)
    async def ja_existe(request: Request, erro: FileExistsError):
        return JSONResponse({"erro": "Já existe um arquivo com esse nome."}, status_code=409)

    async def corpo_json(request: Request) -> dict[str, Any]:
        try:
            dados = await request.json()
        except ValueError:
            raise Recusado("O corpo da requisição não é um JSON válido.") from None
        if not isinstance(dados, dict):
            raise Recusado("Esperava um objeto JSON.")
        return dados

    # ------------------------------------------------------------ páginas

    @app.get("/", response_class=HTMLResponse)
    async def inicio(request: Request):
        hoje = dt.date.today()
        semana, para_hoje = ap.montar_semana(painel, hoje)
        slides = []
        total_decidir = 0
        for modulo in painel.indice.modulos.values():
            resumo = painel.indice.resumo(modulo, hoje)
            total_decidir += resumo.decidir
            slides.append(
                {
                    "id": modulo.id,
                    "titulo": modulo.nome,
                    "sobre": modulo.descricao,
                    "url": f"/m/{quote(modulo.id)}",
                    "capa": ap.capa_de(painel, modulo.id, modulo.capa),
                    "selo": ap.texto_selo(resumo, modulo),
                }
            )
        slides.append(
            {
                "id": "decidir",
                "titulo": "Para decidir",
                "sobre": "Tudo que espera uma resposta sua, de qualquer módulo.",
                "url": "/decidir",
                "capa": ap.capa_de(painel, "decidir"),
                "selo": f"{total_decidir} esperando" if total_decidir else "nada pendente",
            }
        )
        slides.append(
            {
                "id": "diario",
                "titulo": "Diário",
                "sobre": "O que mudou no vault e o que os agentes fizeram.",
                "url": "/diario",
                "capa": ap.capa_de(painel, "diario"),
                "selo": f"{len(diario.ler_registro(painel.vault, hoje))} mudanças hoje",
            }
        )
        return pagina(
            request, "inicio.html", "inicio", semana=semana, para_hoje=para_hoje, total_decidir=total_decidir, slides=slides
        )

    @app.get("/m/{modulo_id}", response_class=HTMLResponse)
    async def ver_modulo(request: Request, modulo_id: str, aba: str = "v0"):
        modulo = painel.modulo(modulo_id)
        hoje = dt.date.today()
        itens = painel.indice.itens(modulo.id)
        contexto: dict[str, Any] = {
            "modulo": modulo,
            "aba": aba,
            "capa": ap.capa_de(painel, modulo.id, modulo.capa),
            "resumo": painel.indice.resumo(modulo, hoje),
            "n_humano": len(painel.indice.notas_em(modulo.id, "humano")),
            # valores iniciais do formulário "Novo", vindos do schema
            "padroes": {
                k: (", ".join(map(str, v)) if isinstance(v, list) else simples(v)) for k, v in padroes(modulo).items()
            },
        }

        if aba == "humano":
            contexto["notas"] = [
                {"url": ap.url_nota(n.rel), "titulo": n.titulo, "trecho": ap.trecho(n)}
                for n in painel.indice.notas_em(modulo.id, "humano")
            ]
        elif aba == "maquina":
            contexto["notas"] = [
                {"url": ap.url_nota(n.rel), "titulo": n.titulo, "trecho": ap.trecho(n)}
                for n in painel.indice.notas_em(modulo.id, "maquina")
            ]
            contexto["coletores"] = [
                {
                    "def": c,
                    "ultima": painel.ultima_coleta(modulo.id, c.script),
                    "rodando": f"{modulo.id}/{c.script}" in painel.rodando,
                    "quando": c.a_cada and f"a cada {c.a_cada}" or c.diario_as and f"todo dia às {c.diario_as}" or "só manual",
                }
                for c in modulo.coletores
            ]
            contexto["arquivadas"] = len(painel.indice.notas_em(modulo.id, "arquivo"))
        else:
            try:
                indice_visao = max(0, min(int(aba.lstrip("v") or 0), len(modulo.visoes) - 1))
            except ValueError:
                indice_visao = 0
            visao = modulo.visoes[indice_visao]
            contexto["aba"] = f"v{indice_visao}"
            contexto["visao"] = visao
            if visao.tipo == "kanban":
                campo = modulo.campos.get(visao.agrupar_por)
                opcoes = campo.opcoes if campo else []
                grupos: dict[str, list] = {o: [] for o in opcoes}
                sem_grupo: list = []
                for nota in itens:
                    valor = str(nota.campo(visao.agrupar_por) or "")
                    (grupos[valor] if valor in grupos else sem_grupo).append(
                        ap.cartao(nota, modulo, hoje, omitir=visao.agrupar_por)
                    )
                colunas = [
                    {
                        "valor": o,
                        "rotulo": rotulo(o),
                        "total": len(grupos[o]),
                        "cartoes": grupos[o][:LIMITE_POR_COLUNA],
                        "concluida": o in modulo.concluidos,
                    }
                    for o in opcoes
                ]
                if sem_grupo:
                    colunas.insert(
                        0,
                        {"valor": "", "rotulo": "Sem " + visao.agrupar_por, "total": len(sem_grupo), "cartoes": sem_grupo[:LIMITE_POR_COLUNA], "concluida": False},
                    )
                contexto["colunas"] = colunas
                contexto["opcoes"] = opcoes
            else:
                nomes = visao.colunas or ["titulo", *modulo.campos.keys()]
                contexto["colunas_tabela"] = [
                    {"nome": n, "rotulo": "Título" if n == "titulo" else (modulo.campos[n].rotulo if n in modulo.campos else rotulo(n))}
                    for n in nomes
                ]
                linhas = []
                for nota in itens:
                    c = ap.cartao(nota, modulo, hoje)
                    celulas = []
                    for n in nomes:
                        valor = nota.campo(n)
                        campo = modulo.campos.get(n)
                        if n == "titulo":
                            celulas.append({"tipo": "titulo", "texto": nota.titulo})
                        elif valor in (None, "", []):
                            celulas.append({"tipo": "vazio", "texto": ""})
                        elif campo and campo.tipo == "data":
                            dia = data_de(nota, modulo) if n == modulo.campo_data else None
                            celulas.append({"tipo": "data", "texto": ap.data_curta(dia, hoje) if dia else str(valor), "ordem": str(valor)})
                        elif campo and campo.tipo == "escolha":
                            celulas.append({"tipo": "escolha", "texto": rotulo(valor), "classe": f"et-{n} v-{valor}"})
                        elif isinstance(valor, list):
                            celulas.append({"tipo": "texto", "texto": ", ".join(map(str, valor))})
                        elif campo and campo.tipo == "link" and ap.link_seguro(valor):
                            celulas.append({"tipo": "link", "texto": str(valor)})
                        else:
                            celulas.append({"tipo": "texto", "texto": str(valor)})
                    linhas.append({"cartao": c, "celulas": celulas})
                contexto["linhas"] = linhas
        return pagina(request, "modulo.html", f"m:{modulo.id}", **contexto)

    @app.get("/n/{rel:path}", response_class=HTMLResponse)
    async def ver_nota(request: Request, rel: str):
        nota = painel.nota(rel)
        modulo = painel.indice.modulo_de(rel)
        zona = painel.indice.zona_de(rel) if modulo else ""
        campos = []
        outros = {}
        if modulo and zona in ("itens", "arquivo"):
            for campo in modulo.campos.values():
                campos.append({"def": campo, "valor": ap.valor_para_formulario(nota, campo.nome, campo.tipo)})
            conhecidos = set(modulo.campos) | {"titulo"}
            outros = {k: v for k, v in nota.campos().items() if k not in conhecidos}
        else:
            outros = {k: v for k, v in nota.campos().items() if k != "titulo"}
        imagem = None
        if modulo:
            for campo in modulo.campos.values():
                if campo.tipo == "imagem" and nota.campo(campo.nome):
                    imagem = ap.url_midia(nota.campo(campo.nome))
        return pagina(
            request,
            "nota.html",
            f"m:{modulo.id}" if modulo else "",
            nota=nota,
            modulo=modulo,
            zona=zona,
            campos=campos,
            outros={k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in outros.items()},
            html=ap.render_markdown(nota.corpo, painel.indice),
            avisos=validar(modulo, nota.meta) if modulo and zona == "itens" else [],
            imagem=imagem,
            link_obsidian="obsidian://open?path=" + quote(str(nota.caminho), safe=""),
        )

    @app.get("/decidir", response_class=HTMLResponse)
    async def decidir(request: Request):
        hoje = dt.date.today()
        grupos = []
        for modulo in painel.indice.modulos.values():
            cartoes = []
            for nota in painel.indice.itens(modulo.id):
                if espera_decisao(nota, modulo):
                    c = ap.cartao(nota, modulo, hoje)
                    c["trecho"] = ap.trecho(nota, 180)
                    # As ações do módulo valem para itens na fila pelo status;
                    # uma pergunta de agente se resolve respondendo.
                    c["por_status"] = str(nota.campo(modulo.campo_status) or "") in modulo.decidir
                    cartoes.append(c)
            if cartoes:
                grupos.append({"modulo": modulo, "cartoes": cartoes})
        return pagina(request, "decidir.html", "decidir", grupos=grupos, total=sum(len(g["cartoes"]) for g in grupos))

    @app.get("/diario", response_class=HTMLResponse)
    async def ver_diario(request: Request, dia: str = ""):
        hoje = dt.date.today()
        try:
            alvo = dt.date.fromisoformat(dia) if dia else hoje
        except ValueError:
            alvo = hoje
        entradas = diario.ler_registro(painel.vault, alvo)
        for entrada in entradas:
            entrada.existe = entrada.rel in painel.indice.notas  # type: ignore[attr-defined]
        return pagina(
            request,
            "diario.html",
            "diario",
            dia=alvo,
            dia_longo=ap.data_longa(alvo),
            e_hoje=alvo == hoje,
            anterior=(alvo - dt.timedelta(days=1)).isoformat(),
            proximo=(alvo + dt.timedelta(days=1)).isoformat() if alvo < hoje else "",
            entradas=entradas,
            sessoes=ap.render_markdown(diario.ler_sessoes(painel.vault, alvo), painel.indice),
            dias=[d.isoformat() for d in diario.dias_com_registro(painel.vault)[:14]],
        )

    @app.get("/dia/{data}", response_class=HTMLResponse)
    async def ver_dia(request: Request, data: str):
        hoje = dt.date.today()
        try:
            alvo = dt.date.fromisoformat(data)
        except ValueError:
            raise NaoEncontrado(data) from None
        grupos = []
        for modulo in painel.indice.modulos.values():
            if not modulo.campo_data:
                continue
            cartoes = []
            for nota in painel.indice.itens(modulo.id):
                dia = data_de(nota, modulo)
                if dia is None or str(nota.campo(modulo.campo_status) or "") in modulo.concluidos:
                    continue
                # Na página de hoje também entram os atrasados.
                if dia == alvo or (alvo == hoje and dia < hoje):
                    cartoes.append(ap.cartao(nota, modulo, hoje))
            if cartoes:
                grupos.append({"modulo": modulo, "cartoes": cartoes})
        return pagina(request, "dia.html", "inicio", dia=alvo, dia_longo=ap.data_longa(alvo), e_hoje=alvo == hoje, grupos=grupos)

    @app.get("/buscar", response_class=HTMLResponse)
    async def buscar(request: Request, q: str = ""):
        resultados = [
            {
                "url": ap.url_nota(n.rel),
                "titulo": n.titulo,
                "trecho": ap.trecho(n),
                "onde": n.rel.rsplit("/", 1)[0],
            }
            for n in painel.indice.buscar(q)
        ]
        return pagina(request, "buscar.html", "", q=q, resultados=resultados)

    @app.get("/ajustes", response_class=HTMLResponse)
    async def ajustes(request: Request):
        lista_temas = []
        for tema in temas.listar(painel.vault):
            lista_temas.append({**tema, "previa": temas.resolver_capa(tema, "tarefas"), "atual": tema["id"] == painel.tema["id"]})
        estado = painel.ler_estado()
        avisos = [(m.nome, a) for m in painel.indice.modulos.values() for a in m.avisos]
        coletores = [
            {"modulo": m, "def": c, "ultima": painel.ultima_coleta(m.id, c.script)}
            for m in painel.indice.modulos.values()
            for c in m.coletores
        ]
        return pagina(
            request,
            "ajustes.html",
            "ajustes",
            temas=lista_temas,
            vault=str(painel.vault),
            tem_git=backup.e_repositorio(painel.vault),
            tem_remoto=backup.tem_remoto(painel.vault) if backup.git_disponivel() else False,
            ultimo_commit=backup.ultimo_commit(painel.vault),
            estado_backup=estado.get("backup", {}),
            avisos=avisos,
            coletores=coletores,
            n_notas=len(painel.indice.notas),
            host=request.headers.get("host", ""),
        )

    # ------------------------------------------------------------ API

    @app.post("/api/notas")
    async def api_criar(request: Request):
        dados = await corpo_json(request)
        nota = painel.criar_nota(
            str(dados.get("modulo") or ""),
            str(dados.get("titulo") or ""),
            dados.get("campos") if isinstance(dados.get("campos"), dict) else {},
            str(dados.get("corpo") or ""),
            zona=str(dados.get("zona") or "itens"),
        )
        return {"rel": nota.rel, "url": ap.url_nota(nota.rel), "versao": nota.versao}

    @app.put("/api/notas/{rel:path}")
    async def api_editar(request: Request, rel: str):
        dados = await corpo_json(request)
        nota = painel.editar_nota(
            rel,
            str(dados["versao"]) if dados.get("versao") else None,
            titulo=dados.get("titulo") if isinstance(dados.get("titulo"), str) else None,
            campos=dados.get("campos") if isinstance(dados.get("campos"), dict) else None,
            corpo=dados.get("corpo") if isinstance(dados.get("corpo"), str) else None,
        )
        return {"rel": nota.rel, "versao": nota.versao, "html": str(ap.render_markdown(nota.corpo, painel.indice))}

    @app.post("/api/arquivar/{rel:path}")
    async def api_arquivar(request: Request, rel: str):
        await corpo_json(request)
        return {"rel": painel.arquivar(rel)}

    @app.post("/api/captura")
    async def api_captura(request: Request):
        dados = await corpo_json(request)
        texto = str(dados.get("texto") or "").strip()
        if not texto:
            raise Recusado("Escreva alguma coisa antes de guardar.")
        if painel.config.captura not in painel.indice.modulos:
            raise Recusado(f"O módulo de captura '{painel.config.captura}' não existe. Ajuste 'captura' no orquestra.yaml.")
        primeira = texto.splitlines()[0].strip()
        titulo = primeira if len(primeira) <= 70 else primeira[:67].rstrip() + "..."
        nota = painel.criar_nota(painel.config.captura, titulo, {}, texto, origem="humano")
        return {"rel": nota.rel, "url": ap.url_nota(nota.rel)}

    @app.post("/api/coletores/rodar")
    async def api_rodar_coletor(request: Request):
        dados = await corpo_json(request)
        modulo, coletor = painel.coletor(str(dados.get("modulo") or ""), str(dados.get("script") or ""))
        resultado = await painel.rodar_coletor(modulo, coletor)
        if not resultado.ok:
            return JSONResponse({"erro": resultado.erro}, status_code=502)
        return {"novos": resultado.novos, "repetidos": resultado.repetidos}

    @app.post("/api/coletores/ativo")
    async def api_coletor_ativo(request: Request):
        dados = await corpo_json(request)
        painel.definir_coletor_ativo(str(dados.get("modulo") or ""), str(dados.get("script") or ""), bool(dados.get("ativo")))
        return {"ok": True}

    @app.post("/api/tema")
    async def api_tema(request: Request):
        dados = await corpo_json(request)
        painel.definir_tema(str(dados.get("tema") or ""))
        return {"ok": True}

    @app.post("/api/backup")
    async def api_backup(request: Request):
        dados = await corpo_json(request)
        if not backup.e_repositorio(painel.vault):
            raise Recusado("O vault ainda não é um repositório git. Rode `orquestra backup` no terminal para criar.")
        return await asyncio.to_thread(painel.fazer_backup, bool(dados.get("enviar")))

    @app.get("/api/resumo")
    async def api_resumo():
        hoje = dt.date.today()
        dock = ap.montar_dock(painel, "", hoje)
        _, para_hoje = ap.montar_semana(painel, hoje)
        selos = {m["id"]: m["selo"] for m in dock["modulos"]}
        selos["decidir"] = dock["decidir"]
        return {"selos": selos, "decidir": dock["decidir"], "hoje": para_hoje}

    @app.get("/eventos")
    async def eventos(request: Request):
        fila = painel.eventos.assinar()

        async def fluxo():
            try:
                yield "retry: 3000\n\n"
                while True:
                    try:
                        evento = await asyncio.wait_for(fila.get(), timeout=20)
                        yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"  # mantém a conexão viva
                    if await request.is_disconnected():
                        break
            finally:
                painel.eventos.cancelar(fila)

        return StreamingResponse(
            fluxo(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    @app.get("/arquivo/{rel:path}")
    async def arquivo(rel: str):
        """Serve imagens e vídeos do vault (miniaturas, capas). Só mídia, nunca outros arquivos."""
        caminho = painel.caminho_seguro(rel)
        if caminho.suffix.lower() not in EXT_MIDIA or not caminho.is_file():
            raise NaoEncontrado(rel)
        # A política abaixo impede que um SVG malicioso execute script se for aberto direto.
        return FileResponse(caminho, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"})

    @app.get("/favicon.ico")
    async def favicon():
        return RedirectResponse("/static/icone.svg")

    return app
