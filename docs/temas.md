# Temas e capas

A aparência do painel tem duas camadas, e as duas moram no vault:

- o **tema** (uma pasta em `_orquestra/temas/`) define as cores e as capas;
- as **suas escolhas** por cima dele (`aparencia:` no `orquestra.yaml`): claro ou
  escuro, cor de destaque, cantos, letra e tamanho da fonte.

Tudo se muda em **Ajustes**, sem editar arquivo. Como está no vault, um agente
também consegue: "crie um tema verde-escuro com capas de floresta".

## Do seu jeito (Ajustes > Aparência)

| Escolha | Opções | No `orquestra.yaml` |
|---|---|---|
| Claro ou escuro | Escuro, Claro, Igual ao sistema | `modo: escuro \| claro \| auto` |
| Cor de destaque | a do tema, oito sugestões ou qualquer cor | `destaque: "#7cc4ff"` (vazio usa a do tema) |
| Cantos | Retos, Discretos, Médios, Redondos (botões em pílula) | `cantos: reto \| discreto \| medio \| redondo` |
| Letra | Padrão, Serifada, Arredondada, Monoespaçada | `fonte: sistema \| serifada \| arredondada \| mono` |
| Tamanho da fonte | Pequena, Padrão, Grande | `tamanho: pequena \| padrao \| grande` |

```yaml
aparencia:
  modo: auto
  destaque: "#7cc4ff"
  cantos: redondo
  fonte: sistema
  tamanho: padrao
```

Três detalhes de como isso funciona:

- **A cor de destaque se ajusta ao modo.** Um tom pastel aparece bem no escuro e
  some no claro. Em vez de recusar a sua cor, o painel escurece (ou clareia) só o
  necessário para ela continuar legível, e escolhe sozinho se o texto em cima dela
  fica preto ou branco.
- **As letras são as do seu computador.** Nada é baixado da internet, então o painel
  continua funcionando sem conexão. Por isso a mesma opção pode ter um desenho um
  pouco diferente no Windows, no macOS e no celular.
- **As capas não mudam com o modo claro.** São cenas de fim de tarde e de noite, e
  funcionam como imagem nos dois modos.

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

cores_claras:                # as mesmas dez chaves, para o modo claro
  fundo: "#fbf6f1"
  texto: "#2b1a10"
  destaque: "#c2571a"
  # ...
                             # sem este bloco, o painel deriva um modo claro do escuro

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

cenas: [janela, deserto, cidade, montanhas]   # o estilo do tema: as cenas que combinam com ele

capas:                       # qual cena e paleta cada módulo usa
  tarefas: {cena: janela, paleta: poente}
  conteudo: {cena: cidade, paleta: brasa}
  decidir: {cena: montanhas, paleta: poente}
  diario: {cena: floresta, paleta: cobre}
```

Ao alterar o arquivo fora do painel, ele avisa que há novidades. Use **Atualizar**
para aplicar o conteúdo novo. Os controles de aparência da própria tela aplicam
as preferências sem recarregar o documento.

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
| `ceu` | acima das nuvens, com balões | o mar de nuvens deslizando em três planos, balões, pássaros |
| `aurora` | colinas nevadas e uma cabana | as cortinas da aurora, neve caindo, estrelas |
| `deserto` | dunas, chapadas e cactos | uma caravana atravessando, areia ao vento, nuvens |

### Cada tema tem um estilo

| Tema | Estilo | Cenas preferidas |
|---|---|---|
| **Brasa** | fim de tarde e noite quente | janela, deserto, cidade, montanhas |
| **Maré** | verde profundo com destaque em pêssego: mar, céu e farol | mar, céu, aurora, montanhas |
| **Noturno** | espaço, aurora e madrugada | espaço, aurora, cidade, janela |

Nos temas que vêm prontos, cada área do catálogo tem um par (cena, paleta) só dela:
duas áreas nunca ficam com a mesma capa. Uma área que o tema não lista em `capas`
(uma que você criou, ou uma pasta sua) ganha um par ainda não usado, escolhido entre
as `cenas` do tema a partir do nome da área, sempre o mesmo. Uma pasta sua chamada
"1. Projetos" usa a capa que o tema reservou para `projetos`.

Para escolher a cena de uma área, use **Personalizar** (o ícone ao lado das abas).
**Ver cenas animadas** abre os previews no mesmo modal. A cena pode ser automática,
seguindo o tema, ou uma escolha sua.

## Usar a sua própria imagem ou vídeo

Em **Personalizar > Adicionar capa**, envie PNG, JPEG, WebP, MP4 ou WebM de até
2 MB. Prefira vídeos curtos, até 20 segundos, comprimidos e sem áudio. O servidor
limita formato e tamanho, mas não transcodifica nem verifica a duração. Confira
o resultado e salve a personalização para aplicar.

Também é possível colocar um arquivo no vault (sugestão: `_orquestra/capas/`) e
apontar no `_modulo.yaml` do módulo:

```yaml
capa: _orquestra/capas/meu-estudio.webp
```

Arquivos já existentes podem usar PNG, JPG, WebP, GIF, SVG, MP4 e WebM. Vídeos
tocam em loop, sem som, pausam fora da tela e respeitam movimento reduzido. A
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
ser bem legíveis, em `cores` e em `cores_claras`. Os três temas que vêm prontos têm
os dois modos e são conferidos por teste automático (`tests/test_aparencia_e_automacoes.py`).

## Criar uma cena nova (para quem programa)

As cenas ficam em `src/orquestra/static/js/cenas.js`. Uma cena é uma função que
recebe a paleta e um gerador de números aleatórios, prepara as camadas fixas uma
vez e devolve a função que desenha cada quadro:

```js
CENAS.praia = function (pal, R) {
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
