# Orquestra

**Um painel local para trabalhar com agentes de IA em cima de uma pasta de arquivos markdown.**

Você já usa ChatGPT, Claude ou Gemini todo dia, mas cada conversa começa do zero e
nada fica organizado em lugar nenhum. O Orquestra resolve isso com uma ideia simples:
suas tarefas, seu conteúdo e sua pesquisa viram arquivos de texto numa pasta. O
painel mostra essa pasta de um jeito bonito e rápido; seus agentes trabalham direto
nela; e você abre no Obsidian quando quiser.

![Tela inicial do Orquestra](docs/img/inicio.png)

- **Roda no seu computador.** Sem conta, sem nuvem, sem mensalidade. Os dados são arquivos seus.
- **Funciona com qualquer agente.** Claude, Codex, Gemini: basta dar acesso à pasta. As regras ficam num `AGENTS.md`.
- **Separa o que você disse do que a IA escreveu.** Um resumo da máquina nunca vira "fala sua".
- **Abre no celular** pela sua rede privada do Tailscale.
- **Compatível com o Obsidian.** O vault abre normalmente; o painel só acrescenta o que falta.

| Quadro de tarefas | Pipeline de conteúdo |
|---|---|
| ![Módulo Tarefas](docs/img/tarefas.png) | ![Módulo Conteúdo](docs/img/conteudo.png) |

## O que vem pronto

| | |
|---|---|
| **Tarefas** | Quadro e lista, com prioridade, data e o que é para hoje. |
| **Conteúdo** | Pipeline de ideia a publicado, por plataforma, com miniaturas. |
| **Radar** | Coletores trazem vídeos, posts e assuntos em alta. Você (ou um agente) faz a triagem. |
| **Entrada** | Captura rápida: anote do celular, um agente organiza depois. |
| **Decidir** | Uma fila só com tudo que espera você, incluindo perguntas dos agentes. |
| **Diário** | O que mudou no vault e o que cada agente fez, com autor e horário. |
| **Temas** | Três temas com capas em pixel art animadas, desenhadas por código. |

Cada área é um **módulo**: uma pasta com um arquivo de configuração. Para criar a
sua (finanças, clientes, estudos), é só pedir a um agente.

## Instalação

Leva uns dez minutos. Você precisa de duas ferramentas gratuitas: o **uv**
(instala o Python e as dependências sozinho) e o **git**.

### Windows

1. Abra o **PowerShell** e instale o uv:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. Instale o git: baixe em <https://git-scm.com/download/win> e avance com as opções padrão.
3. **Feche e abra o PowerShell de novo**, para ele enxergar os dois.

### macOS e Linux

1. Abra o **Terminal** e instale o uv:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. O git já vem no Linux. No macOS, rode `git --version`: se não estiver instalado, o sistema oferece instalar.
3. Feche e abra o Terminal de novo.

### Baixar e iniciar (todos os sistemas)

```bash
git clone https://github.com/antoniogsouzaag/orquestra.git
```

```bash
cd orquestra
```

Crie o seu vault. Por padrão ele fica na pasta `Orquestra`, dentro da sua pasta pessoal:

```bash
uv run orquestra criar
```

Inicie o painel:

```bash
uv run orquestra iniciar --abrir
```

O navegador abre em <http://localhost:8420> já com exemplos preenchidos. Na primeira
vez o `uv` baixa o que precisa e demora um pouco mais.

Para encerrar, `Ctrl+C` no terminal. Nas próximas vezes, basta entrar na pasta e
rodar `uv run orquestra`.

> Algo não funcionou? Rode `uv run orquestra doctor`. Ele confere a instalação e
> explica, em português, o que falta.

## Primeiros passos

1. **Olhe os exemplos.** Arraste um cartão no quadro de Tarefas, abra uma nota, aperte `C` para capturar uma ideia.
2. **Diga quem você é.** Em cada módulo, a aba **Humano** tem uma nota de exemplo (como você prioriza, sua voz, o que te interessa). Reescreva com as suas regras: é o que os agentes leem antes de agir.
3. **Conecte um agente.** Abra o Claude Code ou o Codex na pasta do vault e peça: "leia o AGENTS.md e processe a minha entrada". Detalhes em [docs/agentes.md](docs/agentes.md).
4. **Ligue os coletores.** Em Radar > Máquina, troque os canais de exemplo pelos seus. Veja [docs/coletores.md](docs/coletores.md).
5. **Abra no celular.** Siga [docs/tailscale.md](docs/tailscale.md).
6. **Abra no Obsidian** (opcional): "Abrir pasta como cofre" e escolha a pasta do vault.

## Como funciona

```
seu vault/
  AGENTS.md            as regras que todo agente lê
  orquestra.yaml       nome, tema, backup
  tarefas/             um módulo
    _modulo.yaml       campos, status, visões
    itens/             uma nota .md por tarefa
    humano/            o que VOCÊ disse (agentes leem, não reescrevem)
    maquina/           instruções para agentes e coletores
  conteudo/  radar/  entrada/
  diario/              o que mudou e o que os agentes fizeram
  _orquestra/temas/    cores e capas
```

Uma tarefa é só isto:

```markdown
---
status: a_fazer
prioridade: alta
data: 2026-01-15
origem: humano
---

Gravar o vídeo principal da semana.
```

Você edita no painel, no Obsidian ou pede a um agente: é o mesmo arquivo. Se ele
mudar no disco enquanto está aberto no painel, a tela se atualiza; se você estiver
editando, o painel avisa em vez de sobrescrever.

### Humano e máquina

É a regra que mais importa. Em cada módulo:

- `humano/` guarda o que você disse ou decidiu. Agentes leem sempre e nunca reescrevem.
- `maquina/` guarda o que faz o sistema andar: instruções e scripts.
- Toda nota tem um campo `origem` (`humano`, `agente` ou `coletor`).

Sem isso, depois de algumas semanas ninguém sabe mais o que foi ideia sua e o que
foi um resumo que a IA fez de uma ideia sua.

### Coletar é script, decidir é IA

Buscar os vídeos novos de um canal não precisa de inteligência: um script faz todo
dia, de graça. A IA entra depois, para dizer quais valem o seu tempo. Os coletores
do Orquestra são scripts Python pequenos, que você pode ler e adaptar.

## Comandos

Rode dentro da pasta do Orquestra.

| Comando | O que faz |
|---|---|
| `uv run orquestra` | Inicia o painel |
| `uv run orquestra criar [pasta]` | Cria um vault novo |
| `uv run orquestra doctor` | Confere tudo e explica o que falta |
| `uv run orquestra coletar [módulo]` | Roda os coletores agora |
| `uv run orquestra backup [--enviar]` | Commit do vault (e envio ao remoto) |
| `uv run orquestra autostart ativar` | Inicia o painel junto com o computador |
| `uv run orquestra --vault PASTA` | Usa outro vault (e passa a lembrar dele) |

## Documentação

| | |
|---|---|
| [Conectar agentes](docs/agentes.md) | Claude Code, Codex, Gemini e o que pedir a eles |
| [Celular com Tailscale](docs/tailscale.md) | Acesso remoto sem expor nada à internet |
| [Módulos](docs/modulos.md) | Criar áreas novas e a referência do `_modulo.yaml` |
| [Temas e capas](docs/temas.md) | Cores, paletas, suas imagens e as cenas em pixel art |
| [Coletores](docs/coletores.md) | Configurar os prontos e escrever o seu |
| [Histórico e backup](docs/backup.md) | Desfazer alterações e guardar uma cópia fora do computador |
| [Arquitetura](docs/arquitetura.md) | Como o código está organizado, para estudar ou contribuir |

## Segurança, em três linhas

- O painel **não tem senha** e escuta só no seu computador (`127.0.0.1`).
- No celular, use **`tailscale serve`**. **Nunca** use `tailscale funnel` nem abra a porta no roteador.
- Chaves de API ficam em `~/.orquestra/.env`, **fora** do vault. Mantenha o backup do vault em repositório **privado**.

## Estado do projeto

Versão 0.3. Funciona e tem testes automatizados, mas é novo: faça backup.

- Testado no **Windows 10** com Chrome. macOS e Linux usam o mesmo código, mas ainda não foram testados em máquina real; relatos são bem-vindos.
- O acesso por Tailscale e o início automático no macOS/Linux foram escritos seguindo a documentação de cada sistema e ainda precisam de confirmação de quem usa.
- Os temas que vêm prontos são escuros.

O que vem depois: tema claro, arquivos `.base` para as visões aparecerem também no
Obsidian, mais cenas, módulos de exemplo (finanças, clientes, estudos) e um guia
para compartilhar módulos.

## Contribuir

O código é comentado em português e feito para ser lido. Comece por
[docs/arquitetura.md](docs/arquitetura.md).

```bash
uv run pytest
```

Ideias, problemas e módulos novos são bem-vindos nas issues.

## Licença

[MIT](LICENSE). Use, modifique e distribua à vontade.
