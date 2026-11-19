"""Notas de apoio e de execução: leitura contextual, sem criar cartões ou registros."""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode

from orquestra import armazenamento, apresentacao as ap, lixeira, vinculos
from orquestra.caminhos import eh_link, ignorar
from orquestra.indice import EXT_MIDIA

_IMAGEM = re.compile(r"!\[\[([^\]|#]+)|!\[[^\]]*\]\(<?([^)\s>]+)")
_EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".svg"}
CAMPO_VINCULO = {"projetos": "projeto", "estudos": "estudo", "habitos": "habito"}


def subpastas_fisicas(painel, rel: str) -> list[str]:
    """Filhas visíveis, inclusive vazias e com apenas anexos."""
    pasta = painel.caminho_seguro(rel)
    if not pasta.is_dir():
        return []
    return sorted((n.name for n in pasta.iterdir() if not eh_link(n) and n.is_dir()
                   and not ignorar(f"{rel}/{n.name}/x.md") and not n.name.startswith("_")), key=str.casefold)


def midias_da_pasta(painel, rel: str) -> list[dict]:
    pasta = painel.caminho_seguro(rel)
    if not pasta.is_dir():
        return []
    arquivos = []
    for filho in sorted(pasta.iterdir(), key=lambda p: p.name.casefold()):
        caminho = filho.relative_to(painel.vault).as_posix()
        if eh_link(filho) or not filho.is_file() or ignorar(caminho):
            continue
        ext = filho.suffix.lower()
        if ext in EXT_MIDIA or ext in {".html", ".htm"}:
            arquivos.append({"nome": filho.name, "rel": caminho, "url": "/documento/" + quote(caminho),
                             "tipo": "html" if ext in {".html", ".htm"} else "midia",
                             "imagem": "/arquivo/" + quote(caminho) if ext in _EXT_IMAGEM else ""})
    return arquivos


def pasta_visual(chave: str, titulo: str, url: str, total: int, modulo=None, arquivos=()) -> dict:
    """Modelo comum à lista, aos cartões e às pastas de vidro."""
    arquivos = list(arquivos)
    imagem = next((a["imagem"] for a in arquivos if a.get("imagem")), "")
    visual = ajuste_de(modulo, chave, False, imagem, capa_automatica=True)
    return {**visual, "chave": chave, "nome": titulo, "titulo": visual["ajuste"]["titulo"] or titulo,
            "url": url, "total": total, "arquivos": arquivos}


def dividir_notas(notas: list[dict], rel: str) -> tuple[list[dict], dict[str, list[dict]]]:
    diretas, filhas = [], defaultdict(list)
    prefixo = rel + "/"
    for nota in notas:
        caminho = nota["rel"].removeprefix(prefixo)
        if caminho != nota["rel"] and "/" in caminho:
            filhas[caminho.split("/", 1)[0]].append(nota)
        else:
            diretas.append(nota)
    return diretas, filhas


def nivel(painel, modulo, pasta: dict, sub: str) -> dict:
    """Abre um nível da pasta, conservando a associação de todas as suas notas."""
    raiz = pasta["diretorio"]
    rel = f"{raiz}/{sub}" if sub else raiz
    # A rota só chega a subpastas apresentadas no nível anterior.
    atual = raiz
    for parte in sub.split("/") if sub else ():
        if parte not in subpastas_fisicas(painel, atual):
            from orquestra.painel import NaoEncontrado
            raise NaoEncontrado(sub)
        atual += "/" + parte
    notas = pasta["notas"]
    if sub:
        notas = [n for n in notas if n["rel"].startswith(rel + "/")]
    diretas, filhas = dividir_notas(notas, rel)
    consulta = {"abrir": pasta["chave"]}
    visual = []
    filhos = [] if pasta["chave"] == "grupo:" else subpastas_fisicas(painel, rel)
    for nome in filhos:
        caminho = f"{rel}/{nome}"
        arquivos = filhas.get(nome, [])[:4]
        if not any(a["imagem"] for a in arquivos):
            arquivos = [*arquivos, *(dict(a, titulo=a["nome"]) for a in midias_da_pasta(painel, caminho)[:4])]
        visual.append(pasta_visual("diretorio:" + caminho, nome,
                                  "?" + urlencode({**consulta, "pasta": "/".join(filter(None, (sub, nome)))}, quote_via=quote),
                                  len(filhas.get(nome, ())), modulo, arquivos))
    if sub:
        chave = "diretorio:" + rel
        pasta.update(ajuste_de(modulo, chave, False, capa_automatica=True), chave_ajustes=chave, estado="",
                     versao=lixeira.versao_pasta(painel.caminho_seguro(rel)), tipo_acao="diretorio")
        pasta["titulo"] = pasta["ajuste"]["titulo"] or sub.rsplit("/", 1)[-1]
        pai = sub.rpartition("/")[0]
        pasta["voltar"] = "?" + urlencode({**consulta, **({"pasta": pai} if pai else {})})
    return {**pasta, "notas": diretas, "subpastas": visual, "midias": midias_da_pasta(painel, rel),
            "sub": sub, "destino_nota": rel, "total": len(notas)}


def notas_da_acao(painel, item: str, vinculadas: dict) -> list:
    """Uma pasta de item só leva notas exclusivas dela."""
    compartilhadas = {n["rel"] for outro, notas in vinculadas.items() if outro != item for n in notas}
    return [painel.indice.notas[n["rel"]] for n in vinculadas.get(item, []) if n["rel"] not in compartilhadas] + [painel.nota(item)]


def versao_da_acao(notas) -> str:
    return armazenamento.versao(json.dumps(sorted((n.rel, n.versao) for n in notas)).encode())


def imagem_de(painel, nota) -> str:
    """Primeira imagem da nota: campo de imagem ou imagem incorporada no texto."""
    modulo = painel.indice.modulo_de(nota.rel)
    if modulo:
        for campo in modulo.campos.values():
            if campo.tipo == "imagem" and nota.campo(campo.nome):
                return ap.url_midia(nota.campo(campo.nome))
    for achado in _IMAGEM.finditer(nota.corpo or ""):
        alvo = (achado.group(1) or achado.group(2) or "").strip()
        if alvo.lower().startswith(("http://", "https://")):
            return alvo
        destino = painel.indice.resolver_referencia(alvo, nota.rel).rel
        if PurePosixPath(destino).suffix.lower() in _EXT_IMAGEM:
            return "/arquivo/" + quote(destino)
    return ""


def pastas(painel, modulo, itens) -> list[dict]:
    """Cada item vira uma pasta com suas notas vinculadas. Referências soltas
    ficam agrupadas pela própria subpasta, sem virar item do módulo."""
    from orquestra.modulos import rotulo
    vinculadas = por_item(painel, modulo.id, "referencias")
    hoje = dt.date.today()
    # Abertas primeiro; concluídas vão para o fim, sem sumir.
    itens = sorted(itens, key=lambda n: str(n.campo(modulo.campo_status) or "") in modulo.concluidos)

    def arquivo(info: dict) -> dict:
        nota = painel.indice.notas.get(info["rel"])
        return {**info, "imagem": imagem_de(painel, nota) if nota else ""}

    resultado = []
    for nota in itens:
        notas = vinculadas.get(nota.rel, [])
        status = nota.campo(modulo.campo_status) if modulo.tem_status else None
        # A nota do projeto mora dentro da pasta, atrás das mais recentes.
        arquivos = [*(arquivo(n) for n in notas[:3]), arquivo(apresentar(nota))]
        apoio = next((str(nota.campo(c.nome)) for c in modulo.campos.values()
                      if c.tipo == "texto" and c.nome != "origem" and nota.campo(c.nome) not in (None, "")), "")
        try:
            quando = ap.data_curta(dt.date.fromisoformat(str(nota.campo(modulo.campo_data) or "")[:10]), hoje) if modulo.campo_data else ""
        except ValueError:
            quando = ""
        resultado.append({
            "rel": nota.rel, "url": ap.url_nota(nota.rel), "titulo": nota.titulo,
            "apoio": apoio, "quando": quando,
            "estado": rotulo(status) if status else "",
            "concluido": str(status or "") in modulo.concluidos,
            "imagem": imagem_de(painel, nota) or next((a["imagem"] for a in arquivos if a["imagem"]), ""),
            "arquivos": arquivos, "total": len(notas) + 1, "item": True, "chave": nota.rel,
        })
    ligadas = {n["rel"] for notas in vinculadas.values() for n in notas}
    grupos: dict[str, list] = defaultdict(list)
    for nota in painel.indice.notas_em(modulo.id, "referencias"):
        if nota.rel not in ligadas and not nota.erro:
            partes = PurePosixPath(nota.rel).parts
            grupos[partes[2] if len(partes) > 3 else ""].append(apresentar(nota))
    raiz = f"{modulo.id}/referencias"
    if midias_da_pasta(painel, raiz):
        grupos.setdefault("", [])
    # Referências ligadas a um item usam a pasta dele. Uma pasta importada com
    # conteúdo próprio continua acessível mesmo sem notas Markdown.
    nomes_de_itens = {n.caminho.stem.casefold() for n in itens}
    for nome in subpastas_fisicas(painel, raiz):
        if nome.casefold() not in nomes_de_itens and (nome in grupos or not any(
            rel.startswith(f"{raiz}/{nome}/") for rel in ligadas
        ) or midias_da_pasta(painel, f"{raiz}/{nome}")):
            grupos.setdefault(nome, [])
    for nome, notas in sorted(grupos.items(), key=lambda g: g[0].casefold()):
        notas.sort(key=lambda n: n["titulo"].casefold())
        rel = f"{raiz}/{nome}" if nome else raiz
        midias = midias_da_pasta(painel, rel)
        resultado.append({
            "rel": "", "url": ap.url_pasta(rel),
            "titulo": nome or "Referências", "estado": "", "apoio": "", "quando": "", "concluido": False, "imagem": "",
            "arquivos": [arquivo(n) for n in notas[:4]] + [dict(a, titulo=a["nome"]) for a in midias[:4]],
            "total": len(notas), "item": False, "chave": "grupo:" + nome,
        })
    for pasta in resultado:
        pasta.update(ajuste_de(modulo, pasta["chave"], pasta["item"], pasta["imagem"]))
        pasta["titulo"] = pasta["ajuste"].get("titulo") or pasta["titulo"]
        pasta["href"] = "?" + urlencode({"abrir": pasta["chave"]}, quote_via=quote)
    return resultado


def ajuste_de(modulo, chave: str, item: bool, imagem_detectada: str = "", *, capa_automatica: bool = False) -> dict:
    """Capa e entrada rápida efetivas. Sem ajuste, cada pasta de item recebe uma
    das artes nativas pelo próprio nome (estável) ou a imagem achada nas notas;
    grupos de referências ficam lisos."""
    import zlib
    from orquestra.modulos import ARTES_DE_PASTA
    ajuste = modulo.pastas.get(chave, {}) if modulo else {}
    artes = list(ARTES_DE_PASTA)
    if ajuste.get("imagem"):
        imagem, arte = "/arquivo/" + quote(ajuste["imagem"]), ""
    elif ajuste.get("cor"):
        imagem, arte = "", ""
    elif ajuste.get("arte"):
        imagem, arte = "", ajuste["arte"]
    else:
        imagem = imagem_detectada if item or capa_automatica else ""
        arte = artes[zlib.crc32(chave.encode("utf-8")) % len(artes)] if (item or capa_automatica) and not imagem else ""
    return {"imagem": imagem, "arte": arte, "cor": ajuste.get("cor", ""), "entrada_rapida": bool(item and ajuste.get("entrada_rapida")),
            "ajuste": {"arte": ajuste.get("arte", ""), "imagem": ajuste.get("imagem", ""), "cor": ajuste.get("cor", ""),
                       "titulo": ajuste.get("titulo", ""),
                       "subpastas": ajuste.get("subpastas", ""),
                       "entrada_rapida": bool(ajuste.get("entrada_rapida"))}}


def dentro(painel, modulo, abrir: str) -> dict:
    """Conteúdo de uma pasta aberta: a nota do projeto primeiro, depois as vinculadas.
    `abrir` é o caminho do item ou `grupo:<subpasta>` para referências soltas."""
    from orquestra.modulos import rotulo
    from orquestra.painel import NaoEncontrado
    if abrir.startswith("grupo:"):
        nome = abrir[6:]
        prefixo = f"{modulo.id}/referencias/" + (f"{nome}/" if nome else "")
        ligadas = {n["rel"] for notas in por_item(painel, modulo.id, "referencias").values() for n in notas}
        notas = [apresentar(n) for n in painel.indice.notas_em(modulo.id, "referencias")
                 if n.rel not in ligadas and not n.erro and n.rel.startswith(prefixo)
                 and (nome or len(PurePosixPath(n.rel).parts) == 3)]
        pasta = prefixo.rstrip("/")
        if not notas and not (nome in subpastas_fisicas(painel, f"{modulo.id}/referencias") if nome else midias_da_pasta(painel, pasta)):
            raise NaoEncontrado(abrir)
        notas.sort(key=lambda n: n["titulo"].casefold())
        return {"titulo": modulo.pastas.get(abrir, {}).get("titulo") or nome or "Referências", "estado": "", "vinculo": "", "chave": abrir,
                "diretorio": pasta, "tipo_acao": "diretorio",
                "chave_acao": "diretorio:" + pasta,
                "versao": lixeira.versao_pasta(painel.caminho_seguro(pasta)) if nome and painel.caminho_seguro(pasta).is_dir() else "",
                **ajuste_de(modulo, abrir, False),
                "notas": [{**n, "imagem": imagem_de(painel, painel.indice.notas[n["rel"]]), "principal": False} for n in notas]}
    item = painel.indice.notas.get(abrir)
    if item is None or getattr(painel.indice.modulo_de(abrir), "id", None) != modulo.id or painel.indice.zona_de(abrir) != "itens":
        raise NaoEncontrado(abrir)
    status = item.campo(modulo.campo_status) if modulo.tem_status else None
    principal = {**apresentar(item), "imagem": imagem_de(painel, item), "principal": True}
    ligacoes = por_item(painel, modulo.id, "referencias")
    vinculadas = [{**n, "imagem": imagem_de(painel, painel.indice.notas[n["rel"]]), "principal": False}
                  for n in ligacoes.get(abrir, [])]
    return {"titulo": modulo.pastas.get(abrir, {}).get("titulo") or item.titulo, "estado": rotulo(status) if status else "", "vinculo": abrir, "chave": abrir,
            "diretorio": f"{modulo.id}/referencias/{item.caminho.stem}",
            "versao": versao_da_acao(notas_da_acao(painel, abrir, ligacoes)), "tipo_acao": "item",
            **ajuste_de(modulo, abrir, True), "notas": [principal, *vinculadas]}


def criar_vinculada(painel, item_rel: str, titulo: str, texto: str = "", destino: str = ""):
    """Cria uma nota de apoio ligada ao item, em <modulo>/referencias/<item>/."""
    from orquestra.painel import Recusado
    modulo = painel.indice.modulo_de(item_rel)
    item = painel.indice.notas.get(item_rel)
    if item is None or modulo is None or modulo.id not in ("projetos", "estudos") or painel.indice.zona_de(item_rel) != "itens":
        raise Recusado("Escolha um projeto ou estudo existente.")
    pasta = f"{modulo.id}/referencias/{item.caminho.stem}"
    if destino and destino != pasta:
        if not destino.startswith(pasta + "/") or not painel.caminho_seguro(destino).is_dir() or ignorar(destino + "/x.md"):
            raise Recusado("Escolha uma subpasta existente deste item.")
        pasta = destino
    painel.caminho_seguro(pasta).mkdir(parents=True, exist_ok=True)
    return painel.criar_nota_em_pasta(pasta, titulo, texto, campos={CAMPO_VINCULO[modulo.id]: f"[[{item.caminho.stem}]]"})


def _nome(valor: str) -> str:
    return unicodedata.normalize("NFC", valor).casefold().strip()


def apresentar(nota) -> dict:
    data = str(nota.campo("data") or "")[:10]
    if not data:
        achado = re.search(r"\d{4}-\d{2}-\d{2}", nota.caminho.stem)
        data = achado.group() if achado else ""
    try:
        data = dt.date.fromisoformat(data).isoformat()
    except ValueError:
        data = ""
    return {"titulo": nota.titulo, "rel": nota.rel, "url": ap.url_nota(nota.rel), "data": data,
            "pasta": str(PurePosixPath(nota.rel).parent)}


def por_item(painel, modulo_id: str, zona: str) -> dict[str, list[dict]]:
    candidatas = painel.indice.notas_em(modulo_id, zona, ordenar=False)
    if not candidatas:
        return {}
    itens = list(painel.indice.registros_em(modulo_id))
    ids = {n.rel for n in itens}
    nomes = defaultdict(set)
    for item in itens:
        for nome in (item.titulo, item.caminho.stem):
            nomes[_nome(nome)].add(item.rel)
    resultado = defaultdict(list)
    with vinculos.resolver_em_lote(painel.indice):
        for nota in candidatas:
            if nota.erro:
                continue
            referencias = list(painel.indice.referencias_de(nota.rel))
            destinos = set()
            if zona == "execucoes":
                destinos = {d.rel for ref in referencias if ref.campo == "habito"
                            and (d := painel.indice.resolver_referencia(ref, nota.rel)).rel in ids}
            if not destinos:
                destinos = {d.rel for ref in referencias
                            if (d := painel.indice.resolver_referencia(ref, nota.rel)).rel in ids}
            if not destinos:
                # A pasta mais próxima pode dar contexto; nomes ambíguos não são associados.
                for pasta in reversed(PurePosixPath(nota.rel).parts[2:-1]):
                    candidatos = nomes.get(_nome(pasta), set())
                    if len(candidatos) == 1:
                        destinos = candidatos
                        break
            for rel in destinos:
                resultado[rel].append(apresentar(nota))
    for notas in resultado.values():
        if zona == "execucoes":
            notas.sort(key=lambda n: (n["data"], painel.indice.notas[n["rel"]].mtime, n["rel"]), reverse=True)
        else:
            notas.sort(key=lambda n: (n["data"], n["titulo"].casefold(), n["rel"]), reverse=True)
    return resultado
