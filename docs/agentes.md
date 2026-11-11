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

## Pedidos para começar

- "Leia o AGENTS.md e me diga o que você entendeu das regras."
- "Processe a minha entrada."
- "Faça a triagem do radar com base no que me interessa."
- "Organize meu dia: o que está para hoje e o que está atrasado?"
- "Escreva o roteiro da ideia X usando a minha voz."
- "Crie um módulo de finanças com receitas e despesas por mês."
- "Crie um tema claro, com capas de mar."

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
