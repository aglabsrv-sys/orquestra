# Coletores

Um coletor é um script que busca informação fora (vídeos novos, posts, assuntos em
alta) e entrega ao painel, que transforma cada item em uma nota com `status: novo`.

**Coletor não usa IA.** Buscar e guardar é trabalho mecânico: um script faz mais
rápido, de graça e sempre do mesmo jeito. A IA entra depois, na triagem, quando já
existe o que avaliar.

## Os que vêm prontos (módulo Radar)

| Script | O que traz | Precisa de chave? |
|---|---|---|
| `youtube_rss.py` | vídeos novos dos canais que você listar | não |
| `rss.py` | posts de qualquer feed RSS ou Atom | não |
| `google_trends.py` | assuntos em alta no Google no seu país | não |
| `youtube_api.py` | busca de vídeos por termo | sim (gratuita) |

Todos vêm desligados. Para configurar, edite `radar/_modulo.yaml`:

```yaml
coletores:
  - script: youtube_rss.py
    nome: Canais do YouTube
    ativo: true              # roda sozinho
    a_cada: 6h               # 30m, 6h, 1d...   ou   diario_as: "07:00"
    config:
      canais:
        - "@NomeDoCanal"     # também aceita o link do canal ou o ID (UC...)
      maximo_por_canal: 4
```

Na aba **Máquina** do módulo você liga e desliga cada coletor, vê quando rodou pela
última vez e pode rodar na hora. Pelo terminal:

```bash
uv run orquestra coletar
```

```bash
uv run orquestra coletar radar
```

O agendamento vive dentro do painel: os coletores automáticos só rodam com o painel
aberto. Se o computador ficou desligado, o que estava atrasado roda quando o painel
volta.

## Instagram e TikTok

Não há coletor para eles, de propósito. Essas plataformas não oferecem feed público
e proíbem a raspagem nos termos de uso; um coletor assim quebraria a toda hora e
poderia custar a sua conta.

## Chave do YouTube (opcional)

Só o `youtube_api.py` precisa. A chave é gratuita:

1. Entre em <https://console.cloud.google.com> e crie um projeto.
2. Em "APIs e serviços", ative a **YouTube Data API v3**.
3. Em "Credenciais", crie uma **chave de API**.
4. Abra o arquivo `.env` que fica na pasta `.orquestra` da sua pasta pessoal
   (`C:\Users\voce\.orquestra\.env` ou `~/.orquestra/.env`) e acrescente:

   ```
   YOUTUBE_API_KEY=sua-chave-aqui
   ```

A chave fica fora do vault de propósito: o vault vai para backup, e segredo não
deve ir junto. O `orquestra doctor` avisa se um coletor espera uma chave que não existe.

## Escrever o seu coletor

O contrato é uma frase: **imprima uma linha de JSON por item**. O painel cuida de
descartar repetidos, criar a nota, aplicar o schema e registrar no diário.

Crie `radar/maquina/coletores/meu_coletor.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: o que ele traz, em uma linha."""

from _comum import CONFIG, baixar, emitir

for endereco in CONFIG.get("enderecos", []):
    pagina = baixar(endereco).decode("utf-8")
    emitir(
        id=f"meu:{endereco}",        # estável: é por ele que o painel evita repetidos
        titulo="Título do item",
        corpo="Texto que vira o corpo da nota.",
        fonte="meu_coletor",         # daqui para baixo, campos do frontmatter
        link=endereco,
    )
```

E registre no `_modulo.yaml`:

```yaml
coletores:
  - script: meu_coletor.py
    nome: Meu coletor
    ativo: false
    a_cada: 1d
    config:
      enderecos:
        - https://exemplo.com
```

Detalhes úteis:

- `_comum.py` (na mesma pasta) traz `CONFIG`, `baixar`, `emitir` e `avisar`. Não é
  obrigatório: qualquer script que imprima o JSON serve, em qualquer estilo.
- Campos que existem no schema do módulo são convertidos e validados. Um valor
  inválido é ignorado, sem perder o item. Campos extras entram como estão.
- O painel acrescenta `origem: coletor`, `coletor`, `id_externo` e `coletado_em`.
- Precisa de uma biblioteca? Liste em `dependencies` no topo do arquivo (por exemplo
  `dependencies = ["feedparser"]`). O `uv` instala sozinho na primeira execução.
- Chaves de API chegam como variáveis de ambiente, lidas do `.env`. Declare em
  `requer: [NOME_DA_CHAVE]` para o `doctor` conferir.
- Mensagens de diagnóstico vão com `avisar(...)`; se o script terminar com erro, a
  última linha aparece no painel.
- Um coletor tem até 3 minutos por execução.

Coletores funcionam em qualquer módulo, não só no Radar: coloque o script em
`<modulo>/maquina/coletores/` e a lista `coletores:` no `_modulo.yaml` daquele módulo.

## Segurança

Um coletor é código que roda no seu computador com as suas permissões. Antes de
usar um coletor que não foi você quem escreveu, leia o arquivo, do mesmo jeito que
leria qualquer script baixado da internet.
