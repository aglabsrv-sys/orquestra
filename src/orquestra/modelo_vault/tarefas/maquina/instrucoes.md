# Instruções para agentes: Tarefas

Leia antes `tarefas/_modulo.yaml` e `tarefas/humano/`.

## O que você pode fazer

- Criar tarefas em `tarefas/itens/` com `origem: agente`, sempre com `data` quando houver prazo.
- Mudar `status` para `fazendo` quando começar a trabalhar numa tarefa que é sua.
- Quando terminar algo que precisa do olho da pessoa, mudar para `aguardando` e, se
  houver uma dúvida concreta, preencher `pergunta`. Isso leva o item para a fila Decidir.

## O que você não faz

- Marcar como `feito` uma tarefa com `origem: humano`. Use `aguardando`.
- Alterar o texto de tarefas com `origem: humano`. Acrescente `## Notas do agente` ao final.
- Criar tarefas vagas. O título começa com um verbo e diz o resultado: "Editar corte de 60s do vídeo X".

## Revisão diária (quando pedirem "organize meu dia")

1. Liste o que tem `data` de hoje ou anterior e não está `feito`.
2. Confira com as regras de `humano/Como eu priorizo.md`.
3. Proponha a ordem do dia na sessão do diário. Não reordene nada sozinho.
