# Atualizar o Orquestra

O painel consulta a revisão publicada na `main` do repositório oficial ao abrir
uma página e, depois, a cada 30 minutos. Uma revisão nova pode aparecer mesmo
sem mudança no número da versão. Sem conexão, a consulta não interrompe seu uso.

O botão aparece quando há código novo para carregar, com um ponto na cor
de destaque. Fica no canto inferior esquerdo; no celular, ao lado esquerdo do dock,
na mesma faixa inferior, separado dos indicadores do carrossel.
Clique para atualizar; salve as edições abertas
e confirme **Atualizar e reiniciar**. A página aguarda o novo processo e recarrega
quando confirma a revisão instalada.

Se os arquivos da cópia Git local mudarem com o painel aberto, o mesmo botão
aparece em até 15 segundos numa aba ativa. **Reiniciar com os novos arquivos**
carrega essa cópia e preserva suas alterações locais. Após o reinício, o botão
volta a avisar sobre revisões publicadas.

A instalação pelo painel exige acesso direto por localhost e uma cópia Git na
`main` do repositório oficial, com Git e uv disponíveis. Pelo Tailscale, o ícone
avisa da novidade e orienta a abrir localhost no computador. O aplicativo não
atualiza sozinho nem recebe comandos ou endereços de download do navegador.

Arquivos extras sem conflito com a versão nova ficam no lugar e não bloqueiam
a atualização. Quando há arquivos do aplicativo alterados, a confirmação oferece
**Guardar cópia e atualizar**. Arquivos extras que ocupem caminhos usados pela
versão nova também são copiados antes de liberar esses caminhos. A confirmação
explica que a versão oficial passa a ser usada: as personalizações ficam guardadas
na cópia, sem serem reaplicadas automaticamente.

As cópias ZIP ficam em `~/.orquestra/atualizacoes/`, separadas por instalação,
ou dentro do `ORQUESTRA_HOME` configurado. Essa pasta precisa ficar fora do
aplicativo e do vault. Cada cópia inclui os arquivos anteriores, um manifesto
com caminhos e exclusões e os patches Git. O histórico Git também retém as
alterações, inclusive o índice. Nenhuma cópia é enviada à internet ou apagada
automaticamente. Depois da retomada, o aviso **Baixar cópia** permite baixar o ZIP
no próprio computador, por localhost. O aplicativo não oferece restauração
automática de código antigo; consulte a cópia antes de reaplicar personalizações.

Commits próprios que divirjam da `main` oficial continuam protegidos: a atualização
explica a divergência e cancela, sem descartar ou mesclar commits. Se um vault
estiver dentro do aplicativo e ocupar um caminho usado pela versão nova, ele
também é preservado e a atualização orienta separar as pastas. As notas do vault
não são modificadas pela atualização.

O painel continua aberto enquanto o código e as dependências são preparados.
Se essa preparação falhar, o aviso informa o problema e as cópias já feitas
permanecem guardadas. Se a
retomada não for confirmada, confira o computador e use `uv run --frozen orquestra`
na pasta do aplicativo para abrir novamente. A atualização não desfaz código ou
dependências parcialmente instalados; corrija a falha antes de tentar novamente.

Também continua disponível o comando `uv run --frozen orquestra atualizar`.
Ele guarda as alterações do aplicativo antes de instalar e informa a pasta
da cópia no terminal, usando as mesmas proteções do painel.

## Recuperar uma instalação antiga no Windows

Se a versão antiga só mostra **Há alterações locais no aplicativo. Guarde essas
mudanças antes de atualizar**, salve as edições abertas e baixe
[Atualizar Orquestra.cmd](../scripts/Atualizar%20Orquestra.cmd). No GitHub, use
**Download raw file** para salvar o arquivo. Abra-o com dois cliques, escolha a
pasta do aplicativo, onde ficam `pyproject.toml` e `uv.lock`, e confirme a cópia
e a atualização. Escolha a pasta do aplicativo, e não a pasta de notas.

O recuperador exige Git e uv já instalados, baixa o atualizador da `main` oficial,
guarda as alterações em uma cópia e prepara as dependências antes de reabrir o
painel no mesmo vault e porta. Ele não altera políticas do PowerShell. Ao terminar,
recarregue a página. Se o painel estava fechado, abra pelo atalho habitual.
