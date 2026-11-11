# Instruções para agentes: Entrada

Tudo em `entrada/itens/` foi escrito pela pessoa, quase sempre com pressa e no
celular. É a fala dela: **não edite o texto**.

Para cada item com `status: novo`:

1. Entenda o que é: uma tarefa, uma ideia de conteúdo, uma referência, ou um pedido para você.
2. Leve para o lugar certo:
   - tarefa → `tarefas/itens/`
   - ideia de conteúdo → `conteudo/itens/` com `status: ideia`
   - referência → `radar/itens/` com `status: util`
   - pedido para você → execute, seguindo as instruções do módulo envolvido
3. No item novo, use `origem: agente` e cite a captura com `[[nome da captura]]`.
4. Na captura, mude `status` para `processado` e preencha `destino` com o que ela
   virou (por exemplo `[[Gravar vídeo sobre X]]`).

Uma captura pode virar mais de uma coisa. Se não der para saber o que ela quis
dizer, preencha `pergunta` na própria captura e deixe como `novo`.
