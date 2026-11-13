# Preparação do Orquestra 0.4 para produção

Implementação de 11/11/2026, incorporando as melhorias locais de adoção de vaults,
áreas, aparência, automações e MCP, junto com as correções da
[revisão anterior](revisao-open-source-2026-11-11.md). Este registro descreve o
candidato corrigido; o relatório anterior permanece como evidência histórica.

## Segurança e integridade

| Achado anterior | Implementação e evidência |
|---|---|
| C1: acesso fora do vault | `caminhos.py` centraliza validação. Scanner, domínio, preparo, temas, diário, HTTP e MCP recusam links/junctions, traversal e caminhos externos. A troca da própria raiz também é recusada. Testes Windows usam junctions reais e marcadores externos. |
| C2: execução por vault importado | Confiança local por assinatura de código, auxiliares, configuração e chaves declaradas. Mudanças revogam aprovação; execução usa snapshot dos arquivos aprovados, ambiente mínimo, limites de saída/tempo e encerramento de filhos. Código aprovado continua com as permissões da conta; não é sandbox. |
| C3: perda em gravações concorrentes | Temporários exclusivos, locks entre processos, precondições e criação/movimentação sem sobrescrever destino. Atualização captura o arquivo efetivamente deslocado para recuperação, inclusive na última janela de disputa. API exige versão para editar/arquivar. |
| I1: encoding e formatação | UTF-8 inválido, ciclos, limites excessivos e números não finitos bloqueiam gravação. BOM, comentários, frontmatter vazio e bytes das partes não editadas, inclusive quebras mistas, têm regressões. |
| I2: histórico/segredos | Histórico Git com aprovação própria, índice separado e ref `refs/orquestra/backups`; HEAD e staging do usuário são preservados. Primeiro snapshot não carrega ancestrais antigos do HEAD. Hash de bytes sem filtros, exclusões mescladas e bloqueio de segredos rastreados. `.git` vinculada ou contendo redirecionamentos é recusada antes de executar Git. Tentativa, falha e sucesso são estados distintos. |
| I3: configuração e entrada | Contratos JSON estritos, limites e mensagens legíveis. YAML inválido não é normalizado e regravado; a interface conserva a última configuração válida, enquanto mutações que dependem do schema inválido são recusadas. |
| I6: operação local | Host e Origin exatos; bootstrap com credencial temporária entregue apenas na conexão local direta. Selecionar/criar/trocar vault e aprovar scripts ou Git exigem essa capacidade. Proxy/headers encaminhados não comprovam localidade. |
| I7: início automático | Plist gerado com `plistlib`, escape específico dos formatos e verificação de retorno. Testes de formatos/caminhos passaram; login real macOS/Linux continua pendente. |
| I9: diagnóstico | Teste de escrita usa temporário exclusivo; não substitui nem remove um arquivo anterior com nome fixo. |

Uma nota removida durante edição produz conflito; o rascunho pode virar outro
arquivo, preservando o caminho removido. Cópias de recuperação mantêm os bytes
originais. A interface vincula mutações ao identificador do vault da aba, evitando
gravar no vault recém-selecionado por uma aba antiga. Clientes próprios da API
devem enviar `X-Orquestra-Vault`, obtido em `/api/resumo`, além das versões das notas.

As primitivas de publicação dependem do sistema de arquivos: Windows usa
[ReplaceFileW com cópia do arquivo deslocado](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew);
Linux usa [renameat2 com exchange/noreplace](https://man7.org/linux/man-pages/man2/renameat2.2.html);
macOS usa renamex_np com swap/exclusividade. A Apple documenta a
[capacidade de swap do volume](https://developer.apple.com/documentation/foundation/urlresourcekey/volumesupportsswaprenamingkey).
Unidades sem a operação necessária falham com orientação, sem fallback que
sobrescreveria sem preservar a versão anterior. Fsync é usado onde disponível;
não foi simulado desligamento físico ou falha do dispositivo.

## Desempenho e arquitetura

O índice usa parsing seguro para leitura, com fallback compatível para extensões
YAML; mutações releem o arquivo com round-trip. Objetos do índice são explicitamente
somente leitura. Consultas por área/zona e wikilinks têm índices auxiliares; a
assinatura de sincronização usa metadados de uma leitura estável, com retry em
disputas. Links ambíguos não escolhem uma nota arbitrariamente.

Listas, busca, pastas e decisões têm paginação no servidor. O Kanban prepara
somente os cartões exibidos. Parsing, gravações e renderizações pesadas ficam
fora do loop de eventos, com coordenação do estado do vault.

O watcher usa um único emissor de polling com enumeração podada, em vez de uma
thread por pasta. Compara metadados a cada 0,75 s, sem ler todos os corpos das
notas. Debounce, teto de espera e lotes limitam rajadas; eventos SSE atravessam
threads corretamente e sinalizam ressincronização em overflow. Os testes incluem
mil pastas visíveis, mil pastas ignoradas, mudanças reais no disco e troca por link.

Medições exploratórias no Windows, Python 3.12.14, notas idênticas de 1.024 bytes
com seis campos, duas cargas por tamanho e seis GETs aquecidos por rota:

| 10 mil notas | Antes | Candidato corrigido |
|---|---:|---:|
| Carga inicial, mediana | 17,03 s | 17,68 s |
| Sincronização sem mudanças | 568 ms | 679 ms |
| GET lista aquecido | 960 ms | 141 ms |
| GET quadro aquecido | 403 ms | 163 ms |
| Renderizar 100 wikilinks | 284 ms | 3,67 ms |
| HTML da lista | 4,71 MB, todos os itens | cerca de 49 KB, uma página |

O ganho de navegação decorre principalmente da paginação e da redução de trabalho
por cartão. Não é uma comparação de renderizar os mesmos dez mil itens de uma vez.
A carga inicial anterior variou de 13,38 a 20,68 s; cache do SO e tarefas concorrentes
influenciam o tempo de parede. O CPU da carga cresceu de 13,82 para 17,62 s, e a
sincronização ficou mais lenta pelas validações adicionais. Não há promessa de
equivalência estatística, latência universal ou ganho em todas as operações.
RAM, anexos grandes, discos de rede e sincronizadores não entraram nesse benchmark.

## Experiência e manutenção

- Pedidos de gravação por nota são serializados. Erros pausam a fila e mantêm
  indicação de alterações pendentes, retry e opções de cópia/recuperação.
- Rascunhos são separados por vault, nota e sessão; cópias incluem metadados
  ocultos. Armazenamento indisponível no navegador gera aviso visível.
- Histórico local tem consulta de versões e criação de cópia sem substituir a
  nota atual. Recuperação e respostas usam controles HTML com foco e labels.
- Botões no mobile têm nome acessível; diálogos/editores são identificados e a
  ordenação da página da tabela pode ser acionada por teclado.
- `CONTRIBUTING.md`, `SECURITY.md`, `.env.example`, ignores e documentação de
  instalação, confiança, backup, limitações e arquitetura foram acrescentados
  ou atualizados. A licença MIT e as demonstrações existentes foram preservadas.
- Ruff verifica `E9` e todas as regras Pyflakes. Contratos e limites vivem em
  módulos próprios; duplicações que permitem coletores independentes foram
  mantidas deliberadamente, sem uma reescrita desnecessária do projeto.

## Verificações executadas e limites

- Suíte integrada da implementação: **287 testes passaram e 1 foi ignorado no
  Windows**, em 196,74 s. O skip é do caso de symlink de arquivo Unix; junctions
  de diretório Windows foram realmente executadas. O candidato também deve ser
  testado no clone do commit consolidado, conforme o processo abaixo.
- **7 testes Node passaram**, cobrindo fila, falhas, rascunhos, metadados de cópia
  e isolamento de protótipos. Ruff, compilação Python e consistência do lock passaram.
- Wheel e sdist da implementação foram instaladas em ambientes novos com
  **Python mínimo 3.11.16**; recursos, perfis, criação de vault, Hospedeiro e MCP
  passaram. O script `scripts/verificar_pacote.py` repete esse smoke para ambas.
- Pip-audit consultou **37 dependências de runtime**, sem vulnerabilidades
  conhecidas nem pacotes ignorados. Esse resultado não cobre novas resoluções
  futuras ou código de coletores que a pessoa instalar separadamente.
- Gitleaks verificou a árvore candidata com valores redigidos e não encontrou
  segredos. O histórico alcançável deve ser escaneado novamente após o commit.
- No navegador foram confirmados primeiro uso com capability, criação de vault
  com Git, gravação e consulta dos bytes da versão anterior. A automação visual
  foi interrompida pelo controle de navegação no diálogo nativo; ele foi depois
  substituído por HTML. Cópia/restauração foi validada por API, e os controles
  novos ainda precisam de uma passagem visual completa.

A CI foi adicionada para Windows/macOS/Linux, Python 3.11 e 3.13, com lint, testes,
Node, empacotamento, dependências e scanner de histórico. Ações estão fixadas em
SHA e credenciais de checkout não são persistidas. **Configurar a CI não equivale
a executá-la:** runners externos, macOS/Linux reais, Tailscale Serve real, login
automático e uma sessão real do Obsidian não foram validados nesta máquina.

Para conferir o candidato final, use um clone limpo do seu commit e execute:

```bash
uv sync --frozen
uv run --frozen ruff check src tests scripts
uv run --frozen python -m pytest -q
node --test tests/js/notas-seguras.test.cjs
uv build
uv run --frozen python scripts/verificar_pacote.py dist
```

As versões de recuperação ficam no mesmo computador, fora do vault, e não são
removidas automaticamente. Acompanhe espaço livre e mantenha backup externo
privado. Locks do aplicativo não obrigam Obsidian/sincronizadores a cooperar;
prefira não editar a mesma nota simultaneamente em várias máquinas. Nenhum teste
desta implementação usou notas, credenciais ou remotos reais do usuário.
