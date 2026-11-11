# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: posts novos de qualquer feed RSS ou Atom (blogs, newsletters, podcasts).

Configuração (em radar/_modulo.yaml):
    feeds: lista de endereços de feed
    maximo_por_feed: quantos itens recentes pegar de cada um
"""

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from _comum import CONFIG, avisar, baixar, emitir

ATOM = "{http://www.w3.org/2005/Atom}"


def limpar(texto: str, tamanho: int = 500) -> str:
    """Tira as marcações HTML do resumo e corta num tamanho razoável."""
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto if len(texto) <= tamanho else texto[: tamanho - 1].rstrip() + "…"


def data_iso(texto: str) -> str:
    """Feeds usam dois formatos de data; devolvemos sempre AAAA-MM-DD (ou vazio)."""
    texto = (texto or "").strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", texto):
        return texto[:10]
    try:
        return parsedate_to_datetime(texto).date().isoformat()
    except (TypeError, ValueError):
        return ""


def itens_do_feed(raiz: ET.Element) -> tuple[str, list[dict]]:
    """Devolve (nome do feed, itens), entendendo os dois formatos: Atom e RSS 2.0."""
    itens = []
    if raiz.tag == ATOM + "feed":
        nome = raiz.findtext(ATOM + "title", default="")
        for e in raiz.findall(ATOM + "entry"):
            links = [link.get("href", "") for link in e.findall(ATOM + "link") if link.get("rel", "alternate") == "alternate"]
            link = links[0] if links else ""
            itens.append(
                {
                    "guid": e.findtext(ATOM + "id") or link,
                    "titulo": e.findtext(ATOM + "title", default=""),
                    "link": link,
                    "data": e.findtext(ATOM + "published") or e.findtext(ATOM + "updated") or "",
                    "resumo": e.findtext(ATOM + "summary") or e.findtext(ATOM + "content") or "",
                }
            )
        return nome, itens

    canal = raiz.find("channel")
    if canal is None:
        return "", []
    for i in canal.findall("item"):
        itens.append(
            {
                "guid": i.findtext("guid") or i.findtext("link") or "",
                "titulo": i.findtext("title", default=""),
                "link": i.findtext("link", default=""),
                "data": i.findtext("pubDate") or "",
                "resumo": i.findtext("description") or "",
            }
        )
    return canal.findtext("title", default=""), itens


def main() -> None:
    maximo = int(CONFIG.get("maximo_por_feed", 5))
    for url in CONFIG.get("feeds", []):
        try:
            nome, itens = itens_do_feed(ET.fromstring(baixar(str(url))))
        except Exception as erro:  # um feed com problema não impede os outros
            avisar(f"Falha em {url}: {erro}")
            continue
        for item in itens[:maximo]:
            titulo = limpar(item["titulo"], 140)
            if not titulo or not item["guid"]:
                continue
            emitir(
                id="rss:" + hashlib.sha1(item["guid"].encode("utf-8")).hexdigest()[:16],
                titulo=titulo,
                corpo=limpar(item["resumo"]),
                fonte="rss",
                canal=limpar(nome, 80),
                link=item["link"].strip(),
                publicado_em=data_iso(item["data"]),
            )


if __name__ == "__main__":
    main()
