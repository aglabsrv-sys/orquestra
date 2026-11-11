# AGENTS.md: como trabalhar neste vault

Você é um agente de IA com acesso a esta pasta. Ela é o sistema de trabalho de uma
pessoa: tarefas, conteúdo, pesquisa. O "banco de dados" são arquivos markdown com
frontmatter YAML. Um painel web (Orquestra) lê e edita os mesmos arquivos, e a
pessoa também os abre no Obsidian. Tudo que você grava aqui aparece para ela na hora.

Leia este arquivo inteiro antes de alterar qualquer coisa.

## Mapa

```
AGENTS.md            este contrato
orquestra.yaml       configuração do painel (nome, tema, backup)
<modulo>/            uma área de trabalho: tarefas, conteudo, radar, entrada...
  _modulo.yaml       schema do módulo: campos, status, visões, coletores
  itens/             os registros (uma nota .md por item)
  humano/            o que a pessoa disse, com as palavras dela
  maquina/           instruções para você, coletores, saídas de script
  arquivo/           itens arquivados (não apague, não edite)
diario/sessoes/      seu relato de cada sessão de trabalho
diario/registro/     registro automático de mudanças (o painel escreve, você não)
_orquestra/          temas e estado do painel
```

Um módulo é qualquer pasta na raiz que tenha `_modulo.yaml`. Antes de trabalhar num
módulo, leia o `_modulo.yaml` dele e tudo em `maquina/` e `humano/` desse módulo.

## Regras que não têm exceção

1. **`humano/` é da pessoa.** Leia sempre, nunca reescreva, resuma nem "melhore" o
   que está lá. Se precisar registrar algo novo que ela disse, acrescente ao final
   da nota um bloco iniciado por `> Acrescentado por agente em AAAA-MM-DD:`.
2. **Nunca trate um resumo seu como fala dela.** O que você escreve vai em `itens/`
   (com `origem: agente`) ou em `maquina/`. Só o que ela escreveu é `origem: humano`.
3. **Não reescreva o texto de um item com `origem: humano`.** Você pode mudar os
   campos do frontmatter (status, data, tags) e acrescentar ao final uma seção
   `## Notas do agente`. O texto original fica intacto.
4. **Nunca apague arquivos.** Para tirar algo de circulação, mude o status ou mova
   para `<modulo>/arquivo/`.
5. **Não grave segredos** (chaves de API, senhas, tokens) em nenhum arquivo do vault.
6. **Não escreva em `diario/registro/` nem em `_orquestra/estado.json`.**
7. **Respeite o schema.** Em campos do tipo `escolha`, use só as opções listadas no
   `_modulo.yaml`. Se precisar de uma opção nova, peça antes (veja "Quando precisar
   de uma decisão").

## Formato de um item

Arquivo: `<modulo>/itens/<Título legível>.md`. O nome do arquivo é o título, com
acentos e espaços, sem os caracteres `\ / : * ? " < > | # ^ [ ]`. Se o título real
tiver um desses caracteres, coloque-o no campo `titulo`.

```markdown
---
status: a_fazer
prioridade: alta
data: 2026-01-15
origem: agente
tags:
  - youtube
---

Texto livre em markdown.
```

- Datas sempre `AAAA-MM-DD`, sem aspas.
- Listas em bloco (um `-` por linha).
- Chaves em minúsculas, sem acento, com `_` no lugar de espaço.
- Nada de objetos aninhados no frontmatter: o Obsidian não exibe bem.
- Campos que não estão no schema são permitidos, mas use com parcimônia.
- `origem` é obrigatório em tudo que você criar: `agente`.
- Links entre notas no estilo do Obsidian: `[[Nome da nota]]`.

Ao editar um arquivo existente, altere só o necessário e preserve a ordem das
chaves, os comentários e o resto do texto.

## Quando precisar de uma decisão

Não adivinhe e não fique parado. Deixe a pergunta no próprio item:

```yaml
pergunta: Posso publicar com este título ou prefere o da versão 2?
```

O item aparece na fila **Decidir** do painel. A pessoa responde por lá, e a resposta
volta no campo `resposta` (o campo `pergunta` é removido). Na sessão seguinte,
procure itens com `resposta`, aja de acordo e apague o campo `resposta` ao concluir.

Alguns módulos também têm status que significam "esperando a pessoa" (lista
`status.decidir` no `_modulo.yaml`). Use esses status quando o módulo oferecer.

## A entrada

`entrada/itens/` recebe as capturas rápidas dela (ideias, pedidos, lembretes),
quase sempre escritas no celular. Para cada item com `status: novo`:

1. Leia e decida o que aquilo é: tarefa, ideia de conteúdo, referência, pedido para você.
2. Crie o item no módulo certo (com `origem: agente` e um link `[[...]]` para a captura),
   ou execute o pedido.
3. Na captura, mude para `status: processado` e preencha `destino` com o que virou.
   Não altere o texto dela.

Se a captura for ambígua, use `pergunta` em vez de chutar.

## O radar e a triagem

Coletores (scripts, sem IA) gravam em `radar/itens/` com `status: novo` e
`origem: coletor`. O seu papel é o critério: leia `radar/humano/` para saber o que
interessa à pessoa e, para cada item novo, marque `util` ou `descartado`. Quando um
item útil inspirar algo, crie a ideia em `conteudo/itens/` e marque o original como
`virou_ideia`. Não rode coletores por conta própria nem invente itens "coletados".

## Diário de sessão

Ao terminar uma sessão de trabalho, acrescente um bloco ao final de
`diario/sessoes/AAAA-MM-DD.md` (crie o arquivo se não existir):

```markdown
## 14:30 · <seu nome ou modelo>

**Pedido:** o que ela pediu, em uma linha.
**Feito:** o que você criou ou alterou, com [[links]] para as notas.
**Pendente:** o que ficou para depois ou depende dela.
```

Seja factual e curto. Este diário é a memória entre sessões: comece cada sessão
lendo os dois ou três últimos dias.

## Estender o sistema

- **Novo módulo:** crie a pasta, um `_modulo.yaml` (copie o de `tarefas/` como base),
  as subpastas `itens/`, `humano/`, `maquina/` e um `maquina/instrucoes.md`. O painel
  detecta sozinho. Ícones disponíveis: inicio, check, video, radar, entrada, sino,
  pulso, lampada, calendario, moeda, livro, grafico, estrela, relogio, pessoas, raio,
  coracao, nota, pasta, caixa.
- **Capa de um módulo:** no `_modulo.yaml`, `capa: {cena: floresta, paleta: musgo}`
  (cenas: janela, cidade, montanhas, mar, floresta, espaco) ou o caminho de uma
  imagem/vídeo do vault, como `capa: _orquestra/capas/minha.webp`.
- **Tema:** copie uma pasta de `_orquestra/temas/`, edite o `tema.yaml` (cores em
  hexadecimal) e ative em `orquestra.yaml` com `tema: <nome da pasta>`.
- **Coletor:** um script Python em `<modulo>/maquina/coletores/` que imprime uma
  linha de JSON por item (`{"id": ..., "titulo": ..., ...}`) e uma entrada em
  `coletores:` no `_modulo.yaml`.

Mudanças de estrutura (módulo, schema, tema) só a pedido da pessoa.

## Antes de encerrar

- [ ] Tudo que criei tem `origem: agente`?
- [ ] Não toquei no texto de nada em `humano/` nem em itens de `origem: humano`?
- [ ] Os campos `escolha` usam opções que existem no schema?
- [ ] Dúvidas viraram `pergunta`, e não suposição?
- [ ] Registrei a sessão em `diario/sessoes/`?
