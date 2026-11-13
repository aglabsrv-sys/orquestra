# Revisão e refinamento para a comunidade — 12/11/2026

Alterações locais sobre a versão 0.4.0. Nenhum commit, push, publicação ou conexão
a contas reais foi feito nesta revisão. Vaults de teste são sintéticos e isolados.

## Resultado da implementação

- Boas-vindas com etapas e paginação das escolhas; aviso final sobre manter o processo
  aberto, reabrir e configurar início automático. Verificação visual em desktop e
  celular 390 × 844. Não há corte deliberado de conteúdo quando a pessoa usa zoom
  ou fonte grande: acessibilidade pode exigir rolagem em telas menores.
- Ajustes separados por URL, em vez de âncoras. Tamanho da fonte validado no backend;
  modo, cantos, fonte e destaque aplicados sem recarregar a página.
- Formulários alinhados pelo topo, controles com altura consistente, opções nas
  cores do tema, ajuda contextual e envio discreto de miniaturas.
- Expansor nativo de recuperação removido; consulta e criação de cópias continuam
  acessíveis por botão. O histórico de proteção não foi eliminado.
- Entrada sem a aba Humano redundante; explicação da diferença entre itens,
  orientações humanas e infraestrutura da máquina.
- Coletores originais comparados integralmente ao catálogo da instalação; versões
  alteradas continuam exigindo aceite local. Revogação explícita tem precedência.
- Pomodoro simples com pausas e relógio baseado em prazo, preservado na sessão.
- Agenda diária com navegação semanal e assistente iCal; link guardado fora do vault.
- Hábitos e metas opcionais, exemplos e mapa de 84 dias com controle de versão nas
  marcações. O módulo Áreas foi mantido para preservar o método PARA.
- Aprovação de criativos com preview e ações Aprovar/Pedir ajustes. Há migração
  aditiva para pipelines existentes; não publica conteúdo em serviços externos.
- Seletor de capas com cenas animadas e mídia local limitada a 2 MB; vídeos em loop
  com pausa fora da tela e respeito à preferência de movimento reduzido.
- Login oficial no GitHub por CLI, seleção de repositório privado e configuração
  explícita de URLs de leitura e envio. Não faz push durante a vinculação.
- Guia Tailscale com liberação local de hostname exato, aplicada sem reiniciar;
  HTTPS de Serve aceito com comparação de origem completa. Outros hosts/origens
  continuam bloqueados e o canal local não é entregue ao proxy.
- Painel de variáveis sem leitura de valores pela API, fora do vault, com validação
  de nomes/linhas e escrita serializada sem cópia dos segredos em recuperação.
- Botões de início automático e comandos `desinstalar`/`uninstall` para orientar a
  remoção e desligar a inicialização, preservando os dados.
- Monitor de arquivos avisa sobre novidades sem recarregar a tela automaticamente.
  A navegação continua com HTML do servidor; não foi criada uma SPA paralela.
- README, guia de coletores, segurança, Tailscale e agentes atualizados; créditos
  solicitados incluídos no README.

## Validação

- Ruff e sintaxe dos arquivos JavaScript: passaram.
- Testes JavaScript: 29 passaram.
- Testes Python: 359 casos validados somando a execução integral e os complementares;
  1 caso de symlink Unix ignorado no Windows. A execução integral teve 357 sucessos
  e encontrou um teste que ainda exigia bloquear os originais do catálogo. Esse teste
  foi atualizado para verificar o bloqueio de código personalizado e passou na
  repetição isolada. Um teste adicional de concorrência no upgrade iCal também passou.
  Não houve uma segunda execução integral depois dessa atualização do contrato.
- `uv build`: wheel e sdist gerados. O primeiro teste offline não encontrou hatchling
  no cache; o build normal baixou o backend oficial e concluiu.
- `scripts/verificar_pacote.py dist`: passou para wheel, sdist, catálogo, CLI instalada,
  inicialização/leitura/gravação MCP stdio e instalação editável em caminho Unicode.
- `pip-audit` sobre as dependências fixadas exportadas do lock: nenhuma vulnerabilidade
  conhecida encontrada. Isso não é uma garantia sobre falhas ainda desconhecidas.
- Interface conferida no navegador: boas-vindas, escolha de modelos, capa com previews,
  formulário de Conteúdo, páginas de ajustes e navegação da agenda.
- Graphify não estava instalado; a leitura de arquitetura foi feita diretamente nas
  fontes, contratos, testes e documentação. Gitleaks não está disponível nesta máquina;
  não houve uma nova varredura automatizada de segredos com essa ferramenta.

Os testes exigem diretório temporário fora da pasta do programa. O ambiente restrito
bloqueou o cache do uv em um teste CLI e no verificador de pacote. Ambos passaram
ao repetir com acesso ao cache; nenhuma proteção do produto foi removida para isso.

## Limites antes do anúncio

1. Validar login e backup com uma conta/repositório privado de teste no GitHub,
   incluindo o gerenciador de credenciais do sistema. A integração foi testada com
   comandos simulados, não autenticada contra uma conta real nesta revisão.
2. Validar Tailscale Serve e celular reais, com política de acesso da rede revisada.
   Os testes locais verificam cabeçalhos, hostname e origem, não uma tailnet real.
3. Testar o link iCal de cada provedor que será anunciado. O importador atual não
   implementa sincronização bidirecional, expansão RRULE nem reconciliação completa
   de alterações e exclusões. A interface e a documentação declaram essas limitações.
4. Confirmar início automático em sessões reais de Windows/macOS/Linux. A mudança
   reaproveita o mecanismo existente; não instalou um serviço no computador do usuário.
5. Validar os vídeos reais e mantê-los compactos: há limite de bytes e detecção básica
   de formato, sem transcodificação, validação integral ou remoção de metadados.
6. Executar a matriz CI de plataformas/Python no remoto antes de anunciar suporte
   amplo. Nesta sessão não houve push nem execução nova do GitHub Actions.

O painel continua local, sem autenticação por usuário. Disponibilizar o código à
comunidade não significa publicar um vault na internet. Não usar Funnel ou exposição
pública direta como implantação desta versão.

Guia do usuário: [Experiência da comunidade](../experiencia-comunidade.md).
