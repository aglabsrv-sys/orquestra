# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: vídeos novos de canais do YouTube, pelo feed público (não precisa de chave).

Configuração (em radar/_modulo.yaml):
    canais: lista com @nome, link do canal ou ID (começa com UC)
    maximo_por_canal: quantos vídeos recentes pegar de cada canal
"""

import re
import xml.etree.ElementTree as ET

from _comum import CONFIG, avisar, baixar, emitir

NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "m": "http://search.yahoo.com/mrss/"}


def id_do_canal(canal: str) -> str | None:
    """Aceita 'UCxxxx', '@nome' ou o link do canal e devolve o ID."""
    canal = canal.strip()
    achado = re.search(r"(UC[\w-]{22})", canal)
    if achado:
        return achado.group(1)
    if not canal.startswith("http"):
        canal = "https://www.youtube.com/" + (canal if canal.startswith("@") else "@" + canal)
    pagina = baixar(canal).decode("utf-8", errors="replace")
    achado = re.search(r"channel_id=(UC[\w-]{22})", pagina) or re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', pagina)
    return achado.group(1) if achado else None


def main() -> None:
    maximo = int(CONFIG.get("maximo_por_canal", 5))
    for canal in CONFIG.get("canais", []):
        try:
            canal_id = id_do_canal(str(canal))
            if not canal_id:
                avisar(f"Não achei o canal {canal}")
                continue
            feed = ET.fromstring(baixar(f"https://www.youtube.com/feeds/videos.xml?channel_id={canal_id}"))
        except Exception as erro:  # um canal com problema não impede os outros
            avisar(f"Falha em {canal}: {erro}")
            continue

        nome_canal = feed.findtext("a:title", default=str(canal), namespaces=NS)
        for entrada in feed.findall("a:entry", NS)[:maximo]:
            video = entrada.findtext("yt:videoId", namespaces=NS)
            if not video:
                continue
            emitir(
                id=f"youtube:{video}",
                titulo=entrada.findtext("a:title", default="(sem título)", namespaces=NS),
                corpo=entrada.findtext("m:group/m:description", default="", namespaces=NS).strip()[:600],
                fonte="youtube",
                canal=nome_canal,
                link=f"https://www.youtube.com/watch?v={video}",
                miniatura=f"https://i.ytimg.com/vi/{video}/hqdefault.jpg",
                publicado_em=entrada.findtext("a:published", default="", namespaces=NS)[:10],
            )


if __name__ == "__main__":
    main()
