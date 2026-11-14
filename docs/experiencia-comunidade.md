# Experiência da comunidade

## Onde cada coisa fica

Tarefas e notas do cotidiano ficam em `itens/`: humanos, agentes e coletores podem
criá-las, com origem identificada. `humano/` reúne suas orientações, preferências e
decisões. `maquina/` contém instruções, aprendizados e scripts. A aba Máquina não é
uma segunda lista de tarefas. Entrada é sua captura rápida; suas visões não precisam
de uma aba Humano adicional. O arquivo continua no vault, mesmo sem a aba.

Áreas é parte do método PARA: saúde, família, finanças, responsabilidades contínuas.
Não é igual a um hábito. Para Academia 3×/semana, use Hábitos e metas, com exemplos
opcionais e check-in diário. Um registro não marcado não é inventado pelo agente.
Pomodoro tem tela própria pelo ícone ao lado da busca; Hábitos abre pela pasta do
módulo. Veja [Pomodoro e Hábitos](foco-e-habitos.md) para uso e limites de persistência.

## Coletores

“Tarefas que se repetem” cria notas para rotinas configuradas no `_modulo.yaml`:
sexta-feira para revisar a semana, dia 5 para conferir contas. A identificação evita
duplicar a rotina na mesma data. Só roda automaticamente se você ligar a chave e
mantiver o processo aberto.

“Compromissos da agenda” lê um endereço iCal e cria tarefas dos próximos 14 dias.
O botão Conectar agenda guarda `AGENDA_ICAL_URL` no `.env` local e declara a variável
em `requer`. A URL não aparece na configuração compartilhável. A configuração nova
fica manual até sua revisão; o botão Rodar agora faz a primeira coleta.

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

Este é um importador de leitura, não uma integração CalDAV/OAuth bidirecional.
O coletor atual não expande regras RRULE, não reconcilia exclusões e não garante
atualização de todos os eventos já importados. Eventos recorrentes podem aparecer
apenas na primeira ocorrência do arquivo; confira a agenda de origem. Não anuncie
sincronização completa de calendário com esta versão.

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
A fila Para decidir mostra o preview com Aprovar criativo e Pedir ajustes. Aprovar
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

O terminal precisa ficar aberto. O início automático usa a sessão do usuário, não
um serviço de sistema executado antes do login. O botão em Ajustes → Vault e o
comando `autostart ativar` fazem a mesma configuração reversível.

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
