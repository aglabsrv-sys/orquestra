# Histórico de mudanças

## Em desenvolvimento

- Links antigos de Decidir abrem Entrada. Depois de responder pelo teclado, o
  foco segue para o próximo cartão. A capa do Diário no Início respeita a
  opção Sem capa, e cliques repetidos em Atualizar abrem uma só confirmação.

- Hábitos aceita notas de realização pelo painel e pelo MCP. O dia selecionado
  no mapa é vinculado automaticamente, e as notas aparecem seis por página,
  com as mais recentes primeiro.

- O Diário volta à tela de origem e tem um calendário mensal para escolher a
  data. Os cartões de Para decidir ficam mais estreitos e centralizados.

- Entrada reúne Capturas e Para decidir. As respostas são salvas nos itens de
  origem. O Diário abre a anotação pessoal da data, e os registros automáticos
  e de sessão ficam em Ajustes → Painel → Registro de atividade. Hoje reúne
  os itens de trabalho e os hábitos. Os compromissos ficam na Agenda.

- O botão Atualizar sinaliza mudanças nos arquivos locais e oferece reiniciar
  o painel com o código disponível no computador.
- O aviso é consultado ao abrir o painel, inclusive em páginas não encontradas.

- Hoje inclui as tarefas abertas sem data no Quadro, na Lista e no resumo do Início.

- Projetos e Tarefas exibem vínculos existentes entre seus itens. Perguntas
  pendentes abrem o item correspondente em Entrada → Para decidir. O contrato dos agentes e o
  MCP orientam onde registrar o mapa, os próximos passos e as perguntas.

- Hábitos registra várias realizações por dia e mostra a contagem no marcador.
  A meta continua em dias, e o mapa da Lista exibe oito semanas com intensidades
  proporcionais quando há repetições.

- Pastas reúne capa, links e automações num menu de ajustes. A árvore destaca
  a pasta escolhida no grafo completo, e a simulação acomoda as notas sem empurrar
  as isoladas para um lado. Lista e Cartões preservam a navegação pelos arquivos.
- Ajustes de Pastas do painel sincroniza a lista e o catálogo ao adicionar ou
  retirar uma área. Os nomes abrem seus painéis.
- Automações usa um painel de edição lateral com regras compactas. Cabeçalhos
  das tabelas podem ser renomeados sem mudar as propriedades das notas.

- No celular, Contatos mantém a busca junto de uma barra compacta e o Início
  libera espaço junto ao dock. A aba Lista também organiza as subpastas em lista.
  Ajustes da pasta mostra as ações diretamente e abre a escolha da capa em uma
  segunda tela do mesmo modal.

- Ajustes de pasta agrupam capas e ações de arquivamento e lixeira. A nova
  visualização das subpastas funciona com notas, mídias e pastas aninhadas.
  Excluir volta à origem, e as notas de realização aparecem em uma lista
  compacta no detalhe do hábito.

- O leitor de notas oferece Voltar junto às ações: retorna à tela anterior do
  painel ou fecha a leitura interna de Pastas, preservando o grafo e a árvore.
- Ajustes da pasta oferecem Cor lisa, com a paleta existente e seletor de cor
  personalizada. Projetos e Estudos lembram separadamente a visualização da área
  e a do interior das pastas. Trocar a visão interna preserva título e controles,
  substituindo somente a apresentação das notas. O contexto MCP informa a
  organização por pastas e o vínculo das notas de apoio.
- Ajustes internos de Projetos e Estudos permitem editar o título da pasta no
  painel, preservando nomes e conteúdo dos arquivos. No celular, cartões de
  Estudos e notas em grade dentro das pastas também usam duas colunas.
- Vínculos em `projeto`, `estudo` e `habito` são reconhecidos igualmente no grafo,
  diagnóstico e MCP, com indicação de que vêm de uma propriedade da nota.
- Trocar entre Pastas, Cartões e Lista conserva a pasta aberta em Projetos e
  Estudos. Voltar retorna à área mantendo a visualização escolhida. Grupos de
  referências exibem as mesmas notas da contagem, sem repetir apoios vinculados.
  Ajustes, Nova nota e capas continuam funcionando após trocar de visão ou
  retornar das abas Humano e Máquina, sem acumular observadores da grade anterior.
- Projetos ganham a visão Pastas: cada projeto é uma pasta de vidro com arte
  gerada ou imagem própria; entrar na pasta mostra a nota do projeto e as notas
  vinculadas. Ajustes da pasta escolhem entre quatro capas nativas (Aurora,
  Brasa, Ametista, Oceano) ou uma imagem, e ligam a entrada rápida (+), que cria
  a nota em `projetos/referencias/<projeto>/` com `projeto: [[...]]`. Os ajustes
  ficam em `pastas:` no `_modulo.yaml`. Referências soltas viram pastas lisas.
- Estudos ganham a visão Cartões, simples e compacta; o status segue nas propriedades.
- Em Projetos e Estudos, Pastas, Cartões e Lista mostram as mesmas pastas e
  entrar numa delas mostra o item e suas notas. Novo cria a pasta; o texto
  opcional vira a primeira nota (primeira linha como título). Dentro da pasta,
  Ajustes e Nova nota agem na pasta. Sem ajuste, a capa nativa é escolhida pelo
  nome e não muda com a ordem. Pastas menores; duas colunas no celular; sem
  animação de entrada.
- Áreas sem descrição genérica no cabeçalho; textos óbvios retirados das telas diárias.
- O canal ao vivo numera os eventos: ao reconectar ou voltar à aba, a página só
  se atualiza se perdeu mudanças ou se o servidor reiniciou.
- Tarefas aplicam Hoje, Semana e Todas ao quadro e à lista, com controles compactos
  junto às configurações. A data de conclusão determina o histórico diário;
  a data agendada determina as tarefas abertas do período. Atrasadas continuam
  em Hoje; futuras e sem data ficam em Todas.
- Propriedades da nota abrem em painel lateral à direita. Mostrar esta nota na
  pasta destaca sua posição no grafo completo e na árvore, sem reabrir o conteúdo.
- Em Estudos, notas de referência aparecem dentro do estudo vinculado, sem lista
  avulsa na área. Nenhum arquivo existente é movido ou convertido.
- Abas ocultas liberam a conexão de eventos e conferem mudanças ao retornar.
  A virada do dia atualiza o recorte; edições pendentes continuam protegidas.
- Com o início automático ativo, o painel aberto por agentes ou scripts sem
  console passa para segundo plano e não cai quando quem o abriu termina.
  Reiniciar encerra as conexões ao vivo sem erro.

- Hábitos mostram notas de execução por data, sem criar marcações nem misturar
  essas notas com os hábitos. Referências de áreas e projetos têm visualização
  própria, preservando os estados originais e separadas dos cartões.
- No celular, Pastas abre o grafo com a árvore recolhida, botão de expansão e
  leitura na área principal. Lista permanece compacta. O leitor oferece abrir
  a nota em Pastas e grafo, em vez de abrir um aplicativo externo.

- Canais do YouTube oferece filtro opcional por termos ou frases no título em
  Mais opções, sem chave de API. Vazio preserva a coleta habitual; o limite por
  canal considera os vídeos que passaram no filtro dentro do feed recente.

- Tarefas recorrentes preservam a data de cada ocorrência mesmo com uma data
  antiga na regra, recusam dias mensais inválidos e aguardam o horário diário
  de hoje ao reabrir. Cópias antigas reconhecidas acompanham a atualização geral,
  preservando regras, notas e código personalizado, sem botão de atualização separado.

- Agenda mantém o cabeçalho compacto, sem os blocos de explicação das fontes
  e de aviso de possíveis duplicações. O diagnóstico continua disponível aos agentes.
- MCP recusa cópias acidentais entre tarefa e compromisso com mesmo título, dia e
  hora; `conexoes_agenda` informa o estado local sem rede ou segredos. A consulta
  diária reconhece intervalos e mantém tarefas com horário entre os atrasados.
- Diário permite buscar mudanças sem acentos, filtrar por autor e ação, escolher
  a data e percorrer páginas de até 80 registros. Links conectam registro, resumo
  e agenda do dia. `diario_dia` oferece a mesma consulta factual aos agentes.
- Resumo do dia pagina seções extensas em até 80 itens por vez, mantendo totais
  completos e acesso às páginas seguintes para não carregar milhares de linhas.
- Cancelar no editor da Agenda volta a fechar o formulário e mantém a confirmação
  de descarte quando há alterações; o botão do evento externo não interfere mais.

- O aviso de atualização aparece apenas com revisão publicada disponível, no
  canto inferior esquerdo. No celular, fica à esquerda do dock na mesma faixa.
- Marcadores de hábitos realizados variam a luminosidade da cor do tema, sem
  atribuir intensidade ou quantidade aos registros.

- Hábitos no celular organiza Progresso em duas colunas compactas, com botão
  grande de marcar na base dos cards e mapa de dez semanas com marcadores
  maiores. Títulos longos ficam em uma linha. A Lista mantém título e descrição à
  esquerda e o histórico de treze semanas à direita. As bordas seguem a
  personalização do usuário.

- Ajustes reaproveita cálculos de contraste e a interpretação de configurações
  idênticas, mantendo a leitura dos arquivos e a detecção de alterações externas.
  As prévias dos temas calculam apenas as paletas que serão exibidas.
- Progresso em Hábitos substitui a preferência Lista ao clicar na aba, inclusive
  ao voltar de Humano e Máquina.
- Lista de Tarefas usa um círculo para concluir e reabrir, com visto e título
  riscado. O quadro mostra concluídas de hoje por padrão e oferece Semana e Todas,
  preservando notas e histórico. A data de conclusão acompanha a mudança de status.
- Quadros atualizam a aparência de conclusão e os contadores após mover cartões.
  Subpastas conservam a visão escolhida e as listas mantêm as colunas entre páginas.

- Navegação em Pastas mantém o modo Notas ao entrar em subpastas, subir um nível
  e percorrer o histórico. Nomes de pastas na árvore abrem o conteúdo nesse modo;
  notas abrem no leitor e voltam à lista. A navegação do Grafo permanece igual.

- Grafo mantém notas legíveis ao afastar e acompanha a acomodação das forças no
  enquadramento inicial. Conexões ganham contraste e notas sem links ficam
  identificadas, com orientação quando não há ligações no recorte.

- A verificação de atualizações consulta a publicação já no primeiro acesso,
  inclusive em computadores recém ligados; o cache só é usado depois da leitura.

- Atalhos 1–9 selecionam os cards em ordem e 0 abre o menu. Início retorna à capa
  da última área acessada, inclusive pelo dock; outro clique vai ao primeiro card.
- Tarefas recorrentes usam um único exemplo e seleção de dias da semana ou do mês,
  com validação da regra e explicação da verificação diária.
- Conectar agenda assina um iCal somente para leitura, com recorrências e atualizações,
  sem criar tarefas. A importação antiga permanece identificada como legada.
- Novo em Tarefas e Projetos mostra descrição opcional. Hábitos tem editor compacto
  e descrição no corpo da nota, visível na Lista ou ao abrir o nome.
- Guias de agenda e Tailscale com passos separados; seletor visual de ícones,
  capa salva ao escolher, seleção com ações na lixeira e forças para notas sem links.
- Git de backup e diagnósticos executam sem abrir consoles auxiliares no Windows.

- Cards de Hábitos exibem o mapa completo de treze semanas diretamente, inclusive
  na Lista, com datas no hover e navegação por teclado. Marcar e Editar permanecem
  lado a lado no cabeçalho.

- Hábitos com semana compacta em quadrados, data e realização no hover ou foco;
  Marcar hoje vira um ícone junto de Editar.

- Novo contato começa com Nome, Telefone e E-mail; os dois últimos são opcionais.
  A lista usa Nome como coluna principal e oculta propriedades sem dados relevantes.
  O seletor de ações em lote tem mais espaço entre o texto e a seta.

- Ícone discreto no canto inferior quando há uma revisão nova do aplicativo.
  A atualização local pede confirmação, preserva alterações no código e reinicia
  o painel depois de instalar as dependências.

- Ações em lote compactas junto às configurações, sem deslocar a lista ao selecionar;
  filtros de Contatos com busca flexível e favoritos alinhados.
- Endereços Tailscale autorizados podem mover notas para a lixeira, inclusive em lote.
  A exclusão definitiva continua reservada ao acesso local.

- Seleção múltipla nas listas, com alteração de status, arquivamento e exclusão;
  cada nota conserva a conferência de versão e o resultado individual da ação.
- Personalização com abas independentes e cabeçalho no fluxo da página;
  formulários novos mostram o essencial e oferecem Adicionar campo +.
- Lixeira em linhas com ações por ícone, Entrada persistente à direita do dock
  e arraste com mouse no carrossel da home. Ao soltar no meio do movimento, o
  carrossel desliza suavemente até o cartão, seguindo o embalo do gesto.
- Áreas retiradas voltam ao mesmo catálogo compacto. Acesso Tailscale permite
  consultar, copiar e revogar endereços; todas as rotas consultam a permissão atual.
- Catálogo distribuído reutiliza seus metadados enquanto os arquivos não mudam,
  evitando leituras YAML repetidas ao criar cofres e acrescentar módulos.

- Contatos pessoais e profissionais com grupos, favoritos e busca; vínculo
  permanente com Clientes sem duplicar telefone, e-mail ou histórico comercial.
- Agenda nativa como acesso único aos compromissos, preservando a pasta de notas.
- Inicialização no Windows sem console adicional, confirmação real de segundo
  plano e suporte a caminhos acentuados no lançador automático.
- Exclusão explícita de notas com lixeira, restauração sem sobrescrita e limpeza
  definitiva por item, mantendo arquivos de instrução e configuração protegidos.
- Áreas retiradas disponíveis para adicionar novamente nos ajustes, preservando
  notas e personalizações. Contagens reutilizadas até uma alteração ou troca de
  dia e listas com data sem ordenação duplicada.
- Ajuda dos formulários sem deslocar os controles ao mudar o foco, preservando
  o primeiro clique em caixas de seleção e botões.

- Ativar o início automático aplica o funcionamento em segundo plano imediatamente, com reconexão e confirmação antes de liberar o fechamento do terminal; uma configuração já ativa oferece Aplicar agora.

- Backup confere nomes sensíveis em todo o histórico dos snapshots, incluindo arquivos removidos e outros pais de merges; bloqueia a criação e o envio de uma cadeia contaminada e envia apenas o hash validado.

- Grafo libera o nó após o arrasto para que as forças reajustem a posição; notas e leitor usam mais largura, inclusive para tabelas.
- Ajuda dos segredos permanece ao lado do nome; adicionar áreas prontas ou em branco nos Ajustes atualiza a lista e o dock sem sair da página nem perder escolhas.

- Busca prepara o texto no índice e limita os resultados sem perder a contagem; a janela cancela consultas ao trocar o termo ou fechar, descarta respostas antigas e permite tentar novamente após falhas.

- Comandos `status`, `parar`, `reiniciar` e `atualizar`: encontram o painel mesmo quando ele foi aberto por outro terminal, por um agente ou pelo início automático, e o encerram com calma pelo endpoint local.
- Busca flutuante por cima da página (botão de busca, Ctrl+K ou /), com resultados enquanto você digita, termo destacado e navegação pelo teclado; a página de busca completa continua disponível.
- Grafo de pastas com forças ajustáveis como no Obsidian (centrípeta, repulsão, força e distância dos links), guardadas no navegador; o realce ao passar o mouse agora transiciona suavemente, e arrastar uma nota puxa as vizinhas.
- O painel inicia com um único comando (`uv run --frozen orquestra`), que instala o ambiente sozinho na primeira vez.
- Edição de notas no próprio texto: dois cliques deixam a nota editável sem mudar a aparência (tabelas, listas e títulos continuam iguais), com passagem livre entre blocos; só os blocos alterados são reescritos no arquivo.
- MCP ganha contexto por área, panorama de pendências, revisão de schemas e possíveis duplicados, além de links e backlinks; consultas usam os arquivos do vault sem alterar notas.
- Leituras MCP retornam a versão da nota, aceita nas atualizações e perguntas para recusar alterações baseadas numa leitura antiga; ferramentas declaram se são de leitura ou escrita.
- `CLAUDE.md` criado na adoção importa também `AGENTS.orquestra.md`; um `CLAUDE.md` existente é preservado, com aviso de como incluir as regras do painel.
- Contrato de agentes reforça retomada de sessões, autoria, aprendizados com evidência e respeito à política local de vaults adotados, com captura configurável.

- Grafite com capas em tons pastel; Luz ganha modo escuro em preto absoluto; Brasa volta a ter a janela de poente como capa de assinatura.
- Cópias intactas de versões antigas dos temas no vault passam a receber a versão nova; temas editados continuam com prioridade.
- Cor de destaque ajustada ao modo mantendo o tom (sem ficar acinzentada), e amostras de Ajustes mostram a cor que de fato será usada.
- Explorador abre no grafo, mantém a árvore durante a leitura e oferece um canvas mais amplo com centralização pelas posições reais das notas.
- Imagens relativas à nota e anexos soltos no vault são reconhecidos; templates HTML têm prévia isolada com estilos inline e imagens locais ou HTTPS.
- Personalização compacta com salvar no topo, cena selecionada identificada e prévia imediata de cenas, imagens e vídeos.
- Sete temas, cada um com paletas e estilo de capas próprios: Brasa, Maré (verde-mar e coral), Noturno (cyberpunk), Azul profundo (cobalto e gelo), Terminal (fósforo), Luz (capas de dia) e Grafite (nanquim neutro).
- Cenas novas em pixel art: Código, Néon e Recife; Observatório, Jardim e Orbital redesenhadas no mesmo traço das demais.
- Escolha de capas com prévias fiéis ao que será salvo, cenas do tema primeiro, nomes acentuados e miniaturas sem serrilhado; a prévia de cada tema mostra a sua cena de assinatura.
- Coleção de imagens com uma ilustração por tema e um vídeo em loop.
- Configuração inicial com miniaturas animadas e controles compactos de aparência; abertura mais alta, centralizada e sem sobrepor os formulários.
- Sombra do carrossel mais sutil.

- Agenda com visões de mês, semana, dia e lista, filtros e edição de eventos em notas Markdown.
- Hábitos e metas semanais com marcação diária, histórico e preservação dos registros ao editar.
- Pomodoro com pausas, duração configurável e prazo preservado ao navegar na mesma aba.
- Onboarding por etapas e Ajustes separados por assunto, com variáveis guardadas fora do vault.
- Assistentes locais para GitHub privado, iCal e Tailscale, com limites de integração declarados nos guias.
- Capas em imagem/vídeo, aprovação de criativos e revisão explícita de coletores personalizados.
- Atualizações externas oferecem recarga explícita; reconexões ressincronizam páginas sem trabalho pendente.
- Transições entre páginas só são habilitadas sem preferência por movimento reduzido.
- Navegação do celular com dois atalhos, área atual e gaveta completa, sem destinos cortados.
- Criação e personalização acessíveis ao lado das abas em telas pequenas; navegação identifica a página atual.
- Reconexão ressincroniza a página, preservando rascunhos, formulários e diálogos abertos.
- Rajadas de eventos agrupam consultas de resumo e não abrem pedidos concorrentes.
- Personalização conserva alterações pendentes e recusa salvar sobre uma configuração modificada por outra aba ou pelo editor.
- Kanban preserva os totais de colunas com mais de 80 registros e bloqueia mudanças simultâneas no mesmo cartão.
- Cenas preparadas sob demanda, sem processamento contínuo em segundo plano ou com movimento reduzido.
- Contagens dispensam ordenação; renderização de Markdown após salvar sai do laço de eventos do servidor.
- Política de segurança bloqueia JavaScript inline; scripts do painel continuam servidos localmente.
- CSS e JavaScript usam hash de conteúdo na URL para renovar o cache mesmo em wheels com datas normalizadas.
- Carrossel com controles de toque maiores e slides inativos fora do foco; rótulos ARIA, links no texto e contraste do tema claro revisados com axe-core.
