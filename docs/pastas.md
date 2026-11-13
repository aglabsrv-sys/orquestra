# Pastas e grafo

O explorador apresenta os arquivos do vault em uma árvore lateral persistente.
A visualização inicial é o grafo: cada ponto representa uma nota, e cada linha
representa uma ligação `[[wikilink]]` resolvida dentro da pasta atual.

![Explorador e grafo de notas](img/pastas.png)

## Navegação

- Expanda pastas pela seta e abra uma pasta pelo nome.
- Use **Notas** para ver a lista de subpastas, notas e anexos.
- Clique em uma nota da árvore, da lista ou do grafo para ler sem fechar o explorador.
- **Voltar ao grafo** encerra a leitura e retorna às ligações da pasta.
- Arraste o grafo para mover a vista. Use a roda do mouse ou `+` e `-` para aproximar.
- **Centralizar** ajusta o conjunto de notas ao espaço disponível.

O grafo mostra até 600 notas e 3.000 ligações por consulta. O indicador informa
quando a visualização é parcial. Notas com nomes duplicados exigem links com caminho
para que a ligação seja inequívoca.

## Imagens e vídeos

Imagens podem ser inseridas como `![[foto.png]]`, `![[foto.png|300]]` ou
`![Descrição](<../anexos/foto com espaços.png>)`. Caminhos relativos à nota têm
prioridade, seguidos pelo caminho no vault e pela busca pelo nome do arquivo.
PNG, JPEG, WebP, GIF, SVG, AVIF, BMP e ICO são reconhecidos. A exibição depende
também do suporte do navegador. MP4 e WebM podem ser abertos pelo explorador.

## Templates HTML

Arquivos `.html` e `.htm` aparecem na árvore e na lista de anexos. O painel abre
uma prévia isolada que preserva HTML e CSS inline, incluindo tabelas de email.
Imagens locais e HTTPS são suportadas. Imagens HTTPS são buscadas no servidor de origem.
Scripts, formulários, navegação de topo e folhas de estilo externas ficam bloqueados.
Não é necessário converter o template em Markdown. Uma prévia no navegador não
substitui testar a mensagem nos clientes de email usados pelos destinatários.

A edição de HTML é feita no editor de sua preferência; a edição de notas Markdown
continua disponível no leitor do painel.

[Ver o explorador no celular](img/pastas-mobile.png).
