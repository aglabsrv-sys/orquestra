# Usar um vault que já existe

Se você já tem um vault do Obsidian (ou qualquer pasta de arquivos `.md`), o
Orquestra trabalha em cima dele do jeito que está. Esta página explica o que
acontece com a sua pasta, passo a passo.

## Pela tela

Rode `uv run orquestra`. Se ainda não há vault escolhido, a tela de boas-vindas abre
sozinha. Se já há um, vá em **Ajustes > Vault > Trocar de vault**.

1. Escolha **Já tenho um vault do Obsidian**.
2. O painel lista os cofres que o Obsidian desta máquina conhece. Clique em um, ou
   cole o caminho de outra pasta, ou use **Procurar…**.
3. **Olhar a pasta** conta as notas e as pastas e mostra o que encontrou. Nada é
   gravado nessa etapa.
4. Marque as pastas que você quer ver como área do painel e, se quiser, alguma área
   pronta (Tarefas, Entrada...).
5. A lista **O que vou criar** mostra exatamente o que será acrescentado.
6. **Abrir o painel**.

Pela linha de comando, o equivalente é:

```bash
uv run orquestra adotar "C:\caminho\do\vault" --pastas "Projetos,Leituras" --modulos entrada
```

## O que é criado na sua pasta

| Arquivo ou pasta | Para quê |
|---|---|
| `orquestra.yaml` | Nome do painel, tema, backup. |
| `_orquestra/` | Temas e o estado do painel. |
| `AGENTS.md` e `CLAUDE.md` | As regras que os agentes de IA leem. |
| `Orquestra - comece aqui.md` | Uma nota explicando o que é o quê. Pode apagar. |
| `<sua pasta>/_modulo.yaml` | Um por pasta que você mandou mostrar no painel. |
| `<área pronta>/` | Uma pasta nova para cada área pronta que você marcou. |
| `diario/` | Criada conforme você usa: o registro do que muda. |

A preparação foi desenhada para acrescentar os arquivos do painel sem reorganizar
suas notas. Faça uma cópia do vault antes da primeira adoção; revise os arquivos
que serão criados. Em particular:

- Se você já tem um `AGENTS.md`, ele fica como está. As regras do painel vão para
  `AGENTS.orquestra.md`, e o painel avisa. Peça ao seu agente para ler os dois, ou
  junte os arquivos quando quiser.
- Se já existe uma pasta com o nome de uma área pronta (uma `Tarefas/` sua, por
  exemplo), a área pronta não é criada. Use "Mostrar no painel" na sua pasta.
- A pasta `.obsidian/` é ignorada: o painel não lê nem grava nela.

## Como uma pasta vira área

O painel lê até 80 notas da pasta e olha o **frontmatter** (os campos entre `---`
no topo da nota, que o Obsidian chama de propriedades):

| O que ele encontra | O que vira |
|---|---|
| Um campo `status` (ou `estado`, `etapa`, `stage`...) com poucos valores | Colunas de um quadro, na ordem em que aparecem |
| Valores como `feito`, `concluido`, `done`, `arquivado` | Contam como concluído |
| Um campo `data`, `prazo`, `due`, `vencimento`... com datas | Alimenta a faixa da semana e o "para hoje" |
| Texto que se repete em várias notas | Campo de escolha |
| Listas (`tags`) | Campo de lista |
| Números, verdadeiro/falso, links | Campos do tipo certo |
| Notas sem frontmatter | Uma lista simples; você cria campos depois |

O resultado é gravado em `<pasta>/_modulo.yaml`, com `itens: .` (os registros são
as notas da própria pasta, inclusive as de subpastas). Abra o arquivo ou use
**Personalizar** na área para ajustar: é só um ponto de partida.

Se as notas não têm status e você quer um quadro, marque **com quadro**: o painel
acrescenta um campo `status` com "a fazer, fazendo, feito". As notas que já existem
aparecem numa coluna "Sem status" até você arrastar.

Para desfazer: **Ajustes > Áreas do painel > Tirar do painel**. O `_modulo.yaml` é
só renomeado; a pasta continua como estava, e você pode religar depois em Pastas.

Limite atual: só pastas da **raiz** do vault viram área. Uma subpasta aparece
dentro da área da pasta-mãe e na tela Pastas.

## Estilos que o painel reconhece

Só para orientar a sugestão; nenhum deles é obrigatório.

| Estilo | Como ele reconhece |
|---|---|
| **PARA** | Pastas de projetos, áreas, recursos e arquivo (em português ou inglês, com ou sem número na frente) |
| **ACE** | Pastas como Atlas, Calendar, Cards, Efforts, Sources, Spaces |
| **Johnny Decimal** | Pastas numeradas por faixa (`10-19 ...`, `20-29 ...`) |
| **Zettelkasten** | Muitas notas com número de data e hora no nome, ou pastas permanent/fleeting/literature |
| **Diário** | A maior parte das notas tem uma data como nome |
| **Organização própria** | Qualquer outra coisa: você escolhe o que mostrar |

## Histórico (git) e sincronização

Num vault novo, o painel liga o histórico em git: é o "desfazer" para qualquer
alteração. Num vault que já existia ele **não liga sozinho**, porque você pode já
sincronizar a pasta por OneDrive, iCloud, Obsidian Sync ou um git seu.

- Para ligar: marque a opção na tela de boas-vindas, ou use **Ajustes > Histórico e
  backup > Ligar o histórico**.
- Se a pasta já é um repositório git e você ligar o commit automático, o painel
  passa a fazer commits nele a cada 30 minutos (ajustável no `orquestra.yaml`).

## Agentes no seu vault

O `AGENTS.md` do painel diz aos agentes que as pastas sem `_modulo.yaml` são suas:
podem ler, mas não reescrever, renomear nem reorganizar, a menos que você peça.
Notas sem o campo `origem` são tratadas como escritas por você.

Isso depende de o agente seguir o contrato. Se você ligar o histórico, tem como
desfazer qualquer coisa. Veja [agentes.md](agentes.md).

## Edição e sincronização

O painel verifica versões e mantém recuperação local para suas próprias gravações.
Obsidian e sincronizadores não participam dos locks do Orquestra: evite editar a
mesma nota ao mesmo tempo em dois lugares. Em conflito, preserve o rascunho como
cópia antes de recarregar. Veja [backup e recuperação](backup.md).

Pastas e arquivos ligados por symlink, junction ou outro redirecionamento são
recusados, inclusive quando apontam para outro lugar dentro do vault. Mova ou copie
os dados desejados para arquivos regulares e confira a cópia antes de usá-la.
