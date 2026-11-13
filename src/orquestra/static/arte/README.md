# Coleção de imagens

Ilustrações (e um vídeo em loop) que vêm com o Orquestra, uma para cada tema. Aparecem
em **Personalizar > capa**, depois das cenas desenhadas por código. A lista usada pelo
painel fica em `COLECAO`, em `src/orquestra/temas.py`: ao acrescentar um arquivo aqui,
acrescente-o lá também (há um teste que confere as duas coisas).

| Arquivo | Tema | Origem |
|---|---|---|
| `entardecer.webp` | Brasa | AG LABS, Nano Banana 2.1 |
| `enseada.webp` | Maré | AG LABS, Nano Banana 2.1 |
| `avenida.webp` | Noturno | AG LABS, Nano Banana 2.1 |
| `avenida.webm` | Noturno | AG LABS, Veo 3.1 Fast, a partir de `avenida.webp` |
| `observatorio.webp` | Azul profundo | ImageGen |
| `laboratorio.webp` | Terminal | AG LABS, Nano Banana 2.1 |
| `pavilhao.webp` | Luz | AG LABS, Nano Banana 2.1 |
| `refugio.webp` | Grafite | ImageGen |

Todas são imagens originais, geradas para este projeto e convertidas para WebP
(1920 px de largura, qualidade 80). O vídeo tem 4 segundos, sem áudio, em WebM/VP9.

## Como foram pedidas

As cinco ilustrações do AG LABS usam a mesma moldura de prompt, mudando a cena e a paleta:

> Refined, detailed pixel art illustration, wide 16:9 cinematic landscape used as a
> header cover in a personal notes app. [cena]. Limited palette: [cores do tema].
> Crisp artisanal pixels, visible dithering, atmospheric depth, sophisticated and calm
> rather than game-like. Keep the important details inside the middle horizontal band
> so the image survives shallow banner crops, with a calm uncluttered area for a title.
> No text, no letters, no logos, no UI, no watermark, no border.

- **Entardecer:** a small writer's cabin on a rocky ridge at dusk overlooking a warm
  desert valley, glowing amber windows, layered mesas, saguaro silhouettes, a low
  ember-orange sun; charcoal brown, wine, burnt orange and peach.
- **Enseada:** split-level view of a quiet cove at twilight, a lighthouse and a sailboat
  above the waterline, a coral reef, a shoal of fish and light rays below; dark teal,
  sea green, aqua and a coral-pink accent.
- **Avenida:** a rainy cyberpunk avenue at night, towers framing the view, neon signs
  made of abstract shapes, an elevated train line, a huge hazy magenta sun; near-black
  violet, electric violet, magenta and cyan.
- **Laboratório:** a quiet retro computer lab at night, three CRT monitors glowing
  phosphor green with abstract rows of blocks, keyboard, cables, a mug and a plant;
  strictly monochrome green on near-black.
- **Pavilhão:** a bright spring morning, a minimalist white pavilion beside a still
  pond, a cherry tree in blossom, an arched footbridge, soft green hills; porcelain
  white, pale blue, sage green and blossom pink.

O vídeo anima `avenida.webp` com a câmera parada: só a chuva, o piscar dos letreiros e
os reflexos no asfalto se mexem.

**Observatório:** refined pixel art, serene architectural observatory overlooking
layered blue mountains at dusk, tiny warm windows, subtle stars, restrained indigo,
graphite and silver-blue palette, wide 3:1 composition.

**Refúgio:** wide 3:1 photograph of a minimalist concrete and dark timber library
pavilion on a quiet lake, distant misty mountains, early blue hour with soft amber
light through a few windows; graphite, silver blue and black.
