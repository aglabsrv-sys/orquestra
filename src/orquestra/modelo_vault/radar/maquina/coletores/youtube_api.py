# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: busca vídeos recentes no YouTube por termo, usando a YouTube Data API.

Precisa de uma chave gratuita do Google (YOUTUBE_API_KEY), guardada em
~/.orquestra/.env. Nunca coloque a chave dentro do vault.
Como criar a chave: docs/coletores.md.

Configuração (em radar/_modulo.yaml):
    termos: lista de buscas
    pais / idioma: filtros de região (BR / pt)
    maximo_por_termo: quantos vídeos por busca
"""

import json
import os
import sys
import urllib.error
import urllib.parse

from _comum import CONFIG, baixar, emitir

CHAVE = os.environ.get("YOUTUBE_API_KEY", "")


def main() -> None:
    if not CHAVE:
        sys.exit("Falta a chave YOUTUBE_API_KEY em ~/.orquestra/.env")
    for termo in CONFIG.get("termos", []):
        parametros = urllib.parse.urlencode(
            {
                "part": "snippet",
                "type": "video",
                "order": "date",
                "q": termo,
                "regionCode": CONFIG.get("pais", "BR"),
                "relevanceLanguage": CONFIG.get("idioma", "pt"),
                "maxResults": int(CONFIG.get("maximo_por_termo", 5)),
                "key": CHAVE,
            }
        )
        try:
            dados = json.loads(baixar("https://www.googleapis.com/youtube/v3/search?" + parametros))
        except urllib.error.HTTPError as erro:
            # Não mostramos o endereço: ele contém a chave.
            sys.exit(f"A API do YouTube recusou a busca '{termo}' (código {erro.code}). Confira a chave e a cota.")
        for item in dados.get("items", []):
            video = item.get("id", {}).get("videoId")
            trecho = item.get("snippet", {})
            if not video:
                continue
            emitir(
                id=f"youtube:{video}",
                titulo=trecho.get("title", "(sem título)"),
                corpo=trecho.get("description", ""),
                fonte="youtube",
                canal=trecho.get("channelTitle", ""),
                link=f"https://www.youtube.com/watch?v={video}",
                miniatura=f"https://i.ytimg.com/vi/{video}/hqdefault.jpg",
                publicado_em=trecho.get("publishedAt", "")[:10],
                tags=[termo],
            )


if __name__ == "__main__":
    main()
