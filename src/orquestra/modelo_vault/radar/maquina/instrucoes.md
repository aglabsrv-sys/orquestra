# Instruções para agentes: Radar

Leia antes `radar/_modulo.yaml` e `radar/humano/O que me interessa.md`.

## Triagem

Os coletores gravam itens com `status: novo` e `origem: coletor`. Para cada um:

- Bate com "Quero ver"? Mude para `util` e acrescente, abaixo do texto coletado, uma
  seção `## Por que importa` com uma ou duas linhas.
- Bate com "Não quero ver", ou não bate com nada? Mude para `descartado`.
- Não tem certeza? Deixe como `novo`. A pessoa decide na fila do painel.

Não altere `titulo`, `link`, `canal` nem o texto coletado: são o registro do que veio de fora.

## Transformar em ideia

Quando um item útil render um conteúdo, crie a ideia em `conteudo/itens/` (veja as
instruções de lá), ligue as duas notas com `[[...]]` e mude o item do radar para
`virou_ideia`.

## O que você não faz

- Não rode os coletores e não crie itens fingindo que foram coletados.
- Não busque na internet para "completar" o radar, a menos que peçam. O radar é o que
  os scripts trouxeram, e é isso que o torna confiável.
