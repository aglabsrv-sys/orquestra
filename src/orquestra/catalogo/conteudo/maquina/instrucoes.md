# Instruções para agentes: Conteúdo

Leia antes `conteudo/_modulo.yaml` e `conteudo/humano/Minha voz.md`.

## O pipeline

`ideia` → `roteiro` → `gravado` → `editado` → `publicado`

Você trabalha nas duas primeiras etapas. As outras são da pessoa: só ela grava,
edita e publica, então só ela move um item para `gravado` em diante.

## Propor uma ideia

Crie o item em `conteudo/itens/` com `status: ideia`, `origem: agente` e a
`plataforma`. No corpo, em poucas linhas: por que agora, para quem, qual o ângulo.
Se a ideia veio do radar, ligue com `[[nome do item do radar]]` e marque o item do
radar como `virou_ideia`.

## Escrever um roteiro

Só quando pedirem, ou quando a ideia tiver `resposta` aprovando. Escreva o roteiro
no corpo do próprio item, abaixo de `## Roteiro`, e mude para `status: roteiro`.
Se o item tem `origem: humano`, não toque no texto que já existe: acrescente abaixo.

Siga `Minha voz.md` à risca. Em caso de dúvida sobre tom ou promessa, use `pergunta`.

## Miniaturas

Arquivos de imagem ficam em `conteudo/midia/`. O campo `miniatura` guarda o caminho
a partir da raiz do vault, por exemplo `conteudo/midia/5-erros.png`.
