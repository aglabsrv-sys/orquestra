# Conectar um agente de IA ao vault

O Orquestra não chama nenhuma IA. Quem trabalha é o agente que você já usa, e a
única coisa que ele precisa é **acesso à pasta do vault**. As regras estão no
`AGENTS.md`, na raiz do vault, e valem para qualquer agente.

Por isso você pode trocar de agente quando quiser, ou usar dois ao mesmo tempo: o
sistema é a pasta, não a ferramenta.

## Claude Code

Abra o terminal na pasta do vault e inicie:

```bash
cd ~/Orquestra
```

```bash
claude
```

O vault traz um `CLAUDE.md` com uma linha só (`@AGENTS.md`), que faz o Claude Code
carregar o contrato sozinho a cada sessão. No aplicativo de desktop, escolha a pasta
do vault como pasta de trabalho.

## Codex (OpenAI)

O Codex lê `AGENTS.md` por padrão. Basta iniciar dentro da pasta:

```bash
cd ~/Orquestra
```

```bash
codex
```

## Gemini CLI e outros

Inicie o agente na pasta do vault e, na primeira mensagem, peça:

> Leia o arquivo AGENTS.md desta pasta e siga as regras dele.

Qualquer agente que consiga ler e gravar arquivos funciona, inclusive assistentes
com acesso a pastas do computador.

## Aplicativos que não abrem pastas

Para aplicativos de conversa, o Orquestra oferece um **conector MCP**: o agente usa
ferramentas como "criar tarefa" e "capturar", e as regras do contrato são aplicadas
pelo código. Veja [mcp.md](mcp.md).

## E os conectores de e-mail, agenda, redes sociais?

Ficam com o agente, que já os tem. O Orquestra não duplica essas integrações: quem
lê o e-mail ou a agenda é o agente, e o vault é onde o resultado fica organizado.
"Veja meus e-mails e crie uma tarefa para cada um que pede resposta" funciona com
qualquer agente que tenha o conector de e-mail e acesso ao vault.

O que o Orquestra faz por conta própria são os **coletores**: scripts simples que
rodam sozinhos todo dia, sem IA e sem custo. Veja [coletores.md](coletores.md).

## Pedidos para começar

- "Leia o AGENTS.md e me diga o que você entendeu das regras."
- "Processe a minha entrada."
- "Faça a triagem do radar com base no que me interessa."
- "Organize meu dia: o que está para hoje e o que está atrasado?"
- "Escreva o roteiro da ideia X usando a minha voz."
- "Crie um módulo de finanças com receitas e despesas por mês."
- "Crie um tema claro, com capas de mar."

## Agentes que aprendem com o uso

Cada área tem um `maquina/aprendizados.md`. O contrato manda o agente ler antes de
começar e acrescentar uma linha ao terminar, quando aprendeu algo que vale para a
próxima vez: uma correção sua, um resultado medido, algo a evitar. Você vê (e pode
editar) na aba **Máquina** da área.

Dois pedidos que ajudam:

- "Antes de começar, leia os aprendizados do módulo de conteúdo."
- "Anote nos aprendizados que eu não quero títulos em caixa alta."

## Como acompanhar o que o agente fez

- **Diário** (ícone de pulso no dock): mostra o relato que o agente escreveu ao fim
  da sessão e, abaixo, o registro automático de cada arquivo criado ou alterado.
- **Decidir** (ícone de sino): as perguntas que o agente deixou para você.
- **Histórico git**: o painel faz commits automáticos do vault. Se um agente fizer
  besteira, `git log` e `git checkout` dentro do vault desfazem.

## O que protege você

| Risco | Proteção |
|---|---|
| A IA resume algo e depois trata o resumo como fala sua | Pasta `humano/` separada e campo `origem` em toda nota |
| O agente sobrescreve o que você está editando | O painel confere a versão do arquivo antes de gravar e avisa se mudou |
| O agente apaga algo | A regra é arquivar, não apagar; e o git guarda o histórico |
| Você não sabe o que mudou | O registro do diário vem do vigia de arquivos, não depende de o agente contar |

Essas proteções dependem, em parte, de o agente seguir o `AGENTS.md`. Agentes
atuais seguem bem, mas não são infalíveis: o histórico git é a rede de segurança
que não depende deles.
