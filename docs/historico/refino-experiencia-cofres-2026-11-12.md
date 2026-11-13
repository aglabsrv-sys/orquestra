# Revisão de interface e experiência — 12 de novembro de 2026

O primeiro uso passa a ter três telas: pasta, ponto de partida com módulos e
aparência. O cenário de boas-vindas ocupa o topo com transição em gradiente,
acompanha o tema escolhido e termina em um modal. As opções de histórico ficam
na aparência, com o detalhamento da preparação recolhido.

As notas concentram as ações no cabeçalho. Duplo clique ou Enter abre o editor;
Escape ou clique fora envia o texto pela fila de gravação existente. Ctrl+Z usa
o desfazer nativo do editor. Falhas, conflitos e rascunhos continuam visíveis e
protegidos. As propriedades ficam recolhidas; origem e links existentes aparecem
em detalhes, e a imagem entra por arrastar, colar ou pelo anexo compacto. O campo
de imagem é rastreado no rascunho, inclusive se uma gravação falhar.

A aprovação de criativos tem sua própria lista filtrada por Conteúdo e estado
vazio. A fila de decisão usa ações compactas abaixo do item. O aviso instrucional
anterior foi retirado. Os pipelines existentes preservam seus status e campos;
o refino não migra configurações pessoais automaticamente.

A navegação entre visões de um módulo substitui somente o painel e seus diálogos,
preservando o canvas da capa e o histórico do navegador. Requisições ultrapassadas
são canceladas; uma troca de cofre detectada na resposta exige navegação completa.

Pastas tem árvore lateral com expansão sob demanda e navegação contínua. O grafo
usa ligações reais `[[entre notas]]`, oferece zoom, arraste, centralização e uma
lista acessível de notas. Para manter o custo limitado, exibe até 600 notas e 3.000 ligações do
escopo escolhido. Os ramos mostram até 300 notas diretas e oferecem acesso à lista
completa. Pastas internas e links para fora do cofre são recusados.

Em Ajustes, a ordem das pastas pode ser alterada por arrastar ou pelos botões de
teclado. A lista é gravada de uma vez em `orquestra.yaml`, sem reescrever todos os
schemas; listas obsoletas são recusadas. Novos módulos são acrescentados depois
dos já ordenados. Variáveis ganha busca, atualização em modal e valores nunca
retornados pelo servidor. Gerenciar cofres oferece criar e abrir uma pasta
existente, usando o fluxo local já protegido do aplicativo.

Personalizar usa seções de aparência, propriedades e visualizações, com prévia de
capa, grade equilibrada e ações de salvar fixas. Campos técnicos omitidos da tela
continuam nos schemas e nas notas. As preferências de aparência são salvas sem
notificações de sucesso sobre o conteúdo; erros continuam sendo anunciados.

## Verificação

Os testes de domínio cobrem persistência da ordem, lista obsoleta, novos módulos,
pastas vazias, confinamento, grafo filtrado e metadados discretos. Os testes de
JavaScript verificam duplo clique, Escape, clique fora e salvamento serializado
com uma propriedade em andamento. O roteiro Chromium foi atualizado para os
novos caminhos e verifica a preservação da instância da capa entre abas.

A execução local do Chromium foi bloqueada pela restrição de sockets Unix do
ambiente. O navegador compartilhado também não alcançou o servidor isolado e
recusou arquivos locais. Não há aprovação visual desktop/mobile nesta revisão
local. O roteiro de navegador continua pendente de execução na CI ou em máquina
com Chromium disponível. Um teste de execução isolada de coletor falha também
na versão-base, antes destas alterações; as demais verificações têm os resultados
registrados abaixo.


Resultados locais finais: 417 testes Python aprovados e uma falha que se reproduz
na versão-base (`test_execucao_recebe_so_chaves_declaradas_e_nao_herda_pythonpath`).
Os 57 testes JavaScript passaram; as 80 verificações de API, estrutura e templates
selecionadas também passaram. Ruff, links locais (28 documentos), build de wheel
e sdist e smoke de pacote/CLI/MCP/instalação editável passaram.
