# Histórico de mudanças

## Em desenvolvimento

- Seleção múltipla nas listas, com alteração de status, arquivamento e exclusão;
  cada nota conserva a conferência de versão e o resultado individual da ação.
- Personalização com abas independentes e cabeçalho no fluxo da página;
  formulários novos mostram o essencial e oferecem Adicionar campo +.
- Lixeira em linhas com ações por ícone, Entrada persistente à direita do dock
  e arraste com mouse no carrossel da home.
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
