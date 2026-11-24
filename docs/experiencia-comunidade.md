# Experiência da comunidade

## Onde cada coisa fica

Tarefas e notas do cotidiano ficam em `itens/`: humanos, agentes e coletores podem
criá-las, com origem identificada. **Ajustes → Instruções da IA** é a central única
para orientar a IA. Escreva as preferências gerais e, se necessário, observações
sobre os módulos no mesmo texto: “No Radar…” ou “Na Entrada…”.

As orientações gerais ficam num bloco do `AGENTS.md`. Salvar pela central altera
somente esse bloco e a lista de notas vinculadas; o restante do contrato é
preservado. O texto não é salvo automaticamente, e alterações feitas em outra
janela são detectadas antes da gravação. `CLAUDE.md` continua sendo a ponte para
as regras, sem outra cópia das preferências.
Se já houver um `PREFERENCIAS.md` e nenhum bloco geral no contrato, a central
aproveita esse arquivo como editor geral, sem abrir uma segunda cópia do texto.

Notas anteriores em `humano/` e `PREFERENCIAS.md` aparecem na mesma tela, com a
origem identificada, recolhidas como contexto vinculado e com acesso à nota original.
A central tem apenas um campo compacto de edição. Seus arquivos não são movidos,
apagados nem copiados. Ao salvar as instruções gerais, elas ficam vinculadas no
contrato; pelo MCP, `contexto_area` também reúne as fontes relevantes. A central
não cria novos `PREFERENCIAS.md` nem exige uma pasta Humano para cada módulo.

Os módulos ficam sem a aba Humano; links antigos abrem a central. `maquina/`
continua contendo automações e contexto técnico, apresentado em uma seção
recolhida. Essa área não é outro lugar para configurar preferências da pessoa.

O atalho **Entrada** abre primeiro **Para decidir**, reunindo as pendências dos
módulos. Clicar novamente no mesmo atalho alterna com **Capturas**, quando essa
área estiver disponível. As duas seções também ficam nas abas da Entrada.
As imagens das decisões aparecem como prévias pequenas ao lado do texto.

A seção **Radar dentro de Para decidir** apresenta notícias e vídeos com uma
prévia pequena ao lado do texto. Sem imagem ou quando ela estiver indisponível,
o item segue como texto. O módulo **Radar** mantém sua apresentação habitual
em Lista e Triagem (colunas), e a escolha da visão continua sendo lembrada.
Dentro de Para decidir, a ação **Arquivar** guarda o item no arquivo do Radar e
o retira da fila. O conteúdo é preservado, e vídeos arquivados continuam sendo
reconhecidos pelas automações para evitar uma nova importação do mesmo vídeo.

Responsabilidades contínuas, como saúde e família, podem ser organizadas em pastas
próprias e mostradas no painel. Para Academia 3×/semana, use Hábitos e metas, com exemplos
opcionais e check-in diário. Um registro não marcado não é inventado pelo agente.
Pomodoro tem tela própria pelo ícone ao lado da busca; Hábitos abre pela pasta do
módulo. Veja [Pomodoro e Hábitos](foco-e-habitos.md) para uso e limites de persistência.

## Coletores

“Tarefas que se repetem” cria notas para rotinas configuradas no `_modulo.yaml`:
sexta-feira para revisar a semana, dia 5 para conferir contas. A identificação evita
duplicar a rotina na mesma data. Só roda automaticamente com o agendamento ativo,
enquanto o processo estiver aberto.

**Conectar agenda** assina o iCal para leitura na Agenda, sem criar tarefas.
O endereço fica nas variáveis locais, separado por vault, e a conexão é testada
antes de ser salva. A automação **Importar cópias da agenda (legado)** conserva o
comportamento antigo de gravar notas; você pode pausá-la em Automações.

Coletores exatamente iguais aos distribuídos com a instalação — código, auxiliares,
configuração e chaves declaradas — podem rodar sem um aceite adicional. Alterar
qualquer desses dados exige aprovação local da assinatura. A revogação explícita é
respeitada inclusive nos originais. Código aprovado tem as permissões da sua conta;
a execução não é uma sandbox.

## Agenda e limites da importação

A semana da home abre o dia selecionado. A agenda agora tem visões Mês, Semana,
Dia e Lista, com busca, filtros e edição dos eventos. Veja [Agenda](agenda.md).
O assistente ensina como obter o link no Google Agenda/Android ou iCloud/iPhone.
Trate o link como senha; uma agenda pública do iCloud pode ser lida por quem
conhecer o endereço. O Orquestra não solicita a senha Apple/Google.

A assinatura trata recorrências, exceções e cancelamentos presentes no iCal.
Ao consultar a Agenda, uma nova leitura é feita se o cache tiver cinco minutos.
Não há edição da agenda de origem: use o aplicativo Google/Apple para alterar
compromissos. O importador legado continua sem reconciliar mudanças e exclusões
nas cópias já gravadas. Consulte os [limites da assinatura](agenda.md).

Referência: [Google — sincronizar por iCal](https://support.google.com/calendar/answer/37648).

## GitHub e celular

O botão Login no GitHub usa `gh auth login --web --git-protocol https`. É necessário
instalar o [GitHub CLI](https://cli.github.com/). A tela mostra apenas o código de
autorização temporário, nunca o token. O processo expira após três minutos; o CLI
gerencia o armazenamento da credencial conforme o suporte do sistema operacional.
Fechar o modal não desfaz um login já autorizado no GitHub.

A seleção lista até 100 repositórios privados da conta autenticada. Para contas
de organização, confirme acesso no GitHub CLI. Vincular altera as URLs de leitura
e envio de `origin`. Não faz push e não ativa envio automático. Prepare o histórico
e confira o destino em Backup antes de autorizá-lo. As versões vão para a branch
`orquestra-backup`. A revisão de Git continua necessária, inclusive quando existem
regras locais de reescrita de URLs.

No push HTTPS para `github.com`, o backup usa somente o helper oficial do `gh`
instalado. Configurações globais, hooks e outros helpers herdados continuam
desabilitados; não é necessário habilitar um helper global para este fluxo.

Referência: [login oficial do CLI](https://cli.github.com/manual/gh_auth_login).

Conecte seu celular abre um guia em três passos: instalar Tailscale nos dois
dispositivos, entrar com a mesma conta e executar `tailscale serve --bg PORTA`.
No último passo, cole o endereço HTTPS mostrado pelo Serve: o botão permite somente
esse hostname `.ts.net`, sem curingas, e aplica a configuração ao processo atual.
O computador precisa continuar ligado. O guia não instala nem modifica o Tailscale
automaticamente. Use a rede privada, nunca Funnel para este painel sem senha.

Referência: [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

## Capas, miniaturas e aprovação

Personalizar oferece previews de cenas em modal e upload local de PNG, JPEG,
WebP, MP4 ou WebM até 2 MB. Prefira vídeos curtos (até 20 segundos), comprimidos e
sem áudio. O limite de duração é recomendação; o servidor limita bytes e formatos,
não transcodifica nem remove metadados. Vídeos usam loop, muted, playsinline e
preload de metadados; só reproduzem quando visíveis. Reduzir movimento é respeitado.
Arquivos enviados sem salvar a personalização permanecem no vault para evitar
remover mídia que outra nota possa usar.

Campos de imagem aceitam caminho no vault, URL ou envio de arquivo pelo localhost.
O preview usa a rota confinada de arquivos para mídias locais. Imagens remotas
dependem do servidor de origem e podem revelar seu IP a ele.

No módulo Conteúdo, o agente usa `miniatura` para o criativo e `status: em_aprovacao`.
Em Entrada → Para decidir, a fila mostra o preview com Aprovar criativo e Pedir ajustes. Aprovar
altera o status para `aprovado`: não publica em redes sociais. O botão para pipelines
antigos acrescenta opções e ações, preservando as já configuradas.

## Variáveis e processo local

Ajustes → Variáveis adiciona, substitui e exclui entradas do `.env` fora do vault.
A listagem só retorna nomes. Operações exigem localhost direto e capacidade local;
não funcionam por Tailscale/proxy. Nomes reservados e valores multilinha são recusados.
Não há cópias de recuperação dos valores. O arquivo não é criptografado: no Unix
recebe modo 0600; no Windows depende também das ACLs do perfil do usuário.

As variáveis não são exportadas globalmente para o sistema nem entregues a todos
os agentes. Coletores recebem somente as chaves declaradas em `requer`. Reinicie
outras ferramentas que leem suas próprias configurações; o Orquestra não as altera.

Sem início automático, o terminal mantém o painel aberto. Ao ativar em
**Ajustes → Painel**, o Orquestra retoma o mesmo cofre e porta em um processo
independente. Aguarde a confirmação de funcionamento em segundo plano antes de
fechar o terminal. Se a configuração já estava ativa, use **Aplicar agora**.
Novas aberturas pelo terminal também respeitam a configuração ativa. Desativar
remove o início no próximo login; para encerrar a instância atual, use `orquestra parar`.

O início automático usa a sessão do usuário, não um serviço de sistema executado
antes do login. O comando `autostart ativar` também configura essa entrada
reversível. Os registros do processo independente ficam em
`~/.orquestra/painel.log`, fora do vault.

`desinstalar`/`uninstall` orienta a remoção e, com `--confirmar`, desliga o início
automático. Não apaga o programa enquanto ele está rodando, nem o vault, secrets
ou backups. O usuário remove a pasta clonada depois de encerrar o processo.

## Navegação

Os ajustes são páginas renderizadas no servidor. A navegação normal continua
fazendo requisições HTML, com transição curta onde o navegador suporta. Mudanças
externas mostram aviso para atualizar; não recarregam a página automaticamente.
Fonte, cantos, modo e destaque são aplicados sem recarregar. Salvar o nome ou o
destino de captura preserva o formulário; a navegação seguinte reflete o novo estado.


### Busca de notas

Abra a busca pelo botão, por Ctrl+K ou por `/` fora de um campo de texto.
A consulta procura um trecho literal no título e no corpo, sem distinguir
maiúsculas e minúsculas, e prioriza os títulos. A janela mostra até 12 notas;
a busca completa permite navegar por todos os resultados.

O texto pesquisável fica em memória e acompanha as alterações das notas.
Ao trocar o termo ou fechar a janela, a consulta anterior é cancelada.
Se houver falha ou a resposta demorar mais de dez segundos, tente novamente
ou use o link da busca completa.


### Ajustes e leitura

Em Ajustes > Pastas, acrescentar uma área pronta ou criar uma em branco mantém
você na mesma página, com as escolhas abertas. A lista e o dock recebem a nova
área; você pode abri-la quando terminar de configurar.

No grafo de Pastas, o nó acompanha o ponteiro enquanto é arrastado. Ao soltar,
as forças voltam a acomodar o nó e suas ligações; ele não fica preso na posição.
A preferência de movimento reduzido continua respeitada.

As notas aproveitam até 1.400 pixels de largura no desktop. No leitor dentro
de Pastas, o texto ocupa a largura disponível; tabelas largas continuam com
rolagem horizontal dentro da própria tabela em telas pequenas.
