# Automações

Uma automação busca informação ou executa uma rotina e entrega itens ao painel,
que os guarda em notas. O destino pode ser uma pasta existente, inclusive uma
subpasta, sem instalar um módulo pronto. Os estados seguem o contrato da pasta;
uma pasta comum não ganha um quadro ou um status por receber uma automação.

## Catálogo independente

Abra **Ajustes → Automações**. O catálogo reúne oito opções para novas
configurações, mesmo sem Radar, Tarefas ou Números instalados. A importação iCal
legada aparece somente quando já estiver configurada; use **Agenda → Conectar
agenda** para consultar compromissos sem criar tarefas.

1. Use **Adicionar** na automação e escolha o módulo de destino. **Outra pasta do
   cofre** permite navegar até uma pasta existente, inclusive uma subpasta.
2. Personalize fontes, nome e destino no painel lateral. Escolha execução manual,
   por intervalo ou horário diário. **Execução agendada ativa** permite pausar ou
   ativar o horário; não há uma segunda chave no cartão.
3. Use **Continuar** para conferir destino e política de gravação. Em **Mais opções**,
   o mapeamento de propriedades permite usar nomes existentes na pasta.
4. Confira e salve. A autorização local cobre código, configuração, segredos
   declarados, destino, mapeamento e horário.
5. A engrenagem do catálogo pede qual instância configurar, mostrando nome, pasta e
   estado. Em **Execução e opções**, **Testar fonte** mostra uma amostra sem gravar
   notas; **Executar** usa a última configuração salva. **Remover** preserva as notas.

Na aba **Máquina** de cada módulo, **Adicionar** escolhe uma automação para aquela
pasta. **Configurar** abre o mesmo painel lateral e salvar mantém você no módulo.
As automações já instaladas ficam em **Já nesta pasta**, fora das opções disponíveis.
Use **Adicionar outra configuração** nessa seção quando precisar de fontes ou
horários diferentes; cada configuração continua identificada pelo nome.
**Remover**, no cartão ou no formulário, encerra o agendamento e retira apenas a
configuração escolhida, inclusive nas automações originais. As notas e o código
continuam no vault. As opções atuais do catálogo voltam à lista disponível
depois que sua última configuração for removida da pasta.
Esc fecha o painel; se o seletor de pastas estiver aberto, primeiro fecha o seletor.
Em **Pastas**, o botão de raio abre o catálogo com a pasta atual selecionada.

Cada instância tem nome, destino, fontes e horário próprios. É possível usar a
mesma automação em várias pastas. Instâncias no mesmo destino reconhecem os itens
já presentes pelo identificador externo. No destino de um módulo, o histórico
inclui itens arquivados: um vídeo arquivado no Radar não reaparece na coleta.
Canais e buscas do YouTube compartilham o mesmo identificador por vídeo. As notas
repetidas que já existiam não são excluídas automaticamente.

As métricas podem completar uma nota diária; configurações que disputem o mesmo
campo são recusadas. Valores alterados manualmente são preservados.
As configurações independentes ficam em `_orquestra/automacoes.json`; as automações
originais da pasta mantêm sua identidade e seu destino no `_modulo.yaml`. Aceites e
segredos ficam neste computador. Fontes, canais e assuntos podem ser alterados pelo
formulário. **Usar em outra pasta** cria outra instância explicitamente. Código
personalizado continua sujeito à revisão na pasta, sem ser substituído pelo catálogo.

## Antes de executar: revise o código

Nos módulos legados, os originais distribuídos com a instalação podem executar sem aceite extra enquanto
código, auxiliares, configuração e chaves declaradas coincidirem exatamente com o
catálogo instalado. Uma revogação explícita continua bloqueando o original. As
orientações de aprovação abaixo se aplicam a versões personalizadas ou importadas
que não correspondam integralmente ao catálogo.

Coletores executam Python com as permissões da sua conta. Eles podem ler arquivos,
acessar rede e receber as chaves declaradas na configuração. O processo recebe um
ambiente básico e somente os segredos listados em `requer`, mas isso não impede
que um script malicioso leia outros arquivos acessíveis à conta. Não há sandbox do sistema operacional.
Um módulo importado pode conter código malicioso, mesmo que pareça uma pasta de notas.

Na aba **Máquina**, abra a revisão do coletor, leia os arquivos indicados e confira
a configuração, as chaves declaradas e a assinatura. A aprovação só pode ser feita
por acesso direto a localhost no computador que roda o painel. Pelo Tailscale,
um coletor já aprovado pode executar, mas não receber aprovação nova. Para retirar
permissão de uma automação da pasta, use **Configurar → Execução e opções →
Revogar permissão**. Em scripts personalizados, o controle continua na revisão
avançada da aba Máquina.

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

Todos vêm com o agendamento desligado. Personalizar a configuração exige aprovação da nova versão.

Em **Canais do YouTube → Mais opções**, **Títulos contendo (opcional)** filtra
os vídeos pelos termos ou frases informados, um por linha. Basta um deles
aparecer no título; acentos, maiúsculas e espaços repetidos são ignorados.
Vazio mantém a coleta habitual. O limite por canal é aplicado depois do filtro,
dentro dos vídeos recentes disponíveis no feed; não é uma busca no histórico.
Na configuração YAML, a opção é `titulos_contem`, uma lista de textos.

Para configurar pelo arquivo, edite `radar/_modulo.yaml`:

```yaml
coletores:
  - script: youtube_rss.py
    nome: Canais do YouTube
    ativo: true              # agenda depois da aprovação local desta versão
    a_cada: 6h               # 1h, 6h, 1d...   ou   diario_as: "07:00"
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
desligado; versões personalizadas continuam exigindo aprovação local. Para selecionar
outro vault, acrescente `--vault "CAMINHO COMPLETO"`.

## Automações que vêm com os outros módulos

Todas sem IA e com agendamento desligado. Abra **Configurar** na aba **Máquina**
para escolher o horário e ativar o agendamento; se personalizar, revise e aprove
a nova assinatura. Serviços externos podem ter limites ou custos próprios.

| Módulo | Script | O que faz | Precisa de chave? |
|---|---|---|---|
| Tarefas | `recorrentes.py` | Cria a tarefa do dia para cada rotina: "toda sexta", "dia útil", "dia 5" | não (nem de internet) |
| Tarefas (legado) | `agenda_ics.py` | Mantém a importação antiga em notas; prefira Conectar agenda para leitura | não: usa o endereço iCal da agenda |
| Números | `cotacoes.py` | Grava a cotação do dia (dólar, euro, bitcoin...) | não |
| Números | `github_repo.py` | Grava estrelas e forks de um repositório público | não |
| Números | `youtube_canal.py` | Grava inscritos e visualizações de um canal | sim: `YOUTUBE_API_KEY` |

### Tarefas que se repetem

No painel, escolha **Tarefas que se repetem** no catálogo, informe as regras e
guarde em **Tarefas/itens** para usar os estados e a agenda da área de tarefas.
O horário diário controla quando verificar as regras; mantenha a verificação
diária mesmo para uma tarefa semanal ou mensal. Após revisar e autorizar a
configuração, ative a execução automática.

Cada regra cria uma nova ocorrência datada, sem modificar a tarefa anterior.
Executar novamente no mesmo dia não recria a ocorrência que ainda existe.
A identidade usa o título normalizado e a data: regras com o mesmo título no
mesmo destino e dia representam a mesma ocorrência. Renomear a regra depois
de executá-la pode gerar outra tarefa naquele dia.

A data da ocorrência é sempre a de hoje, mesmo se a regra contiver uma data
antiga. Dias mensais de 29 a 31 usam o último dia nos meses mais curtos;
valores fora de 1 a 31 são inválidos. **Dia útil** significa segunda a sexta,
sem consultar feriados.

O serviço precisa estar rodando. Ao voltar após dias desligado, a verificação
diária espera o horário de hoje e gera apenas a ocorrência de hoje. Datas
perdidas não são recriadas. Concluir uma tarefa não dispara a próxima:
a recorrência segue o calendário, independentemente da conclusão.

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

No formulário, o modelo começa com uma única tarefa. Em **Repetir tarefa**, escolha
os dias da semana, todos os dias ou um dia do mês. **Verificar regras** controla
quando o Orquestra consulta essas regras; mantenha a verificação diária mesmo
para uma tarefa semanal. A regra é validada antes de salvar. Cada tarefa é criada
uma vez por data; alterar seu título muda a identificação das próximas ocorrências.

### Assinar uma agenda sem criar tarefas

Use **Agenda → Conectar agenda**. O assistente separa os passos de Google Agenda
e iCloud, testa o link e guarda o endereço fora do vault, nas variáveis locais
específicas deste cofre. A assinatura é de leitura: não cria notas ou tarefas.
Consulte [Agenda](agenda.md) para atualização, desconexão e limites.

### Importação legada de agenda como tarefas

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

Esse endereço dá acesso de leitura à agenda inteira: **trate como senha**. Prefira
`variavel: AGENDA_ICAL_URL`, com o valor cadastrado em Segredos, em vez de `url:` no
`_modulo.yaml`. Essa importação preserva as cópias antigas, não sincroniza mudanças.
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

Os coletores do catálogo aceitam até 50 fontes por configuração (25 assuntos de
busca no YouTube), 200 regras de tarefas e 2.000 resultados estimados por rodada.
Listas com fontes repetidas são recusadas. Cada feed ou canal produz até 100
resultados; a busca pela API do YouTube aceita até 50 por assunto. O período da
importação iCal legada fica limitado a 90 dias à frente.

O intervalo mínimo das fontes de rede é uma hora, ou seis horas para buscas
pela API do YouTube. Horários diários continuam disponíveis. Configurações antigas
que excedam esses limites ficam disponíveis para edição, com a execução bloqueada
até o ajuste; suas fontes e notas não são apagadas.

Testar uma fonte também faz consultas reais. Tanto testes quanto execuções
aguardam 30 segundos após a tentativa anterior da mesma configuração. Até duas
coletas podem rodar simultaneamente, inclusive somando outros processos e vaults
abertos pela mesma instalação no computador. Reservas de processos interrompidos
são liberadas após 210 segundos; o prazo de execução permanece em 180 segundos.

As cotas abaixo são compartilhadas por todas as pastas e chaves locais, com janela
móvel e intervalo de pelo menos um segundo entre consultas ao mesmo serviço:

| Serviço | Cota local |
| --- | --- |
| GitHub público | 55 consultas por hora |
| Canais YouTube por RSS e páginas públicas | 120 consultas por hora |
| Busca pela API do YouTube | 100 consultas em 24 horas |
| Outros recursos da API do YouTube | 1.000 consultas em 24 horas |
| Outros sites | 120 consultas por host e hora |
| Total de todos os serviços | 1.000 consultas por hora |

Cada processo coletor também limita suas consultas a 120, incluindo
redirecionamentos. Downloads, inclusive métricas do YouTube, são limitados a 8 MB.
Uma resposta 429 interrompe a rodada inteira, sem continuar consultando as demais
fontes. O aplicativo respeita `Retry-After` em segundos ou data e, no GitHub, o
horário de liberação informado por `X-RateLimit-Reset`. Sem prazo informado, a
pausa cresce de um minuto até uma hora; cota diária esgotada do YouTube pausa as
consultas afetadas por 24 horas. Não há repetição imediata de uma requisição bloqueada.

Contadores e pausas ficam no registro local de limites, dentro de
`~/.orquestra/limites-coleta` (ou `ORQUESTRA_HOME`), fora do vault. Reiniciar o painel
ou adicionar a mesma automação em outra pasta não zera a cota. O registro não guarda
URLs, termos de busca nem chaves. As cotas do provedor podem incluir outros
aplicativos e ser menores; o tratamento de bloqueios continua necessário.

Os controles de rede acompanham o ajudante distribuído dos coletores nativos.
Código personalizado aprovado executa com as permissões da conta e pode usar
outras bibliotecas de rede; esses controles não são uma sandbox do sistema.

## Revisar pelo terminal

Para uma instalação sem navegador, use
`uv run --frozen orquestra confiar coletor radar rss.py`. O comando mostra a
assinatura e os nomes dos arquivos/chaves declarados, sem imprimir os valores de
configuração. Leia também o script, os auxiliares e a configuração do módulo.
Depois repita o mesmo comando com `--assinatura HASH`, usando a assinatura que
acabou de conferir. Para revogar: acrescente `--revogar`. A aprovação fica fora do
vault e vale apenas nesse computador e para aquela versão.
