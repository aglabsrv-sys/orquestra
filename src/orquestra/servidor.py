"""Servidor web do painel (FastAPI).

Páginas são HTML renderizado no servidor (templates Jinja). As alterações são
feitas por uma pequena API JSON em /api, chamada pelo JavaScript da página.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import errno
import json
import hashlib
import os
import logging
import math
from functools import wraps
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from pydantic import BaseModel, ValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from orquestra import __version__, adocao, agenda, aparencia, armazenamento, backup, coletores, confianca, contratos, diario, graficos, preparo, temas
from orquestra.caminhos import CaminhoInseguro, ignorar
from orquestra.config import ConfigInvalida
from orquestra import apresentacao as ap
from orquestra.indice import EXT_MIDIA, data_de, deve_ignorar, espera_decisao
from orquestra.modulos import ARQUIVO_DESLIGADO, TIPOS_DE_CAMPO, ValorInvalido, padroes, rotulo, validar
from orquestra.notas import Conflito, FrontmatterInvalido, simples
from orquestra.painel import NaoEncontrado, Painel, Recusado
from orquestra.recursos import marca_estaticos
from orquestra.seguranca import CapabilityLocal, Protecao
from orquestra.vigia import Vigia

PASTA = Path(__file__).parent
LIMITE_POR_COLUNA = 80
TAMANHO_PAGINA = 80
registro = logging.getLogger(__name__)


def criar_app(vault: Path, vigiar: bool = True, agendar: bool = True, hospedeiro: Any = None) -> FastAPI:
    """Monta o painel de um vault.

    `hospedeiro` é quem está servindo este app (ver hospedeiro.py). Quando existe, a
    tela de Ajustes oferece trocar de vault; nos testes ele não existe.
    """
    painel = Painel(vault)
    capacidade = hospedeiro.capacidade if hospedeiro else CapabilityLocal()
    vault_id = hashlib.sha256(os.path.normcase(str(painel.vault)).encode("utf-8")).hexdigest()[:24]

    @asynccontextmanager
    async def vida(app: FastAPI):
        vigia = tarefa = None
        if vigiar:
            vigia = Vigia(painel.vault, asyncio.get_running_loop(), painel.ao_mudar_arquivos, painel.recarregar_tudo)
            await asyncio.to_thread(vigia.iniciar)
        if agendar:
            tarefa = asyncio.create_task(agenda.laco(painel))
        try:
            yield
        finally:
            await asyncio.to_thread(coletores.cancelar_execucoes, painel.vault)
            if tarefa:
                tarefa.cancel()
                try:
                    await tarefa
                except asyncio.CancelledError:
                    pass
            if vigia:
                await asyncio.to_thread(vigia.parar)

    app = FastAPI(title="Orquestra", lifespan=vida, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.painel = painel
    app.state.vault_id = vault_id
    app.add_middleware(Protecao, hosts_extras=painel.config.hosts_permitidos)
    app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")

    modelos = Jinja2Templates(directory=PASTA / "templates")
    modelos.env.globals.update(icone=ap.icone, rotulo=rotulo, url_nota=ap.url_nota, url_pasta=ap.url_pasta)
    # Muda sempre que um arquivo de static/ muda, para o navegador não usar CSS/JS antigo.
    marca = marca_estaticos(PASTA / "static")

    def pagina(request: Request, nome: str, ativo: str, status: int = 200, **extra: Any) -> HTMLResponse:
        hoje = dt.date.today()
        contexto = {
            "cfg": painel.config,
            "tema": painel.tema,
            "estilo": aparencia.estilo(painel.tema, painel.config.aparencia),
            "cor_navegador": aparencia.cor_do_navegador(painel.tema, painel.config.aparencia),
            "versao": __version__,
            "marca": marca,
            "vault_id": vault_id,
            "avisos_config": painel.avisos + [a for m in painel.indice.modulos.values() for a in m.avisos],
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
            {"erro": str(erro) or "Este arquivo mudou no disco. Preserve o rascunho antes de recarregar.", "conflito": True},
            status_code=409,
        )

    @app.exception_handler(ValorInvalido)
    @app.exception_handler(Recusado)
    @app.exception_handler(FrontmatterInvalido)
    @app.exception_handler(ConfigInvalida)
    @app.exception_handler(CaminhoInseguro)
    @app.exception_handler(backup.ErroBackup)
    async def recusado(request: Request, erro: Exception):
        return JSONResponse({"erro": str(erro)}, status_code=400)

    @app.exception_handler(FileExistsError)
    async def ja_existe(request: Request, erro: FileExistsError):
        return JSONResponse({"erro": "Já existe um arquivo com esse nome."}, status_code=409)

    @app.exception_handler(armazenamento.ConflitoDeEscrita)
    async def conflito_de_arquivo(request: Request, erro: Exception):
        return JSONResponse({"erro": str(erro), "conflito": True}, status_code=409)

    @app.exception_handler(OSError)
    async def erro_de_disco(request: Request, erro: OSError):
        registro.warning("Falha ao acessar arquivo no painel", exc_info=True)
        mensagem = "Não consegui acessar ou salvar o arquivo. Confira espaço livre, permissões e sincronização; seu rascunho continua na tela."
        if erro.errno == errno.ENOSPC:
            mensagem = "O disco está sem espaço. Libere espaço e tente novamente; seu rascunho continua na tela."
        elif erro.errno in (errno.ENOTSUP, errno.EOPNOTSUPP) or getattr(erro, "winerror", None) == 50:
            mensagem = "Esta unidade não oferece a troca segura de arquivos exigida pelo painel. Mantenha uma cópia e use um sistema de arquivos local compatível; o rascunho continua na tela."
        if quer_json(request):
            return JSONResponse({"erro": mensagem}, status_code=503)
        return pagina(request, "erro.html", "", 503, titulo="Arquivo indisponível", mensagem=mensagem)

    async def corpo_json(request: Request, modelo: type[BaseModel] | None = None) -> dict[str, Any]:
        vinculo = request.headers.get("x-orquestra-vault")
        if vinculo and vinculo != vault_id:
            raise Conflito("Esta aba pertence a outro vault. Reabra o vault correto ou copie o rascunho antes de atualizar.")
        def constante_invalida(_texto: str):
            raise ValueError("Números JSON precisam ser finitos.")
        def decimal(texto: str) -> float:
            valor = float(texto)
            if not math.isfinite(valor):
                raise ValueError("Números JSON precisam ser finitos.")
            return valor
        try:
            dados = json.loads(await request.body(), parse_constant=constante_invalida, parse_float=decimal)
            json.dumps(dados, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, RecursionError):
            raise Recusado("O corpo da requisição não é um JSON válido.") from None
        if not isinstance(dados, dict):
            raise Recusado("Esperava um objeto JSON.")
        if modelo:
            try:
                return modelo.model_validate(dados).model_dump(exclude_unset=True)
            except ValidationError as erro:
                nomes = ", ".join(dict.fromkeys(str(e["loc"][0]) for e in erro.errors() if e["loc"]))
                raise Recusado(f"Confira os campos {nomes or 'do pedido'}: valor ou formato inválido.") from None
        return dados

    def exigir_local(request: Request) -> JSONResponse | None:
        try:
            capacidade.exigir(request)
        except ValueError as erro:
            return JSONResponse({"erro": str(erro)}, status_code=403)
        return None

    @app.get("/api/local/capacidade")
    async def capacidade_local(request: Request):
        token = capacidade.emitir(request)
        if token is None:
            return JSONResponse({"erro": "Abra localhost diretamente no computador para autorizar esta operação."}, status_code=403)
        return {"token": token}

    def paginar(request: Request, itens: list, tamanho: int = TAMANHO_PAGINA) -> tuple[list, dict]:
        total = len(itens)
        paginas = max(1, (total + tamanho - 1) // tamanho)
        try:
            numero = max(1, min(int(request.query_params.get("pagina", "1")), paginas))
        except ValueError:
            numero = 1
        return itens[(numero - 1) * tamanho:numero * tamanho], {
            "pagina": numero, "paginas": paginas, "total": total,
            "anterior": str(request.url.include_query_params(pagina=numero - 1)) if numero > 1 else None,
            "proxima": str(request.url.include_query_params(pagina=numero + 1)) if numero < paginas else None,
        }

    def estado_confianca(modulo, coletor):
        try:
            return confianca.resumo(painel.vault, modulo, coletor)
        except (ValueError, OSError) as erro:
            return {"confiavel": False, "assinatura": "", "arquivos": [], "requer": coletor.requer,
                    "script": coletor.script, "config": {}, "erro": str(erro)}

    def leitura(funcao):
        """Renderização/I/O em thread, com uma visão coerente do índice daquele vault."""
        @wraps(funcao)
        def executar(*args, **kwargs):
            with painel._trava:
                return funcao(*args, **kwargs)
        return executar

    # ------------------------------------------------------------ páginas

    @app.get("/", response_class=HTMLResponse)
    @leitura
    def inicio(request: Request):
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
        fora = painel.indice.fora_dos_modulos()
        if fora:
            slides.append(
                {
                    "id": "pastas",
                    "titulo": "Suas pastas",
                    "sobre": "As notas que você já tinha, do jeito que você organizou.",
                    "url": "/pastas",
                    "capa": ap.capa_de(painel, "pastas"),
                    "selo": f"{fora} nota{'s' if fora != 1 else ''}",
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
            request,
            "inicio.html",
            "inicio",
            semana=semana,
            para_hoje=para_hoje,
            total_decidir=total_decidir,
            slides=slides,
            sem_areas=not painel.indice.modulos,
        )

    @app.get("/m/{modulo_id}", response_class=HTMLResponse)
    @leitura
    def ver_modulo(request: Request, modulo_id: str, aba: str = "v0"):
        modulo = painel.modulo(modulo_id)
        hoje = dt.date.today()
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
            notas, contexto["paginacao"] = paginar(request, painel.indice.notas_em(modulo.id, "humano"))
            contexto["notas"] = [
                {"url": ap.url_nota(n.rel), "titulo": n.titulo, "trecho": ap.trecho(n)}
                for n in notas
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
                    "confianca": estado_confianca(modulo, c),
                }
                for c in modulo.coletores
            ]
            contexto["arquivadas"] = len(painel.indice.notas_em(modulo.id, "arquivo"))
        else:
            itens = painel.indice.itens(modulo.id)
            try:
                indice_visao = max(0, min(int(aba.lstrip("v") or 0), len(modulo.visoes) - 1))
            except ValueError:
                indice_visao = 0
            visao = modulo.visoes[indice_visao]
            contexto["aba"] = f"v{indice_visao}"
            contexto["visao"] = visao
            if visao.tipo == "grafico":
                contexto["quadros"] = graficos.montar(painel.indice, modulo, visao, hoje)
                de_hoje = painel.indice.notas.get(f"{modulo.id}/" + ("" if modulo.itens_na_raiz else modulo.itens_em + "/") + f"{hoje.isoformat()}.md")
                contexto["numericos"] = [
                    {"def": modulo.campos[n], "valor": de_hoje.campo(n) if de_hoje and de_hoje.campo(n) is not None else ""}
                    for n in modulo.campos_numericos
                ]
            elif visao.tipo == "kanban":
                campo = modulo.campos.get(visao.agrupar_por)
                opcoes = campo.opcoes if campo else []
                grupos: dict[str, list] = {o: [] for o in opcoes}
                sem_grupo: list = []
                for nota in itens:
                    valor = str(nota.campo(visao.agrupar_por) or "")
                    (grupos[valor] if valor in grupos else sem_grupo).append(nota)
                colunas = [
                    {
                        "valor": o,
                        "rotulo": rotulo(o),
                        "total": len(grupos[o]),
                        "cartoes": [ap.cartao(n, modulo, hoje, omitir=visao.agrupar_por) for n in grupos[o][:LIMITE_POR_COLUNA]],
                        "concluida": o in modulo.concluidos,
                    }
                    for o in opcoes
                ]
                if sem_grupo:
                    colunas.insert(
                        0,
                        {"valor": "", "rotulo": "Sem " + visao.agrupar_por, "total": len(sem_grupo),
                         "cartoes": [ap.cartao(n, modulo, hoje, omitir=visao.agrupar_por) for n in sem_grupo[:LIMITE_POR_COLUNA]], "concluida": False},
                    )
                contexto["colunas"] = colunas
                contexto["opcoes"] = opcoes
            else:
                itens, contexto["paginacao"] = paginar(request, itens)
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
    @leitura
    def ver_nota(request: Request, rel: str):
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
            pasta=rel.rsplit("/", 1)[0] if "/" in rel else "",
            html=ap.render_markdown(nota.corpo, painel.indice),
            avisos=validar(modulo, nota.meta) if modulo and zona == "itens" else [],
            imagem=imagem,
            link_obsidian="obsidian://open?path=" + quote(str(nota.caminho), safe=""),
        )

    @app.get("/decidir", response_class=HTMLResponse)
    @leitura
    def decidir(request: Request):
        hoje = dt.date.today()
        pendentes = [(m, n) for m in painel.indice.modulos.values() for n in painel.indice.itens(m.id) if espera_decisao(n, m)]
        selecionadas, paginacao = paginar(request, pendentes)
        grupos: dict[str, dict] = {}
        for modulo, nota in selecionadas:
            c = ap.cartao(nota, modulo, hoje)
            c["trecho"] = ap.trecho(nota, 180)
            c["por_status"] = str(nota.campo(modulo.campo_status) or "") in modulo.decidir
            grupos.setdefault(modulo.id, {"modulo": modulo, "cartoes": []})["cartoes"].append(c)
        return pagina(request, "decidir.html", "decidir", grupos=list(grupos.values()), total=len(pendentes), paginacao=paginacao)

    @app.get("/diario", response_class=HTMLResponse)
    @leitura
    def ver_diario(request: Request, dia: str = ""):
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
    @leitura
    def ver_dia(request: Request, data: str):
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
                # Na página de hoje também entram os atrasados (só onde existe status para atrasar).
                if dia == alvo or (alvo == hoje and dia < hoje and modulo.tem_status):
                    cartoes.append(ap.cartao(nota, modulo, hoje))
            if cartoes:
                grupos.append({"modulo": modulo, "cartoes": cartoes})
        return pagina(request, "dia.html", "inicio", dia=alvo, dia_longo=ap.data_longa(alvo), e_hoje=alvo == hoje, grupos=grupos)

    @app.get("/buscar", response_class=HTMLResponse)
    @leitura
    def buscar(request: Request, q: str = ""):
        notas, paginacao = paginar(request, painel.indice.buscar(q, limite=None))
        resultados = [
            {
                "url": ap.url_nota(n.rel),
                "titulo": n.titulo,
                "trecho": ap.trecho(n),
                "onde": n.rel.rsplit("/", 1)[0],
            }
            for n in notas
        ]
        return pagina(request, "buscar.html", "", q=q, resultados=resultados, paginacao=paginacao)

    @app.get("/pastas", response_class=HTMLResponse)
    @app.get("/pastas/{rel:path}", response_class=HTMLResponse)
    @leitura
    def ver_pasta(request: Request, rel: str = ""):
        """Navegador de pastas: o vault como ele é no disco, inclusive o que não é módulo."""
        rel = rel.strip("/")
        if rel:
            caminho = painel.caminho_seguro(rel)
            if not caminho.is_dir() or deve_ignorar(rel + "/x.md"):
                raise NaoEncontrado(rel)
        hoje = dt.date.today()
        subpastas, notas = painel.indice.conteudo_da_pasta(rel)
        notas, paginacao = paginar(request, notas)
        nomes = dict(subpastas)
        if not rel:
            for modulo in painel.indice.modulos.values():  # módulos vazios também aparecem
                nomes.setdefault(modulo.id, 0)
        pastas = []
        for nome in sorted(nomes, key=str.lower):
            modulo = painel.indice.modulos.get(nome) if not rel else None
            pastas.append(
                {
                    "nome": nome,
                    "notas": nomes[nome],
                    "url": ap.url_pasta(f"{rel}/{nome}"),
                    "modulo": modulo,
                    "desligada": not rel and (painel.vault / nome / ARQUIVO_DESLIGADO).is_file(),
                    "pode_adotar": not rel and modulo is None and nome != "diario" and not nome.startswith("_"),
                }
            )
        partes = rel.split("/") if rel else []
        return pagina(
            request,
            "pastas.html",
            "pastas",
            paginacao=paginacao,
            rel=rel,
            trilha=[{"nome": parte, "url": ap.url_pasta("/".join(partes[: i + 1]))} for i, parte in enumerate(partes)],
            pastas=pastas,
            notas=[
                {
                    "url": ap.url_nota(n.rel),
                    "titulo": n.titulo,
                    "trecho": ap.trecho(n, 120),
                    "quando": ap.modificado_em(n, hoje),
                    "origem": n.campo("origem"),
                }
                for n in notas
            ],
            modulo=painel.indice.modulos.get(partes[0]) if partes else None,
            pode_criar=not (len(partes) > 1 and partes[0] in painel.indice.modulos and partes[1] == "maquina"),
        )

    @app.get("/m/{modulo_id}/personalizar", response_class=HTMLResponse)
    @leitura
    def personalizar(request: Request, modulo_id: str):
        modulo = painel.modulo(modulo_id)
        capa = modulo.capa if isinstance(modulo.capa, dict) else {}
        return pagina(
            request,
            "personalizar.html",
            f"m:{modulo.id}",
            modulo=modulo,
            capa=ap.capa_de(painel, modulo.id, modulo.capa),
            campos=[c for c in modulo.campos.values() if c.nome != "origem"],
            tipos=sorted(TIPOS_DE_CAMPO),
            icones=ap.ICONES_DE_MODULO,
            cenas=temas.CENAS,
            cena_atual=str(capa.get("cena") or ""),
            tem_quadro=any(v.tipo == "kanban" for v in modulo.visoes),
            tem_grafico=any(v.tipo == "grafico" for v in modulo.visoes),
            pode_quadro=modulo.tem_status,
            pode_grafico=bool(modulo.campos_numericos),
        )

    @app.get("/ajustes", response_class=HTMLResponse)
    @leitura
    def ajustes(request: Request):
        lista_temas = []
        for tema in temas.listar(painel.vault):
            lista_temas.append({**tema, "previa": temas.resolver_capa(tema, "tarefas"), "atual": tema["id"] == painel.tema["id"]})
        estado = painel.ler_estado()
        avisos = [(m.nome, a) for m in painel.indice.modulos.values() for a in m.avisos]
        coletores = [
            {"modulo": m, "def": c, "ultima": painel.ultima_coleta(m.id, c.script), "confianca": estado_confianca(m, c)}
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
            confianca_backup=backup.resumo(painel.vault),
            avisos=avisos,
            coletores=coletores,
            n_notas=len(painel.indice.notas),
            host=request.headers.get("host", ""),
            areas=[
                {"modulo": m, "itens": len(painel.indice.notas_em(m.id, "itens")), "propria": m.itens_na_raiz}
                for m in painel.indice.modulos.values()
            ],
            prontos=[
                m for m in preparo.catalogo().values() if m.id not in painel.indice.modulos and not (painel.vault / m.id).exists()
            ],
            icones=ap.ICONES_DE_MODULO,
            visual={
                "modos": aparencia.MODOS,
                "cantos": list(aparencia.CANTOS),
                "fontes": aparencia.FONTES,
                "nomes": aparencia.NOMES,
                "sugestoes": aparencia.SUGESTOES,
                "destaque_do_tema": painel.tema["cores"]["destaque"],
            },
            pode_trocar=hospedeiro is not None,
            tem_git_instalado=backup.git_disponivel(),
            link_obsidian="obsidian://open?path=" + quote(str(painel.vault), safe=""),
        )

    # ------------------------------------------------------------ API

    @app.post("/api/notas")
    async def api_criar(request: Request):
        dados = await corpo_json(request, contratos.CriarNota)
        nota = await asyncio.to_thread(painel.criar_nota,
            str(dados.get("modulo") or ""),
            str(dados.get("titulo") or ""),
            dados.get("campos") if isinstance(dados.get("campos"), dict) else {},
            str(dados.get("corpo") or ""),
            zona=str(dados.get("zona") or "itens"),
        )
        return {"rel": nota.rel, "url": ap.url_nota(nota.rel), "versao": nota.versao}

    @app.put("/api/notas/{rel:path}")
    async def api_editar(request: Request, rel: str):
        painel.caminho_seguro(rel)
        dados = await corpo_json(request, contratos.EditarNota)
        def editar_e_renderizar():
            # Markdown extenso também usa CPU. Mantê-lo fora do laço ASGI evita
            # bloquear eventos e outras abas enquanto se prepara a prévia salva.
            with painel._trava:
                nota = painel.editar_nota(rel, dados["versao"], titulo=dados.get("titulo"),
                                           campos=dados.get("campos"), corpo=dados.get("corpo"))
                return {"rel": nota.rel, "versao": nota.versao, "html": str(ap.render_markdown(nota.corpo, painel.indice))}
        return await asyncio.to_thread(editar_e_renderizar)

    @app.post("/api/arquivar/{rel:path}")
    async def api_arquivar(request: Request, rel: str):
        dados = await corpo_json(request, contratos.Versao)
        return {"rel": await asyncio.to_thread(painel.arquivar, rel, versao=dados["versao"])}

    @app.post("/api/notas/copia/{rel:path}")
    async def api_copia(request: Request, rel: str):
        dados = await corpo_json(request, contratos.CopiaNota)
        nota = await asyncio.to_thread(painel.copiar_nota, rel, dados.get("titulo", ""), dados["corpo"], dados.get("campos"))
        return {"rel": nota.rel, "url": ap.url_nota(nota.rel), "versao": nota.versao}

    @app.get("/api/notas/recuperacao/{rel:path}")
    def api_recuperacao(rel: str, id: str = "", tipo: str = "antes"):
        caminho = painel.caminho_seguro(rel)
        if caminho.suffix.lower() != ".md" or deve_ignorar(rel):
            raise NaoEncontrado(rel)
        if not id:
            return {"versoes": armazenamento.listar_recuperacoes(caminho)}
        try:
            bruto = armazenamento.ler_recuperacao(caminho, id, tipo=tipo)
        except (ValueError, FileNotFoundError):
            raise NaoEncontrado("Versão de recuperação inexistente.") from None
        return {"texto": bruto.decode("utf-8-sig", errors="replace"), "id": id, "tipo": tipo}

    @app.post("/api/notas/recuperacao/copia/{rel:path}")
    async def api_copia_recuperacao(request: Request, rel: str):
        dados = await corpo_json(request, contratos.CopiaRecuperacao)
        nota = await asyncio.to_thread(painel.recuperar_como_copia, rel, dados["id"], dados.get("tipo", "antes"), dados.get("titulo", ""))
        return {"rel": nota.rel, "url": ap.url_nota(nota.rel), "versao": nota.versao}

    @app.post("/api/captura")
    async def api_captura(request: Request):
        dados = await corpo_json(request, contratos.Captura)
        texto = str(dados.get("texto") or "").strip()
        if not texto:
            raise Recusado("Escreva alguma coisa antes de guardar.")
        if painel.config.captura not in painel.indice.modulos:
            raise Recusado(f"O módulo de captura '{painel.config.captura}' não existe. Ajuste 'captura' no orquestra.yaml.")
        primeira = texto.splitlines()[0].strip()
        titulo = primeira if len(primeira) <= 70 else primeira[:67].rstrip() + "..."
        nota = await asyncio.to_thread(painel.criar_nota, painel.config.captura, titulo, {}, texto, origem="humano")
        return {"rel": nota.rel, "url": ap.url_nota(nota.rel)}

    @app.post("/api/coletores/rodar")
    async def api_rodar_coletor(request: Request):
        dados = await corpo_json(request, contratos.Coletor)
        modulo, coletor = painel.coletor(str(dados.get("modulo") or ""), str(dados.get("script") or ""))
        resultado = await painel.rodar_coletor(modulo, coletor)
        if not resultado.ok:
            return JSONResponse({"erro": resultado.erro}, status_code=502)
        return {"novos": resultado.novos, "repetidos": resultado.repetidos}

    @app.post("/api/coletores/ativo")
    async def api_coletor_ativo(request: Request):
        dados = await corpo_json(request, contratos.AtivarColetor)
        await asyncio.to_thread(painel.definir_coletor_ativo, dados["modulo"], dados["script"], dados["ativo"])
        return {"ok": True}

    @app.post("/api/coletores/confiar")
    async def api_confiar_coletor(request: Request):
        if erro := exigir_local(request):
            return erro
        dados = await corpo_json(request, contratos.ConfiarColetor)
        modulo, coletor = painel.coletor(dados["modulo"], dados["script"])
        try:
            if dados.get("acao") == "revogar":
                await asyncio.to_thread(confianca.revogar, painel.vault, modulo, coletor)
                return estado_confianca(modulo, coletor)
            return await asyncio.to_thread(confianca.autorizar, painel.vault, modulo, coletor, dados.get("assinatura", ""))
        except ValueError as erro:
            raise Recusado(str(erro)) from None

    @app.post("/api/tema")
    async def api_tema(request: Request):
        dados = await corpo_json(request, contratos.Tema)
        await asyncio.to_thread(painel.definir_tema, dados["tema"])
        return {"ok": True}

    @app.post("/api/backup")
    async def api_backup(request: Request):
        dados = await corpo_json(request, contratos.Backup)
        if not backup.e_repositorio(painel.vault):
            raise Recusado("O vault ainda não é um repositório git. Rode `orquestra backup` no terminal para criar.")
        resultado = await asyncio.to_thread(painel.fazer_backup, bool(dados.get("enviar")))
        falhas = [r for r in resultado.values() if r not in ("feito", "nada")]
        if falhas:
            return JSONResponse({"erro": "; ".join(falhas), **resultado}, status_code=503)
        return resultado

    @app.post("/api/backup/iniciar")
    async def api_backup_iniciar(request: Request):
        if erro := exigir_local(request):
            return erro
        dados = await corpo_json(request, contratos.Backup)
        if not backup.e_repositorio(painel.vault):
            if not await asyncio.to_thread(backup.iniciar, painel.vault):
                raise Recusado("Não consegui iniciar o repositório. Confira a instalação do Git.")
            return {"revisar": True, "resumo": await asyncio.to_thread(backup.resumo, painel.vault)}
        if not dados.get("assinatura"):
            raise Recusado("Revise a configuração do histórico e confirme a assinatura exibida antes de autorizar.")
        atual = await asyncio.to_thread(backup.resumo, painel.vault)
        if atual["assinatura"] != dados["assinatura"]:
            raise Recusado("A configuração do histórico mudou. Recarregue e revise novamente.")
        if not atual["confiavel"]:
            raise Recusado("Revise e autorize o histórico antes de ativar as cópias automáticas.")
        await asyncio.to_thread(painel.iniciar_backup)
        return await asyncio.to_thread(painel.fazer_backup, False)

    @app.post("/api/backup/confiar")
    async def api_confiar_backup(request: Request):
        if erro := exigir_local(request):
            return erro
        dados = await corpo_json(request, contratos.ConfiarBackup)
        try:
            if dados.get("acao") == "revogar":
                await asyncio.to_thread(backup.revogar, painel.vault)
            else:
                await asyncio.to_thread(backup.autorizar, painel.vault, dados.get("assinatura", ""))
        except ValueError as erro:
            raise Recusado(str(erro)) from None
        return await asyncio.to_thread(backup.resumo, painel.vault)

    @app.post("/api/config")
    async def api_config(request: Request):
        dados = await corpo_json(request, contratos.Configuracao)
        await asyncio.to_thread(painel.definir_config,
            nome=dados.get("nome") if isinstance(dados.get("nome"), str) else None,
            captura=dados.get("captura") if isinstance(dados.get("captura"), str) else None,
            auto_commit=dados.get("auto_commit") if isinstance(dados.get("auto_commit"), bool) else None,
            visual=dados.get("aparencia") if isinstance(dados.get("aparencia"), dict) else None,
        )
        return {"ok": True}

    @app.post("/api/modulos")
    async def api_novo_modulo(request: Request):
        """Acrescenta uma área: um módulo pronto do catálogo ou um em branco."""
        dados = await corpo_json(request, contratos.CriarModulo)
        if dados.get("pronto"):
            modulo = await asyncio.to_thread(painel.adicionar_modulo, dados["pronto"], dados.get("exemplos", False))
        else:
            modulo = await asyncio.to_thread(painel.criar_modulo, dados.get("nome", ""), dados.get("icone", "nota"), dados.get("quadro", True))
        return {"id": modulo.id, "url": f"/m/{quote(modulo.id)}"}

    @app.put("/api/modulos/{modulo_id}")
    async def api_personalizar(request: Request, modulo_id: str):
        dados = await corpo_json(request, contratos.Personalizacao)
        modulo = await asyncio.to_thread(painel.personalizar_modulo, modulo_id, dados)
        return {"id": modulo.id, "url": f"/m/{quote(modulo.id)}", "avisos": modulo.avisos, "versao": modulo.versao}

    @app.post("/api/modulos/{modulo_id}/desligar")
    async def api_desligar(request: Request, modulo_id: str):
        await corpo_json(request)
        await asyncio.to_thread(painel.desligar_modulo, modulo_id)
        return {"ok": True}

    @app.get("/api/pastas/resumo")
    async def api_resumo_da_pasta(pasta: str = ""):
        """O que o painel entendeu de uma pasta, antes de ela virar área."""
        try:
            alvo = adocao._pasta_da_raiz(painel.vault, pasta)
        except adocao.NaoPodeAdotar as e:
            raise Recusado(str(e)) from None
        if (alvo / ARQUIVO_DESLIGADO).is_file():
            return {"nome": adocao.nome_legivel(alvo.name), "religar": True, "campos": [], "tem_status": True}
        return await asyncio.to_thread(adocao.resumo_da_pasta, alvo)

    @app.post("/api/pastas/adotar")
    async def api_adotar(request: Request):
        dados = await corpo_json(request, contratos.AdotarPasta)
        modulo = await asyncio.to_thread(painel.adotar_pasta, dados["pasta"], dados.get("quadro", False))
        return {"id": modulo.id, "url": f"/m/{quote(modulo.id)}"}

    @app.post("/api/pastas/nota")
    async def api_nota_em_pasta(request: Request):
        dados = await corpo_json(request, contratos.NotaPasta)
        nota = await asyncio.to_thread(painel.criar_nota_em_pasta, dados.get("pasta", ""), dados.get("titulo", ""), dados.get("corpo", ""))
        return {"rel": nota.rel, "url": ap.url_nota(nota.rel), "versao": nota.versao}

    @app.post("/api/numeros")
    async def api_numeros(request: Request):
        dados = await corpo_json(request, contratos.Numeros)
        try:
            dia = dt.date.fromisoformat(str(dados["dia"])) if dados.get("dia") else None
        except ValueError:
            raise Recusado("Use uma data no formato AAAA-MM-DD.") from None
        valores = dados.get("valores") if isinstance(dados.get("valores"), dict) else {}
        nota = await asyncio.to_thread(painel.registrar_numeros, dados["modulo"], valores, dia)
        return {"rel": nota.rel, "versao": nota.versao}

    @app.get("/api/resumo")
    @leitura
    def api_resumo():
        hoje = dt.date.today()
        dock = ap.montar_dock(painel, "", hoje)
        _, para_hoje = ap.montar_semana(painel, hoje)
        selos = {m["id"]: m["selo"] for m in dock["modulos"]}
        selos["decidir"] = dock["decidir"]
        selos["_gaveta"] = dock["gaveta_selo"]
        return {"selos": selos, "decidir": dock["decidir"], "hoje": para_hoje, "vault_id": vault_id}

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
    def arquivo(rel: str):
        """Serve imagens e vídeos do vault (miniaturas, capas). Só mídia, nunca outros arquivos."""
        caminho = painel.caminho_seguro(rel)
        if ignorar(rel, configuracao=True) or caminho.suffix.lower() not in EXT_MIDIA or not caminho.is_file():
            raise NaoEncontrado(rel)
        # A política abaixo impede que um SVG malicioso execute script se for aberto direto.
        return FileResponse(caminho, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"})

    @app.get("/favicon.ico")
    async def favicon():
        return RedirectResponse("/static/icone.svg")

    return app
