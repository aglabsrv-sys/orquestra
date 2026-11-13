# Foco, hábitos e desempenho — 12/11/2026

## Produto e jornadas

- A home não contém mais a barra de Pomodoro. O ícone de cronômetro ao lado da
  busca abre uma página dedicada, com mostrador SVG, marcações, anel de progresso,
  indicador móvel, etapas e quatro indicadores de ciclo.
- Os ajustes de duração usam controles de incremento e campos numéricos em um
  modal. O aviso sonoro é opcional. Reiniciar ou trocar uma etapa ativa exige
  confirmação; nenhuma próxima etapa começa sem ação da pessoa.
- O timer usa um prazo absoluto, guardado por vault e aba. Continua correto ao
  navegar, recarregar ou voltar de uma suspensão. Não mantém atualizações visuais
  quando está parado ou com a aba oculta. Fechar a aba não cria um serviço de
  notificação em segundo plano.
- Hábitos é um módulo de verdade em `habitos/`, com entradas no menu e na home.
  O endereço anterior redireciona para o módulo. Criar o primeiro hábito prepara
  a pasta sem exemplos de realizações e sem substituir estruturas incompatíveis.
- Progresso reúne meta semanal, sete indicadores dos dias e mapa de treze semanas.
  Lista oferece a alternativa compacta. Novo/Editar usa um modal com meta de
  1 a 7 dias e modelos de Academia, Leitura e Caminhada.
- Marcar/desmarcar hoje, criar e editar atualizam cartões e contadores sem
  recarregar o documento. A primeira ativação do módulo abre a página completa
  para atualizar também a navegação. Edições preservam registros e metadados.
- Toda gravação exige a versão atual da nota. Registros malformados são recusados
  ao marcar; datas futuras não contam para a realização da semana.

Uso e limites: [Pomodoro e hábitos](../foco-e-habitos.md).

## Desempenho

O custo mais evidente estava nos Ajustes: todas as seções consultavam Git,
backup, temas e coletores, mesmo quando esses dados não apareciam na tela.
Cada página agora monta apenas o contexto que exibe. Informações de confiança
continuam sendo consultadas na origem, sem um cache que esconda alterações.

Outras mudanças:

- Eventos de arquivos agrupam pedidos dos contadores em uma janela de 180 ms.
  Há somente uma requisição em andamento; mudanças durante a requisição pedem
  uma leitura posterior. Uma rajada não inicia um pedido por arquivo.
- Contagens e agenda percorrem o índice sem ordenar por título quando a ordem
  não é usada. Visões que precisam dessa ordenação continuam usando-a.
- O motor das cenas deixa de agendar quadros quando não há cena visível ou vídeo
  de fundo em reprodução. Sai do laço na aba oculta e respeita movimento reduzido.
- Alterações externas oferecem atualização explícita, preservando foco,
  rolagem e formulários. As gravações da própria página são identificadas para
  evitar avisos de novidade desnecessários.

### Medições indicativas

Windows, mesma máquina, vaults sintéticos com 100, 1.000 e 5.000 notas.
Requisições locais via `TestClient`, sem vigia ou agendador. São tempos de resposta
do servidor, incluindo renderização do HTML; não medem rede, pintura, FPS ou
Core Web Vitals. A rodada inicial usou três amostras por rota, incluindo o primeiro
acesso; a rodada final usou cinco após um acesso de aquecimento. As medianas
servem como diagnóstico local, não como garantia de desempenho em outro computador.

| Notas | Rota | Antes (ms) | Depois (ms) |
|---:|---|---:|---:|
| 100 | Ajustes / Painel | 304,81 | 4,63 |
| 1.000 | Ajustes / Painel | 298,01 | 6,98 |
| 5.000 | Ajustes / Painel | 355,99 | 15,38 |
| 100 | Ajustes / Aparência | 298,09 | 69,32 |
| 1.000 | Ajustes / Aparência | 293,46 | 71,11 |
| 5.000 | Ajustes / Aparência | 323,42 | 79,12 |
| 5.000 | Home | 48,59 | 35,34 |
| 5.000 | Agenda | 96,09 | 83,40 |
| 5.000 | Contadores (`/api/resumo`) | 27,24 | 20,68 |

Na última rodada, a inicialização do índice de 5.000 notas levou aproximadamente
8,1 segundos. Ela ainda lê o vault na abertura; esta revisão não implementa um
índice persistente nem promete abertura instantânea de vaults grandes.

## Verificação e limites

- Regressão Python: **389 passaram, 1 ignorado**. Depois dos últimos ajustes,
  repetição dos testes de hábitos, incluindo recusa de registros escalares.
- **43 testes JavaScript passaram**, incluindo prazo do timer, pausa, suspensão,
  retomada no dia seguinte, quatro ciclos, agrupamento de eventos e animações ociosas.
- Ruff, sintaxe JavaScript e validação das páginas de foco, hábitos e agenda passaram.
- Wheel e fonte instalados em ambientes novos; CLI, catálogo e MCP stdio conferidos.
  A verificação inclui recursos estáticos de foco/hábitos, criação de compromisso
  e criação/marcação de hábito usando o pacote instalado.
- Chrome no Windows: as páginas de Pomodoro e Hábitos foram abertas em vault
  sintético e sua estrutura foi conferida pela árvore de acessibilidade. A captura
  de tela falhou no ambiente desta rodada; a aparência final e as interações em
  desktop/celular ainda precisam de conferência visual. Não houve validação
  em dispositivo físico nem em Linux nesta rodada.

As alterações são locais. Nenhuma publicação, conexão de conta externa ou mudança
em vault pessoal foi feita nesta validação.
