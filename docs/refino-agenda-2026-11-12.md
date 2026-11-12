# Agenda — refinamento de 12/11/2026

Referência: [Event Manager, @vaib215 / 21st.dev](https://21st.dev/@vaib215/components/event-manager),
com o prompt de componente enviado pelo usuário. O prompt foi tratado como referência
de produto; a aplicação mantém Python, Jinja e JavaScript progressivo.

## Entrega

- Visões Mês, Semana, Dia e Lista, com período, Hoje e navegação coerente por visão.
- Busca sem exigir acentos, incluindo descrição; filtros por pasta, categoria, cor,
  tag e conclusão. Filtros preservados na navegação e na URL.
- Itens sem horário separados dos eventos com hora, sem atribuir horários fictícios
  às tarefas. Cabeçalhos e a faixa Sem horário permanecem fixos na grade rolável.
- Eventos simultâneos em faixas distintas; intervalos que terminam à meia-noite
  não ocupam visualmente o dia seguinte. Navegação mensal não pula fevereiro no dia 31.
- Modal para criar/editar datas, horários, cor, categoria, tags e descrição.
- Novos eventos persistem em `agenda/itens/` com módulo criado no primeiro uso.
  Tarefas e conteúdos existentes continuam em suas próprias pastas e preservam seus
  metadados. Um diretório `agenda` incompatível não é sobrescrito.
- Reagendamento por arraste, com duração preservada, e alternativa pelo formulário
  para teclado e celular. Edição exige a versão atual do arquivo.
- Arquivamento recuperável com confirmação; não há exclusão definitiva pelo calendário.
- Troca de período/visão sem recarregar o documento inteiro, com cancelamento de
  respostas antigas, histórico de navegação, proteção do formulário e restauração de foco.
- Acesso fixo Agenda no menu, respeitando a compactação dos módulos na gaveta.
- Estilos próprios, usando variáveis dos temas. Sem dependências novas de frontend.

## Verificação

- 20 testes específicos de agenda: persistência, intervalos, sobreposição, meia-noite,
  navegação em fevereiro, busca, conflito com edição externa e escape de conteúdo.
- Na rodada de regressão, 116 testes passaram e uma expectativa antiga do dock foi
  encontrada. O teste foi ajustado para quatro módulos + cinco telas de sistema
  caberem sem gaveta; passou na repetição. O novo teste de busca também passou.
- 29 testes JavaScript existentes, Ruff e checagem de sintaxe: passaram.
- Navegador no Windows, desktop e viewport 390 × 844: quatro visões, formulário,
  gravação, edição, aplicação de filtro, arquivamento e temas claro/escuro conferidos
  com notas sintéticas em vault isolado. O reagendamento por arraste foi validado
  no backend; não houve automação de gesto de arraste na interface.
- O verificador de distribuição inclui os recursos da agenda e a criação/leitura
  de um compromisso usando o catálogo do pacote instalado.

O teste real em outro vault e no Linux continua a cargo da próxima rodada do usuário.
Não foram alterados vaults pessoais, conectadas contas externas ou publicada uma versão.
A integração iCal conserva os limites anteriores: somente leitura, sem RRULE completo
e sem sincronização bidirecional.

Uso e modelo de dados: [Agenda](agenda.md).
