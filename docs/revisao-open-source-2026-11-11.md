# Revisão antes do lançamento open source — Orquestra

> Registro histórico da análise anterior às correções. A implementação posterior
> e suas verificações estão em [Preparação para produção](preparacao-producao-2026-11-11.md).

Data: 11/11/2026. Candidato analisado: **árvore de trabalho 0.4.0**, incluindo alterações locais e arquivos novos. Referência Git: `0c8313b` (HEAD contém 0.3.0; quatro commits alcançáveis pelas refs locais).

**Parecer: corrigir os três achados críticos antes do lançamento para uso com notas reais.** Há reproduções de leitura/escrita fora do vault, execução de código ao abrir um vault não confiável e perda de alterações concorrentes. Portanto, o estado atual **não sustenta a garantia de que nenhuma nota será apagada, sobrescrita ou corrompida**.

A revisão não alterou o código do produto, o histórico Git ou vaults reais. Instalações, experimentos destrutivos e navegação usaram ambientes e notas sintéticos em diretórios temporários. Este relatório é a entrega da revisão, não a implementação das correções.

## Critérios de prioridade

- **Crítico:** quebra a fronteira de acesso a arquivos/código ou pode perder alterações do usuário. Bloqueia a recomendação de lançamento.
- **Importante:** afeta recuperação, confiabilidade, escala, compatibilidade ou a capacidade de reproduzir a versão publicada. Resolver antes de anunciar as respectivas garantias.
- **Desejável:** melhora manutenção, colaboração e experiência; pode ser organizado em etapas posteriores, salvo se fizer parte da promessa pública.

## Verificações e resultados

| Verificação | Resultado efetivamente observado |
|---|---|
| Suíte na árvore atual | **125 testes passaram**, 100,41 s nesta execução |
| Suíte em snapshot isolado | **125 testes passaram**, 99,71 s |
| Instalação com cache de pacotes vazio | `uv sync --frozen` passou no Windows, Python 3.12.14 |
| Empacotamento | sdist e wheel 0.4.0 construídos; recursos do catálogo, modelos, static, templates e licença presentes |
| Instalação da wheel fora da fonte | Passou com Python mínimo 3.11.16; CLI, criação de vault, doctor e construção do servidor MCP funcionaram |
| Clone limpo do HEAD local | Instala e executa, mas entrega **0.3.0**, não o candidato 0.4.0 analisado |
| Vulnerabilidades de dependências | pip-audit 2.10.1: **46 dependências do lock, zero vulnerabilidades conhecidas, zero pacotes ignorados** |
| Segredos no Git | Gitleaks 8.30.1: **quatro commits alcançáveis por todas as refs locais, zero achados** |
| Segredos na árvore atual | Scanner incluiu fontes tracked/untracked, docs e testes: zero achados após excluir um hash de cache gerado pela própria análise, confirmado como falso positivo |
| Navegador | Chrome no Windows: primeiro uso, criação de vault, navegação, captura e conflito de edição; desktop e viewport 390 × 844 |
| Convivência com edição externa | Edição sintética no disco acionou aviso; tentativa normal de salvar retornou conflito e preservou o rascunho no navegador |
| Segurança de caminhos | Junctions Windows reproduziram leitura por HTTP/MCP e escrita fora do vault |
| Código em vault importado | Coletor ativo executou sem gate de confiança e recebeu chave sintética não declarada |
| Concorrência | Interleavings controlados reproduziram perda de edição, sobrescrita na criação e sucesso com conteúdo diferente no disco |

Não houve instalação do próprio uv/git em sistema recém-formatado. O ambiente da aplicação e o cache de pacotes foram isolados; o interpretador 3.12 já estava disponível no host, e o 3.11 foi baixado para o ensaio. macOS, Linux, Tailscale real, login automático, leitor de tela e o aplicativo Obsidian não foram executados. As medidas de performance são exploratórias, desta máquina, com uma execução por tamanho e outras atividades concorrentes.

## Críticos

### C1 — Algumas leituras e escritas escapam do vault por junctions/links

**Onde:** `src/orquestra/indice.py:61`, `:85`; `modulos.py:236`; `painel.py:128`, `:249`, `:585`, `:607`, `:620`. A proteção canônica existente em `painel.py:65` não é aplicada universalmente.

**Prova:** uma junction `vault/external -> outside` fez `GET /n/external/private.md` responder **200 com conteúdo externo**, também acessível por `Ferramentas.ler_nota` no MCP. Outra junction em `tarefas/itens` fez a criação de nota gravar na pasta externa. O validador `caminho_seguro` recusou explicitamente o mesmo destino quando chamado diretamente: o problema é a cobertura incompleta desse controle.

**Impacto:** o painel e agentes podem ler conteúdo fora da pasta escolhida e criar/mover arquivos fora dela. Um vault legítimo com links de pastas já pode acionar o problema, sem atacante remoto. A prova executada usou junctions Windows; symlinks Unix e troca de link durante a operação ainda exigem testes próprios.

**Ação:** centralizar a política de caminhos e usá-la antes de toda descoberta, leitura, cópia, criação, append e rename, inclusive configurações, diário, temas, módulos e coletores. Rejeitar links para fora e validar o pai existente de destinos novos; tratar também mudanças de link entre validação e uso.

**Aceitação:** HTTP, MCP, criação, arquivamento, aprendizados, sessões e preparo recusam `..`, absolutos e links/junctions externos, sem ler nem alterar o marcador externo. Cobrir Windows e Unix.

### C2 — Abrir um vault de terceiros pode executar Python e disponibilizar credenciais locais

**Onde:** `hospedeiro.py:72`; `agenda.py:29`, `:61`; `coletores.py:50`, `:64`, `:87`; `modulos.py:214`.

O próprio `_modulo.yaml` recebido define `ativo: true` e o script. O laço inicia a verificação depois de cinco segundos. Sem execução anterior, `devido` retorna verdadeiro mesmo antes de conferir se há um agendamento. Não há registro de confiança local separado dos dados recebidos. O subprocesso herda o ambiente do processo e todas as chaves carregadas de `.env`, independentemente de `requer`. Caminho absoluto de script externo também foi aceito.

**Prova:** um vault sintético foi aberto por `Hospedeiro.abrir`; a rotina real `agenda.verificar` executou seu coletor sem aceite. O script criou somente um marcador sintético e confirmou a presença de uma chave fictícia não declarada. A verificação foi chamada diretamente, sem esperar o temporizador; o delay do laço foi conferido no código.

**Distinção:** executar scripts próprios é uma capacidade intencional; os coletores do catálogo vêm desativados. A falha é tratar a abertura de dados importados como autorização para executar código e acessar credenciais. Não foi demonstrado ataque vindo apenas de uma página externa.

**Ação:** suspender execução na primeira abertura/importação; registrar confiança fora do vault e apresentar scripts/permissões/chaves para aceite. Vincular a confiança ao código/hash e invalidá-la quando mudar. Confinar a localização do script e transmitir apenas as variáveis e chaves autorizadas. Restringir caminho não cria sandbox: Python continua com as permissões do usuário.

**Aceitação:** abrir/adotar vault não confiável não executa código; alteração de script revoga confiança; coletor não recebe chaves não autorizadas.

### C3 — Escrita atômica atual não impede perda em operações concorrentes

**Onde:** `notas.py:155`, sobretudo `:170–193`; `config.py:49`; `painel.py:282`, `:249`; `servidor.py:542`.

Todos os escritores de um arquivo usam o mesmo temporário `.NOME.orq-tmp`. O hash é conferido antes da escrita/troca, sem coordenação entre processos. `criar=True` faz `exists()` antes de `os.replace`, sem exclusividade real. Painel e MCP podem ser processos separados; o Obsidian não participa de uma eventual trava interna.

**Provas com interleaving controlado nas funções reais:**

1. A e B leem a mesma versão; A grava temporário, B o substitui, A faz o replace. **A recebe sucesso e hash de A, mas o disco contém B; B recebe FileNotFoundError.**
2. Escrita externa inserida depois da checagem do hash é sobrescrita, com sucesso reportado.
3. Arquivo criado por outro escritor depois do `exists()` é sobrescrito por `criar=True`.
4. Nota removida depois da leitura pode ser recriada ao salvar: a precondição só é comparada quando o arquivo ainda existe.

A API também permite editar sem `versao`; o frontend normal envia a versão, mas o contrato de outros clientes pode ignorar a proteção.

**Ação:** temporário exclusivo no mesmo diretório, coordenação dos escritores do Orquestra entre processos, criação exclusiva e versão obrigatória nas edições. Tratar remoção/rename como conflito. Preservar versões/preimagens e oferecer recuperação em disputas com escritor externo; apenas trocar o nome do temporário ou acrescentar um segundo hash não elimina toda a corrida com o Obsidian. Aplicar a disciplina também a YAML/estado e ao destino do arquivamento.

`os.replace` é uma base útil para publicar um arquivo inteiro, mas não é uma operação condicional pela versão anterior; `mkstemp` oferece criação segura de temporários exclusivos. Referências: [Python: os.replace](https://docs.python.org/3/library/os.html#os.replace), [Python: tempfile.mkstemp](https://docs.python.org/3/library/tempfile.html#tempfile.mkstemp).

**Aceitação:** ensaios painel + MCP + escritor externo preservam os conteúdos envolvidos, nunca confirmam hash diferente do conteúdo publicado, não sobrescrevem uma criação concorrente e não ressuscitam silenciosamente nota removida.

## Importantes

### I1 — Encoding e frontmatter vazio permitem alteração destrutiva silenciosa

**Onde:** `notas.py:113–130`, `:146–152`.

`decode('utf-8-sig', errors='replace')` aceita bytes inválidos sem bloquear edição. Numa nota sintética com byte `0xe9`, alterar somente um campo regravou o corpo com `U+FFFD`, perdendo o byte original. Um frontmatter contendo apenas comentário perdeu comentário e delimitadores até numa gravação sem alteração; BOM também não é preservado.

**Ação:** leitura estrita ou modo explicitamente somente leitura para encoding não suportado; preservar existência e conteúdo do frontmatter vazio/comentado. Testar byte a byte BOM, CRLF, comentários, encoding inválido e delimitador incompleto. Corrigir antes de prometer preservação integral de notas adotadas.

### I2 — Backup pode incluir segredos ou informar ausência de mudanças após falhar

**Onde:** `backup.py:53–77`; `painel.py:366–376`; `agenda.py:47`.

- `.gitignore` preexistente fica sem as regras de proteção do Orquestra. Em repositório sintético, um `.env` marcador foi incluído no commit. Ignore novo também não retira arquivo já rastreado.
- `git add -A` usa o índice normal do usuário e ignora o retorno. Com `index.lock`, `commit` retornou **`nada`**, embora a nota nova não tivesse sido salva no histórico. Staging parcial do usuário também pode ser absorvido.
- `ultimo_commit` e `ultimo_push` recebem horário mesmo após falha; o envio diário pode esperar até o próximo dia. Uma tentativa não deve aparecer como sucesso.
- Git local não cobre perda do disco nem alterações ainda não commitadas. Não existe ensaio automatizado completo de restauração/remoto na suíte. Adoção mantém histórico desligado por padrão, decisão adequada, mas a ausência de proteção precisa ficar visível.

**Ação:** conferir cada retorno de Git, separar tentativa/sucesso/falha e fazer retry; preservar regras existentes enquanto acrescenta exclusões; detectar sensíveis já rastreados; evitar interferir no staging do usuário. Testar commit + restauração e push para remoto bare local, além de lock, timeout e falha. A privacidade de um remoto real não foi validada.

### I3 — YAML com tipos errados derruba o carregamento; API pode retornar 500 genérico

**Onde:** `modulos.py:131–168`, `:214–245`; `config.py:41`; `painel.py:489–580`; `servidor.py:627`.

**Provas:** `_modulo.yaml` com `campos: [um, dois]` gera AttributeError; `coletores: [{script: rss.py, config: 12}]` gera TypeError. O tratamento cobre erro de parsing, mas não todos os tipos da estrutura, e a descoberta do painel inteiro pode falhar por um módulo defeituoso. Pela API, `PUT /api/modulos/tarefas` com `{"campos":1}`, `{"remover":1}` ou opções numéricas retornou **500 text/plain**.

**Ação:** validar schemas de entrada e arquivos, responder 400/422 com orientação em português e isolar módulos defeituosos. Preservar última configuração válida durante uma gravação externa transitória. Não descartar ou regravar silenciosamente configuração ilegível. Testar recuperação depois de corrigir o arquivo.

### I4 — Inicialização, listas e MCP precisam de limites para vaults grandes

**Onde:** `indice.py:61–116`; `mcp_servidor.py:60`; `servidor.py:186–295`; resolução de links em `indice.py`.

Notas sintéticas de 1.066 bytes, um módulo, Windows, sem watcher/agendador no benchmark:

| Notas | Carga inicial do índice | Sync sem mudanças | Busca no corpo | GET Kanban | GET Lista | HTML Lista |
|---:|---:|---:|---:|---:|---:|---:|
| 1.000 | 1,421 s | 0,064 s | 0,0029 s | 0,089 s | 0,037 s | 245.765 B |
| 5.000 | 10,387 s | 0,362 s | 0,0174 s | 0,186 s | 0,196 s | 1.197.765 B |
| 10.000 | 14,333 s | 0,621 s | 0,0265 s | 0,281 s | 0,520 s | 2.387.767 B |

Todos os GET retornaram 200. O cache do disco influenciou as medidas; não são percentis, SLO ou previsão para outros computadores. RAM, DOM de 10 mil linhas e anexos pesados não foram medidos.

A busca em memória foi rápida. Os custos mais claros estão no parsing inicial, varredura/stat de todas as notas antes de cada ferramenta MCP, listas sem paginação e construção de todos os cartões antes de limitar o Kanban a 80 por coluna. Resolver muitos wikilinks varre o índice repetidamente. Rotas async e callbacks executam trabalho síncrono que pode bloquear outras requisições.

**Ação:** paginação real de lista/pastas/decisões; montar somente cartões exibidos; índices auxiliares para links/áreas; eliminar recargas MCP duplicadas; retirar I/O pesado do loop preservando a sincronização do estado. Medir RAM e latência concorrente com 10 mil+ notas, anexos e disco lento.

### I5 — Watcher tem exclusões inconsistentes e debounce sem limite de espera

**Onde:** `vigia.py:18`, `:38–41`, `:54`, `:66–82`; `indice.py:20–33`; `diario.py:90`.

O Observer observa a árvore inteira; excluir eventos depois não evita custo de observação. `node_modules`/`.venv` são ignorados pelo índice, mas não pelo filtro inicial do watcher. Cada evento reinicia o timer global de 350 ms: um fluxo contínuo pode adiar o lote indefinidamente. Rename/delete de diretório refaz tudo no loop. O diário lê o registro inteiro para examinar só suas últimas linhas. A pressão de watches inotify no Linux é um risco por inspeção, ainda não medido em Linux real.

**Ação:** unificar exclusões, limitar diretórios observados, impor latência máxima e orçamento por lote, ler cauda do diário e executar rescan pesado fora do loop. Testar watcher real com salvamento temporário + rename, rajadas contínuas, remoção/rename de pasta e recuperação de eventos perdidos.

### I6 — Autorização de operações “só no computador” depende do Host

**Onde:** `boasvindas.py:39–41`, `:60–62`; `seguranca.py:34–86`.

Cliente ASGI simulando endereço remoto recebeu 403 com Host Tailscale e 200 com Host/Origin localhost ao analisar a mesma pasta sintética. Isso demonstra que o código valida um cabeçalho, não a identidade/localidade da conexão. **Não demonstra exploração pelo Tailscale Serve real.** O bind normal em 127.0.0.1 impede conexão TCP direta da LAN; nenhuma exposição pública foi constatada.

**Ação:** credencial/capability local para selecionar/criar/trocar vault e distinção explícita de proxy confiável. Testar configuração real do Serve e cabeçalhos personalizados. Preferir hosts exatos a permissões amplas `*.ts.net`; não confiar indiscriminadamente em forwarded headers. Não basta verificar o IP de loopback quando há proxy local.

### I7 — Autostart macOS gera XML inválido e pode anunciar sucesso sem funcionar

**Onde:** `autostart.py:44`, `:67–68`.

`_conteudo(Path('/Users/alice/P&D'))`, com plataforma macOS simulada, falhou em `plistlib.loads`: XML inválido por `&` sem escape. O retorno de `launchctl load` é ignorado. O teste não criou item de login e não executou macOS real.

**Ação:** gerar plist com `plistlib`, verificar o carregamento e só então anunciar sucesso. Validar `.desktop` Linux e VBS Windows com espaços, acentos, aspas, `&` e `%`. Confirmar ativar/desativar em login real nas três plataformas; no README manter as limitações enquanto não houver essa evidência.

### I8 — O candidato auditado precisa virar um commit reproduzível e ganhar CI

**Onde:** estado Git; `pyproject.toml:3`; README; ausência de workflows `.github`.

O snapshot incluiu 64 arquivos novos ainda não rastreados, entre código, recursos e documentação, além de dois testes novos. O clone limpo local do HEAD instala **0.3.0**; a árvore auditada é **0.4.0**. Logo, os resultados do snapshot não aprovam automaticamente o futuro commit publicado.

**Ação:** após as correções, formar commit/tag completos, repetir instalação e verificações nesse exato candidato, e publicar instruções correspondentes. Adicionar CI Windows/macOS/Linux com Python mínimo 3.11 e versão estável escolhida, smoke de sdist/wheel e testes das fronteiras relevantes. Ausência de CI não invalida as verificações locais feitas, mas deixa regressões sem gate automático.

### I9 — O diagnóstico de escrita pode apagar um arquivo preexistente

**Onde:** `doctor.py:81–83`.

`doctor` escreve `ok` no nome fixo `.orquestra-teste.orq-tmp` e o remove. Reprodução em pasta temporária: um arquivo preexistente com esse nome desapareceu depois de `verificar_vault`. É um nome reservado e pouco provável para uma nota, mas um diagnóstico não deve destruir conteúdo anterior.

**Ação:** temporário exclusivo, criado de forma segura, removendo somente o arquivo desta operação. Cobrir colisão e link no caminho de teste.

## Desejáveis

### D1 — Completar os materiais de colaboração e segurança

README explica produto, instalação, uso, comandos e limitações; LICENSE MIT e prints estão presentes. Faltam `CONTRIBUTING.md`, `SECURITY.md` e `.env.example`. O básico roda sem chave, e o preparo gera um modelo externo: a ausência do exemplo no repositório não bloqueia a instalação.

Adicionar instruções curtas de desenvolvimento/PR, política de preservação de notas, como relatar falha de segurança em privado e exemplo de ambiente sem valores reais, indicando que o destino é `~/.orquestra/.env`. No Linux, não presumir que Git venha instalado em toda distribuição. Explicar que nas execuções seguintes o navegador pode exigir `iniciar --abrir`.

### D2 — Melhorar prevenção de arquivos locais/segredos acidentais

`.gitignore` cobre `.env` exato e somente dois nomes de vault na raiz. Não cobre variantes `.env.local`/`.env.production` nem um vault colocado manualmente com outro nome. O fluxo normal de preparo já impede criar/adotar vault dentro da árvore do programa; o risco restante inclui arquivos copiados manualmente ou caminhos que contornem esse fluxo. Ampliar padrões relevantes, preservando `!.env.example`, manter vaults fora da árvore do app e acrescentar scanner de segredos no processo de contribuição/release.

Não foi encontrado segredo pelo scanner nos arquivos e commits cobertos. Os quatro prints atuais em `docs/img` também foram inspecionados visualmente: mostram demonstrações, sem dados pessoais ou credenciais identificados nos pixels visíveis. Isso não prova ausência matemática: objetos inalcançáveis/reflogs, conteúdo fora da árvore, metadados das imagens e mídias históricas não foram examinados dessa forma. Testes automatizados e notas fictícias do catálogo são materiais legítimos do produto, não devem ser removidos como “lixo de teste”.

### D3 — Facilitar recuperação de conflitos e tornar autosave verificável

**Onde:** `templates/nota.html:8`, `:41`; `static/js/app.js:280–340`; `templates/modulo.html`; `templates/base.html`.

O conflito normal foi tratado corretamente no navegador: a edição externa permaneceu no disco e o rascunho ficou no editor. A solução disponível é recarregar descartando o texto; oferecer copiar rascunho, salvar cópia e comparar versões reduziria retrabalho.

Falha de autosave de título/propriedade mantém o valor novo na tela, com toast temporário, mas sem estado duradouro de “não salvo”, retry ou reversão. Serializar mudanças por nota também evita conflitos entre dois autosaves da mesma aba. Isso é uma lacuna de feedback; não prova corrupção do arquivo.

No viewport mobile, o botão Novo virou apenas ícone sem nome acessível útil (AX mostrou `abrir-novo`). Há diálogos/textarea sem associação adequada com seus títulos; ordenação de tabela usa clique em `th` sem ação equivalente por teclado. Nomear controles, associar labels, mover foco no onboarding e testar teclado/leitor de tela. Já existem foco visível, redução de movimento e seletor de status alternativo ao drag.

As telas verificadas funcionaram em desktop e 390 × 844; o quadro usa rolagem horizontal no mobile. Não houve erros de console nas consultas do fluxo navegado. Isso não certifica todos os temas, navegadores ou acessibilidade integral.

### D4 — Consolidar fronteiras do núcleo sem reescrever a arquitetura

A separação entre notas, schema, índice, domínio Painel, HTTP/MCP, watcher e agenda é clara. Dataclasses e anotações ajudam a leitura. O mapa estrutural identificou Painel, Ferramentas, Nota, Modulo e Indice como os principais pontos de integração.

As prioridades de organização são centralizar acesso ao filesystem e a transação de escrita, validar tipos nas fronteiras e padronizar erros. Hoje há tratamentos amplos/silenciosos e validação manual de dicionários, permitindo estados parcialmente inválidos. O helper `_yaml` aparece em notas/config; helpers de coletores também se repetem, em parte para manter scripts independentes. Consolidar apenas onde houver benefício sem quebrar esse uso isolado.

Não foi comprovado código morto cuja remoção seja segura. Um símbolo pouco conectado no grafo pode ser entrypoint, ferramenta MCP, callback ou recurso carregado dinamicamente; confirmar antes de excluir. Considerar lint/typecheck incrementais e divisão de responsabilidades do Painel conforme crescer, após corrigir integridade e segurança.

### D5 — Fortalecer durabilidade, arquivamento e observabilidade

Temporário + replace evita arquivo parcialmente publicado em operação isolada, mas não há flush/fsync explícito para garantir persistência em queda de energia. Testar disco cheio, permissão negada, arquivo ocupado e interrupções. Arquivar compartilha a corrida de destino descrita em C3; caminhos antigos em wikilinks também podem deixar de resolver após a movimentação.

Limitar stdout/stderr dos coletores, redigir segredos em erros e diferenciar erro operacional de configuração. O timeout existe, mas encerramento de árvore de processos não foi comprovado. Filas SSE são limitadas, porém descartam eventos quando cheias; considerar sinal de ressincronização para o cliente. Criar segredos com permissões adequadas por sistema. Esses itens não substituem os bloqueios C1–C3.

## O que já está bem encaminhado

- Bind explícito em **127.0.0.1**; MCP via stdio. Nenhuma evidência de porta do painel aberta na LAN por padrão.
- Subprocessos usam listas de argumentos, sem `shell=True`; não foi encontrada injeção simples de string de shell nos caminhos revisados. Scripts Python e hooks Git continuam código de confiança.
- Middleware de Host/Origin/JSON bloqueia os casos comuns de CSRF/rebinding testados. Não foi comprovado bypass de navegador.
- HTML bruto desativado no Markdown, escape de templates, validação de links e mídia com proteção de caminho/CSP. Não foi demonstrado XSS nos casos revisados.
- Chaves próprias ficam fora do vault; catálogo começa com coletores desativados; histórico automático desligado na adoção.
- Adoção preservou as notas sintéticas em operação isolada; desligar área preserva a pasta. Frontmatter sintaticamente inválido é bloqueado para edição.
- Atualizações normais do índice são incrementais; busca em memória foi rápida; há testes úteis de YAML, CRLF, schema, conflitos prévios, API, adoção, coletores e MCP.

## Plano de testes para liberar a versão

Os 125 testes atuais são uma base útil, mas fixtures comuns desativam Git, watcher e scheduler (`tests/conftest.py:16–35`). O conflito testado começa antes de salvar, não na janela entre hash e replace. Não foi calculada cobertura percentual; passar a suíte não significa cobrir as fronteiras abaixo.

| Ordem | Fluxo que precisa de cobertura | Resultado esperado |
|---|---|---|
| 1 | Caminhos HTTP/MCP e todos os escritores, traversal/junction/symlink | Nenhum conteúdo externo lido ou alterado |
| 2 | Vault importado, coletor ativo, script alterado, ambiente com chave fictícia | Sem execução antes da confiança; sem chave não autorizada |
| 3 | Painel + MCP + editor externo; criação/arquivo concorrentes; nota removida | Sem perda silenciosa; versões preservadas e conflito recuperável |
| 4 | Encoding inválido, BOM/CRLF, YAML comentado/incompleto | Preservação byte a byte ou bloqueio claro |
| 5 | Backup Git real + restauração + remoto bare; staging, lock e falhas | Cópia recuperável; erro visível; tentativas separadas de sucesso |
| 6 | YAML/API com tipos errados e recuperação posterior | Erro contextual, módulo isolado, restante do vault disponível |
| 7 | Watcher real com rename temporário, pasta movida, rajada e árvore ignorada | Atualização em prazo limitado, sem bloqueio prolongado do painel |
| 8 | Instalação do commit/tag final, Python mínimo, wheel/sdist e login | Resultado reproduzível em Windows/macOS/Linux |
| 9 | Navegador: primeiro uso/adotar/trocar vault/capturar/editar/conflito | Arquivos corretos; rascunho recuperável; mensagens e foco adequados |
| 10 | 10 mil+ notas, muitos links/anexos, mobile e clientes simultâneos | Medidas registradas de RAM, latência, tamanho HTML e responsividade |

Primeiro corrigir C1–C3 e suas regressões. Em seguida, integridade de encoding/backup/configuração, diagnóstico e o candidato de release reproduzível. Publicar como suporte confirmado somente os sistemas e fluxos efetivamente validados; manter no README as limitações reais dos demais.

## Rastreabilidade dos ensaios

As subauditorias e scripts de reprodução foram preservados fora da árvore do produto em `%TEMP%`, com prefixos `orquestra-audit-*`, `orquestra-security-*`, `orquestra-untrusted-vault-*` e `orquestra-install-audit-*`. Os relatórios de scanner foram redigidos para não expor valores. O servidor de revisão usou somente vault sintético em loopback na porta 18420, com agendamento desligado, e foi encerrado após a inspeção.

O grafo auxiliar foi uma extração estrutural de 42 fontes Python/JavaScript, sem extração semântica de docs/imagens ou envio a provedor LLM; artefatos foram mantidos no temporário. A análise das relações serviu como mapa e foi conferida nas fontes. Este relatório não certifica código ou commits futuros nem substitui revalidar o candidato após as correções.
