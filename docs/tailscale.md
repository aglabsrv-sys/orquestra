# Abrir o painel no celular (Tailscale)

O painel escuta apenas em `127.0.0.1`: só o seu computador enxerga. Para abrir no
celular sem expor nada à internet, usamos o [Tailscale](https://tailscale.com), uma
rede privada entre os seus aparelhos. Confira o plano e os limites atuais para sua conta.

> **O painel não tem senha.** Quem alcança o endereço lê e altera o seu vault.
> Por isso: **nunca use `tailscale funnel`** e nunca abra a porta no roteador. O
> Funnel publica o endereço para a internet inteira. O `serve`, usado aqui, só
> fica limitado pela política de acesso da sua rede Tailscale. Confira usuários, compartilhamentos e ACLs antes de habilitar.

## Passo a passo

1. **Instale o Tailscale no computador** onde o painel roda e entre com a sua conta.
   Baixe em <https://tailscale.com/download>.
2. **Instale o Tailscale no celular** (App Store ou Google Play) e entre com a **mesma conta**.
3. Com o painel rodando, abra um terminal no computador e rode uma vez:

   ```bash
   tailscale serve --bg 8420
   ```

   Na primeira vez o Tailscale pode pedir para ativar HTTPS na sua conta: ele mostra
   um link, é só abrir e confirmar.
4. O comando mostra um endereço parecido com `https://seu-pc.tail1234.ts.net`. Abra
   esse endereço no navegador do celular (com o Tailscale ligado nele).
5. Pelo localhost do computador, abra Ajustes → Celular → Conecte seu celular.
   No último passo, cole o endereço HTTPS mostrado e clique em Permitir este endereço.
   O painel aplica o nome exato imediatamente. Como alternativa manual, em
   `orquestra.yaml`, permita **somente o nome exato** e reinicie o painel:

   ```yaml
   hosts_permitidos:
     - seu-pc.tail1234.ts.net
   ```

   Não use curingas. Não permita domínios de terceiros.
6. No celular, use "Adicionar à tela de início" para ter o painel como um aplicativo.

Se você mudou a porta do Orquestra, substitua `8420` pela porta mostrada no terminal.
O `--bg` deixa o encaminhamento ligado mesmo depois de fechar o terminal e de
reiniciar o computador. O painel precisa estar rodando para o endereço responder
(veja `uv run --frozen orquestra autostart ativar` no README).

## Conferir e desligar

```bash
tailscale serve status
```

```bash
tailscale serve reset
```

`reset` remove toda a configuração Serve deste computador, inclusive outros
encaminhamentos que você tenha criado. Confira `tailscale serve status` antes de
usar. A sintaxe e o comportamento estão na [referência oficial de Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

Na pasta do aplicativo, `uv run --frozen orquestra doctor` também consulta o
Tailscale, quando instalado, e aponta se detectar Funnel ativo.

## Se algo não funcionar

| Sintoma | O que fazer |
|---|---|
| O endereço não abre no celular | Confira se o Tailscale está ligado no celular e se o painel está rodando no computador. |
| A página abre, mas nada salva ("Requisição vinda de outro site foi bloqueada") | Acrescente o nome do endereço (sem `https://`) em `hosts_permitidos` no `orquestra.yaml` e reinicie o painel. |
| "Endereço não permitido" | O nome exato não foi permitido. Confira a URL e acrescente somente o seu nome Tailscale em `hosts_permitidos`; reinicie o painel. |
| O computador dorme e o endereço cai | Ajuste as opções de energia para não suspender, ou aceite que o painel só responde com o computador acordado. |

## Falar com o agente pelo celular

O painel não conversa com IA: ele mostra e edita os arquivos. Para dar ordens a um
agente estando fora de casa, você tem dois caminhos que combinam bem com ele:

- **Captura rápida**: o botão "Capturar" grava o seu pedido em `entrada/`. Na próxima
  sessão, o agente processa (é o que o `AGENTS.md` manda).
- **O acesso remoto do seu agente**: Claude Code, por exemplo, pode ser controlado
  pelo celular. O agente trabalha na pasta, e você acompanha o resultado no painel.

## Ações reservadas ao computador

Escolher ou trocar vault, abrir o seletor de pastas e aprovar execução de coletores
ou configuração de backup exigem acesso direto por localhost, sem proxy. Os botões
de aprovação ficam indisponíveis pelo Tailscale. Cabeçalhos de encaminhamento não
concedem acesso local. As edições de notas e os coletores previamente aprovados
continuam disponíveis para quem já tem acesso autorizado à sua rede.
