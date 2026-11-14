# Revisão final de segurança e backup — 13/11/2026

## Resultado

A pendência reproduzida na auditoria foi corrigida: um histórico de snapshots
preexistente com `.env` em um commit antigo, mesmo removido da versão atual,
não pode mais continuar recebendo snapshots nem ser enviado pelo Orquestra.
O código não apaga ou reescreve versões antigas para contornar esse bloqueio.

A divulgação como **beta local para a comunidade** é adequada depois dos checks
do candidato de integração. Não foram encontrados outros impedimentos nos pontos
revisados. Isso não transforma o painel em serviço público com autenticação nem
os coletores em código isolado por sandbox.

## Proteção implementada

- Conferência de todos os ancestrais da referência de backup, incluindo outros
  pais de merges, arquivos removidos e variantes de nomes sensíveis.
- Leitura dos caminhos em formato Git raw com separadores NUL, sem filtros
  externos, textconv ou detecção de renomes que esconda o nome original.
- Falha ou saída incompleta na conferência bloqueia a operação.
- O envio usa a expressão do commit conferido. Trocar a referência depois da
  validação ou criar uma branch com o mesmo nome do hash não altera o objeto enviado.
- O primeiro snapshot continua independente do histórico comum do usuário.
  O histórico do usuário e seu staging permanecem preservados.

O `.env` gerenciado pelo painel fica fora do vault. Arquivos `.env` dentro do
vault são ignorados; um arquivo sensível forçado no staging bloqueia o snapshot.
Modelos `.env.example`, `.env.sample` e `.env.template` continuam permitidos,
desde que não recebam valores reais. Essa proteção por nomes não identifica
todo segredo colado dentro de uma nota ou anexo.

## Envio e recuperação exercitados

O teste usa somente diretórios temporários, um repositório Git bare local como
remoto e dados fictícios. Não acessa credenciais nem remotos do usuário.

1. Cria duas versões de uma nota, preservando BOM UTF-8, acentuação e CRLF na primeira.
2. Mantém um `.env` fictício no vault e outro no diretório local do aplicativo.
3. Envia a cadeia limpa ao remoto descartável e cria um clone separado a partir dele.
4. Confirma a versão atual, a ausência de `.env` no clone e a presença do modelo vazio.
5. Restaura a primeira versão como uma nota nova, com bytes idênticos, sem
   substituir a versão atual.
6. Recusa histórias contaminadas com `.env`, `.env.production`, `.ENV.local`,
   chave `.pem` e `secrets.json`; o remoto permanece sem referência publicada.

## Evidências e limites

- Suíte de armazenamento, backup e fronteiras de segurança: **190 passaram,
  1 ignorado** no Windows/Python 3.12.
- Regressões finais de histórico, envio, troca de referência e restauração:
  **12 passaram**, incluindo o teste de envio já existente.
- Ruff, links locais e `git diff --check` aprovados.
- Os checks remotos do commit de integração ficam no workflow
  [Qualidade](https://github.com/aglabsrv-sys/orquestra/actions/workflows/qualidade.yml).
  A aprovação remota deve ser conferida no PR antes da mesclagem.

O teste comprova transporte Git e recuperação a partir de outra cópia; não
comprova autenticação de uma conta GitHub específica. Tailscale, calendário
externo e início automático ainda dependem do ambiente escolhido pelo usuário.
Os limites de acesso local, execução de coletores, armazenamento de segredos e
edição simultânea estão em [Segurança](../../SECURITY.md) e
[Backup](../backup.md). Nenhuma publicação de release ou mensagem para a
comunidade faz parte desta revisão.
