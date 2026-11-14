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
import subprocess
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

from orquestra import __version__, adocao, agenda, aparencia, armazenamento, automacoes, backup, coletores, confianca, contratos, diario, graficos, preparo, temas, segredos, vinculos
from orquestra.caminhos import CaminhoInseguro, eh_link, ignorar
from orquestra.config import ConfigInvalida, ler_yaml
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
    from orquestra.github_local import LoginGitHub
    github = LoginGitHub()
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
            github.fechar()
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
    hosts_extras = list(painel.config.hosts_permitidos)
    app.add_middleware(Protecao, hosts_extras=hosts_extras)
    app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")

    modelos = Jinja2Templates(directory=PASTA / "templates")
    modelos.env.globals.update(icone=ap.icone, rotulo=rotulo, nome_cena=temas.nome_cena, url_nota=ap.url_nota, url_pasta=ap.url_pasta)
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
        resposta = modelos.TemplateResponse(request, nome, contexto, status_code=status)
        if nome == "nota.html" and request.query_params.get("explorador") == "1":
            from orquestra.seguranca import _CSP
            resposta.headers["Content-Security-Policy"] = _CSP.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
        return resposta

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
    @app.exception_handler(automacoes.ErroAutomacao)
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

    def conferir_vault(request: Request) -> None:
        vinculo = request.headers.get("x-orquestra-vault")
        if vinculo and vinculo != vault_id:
            raise Conflito("Esta aba pertence a outro vault. Reabra o vault correto ou copie o rascunho antes de atualizar.")

    async def corpo_json(request: Request, modelo: type[BaseModel] | None = None) -> dict[str, Any]:
        conferir_vault(request)
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
        vinculo = request.headers.get("x-orquestra-vault")
        if vinculo and vinculo != vault_id:
            raise Conflito("Esta aba pertence a outro vault. Reabra o painel antes de configurar.")
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
            if ap.agenda_nativa(modulo):
                continue
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
    def ver_modulo(request: Request, modulo_id: str, aba: str = "", pasta: str = ""):
        if modulo_id == "agenda" and ap.agenda_nativa(painel.modulo(modulo_id)) and not aba and not pasta:
            return RedirectResponse("/agenda", status_code=303)
        preferencia = "orq-visao-" + hashlib.sha256(f"{vault_id}:{modulo_id}".encode()).hexdigest()[:20]
        escolha_explicita = aba
        aba = aba or request.cookies.get(preferencia, "")
        if modulo_id == "habitos" and aba in ("v0", "progresso", "lista", "v1"):
            from orquestra import habitos
            resposta = pagina(request, "habitos.html", "m:habitos", **habitos.montar(painel, aba))
            if escolha_explicita:
                resposta.set_cookie(preferencia, aba, max_age=31536000, httponly=True, samesite="strict")
            return resposta
        if modulo_id == "habitos" and not aba:
            from orquestra import habitos
            return pagina(request, "habitos.html", "m:habitos", **habitos.montar(painel, "v0"))
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
        if modulo_id == "clientes":
            from orquestra.contatos import contexto as contexto_contatos
            contexto.update(contexto_contatos(painel))

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
                    "ajuda": automacoes.ajuda_coletor(c.script),
                    "atualizacao_disponivel": automacoes.legado_desatualizado(painel, modulo.id, c.script),
                }
                for c in modulo.coletores
            ]
            contexto["arquivadas"] = len(painel.indice.notas_em(modulo.id, "arquivo"))
        else:
            itens = painel.indice.itens(modulo.id)
            if modulo_id == "contatos":
                from orquestra.contatos import filtrar
                itens, filtros = filtrar(painel, itens, request.query_params)
                contexto.update(filtros)
            # Pastas existentes conservam a hierarquia: abrir uma pasta mostra
            # suas notas diretas e seus filhos, em vez de achatar o vault.
            if modulo.itens_na_raiz:
                pasta = pasta.replace("\\", "/").strip("/")
                if pasta and any(p in ("", ".", "..", "humano", "maquina", "arquivo") or p.startswith((".", "_")) for p in pasta.split("/")):
                    raise Recusado("Escolha uma subpasta desta área.")
                prefixo = modulo.id + "/" + (pasta + "/" if pasta else "")
                filhas: dict[str, int] = {}
                diretas = []
                for nota in itens:
                    if not nota.rel.startswith(prefixo):
                        continue
                    resto = nota.rel[len(prefixo):]
                    if "/" in resto:
                        filha = resto.split("/", 1)[0]
                        filhas[filha] = filhas.get(filha, 0) + 1
                    else:
                        diretas.append(nota)
                if pasta and not diretas and not filhas:
                    raise NaoEncontrado(pasta)
                contexto["pasta_atual"] = pasta
                contexto["subpastas"] = [{"nome": nome, "total": total, "caminho": "/".join(filter(None, (pasta, nome)))} for nome, total in sorted(filhas.items(), key=lambda p: p[0].casefold())]
                partes = pasta.split("/") if pasta else []
                contexto["trilha_pastas"] = [{"nome": nome, "caminho": "/".join(partes[:i + 1])} for i, nome in enumerate(partes)]
                itens = diretas
            if not aba:
                # Coleções e hierarquias funcionam melhor como listas. Um quadro
                # só é sugerido quando há distribuição real entre status.
                lista = next((i for i, v in enumerate(modulo.visoes) if v.tipo == "tabela"), 0)
                primeira = modulo.visoes[0]
                valores = {str(n.campo(primeira.agrupar_por)) for n in itens if n.campo(primeira.agrupar_por) not in (None, "")}
                aba = f"v{lista}" if contexto.get("subpastas") or (primeira.tipo == "kanban" and itens and len(valores) < 2) else "v0"
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
                if modulo.itens_na_raiz:
                    nomes = [n for n in nomes if n == "titulo" or any(nota.campo(n) not in (None, "", []) for nota in itens)]
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
        resposta = pagina(request, "modulo.html", f"m:{modulo.id}", **contexto)
        if escolha_explicita and escolha_explicita in {f"v{i}" for i in range(len(modulo.visoes))}:
            resposta.set_cookie(preferencia, contexto["aba"], max_age=31536000, httponly=True, samesite="strict")
        return resposta

    @app.get("/n/{rel:path}", response_class=HTMLResponse)
    @leitura
    def ver_nota(request: Request, rel: str):
        from orquestra import contatos, lixeira
        nota = painel.nota(rel)
        modulo = painel.indice.modulo_de(rel)
        zona = painel.indice.zona_de(rel) if modulo else ""
        campos = []
        outros = {}
        if modulo and zona in ("itens", "arquivo"):
            for campo in modulo.campos.values():
                if campo.nome == "origem" or campo.tipo in ("imagem", "link"):
                    continue
                campos.append({"def": campo, "valor": ap.valor_para_formulario(nota, campo.nome, campo.tipo)})
            conhecidos = {c["def"].nome for c in campos} | {"titulo"}
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
            html=ap.render_markdown(nota.corpo, painel.indice, nota.rel),
            avisos=validar(modulo, nota.meta) if modulo and zona == "itens" else [],
            imagem=imagem,
            campo_imagem=next((c.nome for c in modulo.campos.values() if c.tipo == "imagem"), "") if modulo else "",
            link_obsidian="obsidian://open?path=" + quote(str(nota.caminho), safe=""),
            pode_excluir=lixeira.pode_excluir(painel, rel),
            **(contatos.contexto(painel, nota) if modulo and modulo.id in ("contatos", "clientes") else {}),
        )

    @app.get("/lixeira", response_class=HTMLResponse)
    @leitura
    def ver_lixeira(request: Request):
        from orquestra import lixeira
        return pagina(request, "lixeira.html", "pastas", excluidas=lixeira.listar(painel.vault))

    @app.get("/decidir", response_class=HTMLResponse)
    @leitura
    def decidir(request: Request, modulo: str = ""):
        hoje = dt.date.today()
        aprovacao = modulo == "conteudo"
        pendentes = [(m, n) for m in painel.indice.modulos.values() for n in painel.indice.itens(m.id) if espera_decisao(n, m)]
        if modulo:
            painel.modulo(modulo)
            pendentes = [(m, n) for m, n in pendentes if m.id == modulo]
        selecionadas, paginacao = paginar(request, pendentes)
        grupos: dict[str, dict] = {}
        for modulo, nota in selecionadas:
            c = ap.cartao(nota, modulo, hoje)
            c["trecho"] = ap.trecho(nota, 180)
            c["por_status"] = str(nota.campo(modulo.campo_status) or "") in modulo.decidir
            grupos.setdefault(modulo.id, {"modulo": modulo, "cartoes": []})["cartoes"].append(c)
        return pagina(request, "decidir.html", "decidir", grupos=list(grupos.values()), total=len(pendentes), paginacao=paginacao, aprovacao=aprovacao, capa=None if painel.config.capas.get("decidir") is False else ap.capa_de(painel, "decidir"))

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
            capa=None if painel.config.capas.get("diario") is False else ap.capa_de(painel, "diario"),
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
        return pagina(request, "dia.html", "inicio", dia=alvo, dia_longo=ap.data_longa(alvo), e_hoje=alvo == hoje, resumo=diario.resumo_dia(painel, alvo, hoje))

    @app.get("/agenda", response_class=HTMLResponse)
    @app.get("/agenda/{data}", response_class=HTMLResponse)
    @leitura
    def ver_agenda(request: Request, data: str = "", visao: str = "mes", q: str = "", pasta: str = "", categoria: str = "", cor: str = "", tag: str = "", concluidos: str = ""):
        from orquestra import calendario
        try:
            alvo = dt.date.fromisoformat(data) if data else dt.date.today()
            agenda_visual = calendario.montar(painel, alvo, visao, q[:200], pasta, categoria, cor, tag, concluidos == "1")
        except ValueError as erro:
            raise Recusado(str(erro)) from None
        return pagina(request, "agenda.html", "calendario", cal=agenda_visual)

    @app.get("/api/agenda/evento/{rel:path}")
    @leitura
    def api_evento_agenda(rel: str):
        return painel.evento_agenda(rel)

    @app.post("/api/agenda/eventos")
    async def api_salvar_evento_agenda(request: Request):
        dados = await corpo_json(request, contratos.EventoAgenda)
        nota = await asyncio.to_thread(painel.salvar_evento_agenda, dados)
        return {"rel": nota.rel, "versao": nota.versao, "url": ap.url_nota(nota.rel)}

    @app.post("/api/agenda/mover")
    async def api_mover_evento_agenda(request: Request):
        dados = await corpo_json(request, contratos.MoverEventoAgenda)
        nota = await asyncio.to_thread(painel.mover_evento_agenda, dados)
        return {"rel": nota.rel, "versao": nota.versao}

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

    @app.get("/api/buscar")
    @leitura
    def api_buscar(q: str = "", limite: int = 12):
        """Resultados da busca flutuante: título, onde está e o trecho em volta do termo."""
        termo = " ".join(q.split())[:200]
        limite = max(1, min(int(limite), 30))
        encontrados, total = painel.indice.buscar_com_total(termo, limite)

        def trecho(n) -> str:
            corpo = " ".join(n.corpo.split())
            posicao = corpo.lower().find(termo.lower())
            if posicao < 0:
                return ap.trecho(n)
            inicio = max(0, posicao - 60)
            return ("…" if inicio else "") + corpo[inicio:posicao + len(termo) + 90].strip() + ("…" if posicao + len(termo) + 90 < len(corpo) else "")

        return {"total": total, "resultados": [
            {"url": ap.url_nota(n.rel), "titulo": n.titulo, "trecho": trecho(n), "onde": n.rel.rsplit("/", 1)[0] if "/" in n.rel else ""}
            for n in encontrados[:limite]
        ]}

    @app.get("/habitos", response_class=HTMLResponse)
    def ver_habitos(request: Request):
        return RedirectResponse("/m/habitos", status_code=307)

    @app.get("/foco", response_class=HTMLResponse)
    @leitura
    def ver_foco(request: Request):
        return pagina(request, "foco.html", "foco")

    @app.post("/api/habitos")
    async def salvar_habito(request: Request):
        from orquestra import habitos
        dados = await corpo_json(request, contratos.Habito)
        def gravar_habito():
            with painel._trava:
                instalado = "habitos" in painel.indice.modulos
                resultado = habitos.salvar(painel, dados)
                contexto = habitos.montar(painel)
                resultado["html"] = modelos.env.get_template("habito-card.html").render(**{**contexto, "item": resultado["item"], "hoje": dt.date.today()})
                resultado["ativado"] = not instalado
                return resultado
        return await asyncio.to_thread(gravar_habito)

    @app.post("/api/habitos/marcar")
    async def marcar_habito(request: Request):
        from orquestra import habitos
        dados = await corpo_json(request, contratos.MarcarHabito)
        return await asyncio.to_thread(habitos.marcar, painel, dados)

    @app.post("/api/conteudo/aprovacao")
    async def preparar_aprovacao(request: Request):
        await corpo_json(request)
        from orquestra.config import ler_yaml, gravar_yaml
        modulo = painel.modulo("conteudo")
        caminho = painel.caminho_seguro(str(modulo.pasta / "_modulo.yaml"))
        dados = ler_yaml(caminho)
        campo = (dados.get("campos") or {}).get("status") or {}
        if campo.get("tipo") != "escolha":
            raise Recusado("A aprovação precisa de um campo status do tipo escolha.")
        opcoes = campo.setdefault("opcoes", [])
        for opcao in ("em_aprovacao", "aprovado", "ajustes"):
            if opcao not in opcoes:
                opcoes.append(opcao)
        status = dados.setdefault("status", {})
        decidir = status.setdefault("decidir", [])
        if "em_aprovacao" not in decidir:
            decidir.append("em_aprovacao")
        acoes = status.setdefault("acoes", [])
        for acao in [{"rotulo": "Aprovar criativo", "definir": {"status": "aprovado"}, "estilo": "principal"}, {"rotulo": "Pedir ajustes", "definir": {"status": "ajustes"}}]:
            if not any(a.get("definir") == acao["definir"] for a in acoes if isinstance(a, dict)):
                acoes.append(acao)
        await asyncio.to_thread(gravar_yaml, caminho, dados)
        await asyncio.to_thread(painel.recarregar_tudo)
        return {"ok": True}

    def arquivos_da_pasta(rel: str) -> list[dict]:
        pasta = painel.caminho_seguro(rel)
        arquivos = []
        for filho in sorted(pasta.iterdir(), key=lambda p: p.name.casefold()):
            caminho = (rel + "/" + filho.name).strip("/")
            if filho.is_symlink() or not filho.is_file() or ignorar(caminho):
                continue
            ext = filho.suffix.lower()
            if ext in EXT_MIDIA or ext in {".html", ".htm"}:
                arquivos.append({"nome": filho.name, "rel": caminho, "url": "/documento/" + quote(caminho), "tipo": "html" if ext in {".html", ".htm"} else "midia"})
        return arquivos

    @app.get("/documento/{rel:path}")
    @leitura
    def documento(request: Request, rel: str):
        from html import escape
        caminho = painel.caminho_seguro(rel)
        if ignorar(rel) or not caminho.is_file() or caminho.suffix.lower() not in EXT_MIDIA | {".html", ".htm"}:
            raise NaoEncontrado(rel)
        if caminho.suffix.lower() in {".html", ".htm"}:
            from orquestra.documentos import preparar_html
            return HTMLResponse(preparar_html(caminho.read_text(encoding="utf-8-sig", errors="replace"), rel), headers={
                "Content-Security-Policy": "default-src 'none'; img-src 'self' https: data:; style-src 'unsafe-inline'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'; sandbox",
            })
        url = escape("/arquivo/" + quote(rel), quote=True)
        elemento = f'<video src="{url}" controls muted playsinline></video>' if caminho.suffix.lower() in {".mp4", ".webm"} else f'<img src="{url}" alt="{escape(caminho.name, quote=True)}">'
        return HTMLResponse('<!doctype html><meta name="viewport" content="width=device-width"><style>body{margin:0;display:grid;place-items:center;min-height:100vh;background:#111318}img,video{max-width:100%;max-height:100vh;object-fit:contain}</style>' + elemento, headers={"Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'self'; sandbox"})

    def conteudo_visivel_da_pasta(rel: str):
        subpastas, notas = painel.indice.conteudo_da_pasta(rel)
        nomes = dict(subpastas)
        for filho in painel.caminho_seguro(rel).iterdir():
            caminho = (rel + "/" + filho.name).strip("/")
            if filho.is_dir() and not eh_link(filho) and not deve_ignorar(caminho + "/x.md"):
                nomes.setdefault(filho.name, 0)
        return nomes, notas

    @app.get("/api/pastas/arvore")
    @leitura
    def arvore_pastas(request: Request, rel: str = ""):
        rel = rel.strip("/")
        pasta = painel.caminho_seguro(rel)
        if not pasta.is_dir() or (rel and deve_ignorar(rel + "/x.md")):
            raise NaoEncontrado(rel)
        nomes, notas = conteudo_visivel_da_pasta(rel)
        return {
            "pastas": [{"nome": n, "rel": (rel + "/" + n).strip("/"), "url": ap.url_pasta((rel + "/" + n).strip("/")), "notas": nomes[n]} for n in sorted(nomes, key=str.casefold)],
            "notas": [{"titulo": n.titulo, "rel": n.rel, "url": ap.url_nota(n.rel)} for n in notas[:300]],
            "total_notas": len(notas),
            "arquivos": arquivos_da_pasta(rel),
        }

    @app.get("/api/pastas/grafo")
    @leitura
    def grafo_pastas(request: Request, rel: str = ""):
        rel = rel.strip("/")
        if rel:
            pasta = painel.caminho_seguro(rel)
            if not pasta.is_dir() or deve_ignorar(rel + "/x.md"):
                raise NaoEncontrado(rel)
        notas = [n for n in painel.indice.notas.values() if not rel or n.rel.startswith(rel + "/")]
        selecionadas = sorted(notas, key=lambda n: n.rel.casefold())[:600]
        ids = {n.rel for n in selecionadas}
        ligacoes = set()
        with vinculos.resolver_em_lote(painel.indice):
            for n in selecionadas:
                for referencia in painel.indice.referencias_de(n.rel):
                    destino = painel.indice.resolver_referencia(referencia, n.rel).rel
                    if destino in ids and destino != n.rel:
                        ligacoes.add(tuple(sorted((n.rel, destino))))
                    if len(ligacoes) >= 3000:
                        break
                if len(ligacoes) >= 3000:
                    break
        return {"limitado": len(notas) > len(selecionadas) or len(ligacoes) >= 3000, "notas": [{"id": n.rel, "titulo": n.titulo, "url": ap.url_nota(n.rel)} for n in selecionadas], "ligacoes": sorted(ligacoes), "total": len(notas)}

    def conferir_pasta_vinculos(rel: str) -> str:
        rel = rel.strip("/")
        pasta = painel.caminho_seguro(rel)
        if not pasta.is_dir() or (rel and deve_ignorar(rel + "/x.md")):
            raise NaoEncontrado(rel)
        return rel

    @app.get("/api/vinculos")
    @leitura
    def api_vinculos(request: Request, rel: str = "", limite: int = 1000, filtro: str = "todos"):
        return vinculos.verificar_links(painel.indice, conferir_pasta_vinculos(rel), limite, filtro=filtro)

    @app.get("/vinculos", response_class=HTMLResponse)
    @leitura
    def ver_vinculos(request: Request, rel: str = "", filtro: str = "revisao"):
        rel = conferir_pasta_vinculos(rel)
        if filtro not in {"revisao", "futuro", "todos"}:
            filtro = "revisao"
        resultado = vinculos.verificar_links(painel.indice, rel, filtro=filtro)
        ocorrencias = []
        for item in resultado["ocorrencias"]:
            if filtro == "revisao" and item["estado"] == "futuro" or filtro == "futuro" and item["estado"] != "futuro":
                continue
            nota = painel.indice.notas.get(item["origem"])
            ocorrencias.append({**item, "titulo": nota.titulo if nota else item["origem"], "url_origem": ap.url_nota(item["origem"]),
                                "url_destino": ap.url_nota(item["rel"]) if item["rel"] in painel.indice.notas else "",
                                "opcoes": [{"rel": candidato, "url": ap.url_nota(candidato)} for candidato in item["candidatos"] if candidato in painel.indice.notas]})
        return pagina(request, "vinculos.html", "pastas", resultado=resultado, ocorrencias=ocorrencias, rel=rel, filtro=filtro,
                      url_pasta=ap.url_pasta(rel), rotulos_vinculos={"ausente": "Anexo ausente", "ambiguo": "Destino ambíguo", "ancora_ausente": "Seção ou bloco ausente", "bloqueado": "Destino indisponível", "futuro": "Nota ainda não criada"})

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
        nomes, notas = conteudo_visivel_da_pasta(rel)
        notas, paginacao = paginar(request, notas)
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
            capa_pasta=ap.capa_de(painel, "pastas") if painel.config.capas.get("pastas") else None,
            paginacao=paginacao,
            rel=rel,
            trilha=[{"nome": parte, "url": ap.url_pasta("/".join(partes[: i + 1]))} for i, parte in enumerate(partes)],
            pastas=pastas,
            arquivos=arquivos_da_pasta(rel),
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

    @app.get("/personalizar/{alvo}", response_class=HTMLResponse)
    @leitura
    def personalizar_pagina(request: Request, alvo: str):
        nomes = {"diario": "Diário", "decidir": "Decidir", "pastas": "Pastas"}
        if alvo not in nomes:
            raise NaoEncontrado(alvo)
        return pagina(request, "personalizar-pagina.html", alvo, alvo=alvo, nome_pagina=nomes[alvo],
                      capa=ap.capa_de(painel, alvo), escolha=painel.config.capas.get(alvo),
                      config_versao=armazenamento.versao((painel.vault / "orquestra.yaml").read_bytes() if (painel.vault / "orquestra.yaml").is_file() else b""),
                      cenas=temas.previas_das_cenas(painel.tema, alvo), colecao=temas.colecao(painel.tema["id"]))

    @app.post("/api/paginas/{alvo}/personalizar")
    async def api_personalizar_pagina(request: Request, alvo: str):
        dados = await corpo_json(request)
        await asyncio.to_thread(painel.personalizar_pagina, alvo, dados)
        return {"url": "/" + alvo}

    @app.get("/m/{modulo_id}/personalizar", response_class=HTMLResponse)
    @leitura
    def personalizar(request: Request, modulo_id: str):
        modulo = painel.modulo(modulo_id)
        return pagina(
            request,
            "personalizar.html",
            f"m:{modulo.id}",
            modulo=modulo,
            capa=ap.capa_de(painel, modulo.id, modulo.capa),
            campos=[c for c in modulo.campos.values() if c.nome != "origem"],
            tipos=sorted(TIPOS_DE_CAMPO),
            icones=ap.ICONES_DE_MODULO,
            cenas=temas.previas_das_cenas(painel.tema, modulo.id),
            colecao=temas.colecao(painel.tema["id"]),
            nomes_temas={t["id"]: t["nome"] for t in temas.listar(painel.vault)},
            cena_atual=ap.capa_de(painel, modulo.id, modulo.capa).get("cena", ""),
            cena_propria=modulo.capa.get("cena", "") if isinstance(modulo.capa, dict) else "",
            tem_quadro=any(v.tipo == "kanban" for v in modulo.visoes),
            tem_grafico=any(v.tipo == "grafico" for v in modulo.visoes),
            pode_quadro=modulo.tem_status,
            pode_grafico=bool(modulo.campos_numericos),
        )

    def destinos_automacoes() -> list[str]:
        """Pastas reais, inclusive vazias, sem seguir links ou incluir metadados."""
        encontrados = [""]
        pendentes = [painel.vault]
        while pendentes:
            pasta = pendentes.pop()
            painel.caminho_seguro(str(pasta.relative_to(painel.vault)).replace("\\", "/"))
            for filho in pasta.iterdir():
                rel = filho.relative_to(painel.vault).as_posix()
                if filho.name.startswith("_") or eh_link(filho) or deve_ignorar(rel + "/x.md") or not filho.is_dir():
                    continue
                painel.caminho_seguro(rel)
                encontrados.append(rel)
                pendentes.append(filho)
        return sorted(encontrados, key=str.casefold)

    @app.get("/ajustes", response_class=HTMLResponse)
    @app.get("/ajustes/{secao}", response_class=HTMLResponse)
    @leitura
    def ajustes(request: Request, secao: str = "painel"):
        if secao == "automacoes":
            secao = "coletores"
        if secao not in {"painel", "areas", "aparencia", "backup", "coletores", "acesso", "vault", "variaveis"}:
            raise NaoEncontrado(secao)
        # Cada seção é uma página independente: não ler catálogos, scripts ou Git
        # que não serão exibidos. Revisões de confiança continuam frescas na origem.
        contexto: dict[str, Any] = {"secao": secao, "icones": ap.ICONES_DE_MODULO}
        if secao == "painel":
            contexto["areas"] = [{"modulo": m} for m in painel.indice.modulos.values()]
            contexto.update(vault=str(painel.vault), n_notas=len(painel.indice.notas))
        elif secao == "areas":
            contexto["areas"] = [
                {"modulo": m, "itens": len(painel.indice.notas_em(m.id, "itens")), "propria": m.itens_na_raiz}
                for m in painel.indice.modulos.values()
            ]
            contexto["prontos"] = [
                m for m in preparo.catalogo().values() if m.id != "agenda" and m.id not in painel.indice.modulos and not (painel.vault / m.id).exists()
            ]
            contexto["retirados"] = []
            for pasta in sorted(painel.vault.iterdir(), key=lambda p: p.name.casefold()):
                if pasta.name in painel.indice.modulos or ignorar(pasta.name) or pasta.name.startswith("_") or eh_link(pasta) or not pasta.is_dir():
                    continue
                try:
                    arquivo = painel.caminho_seguro(f"{pasta.name}/{ARQUIVO_DESLIGADO}")
                    if not arquivo.is_file():
                        continue
                    dados = ler_yaml(arquivo)
                    contexto["retirados"].append({"id": pasta.name, "nome": str(dados.get("nome") or pasta.name),
                                                   "icone": str(dados.get("icone") or "pasta")})
                except (OSError, ValueError):
                    contexto["retirados"].append({"id": pasta.name, "nome": pasta.name, "icone": "pasta"})
        elif secao == "aparencia":
            contexto["cenas"] = temas.CENAS
            contexto["temas"] = [
                {**tema, "previa": temas.previa(tema), "atual": tema["id"] == painel.tema["id"],
                 "efetivas": aparencia.amostras(tema, painel.config.aparencia)["tema"]}
                for tema in temas.listar(painel.vault)
            ]
            contexto["visual"] = {
                "modos": aparencia.MODOS,
                "cantos": list(aparencia.CANTOS),
                "fontes": aparencia.FONTES,
                "nomes": aparencia.NOMES,
                "sugestoes": aparencia.SUGESTOES,
                "destaque_do_tema": painel.tema["cores"]["destaque"],
                "amostras": aparencia.amostras(painel.tema, painel.config.aparencia),
            }
        elif secao == "backup":
            confianca_backup = backup.resumo(painel.vault)
            tem_git = backup.e_repositorio(painel.vault)
            contexto.update(
                tem_git=tem_git,
                tem_git_instalado=backup.git_disponivel(),
                tem_remoto=bool(confianca_backup.get("remotos")),
                ultimo_commit=backup.ultimo_commit(painel.vault) if tem_git else "",
                estado_backup=painel.ler_estado().get("backup", {}),
                confianca_backup=confianca_backup,
            )
        elif secao == "coletores":
            ultimas = painel.ler_estado().get("coletores", {})
            contexto["coletores"] = [
                {"modulo": m, "def": c, "ultima": ultimas.get(f"{m.id}/{c.script}", {})}
                for m in painel.indice.modulos.values() for c in m.coletores
            ]
            contexto.update(catalogo_automacoes=automacoes.catalogo(), automacoes=automacoes.listar(painel), automacoes_legadas=automacoes.legadas(painel))
        elif secao == "acesso":
            contexto["host"] = request.headers.get("host", "")
        elif secao == "vault":
            contexto.update(
                vault=str(painel.vault), n_notas=len(painel.indice.notas),
                avisos=[(m.nome, a) for m in painel.indice.modulos.values() for a in m.avisos],
                pode_trocar=hospedeiro is not None,
                link_obsidian="obsidian://open?path=" + quote(str(painel.vault), safe=""),
            )
        return pagina(request, "ajustes.html", "ajustes", **contexto)

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
            subpasta=str(dados.get("subpasta") or ""),
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
                return {"rel": nota.rel, "versao": nota.versao, "html": str(ap.render_markdown(nota.corpo, painel.indice, nota.rel))}
        return await asyncio.to_thread(editar_e_renderizar)

    @app.post("/api/arquivar/{rel:path}")
    async def api_arquivar(request: Request, rel: str):
        dados = await corpo_json(request, contratos.Versao)
        return {"rel": await asyncio.to_thread(painel.arquivar, rel, versao=dados["versao"])}

    @app.post("/api/contatos/cliente/{rel:path}")
    async def api_vincular_cliente(request: Request, rel: str):
        dados = await corpo_json(request, contratos.Versao)
        nota = await asyncio.to_thread(painel.vincular_cliente, rel, dados["versao"])
        return {"rel": nota.rel, "url": ap.url_nota(nota.rel)}

    @app.post("/api/excluir/{rel:path}")
    async def api_excluir(request: Request, rel: str):
        if erro := exigir_local(request):
            return erro
        dados = await corpo_json(request, contratos.Versao)
        return {"id": await asyncio.to_thread(painel.excluir, rel, dados["versao"])}

    @app.post("/api/lixeira/{identificador}/{acao}")
    async def api_lixeira(request: Request, identificador: str, acao: str):
        if erro := exigir_local(request):
            return erro
        from orquestra import lixeira
        dados = await corpo_json(request, contratos.Versao)
        try:
            if acao == "restaurar":
                rel = await asyncio.to_thread(painel.restaurar_excluida, identificador, dados["versao"])
                return {"url": ap.url_nota(rel)}
            if acao == "apagar":
                await asyncio.to_thread(lixeira.apagar, painel.vault, identificador, dados["versao"])
                return {"ok": True}
        except FileNotFoundError:
            raise NaoEncontrado("Este item não está mais na lixeira.") from None
        except ValueError as erro:
            raise Recusado(str(erro)) from None
        raise Recusado("Escolha restaurar ou apagar.")

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

    @app.get("/api/automacoes/catalogo")
    @leitura
    def api_catalogo_automacoes(request: Request):
        return {"catalogo": automacoes.catalogo(), "instancias": automacoes.listar(painel), "legadas": automacoes.legadas(painel), "pastas": destinos_automacoes()}

    @app.post("/api/automacoes/legado/prever")
    async def api_prever_automacao_legada(request: Request):
        dados = await corpo_json(request, contratos.ConfigurarColetor)
        return await asyncio.to_thread(automacoes.prever_legada, painel, **dados)

    @app.post("/api/automacoes/legado/editar")
    async def api_editar_automacao_legada(request: Request):
        dados = await corpo_json(request, contratos.ConfigurarColetor)
        return await asyncio.to_thread(automacoes.atualizar_legada, painel, **{"versao": "", **dados})

    @app.post("/api/automacoes/legado/atualizar")
    async def api_atualizar_automacao_legada(request: Request):
        if erro := exigir_local(request):
            return erro
        dados = await corpo_json(request, contratos.AtualizarColetor)
        return await asyncio.to_thread(automacoes.atualizar_codigo_legado, painel, **dados)

    @app.post("/api/automacoes/prever")
    async def api_prever_automacao(request: Request):
        dados = await corpo_json(request, contratos.PreviaAutomacao)
        return await asyncio.to_thread(automacoes.prever, painel, dados["definicao"], dados.get("destino", ""), dados.get("config"), dados.get("mapeamento"), ignorar_id=dados.get("id"))

    @app.post("/api/automacoes/criar")
    async def api_criar_automacao(request: Request):
        dados = await corpo_json(request, contratos.PedidoAutomacao)
        return await asyncio.to_thread(automacoes.criar, painel, **{"destino": "", **dados})

    @app.post("/api/automacoes/editar")
    async def api_editar_automacao(request: Request):
        dados = await corpo_json(request, contratos.EditarAutomacao)
        identificador = dados.pop("id")
        return await asyncio.to_thread(automacoes.atualizar, painel, identificador, **{"destino": "", **dados})

    @app.post("/api/automacoes/confiar")
    async def api_confiar_automacao(request: Request):
        if erro := exigir_local(request):
            return erro
        dados = await corpo_json(request, contratos.ConfiarAutomacao)
        return await asyncio.to_thread(automacoes.autorizar, painel, dados["id"], dados["assinatura"])

    @app.post("/api/automacoes/ativo")
    async def api_automacao_ativa(request: Request):
        dados = await corpo_json(request, contratos.AtivarAutomacao)
        return await asyncio.to_thread(automacoes.ativar, painel, dados["id"], dados["ativo"])

    @app.post("/api/automacoes/remover")
    async def api_remover_automacao(request: Request):
        dados = await corpo_json(request, contratos.IdAutomacao)
        await asyncio.to_thread(automacoes.remover, painel, dados["id"])
        return {"ok": True}

    @app.post("/api/automacoes/rodar")
    async def api_rodar_automacao(request: Request):
        dados = await corpo_json(request, contratos.ExecutarAutomacao)
        resultado = await automacoes.rodar(painel, dados["id"], previa=dados.get("previa", False))
        return JSONResponse(resultado, status_code=200 if resultado.get("ok", True) else 502)

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
        return {"ok": True, "estilo": aparencia.estilo(painel.tema, painel.config.aparencia)}

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

    @app.get("/api/variaveis")
    async def api_variaveis(request: Request):
        if erro := exigir_local(request):
            return erro
        try:
            return {"nomes": await asyncio.to_thread(segredos.nomes, painel.vault)}
        except ValueError as erro:
            raise Recusado(str(erro)) from None

    @app.post("/api/agenda/conectar")
    async def api_conectar_agenda(request: Request):
        if erro := exigir_local(request):
            return erro
        dados = await corpo_json(request)
        from urllib.parse import urlsplit
        endereco = str(dados.get("url") or "").replace("webcal://", "https://", 1)
        try:
            url = urlsplit(endereco)
        except ValueError:
            raise Recusado("Endereço iCal inválido.") from None
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
            raise Recusado("Use um endereço iCal HTTPS, sem usuário ou senha na URL.")
        modulo, coletor = painel.coletor("tarefas", "agenda_ics.py")
        script = confianca.caminho_script(painel.vault, modulo, coletor)
        novo = (PASTA / "catalogo/tarefas/maquina/coletores/agenda_ics.py").read_bytes().replace(b"\r\n", b"\n")
        anterior = novo.replace(b"import os\n", b"").replace(b'        if isinstance(agenda, dict) and agenda.get("variavel"):\n            endereco = os.environ.get(str(agenda["variavel"]), "")\n', b"")
        atual = script.read_bytes().replace(b"\r\n", b"\n")
        if atual not in (novo.replace(b"\r\n", b"\n"), anterior.replace(b"\r\n", b"\n")):
            raise Recusado("Este coletor foi personalizado. Adapte a leitura da variável AGENDA_ICAL_URL no script antes de conectar.")
        if atual != novo.replace(b"\r\n", b"\n"):
            def atualizar_script(antes: bytes) -> bytes:
                if antes.replace(b"\r\n", b"\n") != atual:
                    raise Conflito("O coletor mudou durante a configuração. Confira a nova versão antes de continuar.")
                return novo
            await asyncio.to_thread(armazenamento.atualizar_bytes, script, atualizar_script)
        # Não substitui código alterado pelo usuário. O novo contrato pede revisão.
        from orquestra.config import ler_yaml, gravar_yaml
        caminho = painel.caminho_seguro(str(modulo.pasta / "_modulo.yaml"))
        conf = ler_yaml(caminho)
        await asyncio.to_thread(segredos.salvar, painel.vault, "AGENDA_ICAL_URL", endereco)
        for definicao in conf.get("coletores") or []:
            if definicao.get("script") == coletor.script:
                definicao["config"] = {"agendas": [{"nome": "Pessoal", "variavel": "AGENDA_ICAL_URL"}], "dias_a_frente": 14}
                definicao["requer"] = ["AGENDA_ICAL_URL"]
                definicao["ativo"] = False
        await asyncio.to_thread(gravar_yaml, caminho, conf)
        await asyncio.to_thread(painel.recarregar_tudo)
        return {"ok": True, "revisar": True}

    @app.post("/api/capas")
    async def api_enviar_capa(request: Request):
        if erro := exigir_local(request):
            return erro
        conferir_vault(request)
        dados = await request.body()
        if not dados or len(dados) > 2 * 1024 * 1024:
            raise Recusado("Envie uma capa de até 2 MB.")
        extensao = ""
        if dados.startswith(b"\x89PNG\r\n\x1a\n"):
            extensao = ".png"
        elif dados.startswith(b"\xff\xd8\xff"):
            extensao = ".jpg"
        elif dados.startswith(b"RIFF") and dados[8:12] == b"WEBP":
            extensao = ".webp"
        elif dados[4:8] == b"ftyp":
            extensao = ".mp4"
        elif dados.startswith(b"\x1a\x45\xdf\xa3"):
            extensao = ".webm"
        if not extensao:
            raise Recusado("Use PNG, JPEG, WebP, MP4 ou WebM.")
        rel = "midia/capas/" + hashlib.sha256(dados).hexdigest()[:32] + extensao
        caminho = painel.caminho_seguro(rel)
        await asyncio.to_thread(armazenamento.atualizar_bytes, caminho, lambda _: dados, backup=False,
                                validar=lambda: painel.caminho_seguro(rel))
        return {"caminho": rel}

    @app.post("/api/variaveis")
    async def api_salvar_variavel(request: Request):
        if erro := exigir_local(request):
            return erro
        dados = await corpo_json(request, contratos.SalvarSegredo)
        try:
            await asyncio.to_thread(segredos.salvar, painel.vault, dados["nome"], dados["valor"])
            return {"ok": True}
        except ValueError as erro:
            raise Recusado(str(erro)) from None

    def estado_autostart():
        from orquestra import autostart, processo
        estado = autostart.resumo(painel.vault)
        if hospedeiro is not None and hospedeiro.servidor is not None:
            independente = processo.em_segundo_plano()
            estado.update(segundo_plano=independente, precisa_aplicar=estado["ativo"] and not independente)
            if estado["ativo"]:
                estado["descricao"] = "Ativado. O painel está em segundo plano; você pode fechar o terminal." if independente else "Configurado para iniciar com o computador. Aplique agora para poder fechar o terminal."
        return estado

    @app.get("/api/autostart")
    async def api_estado_autostart(request: Request):
        if erro := exigir_local(request):
            return erro
        return await asyncio.to_thread(estado_autostart)

    @app.post("/api/autostart")
    async def api_autostart(request: Request):
        if erro := exigir_local(request):
            return erro
        from orquestra import autostart
        dados = await corpo_json(request)
        acao = dados.get("acao")
        if acao not in {"ativar", "desativar", "status"}:
            raise Recusado("Escolha ativar, desativar ou status.")
        try:
            await asyncio.to_thread(autostart.executar, acao, painel.vault if acao in {"ativar", "status"} else None)
            estado = await asyncio.to_thread(estado_autostart)
            if acao == "ativar" and estado.get("precisa_aplicar"):
                from orquestra import processo
                porta = hospedeiro.servidor.config.port
                await asyncio.to_thread(processo.destacar, painel.vault, porta, os.getpid())
                return {**estado, "reiniciando": True, "mensagem": "Aplicando em segundo plano…"}
            return {**estado, "mensagem": "Pronto"}
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as erro:
            raise Recusado(str(erro)) from None

    @app.post("/api/tailscale/host")
    async def api_tailscale_host(request: Request):
        if erro := exigir_local(request):
            return erro
        import re
        from urllib.parse import urlsplit
        from orquestra.config import ler_yaml, gravar_yaml
        dados = await corpo_json(request)
        endereco = str(dados.get("url") or "").strip()
        try:
            parsed = urlsplit(endereco if "://" in endereco else "https://" + endereco)
        except ValueError:
            raise Recusado("Endereço Tailscale inválido.") from None
        host = parsed.hostname or ""
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or not re.fullmatch(r"[a-z0-9-]+\.[a-z0-9-]+\.ts\.net", host):
            raise Recusado("Cole somente o endereço HTTPS exato mostrado pelo Tailscale Serve.")
        try:
            if parsed.port not in (None, 443):
                raise Recusado("Use o endereço HTTPS padrão do Tailscale Serve.")
        except ValueError:
            raise Recusado("A porta do endereço é inválida.") from None
        caminho = painel.vault / "orquestra.yaml"
        cfg = ler_yaml(caminho)
        nomes = list(cfg.get("hosts_permitidos") or [])
        if host not in nomes:
            nomes.append(host)
        cfg["hosts_permitidos"] = nomes
        await asyncio.to_thread(gravar_yaml, caminho, cfg)
        await asyncio.to_thread(painel.recarregar_config)
        hosts_extras[:] = nomes
        return {"ok": True, "mensagem": "Endereço permitido. Abra-o no celular conectado à sua rede Tailscale."}

    @app.post("/api/github/login")
    async def api_github_login(request: Request):
        if erro := exigir_local(request):
            return erro
        try:
            return await asyncio.to_thread(github.iniciar)
        except (ValueError, OSError) as erro:
            raise Recusado(str(erro) if isinstance(erro, ValueError) else "Não consegui abrir o GitHub CLI.") from None

    @app.get("/api/github/estado")
    async def api_github_estado(request: Request):
        if erro := exigir_local(request):
            return erro
        return github.estado()

    @app.get("/api/github/repositorios")
    async def api_github_repositorios(request: Request):
        if erro := exigir_local(request):
            return erro
        try:
            resultado = await asyncio.to_thread(github.comando, ["repo", "list", "--visibility", "private", "--limit", "100", "--json", "nameWithOwner"])
            return {"repositorios": [r["nameWithOwner"] for r in json.loads(resultado)]}
        except (ValueError, OSError, subprocess.TimeoutExpired):
            raise Recusado("Não consegui listar os repositórios privados. Confira o login no GitHub CLI.") from None

    @app.post("/api/github/vincular")
    async def api_github_vincular(request: Request):
        if erro := exigir_local(request):
            return erro
        import re
        dados = await corpo_json(request)
        repo = str(dados.get("repositorio") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", repo):
            raise Recusado("Escolha um repositório no formato usuario/repositorio.")
        if not backup.e_repositorio(painel.vault):
            raise Recusado("Prepare primeiro o histórico local em Ajustes → Backup.")
        resumo = await asyncio.to_thread(backup.resumo, painel.vault)
        if resumo.get("erro"):
            raise Recusado("Revise a configuração Git antes de vincular.")
        try:
            metadados = json.loads(await asyncio.to_thread(github.comando, ["repo", "view", "https://github.com/" + repo, "--json", "isPrivate"]))
            if not metadados.get("isPrivate"):
                raise Recusado("Escolha um repositório privado para proteger suas notas.")
            import shutil
            git = shutil.which("git")
            if not git:
                raise Recusado("Instale o Git antes de vincular.")
            for chave in ("remote.origin.url", "remote.origin.pushurl"):
                await asyncio.to_thread(subprocess.run, [git, "-C", str(painel.vault), "config", "--local", "--replace-all", chave, "https://github.com/" + repo + ".git"], check=True, capture_output=True, timeout=15,
                                        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            return {"ok": True, "mensagem": "Repositório vinculado. Revise e autorize o destino em Backup antes do primeiro envio."}
        except (ValueError, OSError, subprocess.SubprocessError):
            raise Recusado("Não foi possível vincular o repositório. Nenhuma nota foi enviada.") from None

    @app.post("/api/config")
    async def api_config(request: Request):
        dados = await corpo_json(request, contratos.Configuracao)
        await asyncio.to_thread(painel.definir_config,
            nome=dados.get("nome") if isinstance(dados.get("nome"), str) else None,
            captura=dados.get("captura") if isinstance(dados.get("captura"), str) else None,
            auto_commit=dados.get("auto_commit") if isinstance(dados.get("auto_commit"), bool) else None,
            visual=dados.get("aparencia") if isinstance(dados.get("aparencia"), dict) else None,
            ordem_pastas=dados.get("ordem_pastas"),
        )
        return {"ok": True, "estilo": aparencia.estilo(painel.tema, painel.config.aparencia)}

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
