# Comandos

Rode os comandos dentro da pasta do aplicativo (onde estão `pyproject.toml` e
`uv.lock`), depois de `uv sync --locked`. O vault fica em outra pasta.

```bash
uv run --frozen orquestra --help
uv run --frozen orquestra iniciar --help
```

## Referência

| Comando | O que faz |
|---|---|
| `uv run --frozen orquestra` | Inicia o painel; na primeira vez, abre a escolha do vault |
| `uv run --frozen orquestra iniciar --abrir` | Inicia e abre o navegador também nas próximas vezes |
| `uv run --frozen orquestra iniciar --porta 8421` | Usa outra porta local nesta execução |
| `uv run --frozen orquestra iniciar --vault "OUTRO VAULT"` | Abre outro vault e passa a lembrá-lo como padrão |
| `uv run --frozen orquestra criar "PASTA NOVA" --perfil essencial` | Cria um vault; `--sem-exemplos` deixa as áreas vazias |
| `uv run --frozen orquestra adotar "PASTA EXISTENTE"` | Prepara uma pasta existente, preservando as notas |
| `uv run --frozen orquestra doctor` | Diagnostica instalação, vault, Git e acesso remoto |
| `uv run --frozen orquestra coletar radar` | Roda as automações aprovadas do Radar; sem `radar`, roda todas |
| `uv run --frozen orquestra confiar coletor radar rss.py` | Mostra a assinatura e os arquivos de uma automação para revisão |
| `uv run --frozen orquestra confiar backup` | Mostra a configuração e os destinos do histórico para revisão |
| `uv run --frozen orquestra backup --enviar` | Cria um snapshot e envia ao remoto aprovado; sem `--enviar`, fica local |
| `uv run --frozen orquestra mcp --vault "PASTA DO VAULT"` | Inicia o conector MCP por stdio (quem inicia é o cliente MCP) |
| `uv run --frozen orquestra autostart ativar` | Inicia o painel ao entrar na sua conta; aceita também `status` e `desativar` |
| `uv run --frozen orquestra desinstalar` | Explica a remoção; com `--confirmar`, tira o início automático |

Os caminhos entre aspas são exemplos. Os apelidos `init` e `diagnostico` equivalem
a `criar` e `doctor`.

## Detalhes

- **`--vault`** escolhe o vault de `iniciar`, `doctor`, `mcp`, `coletar`, `backup` e
  `confiar`. Em `criar` e `adotar` o destino é o argumento `caminho`, e esses dois
  recusam `--vault` para não preparar uma pasta diferente da desejada.
- **`confiar`** sem `--assinatura` só mostra o que seria aprovado. Leia os arquivos
  e repita com `--assinatura HASH`; `--revogar` retira a autorização. Veja
  [automações](coletores.md) e [backup](backup.md).
- **Códigos de saída:** `0` sem erro, `1` falha de operação ou diagnóstico, `2`
  argumentos inválidos. Avisos do `doctor`, sozinhos, não geram `1`.
- **`autostart status` e `desativar`** funcionam mesmo se o vault anterior não existir mais.

## Encerrar e remover

`Ctrl+C` no terminal (ou fechar o terminal) encerra o painel. Para trocar de vault
com o painel aberto: **Ajustes → Cofres → Abrir pasta como cofre**.

Para remover: `uv run --frozen orquestra desinstalar --confirmar`, encerre o
processo e apague a pasta do aplicativo. O vault, os backups e `~/.orquestra`
(incluindo seus segredos) são preservados.
