# Conectar um agente de IA ao vault

O Orquestra não chama nenhuma IA. Quem trabalha é o agente que você já usa, e a
única coisa que ele precisa é **acesso à pasta do vault**. As regras estão no
`AGENTS.md`, na raiz do vault, e valem para qualquer agente.

Você pode trocar de agente mantendo a mesma pasta. Ao usar mais de um, separe as
notas em que cada um trabalha: editores e agentes externos não participam dos
locks do Orquestra.

## Claude Code

Abra o terminal na pasta do vault e inicie:

```bash
cd ~/Orquestra
```

```bash
claude
```

O vault traz um `CLAUDE.md` com uma linha só (`@AGENTS.md`), que faz o Claude Code
carregar o contrato. Se você já tinha `CLAUDE.md` ou `AGENTS.md` antes da adoção,
eles são preservados: peça também a leitura de `AGENTS.orquestra.md`, quando existir.

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
podem ser agendados. Versões personalizadas exigem revisão e aprovação local;
originais idênticos ao catálogo instalado não exigem aceite extra. Não usam IA; os serviços consultados
podem ter custos ou limites próprios. Veja [coletores.md](coletores.md).

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
- **Histórico Git**: quando autorizado e habilitado, o painel cria snapshots em
  `refs/orquestra/backups`, sem mover sua branch ou staging. Consulte com
  `git log --oneline refs/orquestra/backups` na pasta do vault e recupere primeiro
  uma cópia da nota, seguindo [backup.md](backup.md).

## O que protege você

| Risco | Proteção |
|---|---|
| A IA resume algo e depois trata o resumo como fala sua | Pasta `humano/` separada e campo `origem` em toda nota |
| Outra edição mudou a nota antes da gravação do painel | O painel verifica a versão e oferece preservação do rascunho em caso de conflito; isso não impede outro programa de gravar depois |
| O agente apaga algo | O contrato orienta arquivar; snapshots já feitos e cópias externas permitem recuperar conteúdo preservado |
| Você não sabe o que mudou | O registro do diário vem do vigia de arquivos, não depende de o agente contar |

Agentes com acesso direto à pasta têm as permissões da conta e podem desobedecer
ao `AGENTS.md`. As ferramentas do MCP aplicam suas próprias restrições por código;
elas não restringem ferramentas de arquivo que o mesmo agente já possua. Revise
o que foi alterado e mantenha uma cópia externa, além do histórico local.
