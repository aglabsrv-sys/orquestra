# Histórico de mudanças

## Em desenvolvimento

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

Evidências e limites em [Revisão de lançamento](docs/revisao-lancamento-2026-11-12.md).
A versão publicada continua sendo a indicada pelo aplicativo; esta seção não representa um lançamento já feito.
