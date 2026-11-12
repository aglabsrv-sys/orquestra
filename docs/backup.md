# Histórico, rascunhos e recuperação

O Orquestra tem três mecanismos diferentes. Nenhum deles dispensa uma cópia fora
do computador.

| Mecanismo | O que preserva | Onde fica |
|---|---|---|
| Rascunho do navegador | Texto, título e propriedades ainda não salvos nesta aba | Perfil local do navegador, separado por vault e nota |
| Recuperação de gravações | Conteúdo anterior e proposta de cada edição feita pelo Orquestra | `~/.orquestra/recuperacao/` ou `ORQUESTRA_HOME/recuperacao/` |
| Snapshots Git | Arquivos do vault em momentos escolhidos | Referência local `refs/orquestra/backups`; cópia remota opcional |

## Com Obsidian aberto

O painel usa a versão lida do arquivo como pré-condição, coordena suas próprias
instâncias com locks e publica por arquivo temporário exclusivo. Se encontra uma
mudança externa, responde com conflito em vez de salvar com uma versão antiga.
Obsidian e sincronizadores não participam desses locks: ainda existe uma janela de
corrida entre programas diferentes. Evite editar a mesma nota ao mesmo tempo.

No aviso de conflito, **Copiar meu texto** preserva o texto na área de transferência;
**Salvar uma cópia no vault** cria outra nota no mesmo diretório com os valores do
rascunho. **Descartar rascunho e recarregar** pede confirmação antes de abrir o
conteúdo atual do disco. Se uma gravação falhar, o aviso fica na tela e permite
salvar novamente as alterações atuais ou descartá-las explicitamente.

Ao reabrir uma nota com rascunho anterior neste navegador, escolha **Retomar
rascunho**. Se o arquivo mudou desde a versão do rascunho, salve uma cópia; retomar
não sobrescreve o arquivo. Abas diferentes guardam entradas separadas. O navegador
pode bloquear armazenamento ou esgotar a quota; nesse caso o painel avisa. A
limpeza do perfil apaga esses rascunhos. Não use perfis compartilhados para notas
privadas.

## Versões de recuperação no disco

Antes de publicar uma alteração, o Orquestra preserva arquivos `.antes`, `.proposta`
e metadados `.json` em subpastas de `~/.orquestra/recuperacao/`. O JSON identifica o
caminho original, versões e momento; os arquivos de conteúdo podem ser lidos num
editor de texto. Esse diretório fica fora do vault para não gerar eventos nem ir
junto do backup público do aplicativo. No Windows, use sua pasta pessoal
`.orquestra\recuperacao`.

Para recuperar, copie o conteúdo desejado para uma nota nova, confira o resultado
e só então decida como integrar com a nota atual. Não substitua o arquivo ativo
sem antes preservar sua versão atual. Arquivos de recuperação não são apagados
automaticamente; revise o espaço usado e copie versões importantes antes de uma
limpeza manual. Eles podem conter conteúdo privado e segredos antigos.

Na própria nota, abra **Versões locais de recuperação**, escolha a gravação e
consulte o conteúdo **antes da gravação** ou a **proposta**. **Copiar versão** copia
o arquivo completo; **Salvar versão como nova nota** preserva frontmatter e texto
em outra nota. A nota aberta e seu rascunho não são substituídos.

## Snapshots Git

Em um vault novo, a opção de histórico pode vir marcada. Num vault adotado, fica
desligada até sua escolha. Se o Git não estiver instalado, o painel informa a
limitação. **Ajustes > Histórico e backup** mostra a configuração e os destinos
remotos antes da autorização local. Repositórios/configurações importados não são
executados automaticamente sem revisão. Mudanças relevantes exigem nova aprovação.

Com histórico aprovado e automático ligado, o painel cria uma versão após mudanças,
respeitando o intervalo (30 minutos por padrão). Sem mudança não há snapshot. Os
snapshots usam um índice temporário e a referência **`refs/orquestra/backups`**:
não movem seu `HEAD`, branch atual ou staging. Isso permite usar o Git do Obsidian
sem incluir no commit do usuário notas que ainda não pretendia preparar.

Os comandos `uv run` deste guia são executados na pasta do **aplicativo**, que tem
`pyproject.toml` e `uv.lock`. Os comandos `git` indicados abaixo são executados na
pasta do **vault**. Se houver mais de um vault, informe `--vault "CAMINHO COMPLETO"`
em cada comando Orquestra para selecionar o mesmo destino.

Para pedir uma versão agora, depois da aprovação:

```bash
uv run --frozen orquestra backup
```

Sem interface gráfica, esse comando prepara um repositório ausente e orienta a
revisão antes da primeira cópia. Até a aprovação, retorna falha: isso não confirma
que uma cópia foi feita. Consulte a configuração com
`uv run --frozen orquestra confiar backup`, confira os arquivos/destinos e repita
com `--assinatura HASH` usando a assinatura exibida. Para retirar a autorização,
use `uv run --frozen orquestra confiar backup --revogar`. O aceite fica somente
nesse computador; uma mudança na configuração exige revisão nova.

Depois de aprovar, execute `uv run --frozen orquestra backup` novamente para criar
o primeiro snapshot. Na criação de um vault novo pelo modelo, o histórico inicial
gerado pelo próprio Orquestra pode já ter sido preparado e autorizado; configurações
e destinos remotos acrescentados depois ainda exigem nova revisão.

Os comandos abaixo são somente de leitura e devem ser usados na pasta do vault:

```bash
git log --oneline refs/orquestra/backups
git show refs/orquestra/backups:"tarefas/itens/Minha tarefa.md"
```

Troque a referência por um hash da lista para consultar uma versão anterior. Evite
`git checkout` ou `git reset` como primeira tentativa: eles podem substituir trabalho
atual e alterar staging. Abra a versão anterior e crie uma nota de recuperação.

Os snapshots gravam blobs sem executar filtros de `.gitattributes`. O backup
mescla regras de ignore com as existentes, exclui nomes comuns de segredos
e recusa arquivos sensíveis já rastreados. Esse filtro não reconhece todo segredo
possível dentro de uma nota ou anexo. Confira o que há no vault antes de enviar.

## Cópia externa privada

Crie um repositório **privado** e vazio e configure seu endereço dentro do vault:

```bash
git remote add origin git@github.com:voce/meu-vault.git
```

Se já existe um remoto `origin`, confira seu destino e use a configuração que
pretende manter. Não adicione nem substitua um remoto sem revisar para onde as
notas serão enviadas.

Prefira SSH com uma chave protegida e um agente SSH já configurado. O processo de
backup desabilita configuração Git global/system e helpers globais de credenciais;
um gerenciador HTTPS já usado pelo seu terminal pode não funcionar nesse processo.
Não coloque tokens ou senhas na URL do remoto. Autenticação e envio real ao seu
provedor precisam ser conferidos no seu ambiente; os testes automatizados usam um
remoto Git local independente.

Revise o novo destino em Ajustes e autorize a configuração localmente. Volte à
pasta do aplicativo e envie, indicando o caminho completo do mesmo vault:

```bash
uv run --frozen orquestra backup --enviar --vault "CAMINHO COMPLETO DO VAULT"
```

O Orquestra envia a referência local para a branch remota **`orquestra-backup`**;
não usa force push. Divergências e falhas são informadas, sem tratar envio ausente
como sucesso. Para enviar diariamente, configure:

```yaml
backup:
  auto_commit: true
  intervalo_min: 30
  push: true
  push_as: "03:00"
```

O painel precisa estar aberto; tarefas atrasadas são retomadas quando ele volta.
Remoto configurado não comprova que o último envio funcionou. Confira o resultado
em Ajustes e, periodicamente, teste abrir uma cópia separada do backup.

Em outro computador, clone a branch de backup para uma pasta nova:

```bash
git clone --branch orquestra-backup git@github.com:voce/meu-vault.git MeuVaultRecuperado
```

Na pasta do aplicativo, abra o caminho completo desse vault com `--vault`. As chaves
em `~/.orquestra/.env`, aprovações de scripts, rascunhos do navegador e recuperação
local não são transferidos junto: configure/revise-os novamente no novo computador.

## Sincronizadores e limites

OneDrive, iCloud, Dropbox e Obsidian Sync podem sincronizar um arquivo durante uma
gravação. Evite rodar o painel do mesmo vault em dois computadores ao mesmo tempo.
Não compartilhe `.git` por sincronizador sem entender os conflitos possíveis;
backup Git e sincronização são mecanismos diferentes. Pastas com metadados Git
vinculados (worktree/submódulo) ou includes externos de configuração não são aceitas
pelo backup automático. Use uma cópia independente do vault nesses casos.

As exclusões globais do Git também ficam desligadas. Coloque as regras de
privacidade no `.gitignore` do próprio vault; não dependa de uma configuração
global do computador para impedir que um arquivo entre no snapshot.
