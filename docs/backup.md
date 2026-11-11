# Histórico e backup

O vault é um repositório git próprio, separado do repositório do app. Isso dá
duas coisas diferentes:

- **Histórico (local):** cada commit é um ponto para onde você pode voltar. É o
  "desfazer" para qualquer alteração, sua ou de um agente.
- **Backup (remoto):** uma cópia fora do computador, para o dia em que ele quebrar.

## Histórico: já vem ligado

Ao criar o vault, o Orquestra inicia o git e faz o primeiro commit. Com o painel
aberto, ele faz um commit automático a cada 30 minutos, se algo mudou. Para fazer
um na hora:

```bash
uv run orquestra backup
```

Ou em **Ajustes > Histórico e backup**. As opções ficam no `orquestra.yaml`:

```yaml
backup:
  auto_commit: true
  intervalo_min: 30
```

### Voltar atrás

Dentro da pasta do vault:

```bash
git log --oneline
```

Para ver como um arquivo estava num commit antigo (troque `abc123` e o caminho):

```bash
git show abc123:"tarefas/itens/Minha tarefa.md"
```

Para restaurar esse arquivo como estava:

```bash
git checkout abc123 -- "tarefas/itens/Minha tarefa.md"
```

Se não tem prática com git, peça ao agente: "restaure o arquivo X como estava ontem".

## Backup: enviar para um repositório privado

1. Crie um repositório **privado** e **vazio** no GitHub (ou GitLab, ou outro).
   Privado mesmo: o vault tem as suas tarefas, ideias e anotações.
2. Dentro da pasta do vault, ligue os dois (troque pelo endereço do seu repositório):

   ```bash
   git remote add origin https://github.com/voce/meu-vault.git
   ```

3. Envie pela primeira vez:

   ```bash
   uv run orquestra backup --enviar
   ```

4. Para enviar sozinho todo dia, no `orquestra.yaml`:

   ```yaml
   backup:
     push: true
     push_as: "03:00"
   ```

Se o computador estava desligado no horário, o envio acontece quando o painel voltar.

## Em outro computador

```bash
git clone https://github.com/voce/meu-vault.git ~/Orquestra
```

```bash
uv run orquestra --vault ~/Orquestra
```

Faltam só as chaves de API (`~/.orquestra/.env`), que ficam fora do vault e não vão
no backup: copie à mão.

## O que não entra no backup

O `.gitignore` do vault deixa de fora o estado do painel (`_orquestra/estado.json`),
a área de trabalho do Obsidian e a lixeira. Segredos nunca devem estar no vault.

## Obsidian Sync, iCloud, Dropbox

Funcionam junto com o git, mas evite abrir o mesmo vault em dois computadores com
o painel rodando nos dois: os commits automáticos de um e do outro vão brigar.
