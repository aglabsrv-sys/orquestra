# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: estrelas e forks de um repositório público do GitHub nos seus Números.

Usa a API pública do GitHub, sem chave (o limite é de 60 consultas por hora, e este
coletor faz uma por repositório por dia).

Configuração (em numeros/_modulo.yaml):

    repositorios:
      - repo: dono/nome            # como aparece no endereço do GitHub
        campo_estrelas: estrelas   # em que campo guardar; deixe vazio para não guardar
        campo_forks: ""

Cada campo precisa existir no módulo, com o tipo `numero` (crie em Personalizar).
"""

import datetime
import json

from _comum import CONFIG, avisar, baixar, emitir


def main() -> None:
    hoje = datetime.date.today().isoformat()
    campos = {"dia": hoje}
    for item in CONFIG.get("repositorios") or []:
        if not isinstance(item, dict) or not item.get("repo"):
            continue
        try:
            dados = json.loads(baixar(f"https://api.github.com/repos/{str(item['repo']).strip('/')}"))
        except Exception as erro:
            avisar(f"Não consegui ler {item['repo']}: {erro}")
            continue
        if item.get("campo_estrelas"):
            campos[str(item["campo_estrelas"])] = int(dados.get("stargazers_count", 0))
        if item.get("campo_forks"):
            campos[str(item["campo_forks"])] = int(dados.get("forks_count", 0))
    if len(campos) > 1:
        emitir(id=f"numeros:{hoje}", titulo=hoje, atualizar=True, **campos)


if __name__ == "__main__":
    main()
