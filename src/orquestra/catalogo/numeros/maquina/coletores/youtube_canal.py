# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: números públicos de um canal do YouTube (inscritos e visualizações).

Usa a API oficial (YouTube Data API v3), que pede uma chave gratuita:
https://console.cloud.google.com/apis/library/youtube.googleapis.com
Coloque a chave em ~/.orquestra/.env, assim:  YOUTUBE_API_KEY=sua-chave

O script imprime uma linha de JSON com os números de hoje. O campo
"atualizar": true diz ao painel para completar a nota do dia se ela já existir,
em vez de ignorar o item como repetido.
"""

import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

config = json.loads(os.environ.get("ORQUESTRA_CONFIG") or "{}")
chave = os.environ.get("YOUTUBE_API_KEY", "")
canal = str(config.get("canal") or "").strip()

if not chave:
    sys.exit("Falta a YOUTUBE_API_KEY em ~/.orquestra/.env")
if not canal:
    sys.exit("Diga qual é o canal em numeros/_modulo.yaml (config.canal)")

filtro = {"forHandle": canal} if canal.startswith("@") else {"id": canal}
url = "https://www.googleapis.com/youtube/v3/channels?" + urllib.parse.urlencode(
    {"part": "statistics", "key": chave, **filtro}
)
with urllib.request.urlopen(url, timeout=30) as resposta:
    dados = json.load(resposta)

if not dados.get("items"):
    sys.exit(f"Canal não encontrado: {canal}")
numeros = dados["items"][0]["statistics"]

hoje = datetime.date.today().isoformat()
campos = {"dia": hoje}
if config.get("campo_inscritos") and "subscriberCount" in numeros:
    campos[config["campo_inscritos"]] = int(numeros["subscriberCount"])
if config.get("campo_visualizacoes") and "viewCount" in numeros:
    campos[config["campo_visualizacoes"]] = int(numeros["viewCount"])

print(json.dumps({"id": f"numeros:{hoje}", "titulo": hoje, "atualizar": True, "campos": campos}))
