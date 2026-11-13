# Revisão de comandos, MCP e documentação — 11 de novembro de 2026

Revisão implementada sobre o refinamento de UI/UX. Os comandos foram executados
com vaults e configurações descartáveis; nenhuma nota ou configuração de cliente
MCP real foi usada. Não houve envio a remoto, publicação ou ativação de login.

## Correções

| Prioridade | Achado | Correção |
| --- | --- | --- |
| Importante | A instalação editável falhava no Windows/Python 3.11–3.12 quando o caminho do aplicativo continha acentos | Ativado o modo editável exato do Hatch, com `editables>=0.5,<1` incluído no lock. O arquivo `.pth` usa import ASCII; o caminho Unicode fica no módulo Python. Mantém edição sem reinstalar. |
| Importante | O SDK MCP mínimo declarado, 1.2.0, não iniciava com Pydantic atual | Faixa ajustada para `mcp>=1.30,<3`, com SDKs 1.30.0 e 2.3.0 verificados. Erros de importação agora orientam reparo sem traceback nem texto em stdout. |
| Importante | Acrescentar texto pelo MCP removia linhas vazias finais da nota humana | O corpo anterior é preservado e somente o separador necessário é acrescentado. Teste real com CRLF e três linhas vazias protege o prefixo original. |
| Importante | Coleta falha ou módulo inexistente retornavam sucesso | Saída `1` em falha; módulo sem coletores continua sendo uma consulta válida com saída `0`. |
| Importante | Autorizações com módulo/script inválido exibiam traceback; argumentos podiam ser ignorados | Erros explicados em português; `--assinatura` e `--revogar` são mutuamente exclusivos. `confiar backup` recusa módulo/script extra. |
| Importante | `--vault` global podia ser ignorado por `criar`/`adotar` e usar outro destino | Esses comandos recusam a opção e orientam o caminho posicional. `--vault` vazio também é recusado antes de gravar. |
| Importante | Desligar autostart exigia que o vault anterior ainda existisse | `status` e `desativar` dispensam vault; `ativar` continua exigindo pasta existente. |
| Importante | Doctor podia ocultar YAML inválido, abortar em script ausente ou apresentar componentes não autorizados como funcionando | Diagnóstico continua, mostra configuração inválida, autorização pendente e limites do backup. Captura desativada deixa de gerar aviso incorreto. |
| Importante | Doctor confundia serviço na porta com Orquestra e porta 18420 com 8420 | Relata somente a conexão TCP observada; compara URL e porta local exatas no Serve. Configuração encontrada não é apresentada como acesso real de celular. |
| Desejável | Ajuda pós-criação pressupunha uso de uv e a sugestão de porta podia ultrapassar 65535 | Orientação adequada para pacote instalado e checkout; sugestão de porta permanece no intervalo permitido. |
| Desejável | Guias descreviam recuperação Git e autoria MCP diferentes do código | Corrigidos referência de backup, aprovação, limites de autoria/captura, seleção de vault, ambiente de coletores e exemplos dos clientes. |

## Comandos conferidos

- Ajuda principal, versão e ajuda dos 11 subcomandos/aliases: `criar`, `init`,
  `adotar`, `iniciar`, `mcp`, `doctor`, `diagnostico`, `coletar`, `backup`,
  `confiar` e `autostart`.
- Criação e adoção reais, com espaços e acentos, preservando nota preexistente
  com BOM, comentários e CRLF. Repetir a criação preserva o vault existente.
- `--vault` antes e depois dos subcomandos que o aceitam, argumentos inválidos
  e códigos de saída: `0` conclusão, `1` falha de operação/diagnóstico,
  `2` erro de argumentos.
- `iniciar` respondeu HTTP na porta local configurada e foi encerrado.
- Backup local: preparar, revisar assinatura, autorizar e criar snapshot.
  Enviar sem remoto retornou falha; não foi configurado destino externo.
- Coletor local inofensivo: revisar, autorizar, executar e revogar. Scripts de
  catálogo sem aprovação foram recusados antes de chamar provedores.
- Autostart: status isolado e desativação em arquivo temporário simulado.
  Não foi ativado nem desativado o início automático real da máquina.

## MCP real

Os testes iniciam `python -m orquestra mcp --vault ...` em outro processo e
trocam JSON-RPC por stdio: initialize, descoberta dos schemas e chamadas das
**17 ferramentas**. Conferem erros em português, origem, proteção de notas
humanas, traversal, valores inválidos, mudanças externas, UTF-8, stdout somente
com mensagens do protocolo e encerramento por EOF.

O smoke dos pacotes usa também `ClientSession` do SDK oficial em venv nova:
inicialização, lista de ferramentas, leitura de regras e gravação de captura.
Uma terceira instalação copia o checkout para um caminho com espaços e acentos,
sincroniza sem dependências de desenvolvimento e testa o launcher `uv run
--frozen --directory ... orquestra mcp --vault ...` fora da pasta do aplicativo.

O SDK 1.2.0 foi reproduzido como incompatível por depender de API privada removida
do Pydantic. O diagnóstico corrigido terminou com saída `1`, zero bytes em stdout
e orientação de reparo. Não foi criado um patch sobre a API privada do SDK antigo.

## Documentação

README, guias de agentes, MCP, backup, coletores, Tailscale, vault existente,
arquitetura, SECURITY e contrato do modelo foram comparados ao código.

- Separação explícita entre pasta do aplicativo e pasta do vault.
- Exemplos stdio para Claude Code, Codex CLI e JSON do Claude Desktop; caminho
  explícito do vault, cuidado com PATH e escapes do Windows.
- Captura literal pode ser `origem: humano`; resumos do agente continuam sendo
  `origem: agente`. A distinção depende do parâmetro informado pelo agente.
- Backups usam `refs/orquestra/backups`, sem mover a branch/staging do usuário.
  Removidas recomendações antigas de checkout sobre trabalho atual e promessas
  de recuperar qualquer alteração anterior ao primeiro snapshot.
- Aprovação local, agenda opcional, ambiente mínimo de coletores e privacidade
  do provedor de IA descritos com seus limites.
- Testes automáticos verificam destinos de links locais, as 17 ferramentas da
  tabela e o JSON copiável de configuração do MCP.

O modo exato de instalação editável pode exigir configurar `src` como raiz de
fontes na IDE para autocomplete; isso está explicado em CONTRIBUTING.

## Evidências e limites

- Windows/Python 3.12.14, SDK fixado no lock: **336 testes aprovados e 1 ignorado**
  em 251,19 segundos. O caso ignorado depende de symlink de arquivo no Windows;
  testes de junctions continuam executados. Ruff e `git diff --check` aprovados.
- Windows/Python 3.11.16 + MCP SDK 1.30.0: **35 testes focados aprovados**.
  Houve um aviso de depreciação de TestClient/httpx na combinação de dependências
  resolvida para esse ambiente; nenhum teste falhou.
- SDK 2.3.0: protocolo stdio real e pacote instalado verificados.
- Editables 0.5 e 0.6: importação e CLI conferidas em caminho Unicode;
  a versão 0.6 está fixada no lock. Venv nova sem dependências de desenvolvimento
  e sessões MCP passaram no cenário Windows/cp1252/Python 3.11.
- Wheel e sdist: instalados em ambientes novos, com CLI, catálogo, recursos e
  sessão MCP real. O checkout editável também passou pelo mesmo smoke.
- Auditoria das **38 dependências de execução**: nenhuma vulnerabilidade conhecida
  encontrada e nenhuma dependência ignorada.
- CI mantém os gates existentes e acrescenta protocolo MCP com SDKs 1.30.0/2.3.0
  em Python 3.11; o smoke de instalação roda na matriz de sistemas/Python existente.

CI remota não foi executada nesta rodada. macOS/Linux nativos, login automático,
autenticação/envio Git externo, Tailscale em rede real e chamadas dentro dos
aplicativos Claude/Codex continuam pendentes. Os exemplos desses clientes foram
conferidos na ajuda/documentação; o protocolo foi testado diretamente por clientes
de teste, sem cadastrar ou alterar conectores do usuário.

## Referências

- [Transporte stdio do MCP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Comandos e seleção de diretório do uv](https://docs.astral.sh/uv/reference/cli/#uv-run)
- [Modo editável do Hatch](https://hatch.pypa.io/latest/config/build/#dev-mode)
- [Leitura de arquivos .pth no CPython 3.11](https://github.com/python/cpython/blob/v3.11.16/Lib/site.py#L169)
- [MCP no Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [MCP no Claude Code](https://code.claude.com/docs/en/mcp)
