# Conector MCP: o vault como ferramenta para agentes

Há dois jeitos de um agente trabalhar no seu vault:

1. **Com acesso à pasta** (Claude Code, Codex, Gemini CLI). O agente lê e grava os
   arquivos direto e segue o `AGENTS.md`. É o jeito mais completo. Veja [agentes.md](agentes.md).
2. **Pelo conector MCP.** O Orquestra se apresenta ao agente como um conjunto de
   ferramentas: "criar tarefa", "capturar", "o que espera uma decisão". Serve para
   aplicativos que não abrem pastas, e para quando você quer que as regras sejam
   garantidas pelo código, e não pela boa vontade do agente.

Pelo conector, um agente **não consegue**:

- reescrever o texto de uma nota sua (só acrescentar, sob "Notas do agente");
- alterar nada em `humano/` além de acrescentar um bloco marcado como dele;
- criar algo sem `origem: agente`, ou mudar a `origem` de uma nota;
- usar uma opção que não existe num campo de escolha;
- apagar um arquivo.

## Ligar

O servidor conversa pela entrada e saída padrão (stdio). Quem o inicia é o próprio
aplicativo do agente; você só precisa dizer qual é o comando. Troque o caminho pela
pasta onde você baixou o Orquestra.

### Claude Code

```bash
claude mcp add orquestra -- uv run --directory "C:\caminho\do\orquestra" orquestra mcp
```

### Claude Desktop

No arquivo de configuração do aplicativo (`claude_desktop_config.json`, acessível em
Configurações > Desenvolvedor), acrescente:

```json
{
  "mcpServers": {
    "orquestra": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\caminho\\do\\orquestra", "orquestra", "mcp"]
    }
  }
}
```

### Outros clientes

Qualquer cliente MCP que inicie servidores locais usa o mesmo comando:

```bash
uv run --directory "/caminho/do/orquestra" orquestra mcp
```

O servidor usa o vault que o painel usa (o último que você escolheu). Para apontar
outro, acrescente `--vault "/caminho/do/vault"` ao final do comando.

## Ferramentas

| Ferramenta | O que faz |
|---|---|
| `regras` | Devolve o `AGENTS.md` e as áreas do vault. O agente deve chamar primeiro. |
| `listar_areas` | Áreas, campos, opções de status e contagens. |
| `listar_itens` | Itens de uma área, com filtro por status. |
| `ler_nota` | Campos e texto de uma nota. |
| `buscar` | Procura um termo em todas as notas. |
| `agenda` | O que está para um dia (hoje inclui os atrasados). |
| `fila_de_decisoes` | O que espera uma decisão sua. |
| `respostas` | Itens em que você já respondeu uma pergunta. |
| `criar_item` | Cria um item numa área, sempre como `origem: agente`. |
| `atualizar_item` | Muda campos e acrescenta texto, respeitando as regras acima. |
| `perguntar` | Deixa uma pergunta num item; ele aparece em Decidir. |
| `capturar` | Guarda uma anotação rápida na Entrada. |
| `registrar_numeros` | Grava os números de um dia (módulo Números). |
| `aprendizados` | Lê o que os agentes já aprenderam numa área. |
| `registrar_aprendizado` | Acrescenta uma linha aos aprendizados da área. |
| `sessoes_recentes` | O relato das últimas sessões: a memória entre conversas. |
| `registrar_sessao` | Registra no diário o que foi pedido e feito. |

## Como isso conversa com os conectores do agente

O Orquestra não tem integração com e-mail, agenda ou redes sociais, de propósito:
os aplicativos de IA já trazem esses conectores. A combinação é:

> "Veja meus e-mails de hoje e crie uma tarefa para cada um que pede resposta."

O agente lê o e-mail pelo conector dele e grava as tarefas pelo conector do
Orquestra. O vault vira o lugar onde o resultado fica organizado, com autor e
histórico, em vez de se perder numa conversa.

O mesmo vale para os números: "pegue quantos seguidores tenho hoje e registre"
usa o conector da rede social e a ferramenta `registrar_numeros`.

## Limites de hoje

- O servidor é **local** (stdio). Aplicativos que só aceitam conectores remotos,
  como os de celular, ainda não se conectam. Está na lista do que vem depois.
- O painel não precisa estar aberto. Se estiver, ele mostra as mudanças na hora e
  o Diário registra o autor como `agente:mcp`.
- Mudanças de estrutura (criar área, mudar campos) não passam pelo conector: são
  suas, em Ajustes e Personalizar.
