# Atualizar o Orquestra

O painel consulta a revisão publicada na `main` do repositório oficial ao abrir
uma página e, depois, a cada 30 minutos. Uma revisão nova pode aparecer mesmo
sem mudança no número da versão. Sem conexão, a consulta não interrompe seu uso.

O botão aparece somente quando há uma atualização publicada, com um ponto na cor
de destaque. Fica no canto inferior esquerdo; no celular, ao lado esquerdo do dock,
na mesma faixa inferior, separado dos indicadores do carrossel.
Clique para atualizar; salve as edições abertas
e confirme **Atualizar e reiniciar**. A página aguarda o novo processo e recarrega
quando confirma a revisão instalada.

Mudanças locais ainda não publicadas não fazem o botão aparecer. Para carregar
esse código, use `uv run --frozen orquestra reiniciar`.

A instalação pelo painel exige acesso direto por localhost e uma cópia Git na
`main` do repositório oficial, com Git e uv disponíveis. Pelo Tailscale, o ícone
avisa da novidade e orienta a abrir localhost no computador. O aplicativo não
atualiza sozinho nem recebe comandos ou endereços de download do navegador.

Arquivos do aplicativo alterados ou não versionados impedem a instalação; guarde
essas mudanças antes de tentar novamente. Divergências do Git não são mescladas
nem descartadas. As notas do vault não são modificadas pela atualização.

O painel continua aberto enquanto o código e as dependências são preparados.
Se essa preparação falhar, o aviso informa que a atualização não terminou. Se a
retomada não for confirmada, confira o computador e use `uv run --frozen orquestra`
na pasta do aplicativo para abrir novamente. A atualização não desfaz código ou
dependências parcialmente instalados; corrija a falha antes de tentar novamente.

Também continua disponível o comando `uv run --frozen orquestra atualizar`.
