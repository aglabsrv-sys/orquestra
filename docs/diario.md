# Diário e registros

O Diário reúne o registro factual das mudanças nos arquivos e os relatos de
sessão dos agentes. Eles são fontes distintas: o registro mostra o que o painel
observou; um relato informa o que o agente declarou, sem comprovar sua execução.

Escolha um dia, busque pelo arquivo ou alteração e filtre por autor ou ação.
A busca não exige acentos. Cada página mostra até 80 mudanças, com os mesmos
filtros preservados ao avançar. Limpar remove os filtros sem trocar o dia.
O histórico completo continua em diario/registro/AAAA-MM-DD.md dentro do vault.

O total de mudanças e de arquivos se refere ao dia inteiro. O contador da lista
mostra quantas mudanças correspondem aos filtros. Fora do painel significa que
o arquivo foi alterado por fora; não identifica uma pessoa ou agente específico.
Mudanças só são observadas enquanto o painel acompanha o vault ou pelas operações
do MCP; o Diário não reconstrói uma atividade que não observou.

**Resumo do dia** reúne itens datados, pendências, hábitos e atividade. **Agenda do
dia** abre os itens agendados. Essas ligações usam a data selecionada, sem criar
cópias das notas. Sessões de agentes continuam disponíveis mesmo com a lista
de mudanças vazia ou filtrada.

Em dias com muitos itens, o resumo mostra até 80 por seção em cada página. Os
totais permanecem completos e a navegação ao final permite percorrer o restante.

Os relatos ficam em diario/sessoes/AAAA-MM-DD.md. Agentes devem seguir a política
local antes de registrar uma sessão e indicar o que foi feito, verificado e o que
permanece pendente. Pelo [MCP](mcp.md), `diario_dia` oferece leitura paginada e
`registrar_sessao` acrescenta o relato quando permitido.
