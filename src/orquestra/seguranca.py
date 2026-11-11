"""Proteções do servidor local.

O painel não tem login: ele confia em quem consegue chegar até ele. Por isso o
servidor escuta só em 127.0.0.1 e este módulo fecha duas portas que um servidor
local costuma deixar abertas:

1. DNS rebinding: um site malicioso faz o navegador acreditar que o endereço dele
   aponta para 127.0.0.1. Barramos conferindo o cabeçalho Host: só aceitamos
   localhost, o nome da máquina no Tailscale (*.ts.net) e o que estiver em
   `hosts_permitidos` no orquestra.yaml.
2. CSRF: qualquer página aberta no navegador pode tentar enviar um POST para
   localhost. Barramos exigindo que a origem da requisição seja o próprio painel
   e que o corpo seja JSON (formulários de outros sites não conseguem enviar JSON
   sem uma pré-checagem que nós não respondemos).
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}
METODOS_DE_LEITURA = {"GET", "HEAD", "OPTIONS"}


def nome_do_host(valor: str) -> str:
    """'exemplo.ts.net:443' -> 'exemplo.ts.net'; '[::1]:8420' -> '::1'."""
    valor = valor.strip().lower()
    if valor.startswith("["):
        return valor[1:].split("]", 1)[0]
    return valor.rsplit(":", 1)[0] if ":" in valor else valor


def host_permitido(host: str, extras: list[str] | None = None) -> bool:
    nome = nome_do_host(host)
    if nome in HOSTS_LOCAIS or nome.endswith(".localhost"):
        return True
    if nome.endswith(".ts.net"):
        return True
    return nome in (extras or [])


class Protecao:
    """Middleware ASGI que aplica as duas regras acima."""

    def __init__(self, app, hosts_extras: list[str] | None = None):
        self.app = app
        self.hosts_extras = hosts_extras or []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        cabecalhos = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = cabecalhos.get("host", "")
        if not host_permitido(host, self.hosts_extras):
            return await _negar(
                send,
                403,
                f"Endereço '{host}' não permitido. Acesse por localhost ou pelo endereço do "
                "Tailscale, ou acrescente o nome em hosts_permitidos no orquestra.yaml.",
            )

        if scope["method"] not in METODOS_DE_LEITURA:
            origem = cabecalhos.get("origin")
            if origem:
                host_origem = urlparse(origem).netloc.lower()
                # Atrás de um proxy (como o `tailscale serve`) o Host original pode vir em
                # X-Forwarded-Host. Nomes em hosts_permitidos também valem como origem.
                aceitos = {host.lower(), cabecalhos.get("x-forwarded-host", "").lower()}
                if host_origem not in aceitos and nome_do_host(host_origem) not in self.hosts_extras:
                    return await _negar(send, 403, "Requisição vinda de outro site foi bloqueada.")
            if not cabecalhos.get("content-type", "").lower().startswith("application/json"):
                return await _negar(send, 415, "Este painel só aceita alterações em JSON.")

        await self.app(scope, receive, send)


async def _negar(send, status: int, mensagem: str) -> None:
    corpo = json.dumps({"erro": mensagem}, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(corpo)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": corpo})
