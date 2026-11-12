# Revisão para lançamento — 12/11/2026

Esta rodada corrige problemas de jornadas, segurança, documentação e apresentação.
A checagem visual completa ainda não terminou; este registro separa o que foi
observado no navegador do que foi conferido por código e testes.

## O que foi observado

O app foi aberto no Chrome com um vault sintético separado da configuração pessoal,
sem agendador, contas externas ou envio de backups. Foram obtidas capturas reais
de Hábitos em desktop (1425 × 897) e emulação de iPhone SE (375 × 667 CSS pixels).
A captura mobile tem resolução física 750 × 1334; não é um teste em iPhone físico.

As imagens abaixo registram o levantamento, **antes dos ajustes finais** de
compactação e cabeçalho:

- [Hábitos em desktop](img/revisoes/habitos-desktop-antes-2026-11-12.png).
- [Hábitos em mobile](img/revisoes/habitos-mobile-antes-2026-11-12.png).

O topo mobile cortava a trilha e deixava pouco espaço para o nome. Os cartões e o
histórico ocupavam mais altura do que o necessário. Foram ajustados truncamento,
distribuição dos controles, margens e limite de largura do mapa. O tamanho da fonte
agora também afeta os controles comuns; campos crescem com essa escolha e mantêm
alvo de toque mínimo no celular. A regra que impunha duas colunas em todos os
formulários mobile foi removida, devolvendo espaço às datas e aos horários.

A captura nativa do controle do computador falhou com `window capture timed out`.
Foi possível obter os dois registros pelo comando de captura do próprio Chrome.
Depois disso, a ferramenta encerrou o controle por não conseguir determinar a URL
atual com confiança suficiente para aplicar sua política. Nenhum novo comando de
interface foi executado após esse encerramento.

Portanto, os ajustes finais de CSS, os formulários e as demais telas **ainda não
têm aprovação visual nesta rodada**. Os prints anteriores do README foram mantidos
com sua data; não foram substituídos por imagens simuladas ou capturas antigas
apresentadas como novas.

## Correções de jornadas e código

| Problema | Comportamento corrigido |
|---|---|
| Clique no fundo fechava um formulário alterado | Botões e backdrop respeitam o evento de cancelamento e a confirmação de alterações pendentes. Clicar no espaço interno não fecha o modal. |
| Enter na busca/Pomodoro acionava o slide da home | O carrossel ignora controles interativos, teclas já tratadas e combinações com modificadores. |
| Salvar durante upload podia criar uma nota sem miniatura | O envio bloqueia o submit e os botões correspondentes; trata uploads simultâneos, falha e saída da página. |
| Ajudas e estados desapareciam em modais | Apenas dicas de campos ficam sob demanda; explicações gerais e estados de upload permanecem visíveis. |
| Marcar hábito após virar a semana conservava dias antigos | O período é remontado quando a data civil da resposta muda. A descrição acessível do dia também é atualizada. |
| Vídeo continuava após ativar movimento reduzido | A reprodução responde imediatamente à preferência e à visibilidade da aba. |
| Login GitHub não correspondia ao isolamento do backup | O push admite somente o helper oficial `gh` para HTTPS no host `github.com`; mantém bloqueados helpers herdados e hooks. Nenhum token passa pelo app. |
| Personalizar tipos de Hábitos podia converter registros | Criar, editar e marcar conferem o schema atual antes da escrita e recusam tipos incompatíveis. |
| Data extrema em nota externa podia derrubar a Agenda | Datas fora do intervalo navegável são ignoradas antes do cálculo de término. |
| Upload iniciado em outro vault podia cair no atual | A operação binária exige o vínculo do vault e reconfere confinamento na gravação, inclusive diante de junction/symlink trocado. |

## Organização e documentação

- README com navegação coerente, limites das integrações e data das capturas.
- Guias de temas, backup e módulos alinhados a tamanho da fonte, seleção de cenas,
  upload, consulta de recuperação, GitHub e módulos de Agenda/Hábitos.
- [Índice da documentação](README.md) separa guias atuais dos relatórios datados.
- CONTRIBUTING descreve validação visual com dados fictícios e evidência por fluxo.
- A CI confere destinos de links e imagens locais com um script sem dependências.
- Removidos caches descartáveis e o inventário gerado de auditoria. Ambientes,
  distribuições e trabalho útil em andamento foram preservados. Caches e saídas
  de diagnóstico ficam ignorados pelo Git.

## Gates locais

- JavaScript: **49 testes passaram**, incluindo cinco jornadas de modal/teclado/
  upload/movimento e um caso de virada de semana em Hábitos.
- Ruff e destinos de links/imagens locais passaram.
- Auditoria do `uv.lock` com `pip-audit`: nenhuma vulnerabilidade conhecida encontrada
  na consulta desta rodada. Isso não substitui revisão de lógica ou garante ausência
  de falhas futuras.
- Wheel, pacote fonte, instalação em caminho Unicode, CLI e MCP stdio passaram.
  Há criação e leitura de compromisso e criação/marcação de hábito no pacote instalado.
- Regressão Python integrada: **404 passaram, 1 ignorado**, em 428,95 segundos.
  A execução usa vaults sintéticos e não altera configurações ou dados pessoais.
- A distribuição final foi reconstruída; **132 recursos** de templates, catálogo
  e arquivos estáticos foram comparados com a fonte e estavam idênticos. O pacote
  fonte também inclui os guias e as duas capturas identificadas da revisão.

## O que falta para fechar o lançamento

1. Reabrir uma sessão de navegador controlável e conferir os ajustes finais de
   Hábitos em desktop, 375/390 px e janela estreita de 320 px.
2. Completar criação, edição, validação, cancelamento com rascunho e falha de rede
   nos formulários de Notas, Tarefas, Conteúdo, Agenda, Hábitos e personalização.
3. Conferir home, onboarding, busca, Para decidir, Diário, arquivos e todas as
   seções de Ajustes; navegação por teclado, tema claro/escuro e fonte ampliada.
4. Gerar os prints finais dessas telas a partir da versão revisada.
5. Executar a CI remota e o uso real em outro vault e em Linux. GitHub/Tailscale/
   agenda externos e início automático continuam exigindo validação no ambiente
   real; os testes locais não conectaram contas nem enviaram dados externos.

Nenhum push, merge, deploy ou publicação foi feito nesta rodada.
