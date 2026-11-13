# Links do cofre

Em **Pastas**, use **Verificar links** para conferir o cofre inteiro ou a pasta
atual. A verificação lê os arquivos já indexados e não reescreve suas notas.

- **Para revisar:** anexos ausentes, nomes ambíguos, títulos ou blocos ausentes e
  destinos indisponíveis pelas regras de acesso ao cofre.
- **Notas futuras:** referências a notas ainda não criadas. São comuns na escrita
  e ficam separadas das revisões.
- **Todos os pendentes:** as duas categorias, com as revisões primeiro.

O leitor, o grafo e o diagnóstico compartilham a resolução de wikilinks e links
Markdown locais. Ela considera a pasta da nota, caminhos relativos, aliases,
títulos (`#Seção`), blocos (`#^id`) e anexos. Links dentro de exemplos de código
não entram na verificação. URLs externas não são acessadas.

Nomes repetidos sem um destino inequívoco mostram os candidatos. Um caminho
explícito evita depender do nome de arquivo. O grafo mostra somente as notas do
recorte atual; uma ligação para fora dele pode ser válida e aparecer normalmente
no diagnóstico.

O relatório mostra a linha do **corpo Markdown**, sem contar o frontmatter YAML,
correspondendo ao texto editável no painel. O processamento é atualizado quando
as notas e os destinos mudam; não há uma tarefa agendada obrigatória.

Para integrações locais, `GET /api/vinculos` aceita `rel` (pasta relativa),
`filtro=todos|revisao|futuro` e `limite` (até 5.000 ocorrências). Os totais sempre
consideram todo o recorte, mesmo quando a lista é limitada ou filtrada.
