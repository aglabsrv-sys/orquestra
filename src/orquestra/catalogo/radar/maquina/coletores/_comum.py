"""Ajudantes compartilhados pelos coletores desta pasta.

Um coletor só precisa de três coisas, e elas estão aqui:

    CONFIG          o que está em `config:` no _modulo.yaml
    baixar(url)     busca uma página ou feed e devolve os bytes
    emitir(...)     entrega um item ao painel (imprime uma linha de JSON)

Este arquivo não é um coletor: ele só é importado pelos outros scripts.
"""

import json
import os
import socket
import sys
import urllib.request

CONFIG = json.loads(os.environ.get("ORQUESTRA_CONFIG") or "{}")
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (compatible; coletor-rss)", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}
LIMITE_DOWNLOAD = 8 * 1024 * 1024

# Em muitas redes o IPv6 está anunciado, mas não funciona. O Python tenta IPv6
# primeiro e fica esperando até desistir (dezenas de segundos por endereço).
# Aqui só mudamos a ordem: IPv4 primeiro, IPv6 continua valendo como reserva.
_resolver = socket.getaddrinfo


def _ipv4_primeiro(*args, **kwargs):
    return sorted(_resolver(*args, **kwargs), key=lambda endereco: endereco[0] != socket.AF_INET)


socket.getaddrinfo = _ipv4_primeiro

try:  # o painel lê a saída em UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def baixar(url: str, tempo: int = 20) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=NAVEGADOR), timeout=tempo) as resposta:
        # Não confiar no tamanho informado: respostas sem Content-Length ou
        # com comprimento incorreto também precisam permanecer limitadas.
        dados = resposta.read(LIMITE_DOWNLOAD + 1)
        if len(dados) > LIMITE_DOWNLOAD:
            raise ValueError("A resposta da fonte excede o limite de 8 MB.")
        return dados


def emitir(id: str, titulo: str, corpo: str = "", **campos) -> None:
    """Entrega um item. `id` precisa ser estável: é por ele que o painel evita repetidos."""
    campos = {chave: valor for chave, valor in campos.items() if valor not in (None, "", [])}
    print(json.dumps({"id": id, "titulo": titulo, "corpo": corpo, **campos}, ensure_ascii=False), flush=True)


def avisar(mensagem: str) -> None:
    """Mensagem de diagnóstico: vai para o erro padrão, não vira item."""
    print(mensagem, file=sys.stderr, flush=True)
