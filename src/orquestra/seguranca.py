"""Proteções do servidor local.

O painel não tem login: ele confia em quem consegue chegar até ele. Por isso o
servidor escuta só em 127.0.0.1 e este módulo fecha duas portas que um servidor
local costuma deixar abertas:

1. DNS rebinding: um site malicioso faz o navegador acreditar que o endereço dele
   aponta para 127.0.0.1. Barramos conferindo o cabeçalho Host: só aceitamos
   localhost e nomes exatos (inclusive Tailscale) que estiverem em
   `hosts_permitidos` no orquestra.yaml.
2. CSRF: qualquer página aberta no navegador pode tentar enviar um POST para
   localhost. Barramos exigindo que a origem da requisição seja o próprio painel
   e que o corpo seja JSON (formulários de outros sites não conseguem enviar JSON
   sem uma pré-checagem que nós não respondemos).
"""

from __future__ import annotations

import json
import ipaddress
import secrets
from urllib.parse import urlsplit

from starlette.requests import Request

HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}
METODOS_DE_LEITURA = {"GET", "HEAD", "OPTIONS"}
LIMITE_CORPO = 2 * 1024 * 1024
_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' http: https: data:; media-src 'self' http: https:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


def nome_do_host(valor: str) -> str:
    """'exemplo.ts.net:443' -> 'exemplo.ts.net'; '[::1]:8420' -> '::1'."""
    valor = valor.strip().lower()
    if valor.startswith("["):
        return valor[1:].split("]", 1)[0]
    return valor.rsplit(":", 1)[0] if ":" in valor else valor


def host_permitido(host: str, extras: list[str] | None = None) -> bool:
    try:
        endereco = urlsplit(f"http://{host}")
        if not host or endereco.username is not None or endereco.path or endereco.query or endereco.fragment:
            return False
        endereco.port  # valida também portas malformadas
    except ValueError:
        return False
    nome = nome_do_host(host)
    if nome in HOSTS_LOCAIS:
        return True
    return nome in (extras or [])


def _origem_permitida(origem: str, esquema: str, host: str) -> bool:
    """Compara origens completas; cabeçalhos de proxy não concedem confiança."""
    try:
        recebida, atual = urlsplit(origem), urlsplit(f"{esquema}://{host}")
        if recebida.scheme not in ("http", "https") or recebida.username is not None or recebida.password is not None or recebida.path or recebida.query or recebida.fragment:
            return False
        porta = lambda u: u.port or (443 if u.scheme == "https" else 80)
        return (recebida.scheme, recebida.hostname, porta(recebida)) == (atual.scheme, atual.hostname, porta(atual))
    except ValueError:
        return False


def canal_local(request: Request) -> bool:
    """Somente conexão direta de loopback; Host e cabeçalhos não provam localidade.

    Requisições encaminhadas (inclusive pelo Serve) não recebem a credencial de
    operações fora do vault, mesmo quando o proxy se conecta por 127.0.0.1.
    """
    peer = request.scope.get("client")
    try:
        if not peer or not ipaddress.ip_address(peer[0]).is_loopback:
            return False
    except ValueError:
        return False
    if nome_do_host(request.headers.get("host", "")) not in HOSTS_LOCAIS:
        return False
    return not any(k == "forwarded" or k.startswith(("x-forwarded-", "tailscale-")) for k in request.headers)


class CapabilityLocal:
    """Credencial efêmera por processo, entregue apenas por bootstrap local."""

    def __init__(self):
        self.token = secrets.token_urlsafe(32)

    def emitir(self, request: Request) -> str | None:
        if not canal_local(request) or request.headers.get("sec-fetch-site", "") not in ("", "none", "same-origin"):
            return None
        origem = request.headers.get("origin")
        if origem and not _origem_permitida(origem, request.url.scheme, request.headers.get("host", "")):
            return None
        return self.token

    def exigir(self, request: Request) -> None:
        recebido = request.headers.get("x-orquestra-local", "")
        if self.emitir(request) is None or not secrets.compare_digest(recebido, self.token):
            raise ValueError("Esta operação exige a autorização do painel aberto diretamente neste computador (localhost). Reabra a página local e tente novamente.")


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
            if origem and not _origem_permitida(origem, scope.get("scheme", "http"), host):
                return await _negar(send, 403, "Requisição vinda de outro site foi bloqueada.")
            if cabecalhos.get("sec-fetch-site") in ("cross-site", "same-site"):
                return await _negar(send, 403, "Requisição vinda de outro site foi bloqueada.")
            if cabecalhos.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                return await _negar(send, 415, "Este painel só aceita alterações em JSON.")
            mensagens = []
            tamanho = 0
            while True:
                mensagem = await receive()
                if mensagem["type"] != "http.request":
                    return await _negar(send, 400, "A conexão terminou antes de receber o pedido.")
                tamanho += len(mensagem.get("body", b""))
                if tamanho > LIMITE_CORPO:
                    return await _negar(send, 413, "O pedido excede 2 MB. Divida o conteúdo em notas menores.")
                mensagens.append(mensagem)
                if not mensagem.get("more_body"):
                    break

            receber_original = receive

            async def receber():
                if mensagens:
                    return mensagens.pop(0)
                return await receber_original()

            receive = receber

        async def enviar(mensagem):
            if mensagem["type"] == "http.response.start":
                headers = list(mensagem.get("headers", []))
                nomes = {k.lower() for k, _ in headers}
                for k, v in ((b"content-security-policy", _CSP.encode()), (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")):
                    if k not in nomes:
                        headers.append((k, v))
                if b"cache-control" not in nomes and any(k.lower() == b"content-type" and (v.startswith(b"text/html") or v.startswith(b"application/json")) for k, v in headers):
                    headers.append((b"cache-control", b"no-store"))
                mensagem = {**mensagem, "headers": headers}
            await send(mensagem)

        await self.app(scope, receive, enviar)


async def _negar(send, status: int, mensagem: str) -> None:
    corpo = json.dumps({"erro": mensagem}, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(corpo)).encode()),
                (b"cache-control", b"no-store"),
                (b"x-content-type-options", b"nosniff"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": corpo})
