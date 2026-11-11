# Temas e capas

A aparência do painel mora no vault, em `_orquestra/temas/`. Cada tema é uma pasta
com um `tema.yaml`. Trocar de tema é escolher em **Ajustes**; criar um é copiar uma
pasta e editar o arquivo. Como tudo está no vault, um agente também consegue:
"crie um tema verde-escuro com capas de floresta".

## O que um tema define

```yaml
nome: Brasa
descricao: Fim de tarde quente, laranja e carvão.

cores:                       # a interface (sempre em hexadecimal)
  fundo: "#130c09"
  superficie: "#1e1410"
  superficie_alta: "#2a1c16"
  borda: "#3b2a22"
  texto: "#f6ebe3"
  texto_suave: "#b59f92"
  destaque: "#f4b183"        # botões e item ativo do dock
  sobre_destaque: "#2a1608"  # texto em cima do destaque
  alerta: "#ff7a59"
  ok: "#9bd49b"

paletas:                     # as cores das capas em pixel art
  poente:
    ceu: ["#2b1a3a", "#7a2e4a", "#d9603f", "#f7b267"]   # do alto até o horizonte
    astro: "#ffe3a3"         # sol ou lua
    nuvem: "#f29a6b"
    longe: "#8a3f4d"         # plano mais distante
    meio: "#5a2a3c"
    perto: "#33182a"         # plano mais próximo
    sombra: "#1a0d18"        # o tom mais escuro
    luz: "#ffd27a"           # janelas, pontos de luz
    brilho: "#fff3d1"        # estrelas, reflexos
    noite: false             # true desenha mais estrelas

capas:                       # qual cena e paleta cada módulo usa
  tarefas: {cena: janela, paleta: poente}
  conteudo: {cena: cidade, paleta: brasa}
  decidir: {cena: montanhas, paleta: poente}
  diario: {cena: floresta, paleta: cobre}
```

Salve o arquivo e o painel recarrega sozinho.

## As cenas

As capas não são imagens: são desenhadas pelo navegador, pixel por pixel, com as
cores da paleta. Por isso mudam de cor junto com o tema, pesam nada e não têm
problema de licença.

| Cena | O que mostra | O que se mexe |
|---|---|---|
| `janela` | um estúdio com janela para a cidade | nuvens, tela do monitor, rabo do gato, planta, vapor da caneca |
| `cidade` | prédios à noite com lua | janelas acendendo e apagando, carros, avião |
| `montanhas` | serras em camadas com sol | nuvens, névoa, pássaros |
| `mar` | horizonte com farol e veleiro | reflexo na água, facho do farol, ondas |
| `floresta` | pinheiros e uma cabana | vaga-lumes, névoa, fumaça da chaminé |
| `espaco` | planeta com anel | estrelas, lua em órbita, satélite, estrela cadente |

Módulos que o tema não lista em `capas` ganham uma cena escolhida pelo nome do
módulo, sempre a mesma.

## Usar a sua própria imagem ou vídeo

Coloque o arquivo no vault (sugestão: `_orquestra/capas/`) e aponte no
`_modulo.yaml` do módulo:

```yaml
capa: _orquestra/capas/meu-estudio.webp
```

Formatos: PNG, JPG, WebP, GIF, SVG, MP4 e WebM. Vídeos tocam em loop, sem som. A
capa definida no módulo vale mais que a do tema, então ela fica mesmo se você
trocar de tema.

Para a capa de **Decidir** e **Diário**, que não são módulos, use o `capas:` do tema
com o caminho do arquivo:

```yaml
capas:
  decidir: _orquestra/capas/decisoes.mp4
```

## Criar um tema

1. Copie `_orquestra/temas/brasa` para `_orquestra/temas/meu-tema`.
2. Edite o `tema.yaml`: nome, cores, paletas.
3. Em **Ajustes**, escolha o tema novo (ou escreva `tema: meu-tema` no `orquestra.yaml`).

Dica de contraste: `texto` sobre `fundo` e `sobre_destaque` sobre `destaque` precisam
ser bem legíveis. Os temas que vêm prontos são escuros; um tema claro funciona, mas
teste as telas de módulo e de nota.

## Criar uma cena nova (para quem programa)

As cenas ficam em `src/orquestra/static/js/cenas.js`. Uma cena é uma função que
recebe a paleta e um gerador de números aleatórios, prepara as camadas fixas uma
vez e devolve a função que desenha cada quadro:

```js
CENAS.deserto = function (pal, R) {
  var fundo = camada(function (g) {
    degrade(g, pal.ceu, 0, 0, W, 120);          // céu com transição pontilhada
    disco(g, 240, 60, 14, pal.astro);           // sol
  });
  return function (g, t) {                      // t em segundos
    g.drawImage(fundo, 0, 0);
    // ...o que se mexe
  };
};
```

O canvas tem 320x180 pixels. Há ajudantes para degradê pontilhado, nuvens, serras,
pinheiros, estrelas e névoa. Depois de criar, acrescente o nome à lista `CENAS` em
`src/orquestra/temas.py`.
