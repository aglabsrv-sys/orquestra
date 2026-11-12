# Arquitetura (para quem vai estudar ou contribuir)

## A ideia em uma frase

O banco de dados é uma pasta de arquivos markdown. O painel é só uma janela para
ela, e qualquer coisa que saiba ler e gravar arquivos (você, o Obsidian, um agente
de IA, um script) participa do sistema em pé de igualdade.

```mermaid
flowchart LR
    voce([Você]) --> painel[Painel web]
    voce --> obsidian[Obsidian]
    agente([Agente de IA]) --> vault
    obsidian --> vault
    painel <--> vault[(Vault: arquivos .md)]
    coletores[Coletores] --> painel
    vault -. vigia de arquivos .-> painel
    painel --> diario[Diário]
    painel --> git[(git: histórico e backup)]
```

## Decisões e por quê

| Decisão | Por quê |
|---|---|
| Arquivos, não banco de dados | Nenhum formato fechado. Funciona com Obsidian, com git e com qualquer agente, hoje e daqui a dez anos. |
| Módulos, temas e coletores dentro do vault | Personalizar é editar um arquivo, coisa que um agente faz. Atualizar o app nunca desfaz a personalização. |
| Vault fora do repositório do app | `git pull` do app nunca conflita com os dados; o vault tem o próprio git, privado. |
| Python + uv, um runtime só | Coletores e painel na mesma linguagem; o `uv` instala até o Python. |
| HTML no servidor e JavaScript puro | Sem etapa de build. O que está em `static/` é o que roda; dá para ler e mexer. |
| ruamel.yaml em vez de PyYAML | Preserva comentários, ordem e aspas do frontmatter. Editar um campo não reescreve o arquivo. |
| Índice em memória | Rápido e descartável. A verdade está no disco; o índice se refaz ao iniciar. |
| Coletor imprime JSON | O script não conhece o painel. Simples de escrever e de testar sozinho. |
| Agendador dentro do servidor | Igual em Windows, macOS e Linux, sem cron nem Agendador de Tarefas. |
| Sem login, escutando só em 127.0.0.1 | Menos coisa para dar errado. O acesso remoto fica com o Tailscale, que já resolve identidade. |

## Mapa do código

```
src/orquestra/
  notas.py         ler e gravar .md com frontmatter (versão, validação e conflito)
  armazenamento.py locks entre processos, publicação segura e recuperação fora do vault
  caminhos.py      validação comum de caminhos, nomes e redirecionamentos
  contratos.py     contratos tipados e limites de entrada das operações
  confianca.py     aprovações locais de código/configuração e snapshots de coletores
  modulos.py       _modulo.yaml: schema, conversão e validação de valores
  indice.py        espelho do vault em memória; resumos e busca
  painel.py        o núcleo: toda operação que altera o vault passa por aqui
  vigia.py         watchdog: avisa quando um arquivo muda no disco
  eventos.py       canal servidor -> abas abertas (Server-Sent Events)
  diario.py        registro de mudanças e sessões dos agentes
  coletores.py     execução dos scripts e importação dos itens
  agenda.py        laço que roda coletores e backups na hora certa
  calendario.py    períodos, filtros e organização dos eventos da agenda visual
  habitos.py       notas de hábitos, metas semanais e marcações com controle de versão
  backup.py        snapshots Git em referência própria e envio revisado
  github_local.py  autenticação pelo GitHub CLI e conexão revisável com repositório
  segredos.py      variáveis locais fora do vault, sem devolver valores ao navegador
  temas.py         temas e resolução das capas
  aparencia.py     claro/escuro, cor de destaque, cantos e letra: vira o CSS do topo da página
  seguranca.py     checagem de Host e de origem (DNS rebinding e CSRF)
  apresentacao.py  ícones, datas, cartões, markdown -> HTML
  graficos.py      visão de gráfico: séries e geometria das linhas (SVG pronto no HTML)
  servidor.py      rotas FastAPI do painel de UM vault (páginas e API JSON)
  preparo.py       criar um vault ou adaptar um que já existe, sem sobrescrever nada
  adocao.py        ler uma pasta que já existia e escrever o _modulo.yaml dela
  boasvindas.py    tela "escolher ou criar", que funciona antes de existir um vault
  hospedeiro.py    o que o servidor web executa: boas-vindas ou painel, e a troca entre eles
  mcp_servidor.py  o vault como conector MCP, com as regras aplicadas pelo código
  cli.py           comandos: iniciar, criar, adotar, doctor, coletar, backup, confiar, mcp, autostart
  doctor.py        diagnóstico em português
  autostart.py     início automático por sistema operacional
  templates/       páginas (Jinja)
  static/css       estilos comuns e arquivos das telas de agenda, foco e hábitos
  static/js        comportamento progressivo; foco-engine.js isola o estado do timer do DOM
  modelo_vault/    o que todo vault recebe: AGENTS.md, orquestra.yaml, temas
  catalogo/        os módulos prontos (uma pasta cada) e os perfis (perfis.yaml)
tests/             leitura/escrita, schema, API, segurança, coletores, diário, estruturas de vault
```

O Pomodoro guarda o prazo por vault e aba em `sessionStorage`; não grava produtividade
no vault. Hábitos usa o catálogo e os mesmos arquivos e mecanismos de escrita dos
demais módulos. Criar e marcar retornam o registro atualizado; o navegador atualiza
os cartões sem recarregar a página. Leituras compartilhadas e escritas usam a trava
do painel, e alterações de notas exigem a versão lida.

As seções de Ajustes carregam somente seu contexto. Eventos de arquivos agrupam a
atualização dos contadores; alterações externas oferecem atualização explícita para
preservar formulários e foco. Cenas animadas só mantêm o laço visual com trabalho
visível e respeitam a preferência de movimento reduzido.

## Um vault de qualquer formato

O painel não exige uma estrutura de pastas. O que ele precisa saber de cada área
está no `_modulo.yaml` dela, inclusive **onde ficam os registros**:

- `itens: itens` (padrão): em `<modulo>/itens/`, como nos módulos do catálogo;
- `itens: .`: as notas da própria pasta e das subpastas. É o que `adocao.py` escreve
  quando a pessoa manda mostrar no painel uma pasta que já existia.

`Indice.zona_de` é o único lugar que decide o papel de uma nota (item, humano,
máquina, arquivo); o resto do código pergunta a ele. Pastas sem `_modulo.yaml` não
são módulo, mas estão no índice: aparecem em Pastas, na busca e nos links.

`preparo.py` tem uma regra só: nunca sobrescrever. Por isso a mesma função cria um
vault numa pasta vazia e adapta um vault que a pessoa já usa.

## Trocar de vault sem reiniciar

`servidor.criar_app(vault)` monta o painel de um vault, com tudo preso a ele. O que
o uvicorn executa é o `Hospedeiro`, que fica na frente: sem vault, entrega a tela de
boas-vindas; com vault, entrega o painel. Trocar é encerrar o ciclo de vida de um
(vigia e agendador) e iniciar o de outro.

As rotas de boas-vindas criam arquivos fora do vault atual. Por isso só aceitam
pedidos diretos do próprio computador: peer loopback e Host local exatos, sem
encaminhamento, com capacidade temporária por processo. Host sozinho não concede
autorização local. A capacidade não é persistida no navegador.

## O caminho de uma alteração

1. Você arrasta um cartão. O navegador envia `PUT /api/notas/<caminho>` com o campo
   novo e a **versão** do arquivo que a página tinha.
2. `Painel.editar_nota` relê o arquivo do disco. Se a versão não bate, alguém mexeu
   nesse meio-tempo: responde 409 e nada é gravado.
3. A escrita segura coordena instâncias do Orquestra, preserva pré-imagem e
   proposta fora do vault, reconfere a pré-condição e publica por temporário
   exclusivo. Editores externos não participam do lock; recuperação e backups
   continuam necessários.
4. `Painel.apos_escrita` atualiza o índice, acrescenta uma linha ao diário e publica
   um evento.
5. As outras abas abertas recebem o evento e se atualizam.

Quando a alteração vem de fora (Obsidian, um agente), o vigia de arquivos chama o
mesmo `apos_escrita`, com autor "externo". Como o índice compara o conteúdo,
eventos repetidos podem ser deduplicados pela versão observada; o diário também
precisa lidar com remoções, renomes e eventos agrupados do sistema de arquivos.

## Rodar os testes

```bash
uv run --frozen python -m pytest
uv run --frozen ruff check src tests scripts
node --test tests/js/*.test.cjs
```

Os testes criam um vault temporário a partir do modelo e não tocam em nada seu.

## Convenções

- Código, comentários e nomes em português, porque o projeto é para ser estudado
  por quem está começando no Brasil.
- Comentário explica o porquê, não repete o que a linha faz.
- Mensagens de erro dizem o que aconteceu e o que fazer.
- Nada de dependência nova sem motivo forte. Declare dependências diretas em
  `pyproject.toml` e mantenha `uv.lock` revisado.
- Qualquer recurso que só funcione com um agente específico fica de fora do núcleo.

## Aprovação de execução e backup

A presença de um `_modulo.yaml` não autoriza scripts. `confianca.py` calcula uma
assinatura do código, auxiliares, configuração e nomes de chaves apresentados; o
aceite fica fora do vault. A execução usa a versão aprovada, recusando mudanças.
O script ainda roda com as permissões da conta: não é sandbox.

A configuração Git e os destinos do backup também exigem revisão local. Os
snapshots usam índice temporário e `refs/orquestra/backups`, preservando HEAD e
staging; o push explícito usa `orquestra-backup`. Não use `git add -A` ou checkout
no índice do usuário como parte do histórico automático.

## Limites de escala e interface

O índice em memória é descartável e o watcher agrupa mudanças. Listas, busca,
pastas e decisões são paginadas pelo servidor. A tabela ordena apenas os itens da
página atual, como informa seu nome acessível. Faça medições com notas sintéticas
em diferentes sistemas; um benchmark de arquivos pequenos não representa anexos
grandes, sistemas de sincronização ou uma unidade de rede.

Contagens pedem notas sem ordenação; listas continuam ordenadas. O navegador
agrupa consultas de resumo e limita pedidos simultâneos. Reconexão SSE exige
ressincronização porque o canal não mantém um histórico de eventos. Formulários
pendentes bloqueiam a recarga automática; a personalização envia a versão do YAML
lido e recebe conflito se o arquivo mudou. As cenas só são preparadas ao entrar
na área visível e não mantêm um laço ativo quando a página está oculta ou o usuário
prefere movimento reduzido.

O watcher usa `PollingObserverVFS` com um único emissor recursivo. A enumeração
poda diretórios ignorados e links antes de descer e compara metadados, sem reler o
conteúdo de todas as notas. O intervalo de consulta é 0,75 s, com debounce de
0,35 s; mudanças costumam aparecer em cerca de um segundo, variando com disco,
sistema e carga. Esse desenho evita criar uma thread para cada pasta do vault.

Os pedidos de edição de uma nota saem em sequência no navegador, sempre com a
versão devolvida pela resposta anterior. Falhas pausam a fila e ficam na tela.
Rascunhos têm chave por vault, nota e sessão; conteúdo do navegador não substitui
o arquivo nem é aplicado ao disco automaticamente na recuperação.
