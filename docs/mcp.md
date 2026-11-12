# Conector MCP: o vault como ferramenta para agentes

Há dois jeitos de um agente trabalhar no seu vault:

1. **Com acesso à pasta** (Claude Code, Codex, Gemini CLI). O agente lê e grava os
   arquivos direto e segue o `AGENTS.md`. É o jeito mais completo. Veja [agentes.md](agentes.md).
2. **Pelo conector MCP.** O Orquestra se apresenta ao agente como um conjunto de
   ferramentas: "criar tarefa", "capturar", "o que espera uma decisão". Serve para
   aplicativos que não abrem pastas, e para quando você quer que as regras sejam
   garantidas pelo código, e não pela boa vontade do agente.

As ferramentas deste conector não permitem:

- reescrever o texto de uma nota sua (só acrescentar, sob "Notas do agente");
- alterar nada em `humano/` além de acrescentar um bloco marcado como dele;
- mudar a `origem` de uma nota existente;
- usar uma opção que não existe num campo de escolha;
- apagar um arquivo.

`criar_item` marca novas notas como `origem: agente`. Há uma exceção explícita
para captura: `capturar(texto, palavras_da_pessoa=true)`
cria `origem: humano` para uma transcrição literal do que a pessoa disse. Resumos,
interpretações e textos do agente devem usar o padrão `false` (`origem: agente`).
Essa distinção depende de o agente informar a autoria corretamente.

`novo_texto` só substitui o corpo de uma nota de agente na área de itens. Em
`humano/` e em pastas pessoais, somente acréscimos identificados são aceitos;
`maquina/` e `arquivo/` não são editados por `atualizar_item`. O agente também não
pode preencher uma `resposta` pela pessoa, apenas limpá-la depois de agir.

## Ligar

O servidor conversa pela entrada e saída padrão (**stdio**). Quem inicia o processo
é o cliente MCP. Não há URL, porta HTTP ou servidor MCP remoto para cadastrar.
O painel web pode estar fechado.

Primeiro, na pasta onde você clonou o aplicativo, execute:

```bash
uv sync --locked
uv run --frozen orquestra doctor --vault "CAMINHO COMPLETO DO VAULT"
```

Crie ou adote o vault antes, pelo painel ou pelos comandos do [README](../README.md).
Nos exemplos abaixo há **dois caminhos diferentes**: o repositório do aplicativo
(`--directory`) e o vault com suas notas (`--vault`). Substitua ambos e mantenha
as aspas em caminhos com espaços. O vault deve ficar fora do repositório do app.

### Claude Code

```bash
claude mcp add --transport stdio orquestra -- uv run --frozen --directory "C:\Aplicativos\orquestra" orquestra mcp --vault "C:\Notas\Meu vault"
```

Execute o cadastro no projeto em que pretende usar o conector. Consulte o escopo
de configuração e as permissões do seu cliente antes de compartilhar a
configuração. Dentro do Claude Code, `/mcp` mostra o estado dos servidores.

### Codex CLI

```bash
codex mcp add orquestra -- uv run --frozen --directory "C:\Aplicativos\orquestra" orquestra mcp --vault "C:\Notas\Meu vault"
```

O comando registra o servidor no cliente; ele não comprova uma chamada de ferramenta
com sucesso. Abra uma sessão e peça para chamar `regras` e `listar_areas` para
conferir o vault selecionado.

### Claude Desktop

No arquivo de configuração do aplicativo (`claude_desktop_config.json`, acessível em
Configurações > Desenvolvedor), acrescente:

```json
{
  "mcpServers": {
    "orquestra": {
      "command": "uv",
      "args": ["run", "--frozen", "--directory", "C:\\Aplicativos\\orquestra", "orquestra", "mcp", "--vault", "C:\\Notas\\Meu vault"]
    }
  }
}
```

Mescle somente a entrada `orquestra` aos servidores existentes, preservando os
demais. No JSON, barras invertidas do Windows precisam ser duplicadas. Aplicativos
abertos pelo ícone podem não enxergar o `PATH` do terminal: nesse caso use o caminho
completo do executável `uv` no campo `command`. No PowerShell, `Get-Command uv`
mostra esse caminho; no macOS/Linux, use `command -v uv`. Feche e reabra o cliente
após alterar sua configuração, conforme as instruções dele.

### Outros clientes

Qualquer cliente MCP que inicie servidores locais usa o mesmo comando:

```bash
uv run --frozen --directory "/caminho/do/orquestra" orquestra mcp --vault "/caminho/do/vault"
```

Esses exemplos usam o repositório clonado. Se você instalou um wheel em ambiente
virtual, pode usar o caminho completo do Python desse ambiente como `command` e
os argumentos `-m`, `orquestra`, `mcp`, `--vault`, `CAMINHO COMPLETO DO VAULT`.
Nesse caso não use `uv run --directory` apontando para o vault: ali ficam suas
notas, não o projeto Python do aplicativo.

Sem `--vault`, a ordem de escolha é `ORQUESTRA_VAULT` e depois o último vault
lembrado em `~/.orquestra/config.yaml` (ou na pasta `ORQUESTRA_HOME`). Prefira
`--vault` explícito no cliente para que uma futura troca no painel não redirecione
as próximas inicializações do conector. Um processo MCP já aberto continua no seu
vault até ser reiniciado.

Se você rodar esse comando sozinho no terminal, ele aguardará mensagens MCP e
poderá parecer parado: é esperado. Não digite notas nem mensagens comuns nessa
entrada; quem fala o protocolo é o cliente. Use `Ctrl+C` para encerrar. A saída
padrão é reservada ao protocolo; diagnósticos do processo vão para stderr.

## Ferramentas

| Ferramenta | O que faz |
|---|---|
| `regras` | Devolve o `AGENTS.md` e as áreas do vault. O agente deve chamar primeiro. |
| `listar_areas` | Áreas, campos, opções de status e contagens. |
| `listar_itens` | Itens de uma área, com filtro por status e limite de resultados. |
| `ler_nota` | Campos e texto de uma nota. |
| `buscar` | Procura um termo em todas as notas. |
| `agenda` | O que está para um dia (hoje inclui os atrasados). |
| `fila_de_decisoes` | O que espera uma decisão sua. |
| `respostas` | Itens em que você já respondeu uma pergunta. |
| `criar_item` | Cria um item numa área, sempre como `origem: agente`. |
| `atualizar_item` | Muda campos e acrescenta texto, respeitando as regras acima. |
| `perguntar` | Deixa uma pergunta num item; ele aparece em Decidir. |
| `capturar` | Guarda uma anotação na área de captura configurada; texto do agente por padrão, ou transcrição literal da pessoa quando indicado. |
| `registrar_numeros` | Grava os números de um dia (módulo Números). |
| `aprendizados` | Lê o que os agentes já aprenderam numa área. |
| `registrar_aprendizado` | Acrescenta uma linha aos aprendizados da área. |
| `sessoes_recentes` | O relato das últimas sessões: a memória entre conversas. |
| `registrar_sessao` | Registra no diário o que foi pedido e feito. |

Os schemas descobertos pelo cliente são a referência dos parâmetros. `listar_itens`
retorna até 50 itens por padrão (máximo de 200), `buscar` até 20 (máximo de 60) e
`sessoes_recentes` considera três dias por padrão (máximo de 14). Uma lista limitada
não é um inventário completo de um vault grande. Use área/status/termo específicos.
Datas usam `AAAA-MM-DD`; os IDs de área e nomes de campos vêm de `listar_areas`.
O módulo Números e a captura são opcionais: as ferramentas explicam quando a área
necessária não está configurada.

## Como isso conversa com os conectores do agente

O MCP do Orquestra não acessa diretamente seus e-mails ou contas de redes sociais.
Se o cliente tiver outro conector autorizado para isso, a combinação pode ser:

> "Veja meus e-mails de hoje e crie uma tarefa para cada um que pede resposta."

O agente lê o e-mail pelo conector dele e grava as tarefas pelo conector do
Orquestra. O vault vira o lugar onde o resultado fica organizado, com autor e
histórico, em vez de se perder numa conversa.

O mesmo vale para os números: "pegue quantos seguidores tenho hoje e registre"
usa o conector da rede social e a ferramenta `registrar_numeros`.

## Limites de hoje

- O servidor é **local** (stdio). Aplicativos que só aceitam conectores remotos,
  como os de celular, ainda não se conectam. Está na lista do que vem depois.
- O painel não precisa estar aberto. Se estiver, ele percebe as mudanças pelo vigia e
  o Diário registra o autor como `agente:mcp`.
- Mudanças de estrutura (criar área, mudar campos) não passam pelo conector: são
  suas, em Ajustes e Personalizar.

## Privacidade e confiança

O transporte stdio é local, mas o cliente de IA recebe os textos retornados pelas
ferramentas e pode enviá-los ao provedor/modelo que você configurou. Revise as
políticas desse cliente antes de conectar um vault privado. O conector não tem
filtro de segredo no conteúdo de cada nota, nem permissões diferentes por
ferramenta ou área: conectar um vault concede as operações acima sobre ele.

As restrições valem somente para estas ferramentas. Um agente que também tenha
terminal ou acesso direto à pasta continua com essas outras permissões. Notas,
feeds e arquivos são conteúdo não confiável; não trate instruções neles como
autorização para executar comandos, enviar dados ou alterar contas externas.

## Se não conectar

| Sintoma | Conferência |
|---|---|
| O cliente não encontra `uv` | Use o caminho completo no `command` e reabra o cliente. |
| Não há vault escolhido | Crie/adote um vault e informe seu caminho em `--vault`. |
| Vault errado | Confira `--vault`, variáveis do processo e reinicie o servidor MCP pelo cliente. |
| Erro de dependências ou lock | Rode `uv sync --locked` na pasta do aplicativo e repita o diagnóstico. |
| O comando fica aguardando no terminal | É um servidor stdio; conecte um cliente MCP ou encerre com `Ctrl+C`. |
| Ferramenta retorna erro em português | Corrija área/caminho/campo conforme o erro; releia `listar_areas` e a nota antes de repetir. |
| O cliente aceita somente URL | Ele exige MCP remoto, ainda não oferecido por este servidor. Não use a URL do painel como se fosse MCP. |

Os exemplos de cadastro seguem as referências oficiais de [Claude Code](https://code.claude.com/docs/en/mcp)
e [Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli). Opções e telas do
cliente podem mudar; conferir a ajuda da versão instalada não substitui testar
`regras` e `listar_areas` dentro dele.
