# Coletores

Um coletor é um script que busca informação fora (vídeos novos, posts, assuntos em
alta) e entrega ao painel, que transforma cada item em uma nota com `status: novo`.

**Coletor não usa IA.** Buscar e guardar é trabalho mecânico: um script faz a
coleta conforme sua configuração. Serviços externos podem ter custos e limites. A IA entra depois, na triagem, quando já
existe o que avaliar.

## Antes de executar: revise o código

Coletores executam Python com as permissões da sua conta. Eles podem ler arquivos,
acessar rede e receber as chaves declaradas na configuração. O processo recebe um
ambiente básico e somente os segredos listados em `requer`, mas isso não impede
que um script malicioso leia outros arquivos acessíveis à conta. Não há sandbox do sistema operacional.
Um módulo importado pode conter código malicioso, mesmo que pareça uma pasta de notas.

Na aba **Máquina**, abra a revisão do coletor, leia os arquivos indicados e confira
a configuração, as chaves declaradas e a assinatura. A aprovação só pode ser feita
por acesso direto a localhost no computador que roda o painel. Pelo Tailscale,
um coletor já aprovado pode executar, mas não receber aprovação nova. Para retirar
permissão, use **Revogar aprovação**.

A assinatura cobre os arquivos locais apresentados e a configuração. Uma mudança
exige nova aprovação, mesmo se o coletor estava agendado. Dependências remotas
baixadas pelo uv não são uma sandbox nem garantia de integridade futura; prefira
versões fixas, revise sua origem e não execute scripts desconhecidos. Não coloque
segredos no código, logs ou argumentos de comando.

## Os que vêm prontos (módulo Radar)

| Script | O que traz | Precisa de chave? |
|---|---|---|
| `youtube_rss.py` | vídeos novos dos canais que você listar | não |
| `rss.py` | posts de qualquer feed RSS ou Atom | não |
| `google_trends.py` | assuntos em alta no Google no seu país | não |
| `youtube_api.py` | busca de vídeos por termo | sim (gratuita) |

Todos vêm desligados e precisam de aprovação de versão. Para configurar, edite `radar/_modulo.yaml`:

```yaml
coletores:
  - script: youtube_rss.py
    nome: Canais do YouTube
    ativo: true              # agenda depois da aprovação local desta versão
    a_cada: 6h               # 30m, 6h, 1d...   ou   diario_as: "07:00"
    config:
      canais:
        - "@NomeDoCanal"     # também aceita o link do canal ou o ID (UC...)
      maximo_por_canal: 4
```

Na aba **Máquina** do módulo você liga e desliga cada coletor, vê quando rodou pela
última vez e pode rodar na hora. Pelo terminal, na pasta do aplicativo:

```bash
uv run --frozen orquestra coletar
```

```bash
uv run --frozen orquestra coletar radar
```

O agendamento vive dentro do painel: os coletores automáticos só rodam com o painel
aberto. Se o computador ficou desligado, o que estava atrasado roda quando o painel
volta.

Sem `a_cada` ou `diario_as`, não há execução automática, mesmo com `ativo: true`.
O comando `coletar` é manual e também considera coletores com o agendamento
desligado; todos continuam exigindo aprovação local da versão. Para selecionar
outro vault, acrescente `--vault "CAMINHO COMPLETO"`.

## Automações que vêm com os outros módulos

Todas sem IA e desligadas até você revisar, aprovar e ligar (aba **Máquina** do módulo). Serviços externos podem ter limites ou custos próprios.

| Módulo | Script | O que faz | Precisa de chave? |
|---|---|---|---|
| Tarefas | `recorrentes.py` | Cria a tarefa do dia para cada rotina: "toda sexta", "dia útil", "dia 5" | não (nem de internet) |
| Tarefas | `agenda_ics.py` | Traz os compromissos dos próximos dias da sua agenda (Google, Outlook, iCloud) | não: usa o endereço iCal da agenda |
| Números | `cotacoes.py` | Grava a cotação do dia (dólar, euro, bitcoin...) | não |
| Números | `github_repo.py` | Grava estrelas e forks de um repositório público | não |
| Números | `youtube_canal.py` | Grava inscritos e visualizações de um canal | sim: `YOUTUBE_API_KEY` |

### Tarefas que se repetem

Em `tarefas/_modulo.yaml`, na `config` do coletor:

```yaml
tarefas:
  - titulo: Revisar a semana
    quando: sexta              # todo dia | dia util | fim de semana | dia 5
    prioridade: alta           # qualquer campo do módulo
  - titulo: Regar as plantas
    quando: segunda, quinta
```

Rodando uma vez por dia, o coletor cria "Revisar a semana - 14 nov" toda sexta. Se
o painel ficou fechado num dia, a tarefa daquele dia não é criada depois.

### Sua agenda como tarefas

Toda agenda tem um endereço iCal (termina em `.ics`) que pode ser lido sem login:

- **Google Agenda**: Configurações > clique na agenda > "Endereço secreto no formato iCal".
- **Outlook**: Configurações > Calendário > Calendários compartilhados > Publicar um calendário > ICS.
- **iCloud**: compartilhe a agenda como "Agenda pública" e copie o link.

```yaml
agendas:
  - nome: Pessoal
    url: https://calendar.google.com/calendar/ical/.../basic.ics
dias_a_frente: 14
```

Esse endereço dá acesso de leitura à agenda inteira: **trate como senha**. Ele fica
no `_modulo.yaml`, dentro do vault; mantenha o backup do vault em repositório privado.
Compromissos que se repetem entram só na primeira data; para rotinas, use o
`recorrentes.py`. Se você remarcar um compromisso, a tarefa antiga continua lá.

### Mais fontes para o Radar, sem script novo

O coletor `rss.py` lê qualquer feed. Muita coisa tem um e pouca gente sabe:

| Fonte | Endereço do feed |
|---|---|
| Reddit | `https://www.reddit.com/r/NOME/top/.rss?t=day` |
| Bluesky | `https://bsky.app/profile/USUARIO/rss` |
| Lançamentos no GitHub | `https://github.com/DONO/REPO/releases.atom` |
| Substack | `https://NOME.substack.com/feed` |
| Podcasts | o endereço do feed do programa |

## Instagram e TikTok

Não há coletor para eles, de propósito. Essas plataformas não oferecem feed público
e proíbem a raspagem nos termos de uso; um coletor assim quebraria a toda hora e
poderia custar a sua conta.

## Chave do YouTube (opcional)

`youtube_api.py` e `youtube_canal.py` usam a chave. Confira quotas e termos da API no seu projeto Google:

1. Entre em <https://console.cloud.google.com> e crie um projeto.
2. Em "APIs e serviços", ative a **YouTube Data API v3**.
3. Em "Credenciais", crie uma **chave de API**.
4. Abra o arquivo `.env` que fica na pasta `.orquestra` da sua pasta pessoal
   (`C:\Users\voce\.orquestra\.env` ou `~/.orquestra/.env`) e acrescente:

   ```
   YOUTUBE_API_KEY=sua-chave-aqui
   ```

A chave fica fora do vault de propósito: copie o [.env.example](../.env.example)
para `~/.orquestra/.env` e preencha só nesse destino. O `orquestra doctor` avisa se um coletor espera uma chave que não existe.

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
- Chaves de API chegam como variáveis de ambiente, lidas de `~/.orquestra/.env`
  (ou `ORQUESTRA_HOME/.env`) e das variáveis do processo. Declare em
  `requer: [NOME_DA_CHAVE]` para autorizar o repasse e permitir a conferência pelo `doctor`.
- Mensagens de diagnóstico vão com `avisar(...)`; se o script terminar com erro, a
  última linha aparece no painel.
- Um coletor tem até 3 minutos por execução.

Coletores funcionam em qualquer módulo, não só no Radar: coloque o script em
`<modulo>/maquina/coletores/` e a lista `coletores:` no `_modulo.yaml` daquele módulo.

## Coletores de números (um registro por dia)

Um coletor comum cria uma nota por item e ignora o que já coletou. Para números
que mudam todo dia (inscritos, seguidores, saldo), o item representa um **estado**:
o de hoje. Nesse caso, inclua `"atualizar": true`:

```json
{"id": "numeros:2026-01-15", "titulo": "2026-01-15", "atualizar": true, "campos": {"dia": "2026-01-15", "inscritos": 1234}}
```

Se já existe a nota desse dia (pelo `id` ou pelo nome do arquivo), o painel só
completa campos vazios ou ainda iguais ao último valor coletado, preservando edições manuais; não cria outra nota para contornar um conflito. O módulo Números traz um
exemplo pronto, `youtube_canal.py`, que busca inscritos e visualizações de um canal
pela API oficial do YouTube (precisa da `YOUTUBE_API_KEY`).

Para redes que não têm API aberta, o caminho mais simples é pedir a um agente com
o conector da rede: "pegue meus números de hoje e registre". Veja [mcp.md](mcp.md).

## Segurança

Um coletor é código que roda no seu computador com as suas permissões. Antes de
usar um coletor que não foi você quem escreveu, leia o arquivo, do mesmo jeito que
leria qualquer script baixado da internet.

## Atualizar registros sem substituir edições suas

Um item emitido com `atualizar: true` pode completar campos de uma nota existente,
como o registro numérico do dia. Na primeira coleta de uma nota humana existente,
só campos vazios recebem valor. O painel guarda o último valor coletado por campo
no metadado `_orquestra_coleta`; uma coleta posterior só atualiza esse campo se o
valor atual ainda for igual ao último coletado. Se você editou o campo manualmente,
a sua alteração prevalece. Corpo e origem da nota existente são preservados.

Um conflito protegido não cria uma segunda nota para contornar a proteção: ele
entra na contagem de itens já conhecidos. Confira os resultados da coleta e a nota
quando precisar reconciliar um valor externo com uma escolha manual.

## Limites operacionais

O servidor limita JSON de entrada a 2 MB. Cada revisão de coletor aceita até
1.000 arquivos locais e 32 MB no total. A execução tem prazo de 180 segundos,
até 4 MB de saída somada (stdout/stderr) e até 2.000 itens por rodada. Divida
fontes muito grandes em lotes menores. Esses limites reduzem travamentos e consumo
acidental; não restringem as permissões de um script aprovado no sistema.

## Revisar pelo terminal

Para uma instalação sem navegador, use
`uv run --frozen orquestra confiar coletor radar rss.py`. O comando mostra a
assinatura e os nomes dos arquivos/chaves declarados, sem imprimir os valores de
configuração. Leia também o script, os auxiliares e a configuração do módulo.
Depois repita o mesmo comando com `--assinatura HASH`, usando a assinatura que
acabou de conferir. Para revogar: acrescente `--revogar`. A aprovação fica fora do
vault e vale apenas nesse computador e para aquela versão.
