# Contribuir com o Orquestra

O projeto usa Python 3.11 ou mais recente, uv e Git. O JavaScript do painel é
entregue diretamente ao navegador, sem bundler; Node 20+ é necessário apenas para
os testes de JavaScript. Veja a instalação no [README](README.md).

## Preparar e verificar

```bash
uv sync --locked
uv run --frozen python -m pytest -q
uv run --frozen ruff check src tests scripts
node --test tests/js/*.test.cjs
uv build
uv run --frozen python scripts/verificar_pacote.py dist
```

Os testes usam diretórios temporários e `ORQUESTRA_HOME` isolado. Nunca aponte
testes automatizados para seu vault real. Para trabalho manual, crie um vault de
exemplo fora do repositório do aplicativo e mantenha uma cópia de recuperação.
O Ruff verifica erros de sintaxe e todas as regras Pyflakes (`E9` e `F`), incluindo
nomes indefinidos e imports não utilizados.

O workflow de qualidade cobre Windows, macOS e Linux com Python 3.11 e 3.13,
empacotamento, lint, testes e dependências conhecidamente vulneráveis. Um workflow
pendente ou sem runner não significa aprovação. Os testes de instalação em CI
também não substituem uso real de Obsidian, Tailscale e login automático.

## Mudanças e pull requests

- Use nomes, comentários e mensagens em português; explique o motivo de uma
  decisão quando ele não é óbvio.
- Preserve notas existentes, comentários do frontmatter e conteúdo desconhecido.
  Operações de gravação devem passar pelo domínio e pelas rotinas de escrita
  segura. Valide caminhos no ponto da operação, inclusive links simbólicos.
- Cubra falhas reais: disco indisponível, arquivo externo alterado, conflito,
  caminho recusado, backup/restauração e scripts não aprovados.
- Faça PRs com um problema concreto, comportamento resultante e verificações
  executadas. Para mudanças de tela, inclua prints com dados fictícios e confira
  teclado, celular e mensagens de erro.
- Inclua novas dependências em `pyproject.toml` e atualize `uv.lock` com `uv lock`.
  Não envie `.env`, tokens, URLs privadas, vaults reais ou logs com conteúdo pessoal.
- Mantenha arquivos e imagens de demonstração claramente identificados. A suíte
  de testes é parte do projeto; os dados de teste devem ser sintéticos.

Para relatar uma falha de segurança, use o procedimento de [SECURITY.md](SECURITY.md)
em vez de publicar detalhes ou segredos em uma issue.

## Dependências e ações

Para repetir a checagem local de dependências:

```bash
uv export --frozen --format requirements-txt --no-emit-project --output-file requirements-audit.txt
uv run --frozen pip-audit -r requirements-audit.txt --no-deps --disable-pip
```

Remova o arquivo temporário depois; ele não contém valores de ambiente. Alertas
devem ser avaliados e corrigidos, sem ignorar toda uma categoria para passar CI.

As ações de GitHub estão fixadas em SHA completo de seus repositórios oficiais.
Ao atualizá-las, confirme a origem e a tag correspondente; não use código de PRs
com `pull_request_target` e credenciais privilegiadas. Referências:
[segurança de workflows do GitHub](https://docs.github.com/en/actions/reference/security/secure-use),
[setup-uv](https://github.com/astral-sh/setup-uv),
[Gitleaks Action](https://github.com/gitleaks/gitleaks-action).
Gitleaks Action exige licença própria para repositórios de organizações; se o
projeto mudar de dono, configure a licença ou use a CLI oficial com checksum.

## Antes de lançar

Forme o commit/tag candidato incluindo todos os arquivos novos pretendidos.
Execute instalação e verificações em um clone desse commit exato e confirme que
sdist/wheel contêm templates, static, catálogo e modelo. Não conclua prontidão
open source com base apenas na árvore de trabalho local.
