# Histórico de mudanças

## Em desenvolvimento

- Explorador abre no grafo, mantém a árvore durante a leitura e oferece um canvas mais amplo com centralização pelas posições reais das notas.
- Imagens relativas à nota e anexos soltos no vault são reconhecidos; templates HTML têm prévia isolada com estilos inline e imagens locais ou HTTPS.
- Personalização compacta com salvar no topo, cena selecionada identificada e prévia imediata de cenas, imagens e vídeos.
- Sete temas, cada um com paletas e estilo de capas próprios: Brasa, Maré (verde-mar e coral), Noturno (cyberpunk), Azul profundo (cobalto e gelo), Terminal (fósforo), Luz (capas de dia) e Grafite (nanquim neutro).
- Cenas novas em pixel art: Código, Néon e Recife; Observatório, Jardim e Orbital redesenhadas no mesmo traço das demais.
- Escolha de capas com prévias fiéis ao que será salvo, cenas do tema primeiro, nomes acentuados e miniaturas sem serrilhado; a prévia de cada tema mostra a sua cena de assinatura.
- Coleção de imagens com uma ilustração por tema e um vídeo em loop.
- Configuração inicial com miniaturas animadas e controles compactos de aparência; abertura mais alta, centralizada e sem sobrepor os formulários.
- Sombra do carrossel mais sutil; documentação de uso reorganizada e capturas renovadas.

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
- Roteiro Chromium, benchmark sintético, capturas atualizadas e guia de lançamento.
- CI sem execução duplicada entre branch e PR; scanner de segredos com a leitura de commits do PR declarada no próprio job.

Evidências e limites em [Sincronização e revisão da comunidade](docs/sincronizacao-comunidade-2026-11-12.md)
e [Revisão de lançamento anterior](docs/revisao-lancamento-2026-11-12.md).
A versão publicada continua sendo a indicada pelo aplicativo; esta seção não representa um lançamento já feito.
