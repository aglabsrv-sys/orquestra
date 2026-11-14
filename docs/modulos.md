# Criar e ajustar módulos

Um módulo (no painel, uma "área") é uma pasta na raiz do vault com um arquivo
`_modulo.yaml`. O painel descobre sozinho: não há nada para registrar nem código
para mexer.

## Três jeitos de ter um módulo, sem escrever YAML

- **Acrescentar um pronto.** Em Ajustes > Pastas, escolha no catálogo:
  Tarefas, Notas, Projetos, Áreas, Recursos, Arquivos, Contatos, Clientes, Finanças,
  Estudos, Conteúdo, Radar, Números, Entrada e Hábitos e metas. Com ou sem notas de
  exemplo, conforme o módulo. Agenda e Hábitos preparam suas pastas ao
  criar o primeiro registro em suas próprias telas.
- **Criar em branco.** No mesmo lugar: nome, ícone e se quer quadro. Depois ajuste
  os campos em Personalizar.
- **Adicionar novamente.** Uma área retirada aparece no mesmo catálogo de
  **Ajustes → Pastas**, inclusive áreas criadas em branco. O botão religa
  a configuração preservada, com as mesmas notas e personalizações.

## Criar e organizar itens

O botão **Novo** abre título e campos obrigatórios sem valor padrão. Em
**Adicionar campo +**, escolha propriedades adicionais ou Texto. Campos não
adicionados conservam os padrões do módulo; não são enviados como valores vazios.

Na lista, marque itens ou selecione todos da página para arquivar, excluir ou
alterar o status. A seleção é limitada à página atual (até 80 notas). Arquivar
e excluir pedem confirmação. Se uma nota mudou em outra aba ou no Obsidian,
ela fica intacta e seu erro aparece no resultado; as demais podem ser atualizadas.
Excluir mantém a exigência de autorização local. Veja a [lixeira](pastas.md).

Em **Personalizar**, Aparência, Propriedades e Visualizações têm painéis separados.
Trocar de aba preserva as alterações pendentes; Salvar alterações considera todas
as abas. O cabeçalho acompanha a rolagem normal da página.

O dock mantém **Entrada**, quando instalada, à direita. No celular, uma área
principal permanece ao lado dos atalhos fixos; as demais estão em Todas as áreas.
Na home, arraste os cartões com o mouse ou use as setas. Arrastar não abre o cartão.
- **Mostrar uma pasta sua.** Em Pastas, "Mostrar no painel": o painel lê os campos
  que as notas já têm e escreve o `_modulo.yaml` por você. Veja
  [vault-existente.md](vault-existente.md).

O ícone ao lado das abas de cada área abre **Personalizar**: nome, descrição, ícone,
cena da capa, campos (com tipo e opções), o que conta como concluído e se a área
mostra quadro e gráfico. Tudo é gravado no `_modulo.yaml`, preservando os comentários.

Agenda e Hábitos possuem telas próprias, com visões específicas de calendário e
progresso semanal. Seus registros continuam em notas dos respectivos módulos.
Veja os guias de [Agenda](agenda.md) e [Pomodoro e hábitos](foco-e-habitos.md).

Também dá para pedir a um agente ("crie um módulo de receitas") ou editar o arquivo
à mão. O resto desta página é a referência do que vai nele.

## Estrutura

```
financas/
  _modulo.yaml       o contrato do módulo
  itens/             uma nota .md por registro
  humano/            o que você disse sobre este assunto
  maquina/
    instrucoes.md    regras para os agentes
    coletores/       scripts que trazem dados (opcional)
  arquivo/           criada quando você arquiva algo
```

## O `_modulo.yaml` completo

```yaml
nome: Finanças
descricao: Receitas e despesas do mês.
icone: moeda              # veja a lista abaixo
ordem: 5                  # posição no dock e no carrossel
itens: itens              # onde ficam os registros. Use "." se as notas ficam soltas
                          # na própria pasta (é o que "Mostrar no painel" escreve)

campos:
  status:
    tipo: escolha
    opcoes: [previsto, pago, atrasado]
    padrao: previsto
    obrigatorio: true
  valor:
    tipo: numero
  vencimento:
    tipo: data
    rotulo: Vence em      # nome exibido no painel
  recorrente:
    tipo: booleano
  comprovante:
    tipo: imagem
  origem:
    tipo: escolha
    opcoes: [humano, agente, coletor]
    padrao: humano

campo_data: vencimento    # alimenta a faixa da semana e o "para hoje"

status:
  campo: status           # opcional: qual campo é o status (padrão: status)
  concluidos: [pago]      # não contam como "em aberto"
  decidir: [atrasado]     # entram na fila Decidir
  acoes:                  # botões da fila Decidir
    - rotulo: Marcar como pago
      definir: {status: pago}
      estilo: principal   # principal | discreto

visoes:
  - tipo: kanban
    nome: Quadro
    agrupar_por: status   # qualquer campo do tipo escolha
  - tipo: tabela
    nome: Lista
    colunas: [titulo, status, valor, vencimento]
  - tipo: grafico
    nome: Evolução
    campos: [valor]       # opcional: quais campos numero mostrar (padrão: todos)
    dias: 60              # opcional: quantos dias para trás (padrão: 30)

capa: {cena: cidade, paleta: brasa}   # opcional; veja docs/temas.md
```

## Tipos de campo

| Tipo | No frontmatter | No painel |
|---|---|---|
| `texto` | `canal: Fulano` | caixa de texto |
| `escolha` | `status: pago` | lista com as `opcoes` |
| `data` | `data: 2026-01-15` | calendário |
| `lista` | lista em bloco | texto separado por vírgulas |
| `numero` | `valor: 120.5` | campo numérico |
| `booleano` | `recorrente: true` | caixa de marcar |
| `link` | `link: https://...` | abre em outra aba |
| `imagem` | caminho no vault ou `https://` | miniatura no cartão |

Use `padrao: hoje` num campo de data para que notas novas nasçam com a data do dia.

## Visões

| Tipo | O que mostra |
|---|---|
| `kanban` | Colunas por um campo de escolha. Arrastar o cartão muda o campo. |
| `tabela` | Uma linha por nota, com as colunas que você escolher. Clicar no título da coluna ordena. |
| `grafico` | Um quadro para cada campo `numero`: valor mais recente, variação no período e a linha do tempo. A data vem do `campo_data` (ou do primeiro campo de data, ou do nome do arquivo). Vários registros no mesmo dia somam. |

Módulo sem campo de status não tem "em aberto" nem "atrasado": é uma coleção, e o
painel mostra só a contagem.

### O módulo Números

É o uso mais direto do gráfico: uma nota por dia (`numeros/itens/AAAA-MM-DD.md`) e
um campo por número que você acompanha. O botão **Registrar** grava os números de
hoje (ou de outro dia); se a nota do dia já existe, só os campos preenchidos mudam.
Para acompanhar outro número, acrescente um campo do tipo `numero` em Personalizar.

## Ícones

`inicio` `check` `video` `radar` `entrada` `sino` `pulso` `lampada` `calendario`
`moeda` `livro` `grafico` `estrela` `relogio` `pessoas` `pessoa` `raio` `coracao`
`nota` `pasta` `caixa` `casa` `chip` `paleta` `nuvem` `celular` `busca`

## Regras de convivência

- **Campos fora do schema são permitidos.** Você pode acrescentar o que quiser pelo
  Obsidian; o painel mostra em "Outros campos" e não reclama.
- **Valores fora das opções viram aviso**, não erro. A nota aparece com um sinal, e
  o `orquestra doctor` conta quantas existem.
- **Erro no `_modulo.yaml` não derruba o painel.** O problema aparece como aviso na
  página do módulo e em Ajustes.
- **A fila Decidir** junta dois tipos de item: os que têm um status da lista
  `decidir` e os que têm um campo `pergunta` preenchido por um agente.
- **O número no dock** é "para hoje" quando o módulo tem `campo_data`; senão, o que
  espera decisão; senão, o que está em aberto.
- **O dock não cresce sem parar.** Com até nove itens, mostra tudo. Acima disso, mostra
  cinco áreas, a área em que você está e o botão "Todas as áreas" (tecla `G`), que abre
  a lista completa com Diário, Pastas e Ajustes. Agenda e Decidir continuam na barra.
  Para escolher quais ficam sempre à mão,
  liste no `orquestra.yaml`: `dock: [tarefas, projetos, notas]`.
- **Tirar do painel não apaga nada.** O `_modulo.yaml` vira `_modulo.desligado.yaml`
  e a pasta continua no vault. Religar devolve a área como estava.
- **Cada módulo tem um `maquina/aprendizados.md`**, onde os agentes anotam o que
  aprenderam trabalhando ali. O painel cria o arquivo junto com o módulo.

## Compartilhar um módulo

Um módulo é uma pasta. Para compartilhar, copie a pasta sem o conteúdo de `itens/`
(e sem nada pessoal em `humano/`). Quem receber cola na raiz do próprio vault.
