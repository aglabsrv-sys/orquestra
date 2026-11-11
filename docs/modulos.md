# Criar e ajustar módulos

Um módulo é uma pasta na raiz do vault com um arquivo `_modulo.yaml`. O painel
descobre sozinho: não há nada para registrar nem código para mexer. O jeito mais
rápido de criar um é pedir a um agente ("crie um módulo de finanças"), mas é bom
saber o que ele vai escrever.

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

## Ícones

`inicio` `check` `video` `radar` `entrada` `sino` `pulso` `lampada` `calendario`
`moeda` `livro` `grafico` `estrela` `relogio` `pessoas` `pessoa` `raio` `coracao`
`nota` `pasta` `caixa` `chip` `paleta` `nuvem` `celular` `busca`

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

## Compartilhar um módulo

Um módulo é uma pasta. Para compartilhar, copie a pasta sem o conteúdo de `itens/`
(e sem nada pessoal em `humano/`). Quem receber cola na raiz do próprio vault.
