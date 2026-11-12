# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: cotações do dia (dólar, euro, bitcoin...) nos seus Números.

Usa a AwesomeAPI de economia, que é pública e não pede chave:
https://docs.awesomeapi.com.br/api-de-moedas

Configuração (em numeros/_modulo.yaml):

    moedas:
      dolar: USD-BRL       # nome do campo: par de moedas
      euro: EUR-BRL
      bitcoin: BTC-BRL

Cada nome à esquerda precisa existir como campo do tipo `numero` no módulo (crie em
Personalizar). O coletor grava na nota de hoje, sem apagar o que já está nela.
"""

import datetime
import json

from _comum import CONFIG, avisar, baixar, emitir


def main() -> None:
    moedas = {str(campo): str(par).upper() for campo, par in (CONFIG.get("moedas") or {}).items() if par}
    if not moedas:
        avisar("Diga quais moedas acompanhar em numeros/_modulo.yaml (config.moedas).")
        return
    pares = ",".join(dict.fromkeys(moedas.values()))
    dados = json.loads(baixar(f"https://economia.awesomeapi.com.br/json/last/{pares}"))
    hoje = datetime.date.today().isoformat()
    campos = {"dia": hoje}
    for campo, par in moedas.items():
        cotacao = dados.get(par.replace("-", ""))
        if not cotacao or "bid" not in cotacao:
            avisar(f"Sem cotação para {par}.")
            continue
        campos[campo] = round(float(cotacao["bid"]), 4)
    if len(campos) > 1:
        emitir(id=f"numeros:{hoje}", titulo=hoje, atualizar=True, **campos)


if __name__ == "__main__":
    main()
