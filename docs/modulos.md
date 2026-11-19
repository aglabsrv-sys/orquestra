# Criar e ajustar módulos

Um módulo (no painel, uma "área") é uma pasta na raiz do vault com um arquivo
`_modulo.yaml`. O painel descobre sozinho: não há nada para registrar nem código
para mexer.

## Referências da área

Notas em `nome-da-area/referencias/` ficam na aba **Referências**, separadas dos
cartões e contagens de itens. O status original é preservado, mesmo que não faça
parte das opções do módulo. Um link para um item da área, ou sua pasta de nome
inequívoco, também permite consultar a referência dentro desse item como nota
de apoio. A associação é de leitura: não move nem reescreve arquivos.
Em Estudos não há aba separada: essas notas aparecem na própria área e, quando
vinculadas por link ou pasta de nome inequívoco, dentro do estudo correspondente.

## Três jeitos de ter um módulo, sem escrever YAML

- **Acrescentar um pronto.** Em Ajustes > Pastas, escolha no catálogo:
  Tarefas, Notas, Projetos, Áreas, Recursos, Arquivos, Contatos, Clientes, Finanças,
  Estudos, Conteúdo, Radar, Números, Entrada e Hábitos e metas. Com ou sem notas de
  exemplo, conforme o módulo. Agenda e Hábitos preparam suas pastas ao
  criar o primeiro registro em suas próprias telas.
- **Criar em branco.** No mesmo lugar: nome, ícone e se quer quadro.
- **Adicionar novamente.** Uma área retirada aparece no mesmo catálogo de
  **Ajustes → Pastas**, inclusive áreas criadas em branco. O botão religa
  a configuração preservada, com as mesmas notas e personalizações.

## Criar e organizar itens

Em Projetos, a pasta e sua nota principal mostram as **Tarefas do projeto**.
Um wikilink ou link Markdown entre as notas, em qualquer direção, já cria o
vínculo para o painel. Wikilinks na propriedade `projeto` também funcionam.
A tarefa mantém seu status em Tarefas e mostra os projetos ligados. Uma pergunta
pendente pode ser aberta diretamente em **Entrada → Para decidir**.

Em Projetos e Estudos, **Novo** cria uma pasta: o título dá nome à pasta e a
descrição opcional vira sua primeira nota, com a primeira linha como título.
Dentro dela, **Nova nota** cria uma nota vinculada. Pastas, Cartões e Lista
mantêm a pasta aberta ao trocar de visualização. A escolha é lembrada por área
e cofre neste navegador, separando a visão externa da interna: por exemplo,
Pastas por fora e Lista por dentro. **Voltar** restaura a visão externa.
A troca interna mantém o título e os controles; só a apresentação das notas muda.
Os ajustes internos de Projetos personalizam só aquela pasta (capa e entrada
rápida), enquanto os ajustes na raiz são da área.
O título nos ajustes nomeia a pasta no painel, sem renomear arquivos nem
alterar os títulos das notas que estão dentro. Em Estudos, os ajustes internos
oferecem esse título, mantendo os cartões simples.

Nas demais áreas, **Novo** abre título e campos obrigatórios sem valor padrão.
Em Tarefas, a descrição opcional é o texto da nota. Em
**Adicionar campo +**, escolha propriedades adicionais ou Texto. Campos não
adicionados conservam os padrões do módulo; não são enviados como valores vazios.

Na lista de **Tarefas**, o círculo ao lado do título conclui a tarefa. Ele fica
preenchido com um visto e o título riscado; clicar novamente reabre. O controle
funciona por teclado e só muda depois da confirmação do servidor. Os estados
intermediários continuam disponíveis nas propriedades da nota e no quadro.

Em Tarefas, **Hoje** é o padrão no quadro e na lista. Mostra as tarefas abertas
do dia, as atrasadas e as que estão sem data. O resumo **Hoje** do Início reúne
as últimas em **Tarefas sem data**, e o calendário usa as datas agendadas.
**Semana** vai de segunda a domingo. **Todas** também inclui as tarefas abertas
fora do período. As concluídas
aparecem pela data de conclusão, até hoje, dentro do período selecionado. Concluir
registra `concluido_em` na nota; reabrir remove essa data e uma nova conclusão a
renova. Editar o texto de uma tarefa concluída conserva sua data. O prazo da tarefa
e o horário de modificação do arquivo não são usados como data de conclusão.
Notas antigas sem essa informação não recebem uma data estimada.

A Lista usa o mesmo período do quadro, com até 80 notas por página. O quadro mostra
até 80 cartões por coluna e indica o restante na Lista. Nenhuma nota é apagada ou
arquivada automaticamente por sair do recorte diário. Projetos e outras áreas
conservam seu histórico no quadro, conforme o significado dos próprios status.

Nas listas das outras áreas, marque itens ou selecione todos da página para arquivar, excluir ou
alterar o status. A seleção é limitada à página atual (até 80 notas). Arquivar
e excluir pedem confirmação. Se uma nota mudou em outra aba ou no Obsidian,
ela fica intacta e seu erro aparece no resultado; as demais podem ser atualizadas.
As ações aparecem junto às configurações, sem deslocar a tabela ao selecionar.
Excluir exige autorização local ou um endereço Tailscale permitido; apagar
definitivamente continua exigindo acesso local. Veja a [lixeira](pastas.md).

Em **Personalizar**, Aparência e Visualizações têm painéis separados.
Trocar de aba preserva as alterações pendentes; Salvar alterações considera todas
as abas. A capa é a exceção: clicar numa cena ou imagem, ou enviar uma capa, já
salva essa escolha. Outros ajustes ainda pendentes continuam no formulário.
O seletor de ícone mostra os desenhos, com o nome acessível no foco ou hover.
O cabeçalho acompanha a rolagem normal da página.

O dock mantém **Entrada**, quando instalada, à direita. No celular, uma área
principal permanece ao lado dos atalhos fixos. **Mais atalhos** abre a lista completa.
As teclas **1 a 9** levam aos cards pela ordem da home; **0** abre o menu de áreas.
Os atalhos ficam suspensos ao digitar ou com um diálogo aberto. **Início** volta
à capa da última área acessada, inclusive pelo dock. Na home, outro clique em
Início seleciona o primeiro card. A memória é separada por vault e por aba.
Na home, arraste os cartões com o mouse ou use as setas. Arrastar não abre o cartão.
- **Mostrar uma pasta sua.** Em Pastas, "Mostrar no painel": o painel lê os campos
  que as notas já têm e escreve o `_modulo.yaml` por você. Veja
  [vault-existente.md](vault-existente.md).

O ícone ao lado das abas de cada área abre **Personalizar**: nome, descrição, ícone,
cena da capa, o que conta como concluído e se a área mostra quadro e gráfico.
Na lista, clique duas vezes no nome de uma coluna para editar seu rótulo.
Use Enter para salvar e Escape para cancelar. No celular, toque no nome.
A seta ao lado ordena a página. Renomear só altera a apresentação da coluna.
Os ajustes são gravados no `_modulo.yaml`, preservando os comentários.

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
  decidir: [atrasado]     # entram em Entrada → Para decidir
  acoes:                  # botões de Entrada → Para decidir
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
  # - tipo: pastas        # cada item vira uma pasta com suas notas (padrão em Projetos)
  # - tipo: cartoes       # cartões simples: ícone, título e um texto de apoio (padrão em Estudos)

capa: {cena: cidade, paleta: brasa}   # opcional; veja docs/temas.md

# Só na visão pastas, escrito pelo botão Ajustes dentro da pasta:
# pastas:
#   "projetos/itens/Meu projeto.md": {arte: oceano, entrada_rapida: true}
#   "grupo:Arquivo antigo": {imagem: midia/capas/abc.png}
#   "grupo:Notas soltas": {cor: '#7cc4ff'}
```

Na visão `pastas`, as notas de apoio de um item ficam em `<area>/referencias/<item>/`
e trazem `projeto: [[item]]` (ou `estudo:`). Capas nativas: `aurora`, `brasa`,
`ametista` e `oceano`. **Cor lisa** usa a mesma paleta dos ajustes gerais ou uma
cor personalizada no formato `#rrggbb`, tanto em projetos quanto em grupos de
notas. Cor, imagem e arte são alternativas de capa; escolher uma substitui a anterior.
No celular, as pastas e os cartões de Projetos e Estudos, inclusive as notas
internas em grade, usam duas colunas. Lista continua como lista compacta.

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
Para acompanhar outro número, acrescente um campo do tipo `numero` no `_modulo.yaml`.

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
- **Entrada** reúne **Capturas**, ideias e pedidos para organizar, e **Para decidir**,
  itens com status da lista `decidir` ou com uma pergunta pendente. Cada decisão
  é gravada na nota de origem. A fila continua acessível em cofres sem Capturas.
- **O número no dock** é "para hoje" quando o módulo tem `campo_data`; senão, o que
  espera decisão; senão, o que está em aberto.
- **O dock não cresce sem parar.** Com até nove itens, mostra tudo. Acima disso, mostra
  cinco áreas, a área em que você está e o botão **Mais atalhos** (tecla `G`), que abre
  a lista completa com Diário, Pastas e Ajustes. Agenda e Entrada continuam na barra.
  Para escolher quais ficam sempre à mão,
  liste no `orquestra.yaml`: `dock: [tarefas, projetos, notas]`.
- **Tirar do painel não apaga nada.** O `_modulo.yaml` vira `_modulo.desligado.yaml`
  e a pasta continua no vault. Religar devolve a área como estava.
- **Cada módulo tem um `maquina/aprendizados.md`**, onde os agentes anotam o que
  aprenderam trabalhando ali. O painel cria o arquivo junto com o módulo.

## Compartilhar um módulo

Um módulo é uma pasta. Para compartilhar, copie a pasta sem o conteúdo de `itens/`
(e sem nada pessoal em `humano/`). Quem receber cola na raiz do próprio vault.
