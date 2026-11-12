# Comece aqui

Esta pasta é o seu **vault**: o lugar onde vivem suas notas. Tudo aqui é arquivo de
texto. Três coisas trabalham em cima dele:

- **o painel** (Orquestra), para ver e mexer rápido, inclusive do celular;
- **o Obsidian**, se você quiser escrever e navegar com mais calma;
- **seus agentes de IA** (Claude, Codex, Gemini...), que leem o `AGENTS.md` e
  trabalham direto nos arquivos. Eles são opcionais: o painel funciona sem IA.

## As áreas do painel

| Pasta | Para quê |
|---|---|
{{modulos}}

Cada área é um **módulo**: uma pasta com um arquivo `_modulo.yaml` que diz quais
campos as notas têm e como mostrá-las. Em **Ajustes** você acrescenta módulos
prontos, cria um em branco ou tira do painel os que não usa (a pasta fica).
Qualquer outra pasta sua aparece em **Pastas**, e pode virar área do painel com um
clique, sem mudar nenhuma nota de lugar.

As notas de exemplo podem ser apagadas quando quiser.

## Humano e máquina

Cada módulo tem duas pastas com papéis bem diferentes:

- `humano/` guarda o que **você** disse: seu jeito de priorizar, sua voz, o que te
  interessa. Os agentes leem antes de agir e não podem reescrever.
- `maquina/` guarda o que faz o sistema andar: instruções para os agentes, os
  aprendizados deles e os coletores. Você raramente precisa abrir.

Assim, um resumo feito pela IA nunca vira "algo que você disse".

## Primeiros passos

1. Em cada módulo, abra a aba **Humano** e reescreva a nota de exemplo com as suas regras.
2. Use **Capturar** (tecla `C`) para guardar a primeira ideia.
3. Se usa um agente, abra-o nesta pasta e peça: "leia o AGENTS.md e me diga o que entendeu".
