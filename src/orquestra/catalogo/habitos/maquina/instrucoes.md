# Hábitos e metas

Cada hábito é uma nota em `itens/`. `meta_semanal` define quantas vezes por semana
a pessoa pretende realizá-lo; `registros` contém datas ISO (AAAA-MM-DD).
Somente registre uma realização quando a pessoa confirmar que a fez.
Não crie registros para melhorar artificialmente o mapa de atividade.

Quando a pessoa pedir para guardar o treino, a leitura ou outra execução,
use `anotar_realizacao` no MCP com o hábito existente e a data em que ocorreu.
Com acesso direto aos arquivos, guarde a nota em `habitos/execucoes/<hábito>/`,
com `data: AAAA-MM-DD` e `habito: '[[caminho da nota do hábito]]'` no frontmatter.
O relato fica nessa nota. Preserve a descrição e as marcações do hábito.
