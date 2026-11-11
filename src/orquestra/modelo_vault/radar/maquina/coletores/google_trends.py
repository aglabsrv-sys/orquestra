# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: assuntos em alta no Google hoje, pelo feed público de tendências.

Configuração (em radar/_modulo.yaml):
    pais: código do país (BR, PT, US...)
    maximo: quantos assuntos pegar
"""

import datetime as dt
import urllib.parse
import xml.etree.ElementTree as ET

from _comum import CONFIG, baixar, emitir

HT = "{https://trends.google.com/trending/rss}"


def main() -> None:
    pais = str(CONFIG.get("pais", "BR")).upper()
    maximo = int(CONFIG.get("maximo", 10))
    raiz = ET.fromstring(baixar("https://trends.google.com/trending/rss?geo=" + urllib.parse.quote(pais)))

    hoje = dt.date.today().isoformat()
    for item in raiz.findall("channel/item")[:maximo]:
        assunto = (item.findtext("title") or "").strip()
        if not assunto:
            continue
        buscas = item.findtext(HT + "approx_traffic") or ""
        noticias = []
        for noticia in item.findall(HT + "news_item")[:3]:
            titulo = (noticia.findtext(HT + "news_item_title") or "").strip()
            link = (noticia.findtext(HT + "news_item_url") or "").strip()
            fonte = (noticia.findtext(HT + "news_item_source") or "").strip()
            if titulo and link:
                noticias.append(f"- [{titulo}]({link})" + (f" · {fonte}" if fonte else ""))
        emitir(
            # O mesmo assunto pode voltar a ficar em alta outro dia: o dia entra no id.
            id=f"tendencia:{pais}:{hoje}:{assunto.lower()}",
            titulo=f"Em alta: {assunto}",
            corpo=(f"Buscas aproximadas: {buscas}\n\n" if buscas else "") + "\n".join(noticias),
            fonte="tendencias",
            canal=f"Google Trends {pais}",
            link="https://trends.google.com/trends/explore?geo=" + pais + "&q=" + urllib.parse.quote(assunto),
            publicado_em=hoje,
        )


if __name__ == "__main__":
    main()
