# Orquestra: instruções para agentes que trabalham no código

Este arquivo é para quem desenvolve o aplicativo. As regras para agentes que
trabalham dentro de um vault estão em `src/orquestra/modelo_vault/AGENTS.md`.

## Comandos

```bash
uv sync --locked
uv run --frozen python -m pytest -q          # suíte completa (~10 min)
uv run --frozen python -m pytest -q tests/test_x.py -k nome   # prefira rodar só o que mudou
uv run --frozen ruff check src tests scripts .github/scripts
uv run --frozen python .github/scripts/verificar_docs.py      # links e imagens dos .md
node --test tests/js/*.test.cjs
uv run --frozen orquestra iniciar --vault CAMINHO --porta 8421 # painel local para testar
```

Jornadas no navegador: `scripts/verificar_interface.py` (veja `CONTRIBUTING.md`).

## Convenções

- Código, comentários, mensagens e documentação em português do Brasil.
- Python 3.11+, servidor FastAPI e templates Jinja em `src/orquestra/`. O JavaScript
  e o CSS do painel ficam em `src/orquestra/static/` e vão ao navegador sem bundler.
- As capas em pixel art são desenhadas em `static/js/cenas.js`; temas ficam em
  `modelo_vault/_orquestra/temas/<id>/tema.yaml` e só aceitam cores em hexadecimal.
- Fim de linha LF (`.gitattributes`). Mudança de uso entra no `CHANGELOG.md`, em
  "Em desenvolvimento", e nos guias de `docs/`.

## Cuidados

- O vault é da pessoa: o app não apaga notas, não reescreve texto humano e não
  sobrescreve `AGENTS.md`, `CLAUDE.md` ou temas que ela editou.
- Ao mudar um tema distribuído, acrescente o sha256 da versão anterior em
  `TEMAS_ORIGINAIS_ANTIGOS` (`temas.py`), para cópias intactas nos vaults atualizarem.
- Nada de segredos ou notas reais no repositório. Capturas usam um vault de
  demonstração com notas fictícias.
- O painel escuta só em `127.0.0.1` e ações locais exigem a capacidade de
  `seguranca.py`. Não afrouxe isso para facilitar um teste.
- Não versione relatórios de auditoria, diários de implementação, registros de refinos ou contexto de conversas. A documentação do repositório deve descrever o produto; comunique resultados de revisões no chat e no PR.
