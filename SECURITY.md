# Segurança

O Orquestra é um aplicativo local, sem autenticação própria. A versão 0.4.x é o
candidato mantido atualmente; use a revisão corrigida mais recente antes de
abrir um vault importante. Correções ainda não publicadas não protegem versões
antigas já instaladas.

## Relatar uma vulnerabilidade

Use [Report a vulnerability no GitHub](https://github.com/antoniogsouzaag/orquestra/security/advisories/new)
quando o relato privado estiver habilitado. Se essa opção não estiver disponível,
abra uma issue contendo apenas “preciso de um canal privado para um relato de
segurança”, sem prova de exploração, dados do vault ou segredos. O mantenedor
combinará o canal e a divulgação; não há prazo de atendimento garantido.

Inclua a versão/commit, sistema operacional, passos com arquivos sintéticos,
resultado observado e impacto. Nunca envie o vault completo, tokens ou URLs
privadas de calendário. Se um segredo já foi publicado, revogue ou rotacione-o;
apagar a linha do código não o remove do histórico Git.

## Limites de confiança

- O servidor escuta em `127.0.0.1`. Não o exponha por roteador, proxy público,
  Tailscale Funnel ou hospedagem. Host/origem e uma capacidade local temporária
  protegem operações sensíveis; esses mecanismos não são uma conta ou senha.
- Apenas nomes exatos configurados em `hosts_permitidos` são aceitos além dos
  hosts locais. Para Tailscale Serve, permita o nome exato do seu computador e
  restrinja os aparelhos/usuários com acesso no Tailscale.
- Quem alcança o painel pode ler e editar notas. Escolher/trocar vault e aprovar
  execução de código ou configuração de backup exigem localhost direto, sem
  headers de encaminhamento. Outros programas na sua conta já têm acesso local.
- Um coletor é código Python com as permissões da sua conta, acesso à rede e ao
  ambiente. A assinatura aprovada cobre os arquivos/configuração apresentados;
  mudanças exigem nova aprovação. Não aprove módulos recebidos de desconhecidos
  sem ler seu código. Não existe sandbox de sistema operacional para coletores.
- Agentes que recebem acesso direto à pasta podem alterar qualquer arquivo que a
  conta permite. As regras de `AGENTS.md` orientam esses agentes; a proteção de
  escrita do conector MCP aplica-se às ferramentas desse conector.

## Dados, segredos e recuperação

Mantenha vaults fora do repositório público do aplicativo. As chaves declaradas de
API ficam em `~/.orquestra/.env`; [.env.example](.env.example) só contém nomes e
valores vazios. URLs ICS privadas, tokens em links e arquivos anexos também podem
conter segredos. Não presuma que `.gitignore` examina conteúdo ou retira arquivos
já rastreados. Backups remotos de vaults devem ser privados e revisados.

As gravações usam validação de caminho/versão, temporários exclusivos e arquivos
de recuperação. Locks coordenam instâncias do Orquestra; Obsidian, sincronizadores
e outros editores não participam desses locks. Evite editar a mesma nota ao mesmo
tempo. O armazenamento local de rascunhos contém texto das notas no perfil do
navegador; não use um perfil compartilhado para vaults privados.

Uma versão de recuperação no mesmo disco não substitui backup externo. Consulte
[histórico e recuperação](docs/backup.md) para preservar um rascunho, localizar
versões anteriores e restaurar uma cópia sem sobrescrever trabalho recente.
