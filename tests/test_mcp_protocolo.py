"""MCP real pela CLI: handshake, JSON-RPC stdio e regras entre processos."""

from __future__ import annotations

from contextlib import contextmanager
import builtins
import datetime as dt
import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread

import pytest

from orquestra.mcp_servidor import FERRAMENTAS, criar_servidor


class ClienteStdio:
    def __init__(self, vault: Path, cwd: Path):
        self.fila = Queue()
        self.stderr = []
        self.proximo_id = 0
        self.chamadas = set()
        env = dict(os.environ)
        env.pop("ORQUESTRA_VAULT", None)
        env["PYTHONUTF8"] = "1"
        self.processo = subprocess.Popen(
            [sys.executable, "-m", "orquestra", "mcp", "--vault", str(vault)],
            cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
        )

        def ler_saida():
            for linha in self.processo.stdout:
                try:
                    mensagem = json.loads(linha)
                    assert mensagem["jsonrpc"] == "2.0"
                    self.fila.put(mensagem)
                except (ValueError, KeyError, AssertionError):
                    self.fila.put(AssertionError(f"stdout contém conteúdo fora do protocolo: {linha!r}"))
            self.fila.put(EOFError("O servidor encerrou antes de responder."))

        def ler_erros():
            for linha in self.processo.stderr:
                self.stderr.append(linha)

        self.leitores = [Thread(target=ler_saida, daemon=True), Thread(target=ler_erros, daemon=True)]
        for leitor in self.leitores:
            leitor.start()

    def enviar(self, mensagem):
        self.processo.stdin.write(json.dumps({"jsonrpc": "2.0", **mensagem}, ensure_ascii=False) + "\n")
        self.processo.stdin.flush()

    def pedir(self, metodo, parametros=None):
        self.proximo_id += 1
        identificador = self.proximo_id
        self.enviar({"id": identificador, "method": metodo, "params": parametros or {}})
        while True:
            try:
                resposta = self.fila.get(timeout=30)
            except Empty:
                raise AssertionError("O MCP não respondeu em 30 segundos. " + "".join(self.stderr[-10:])) from None
            if isinstance(resposta, Exception):
                if isinstance(resposta, EOFError):
                    self.leitores[1].join(timeout=2)
                    raise AssertionError(str(resposta) + " " + "".join(self.stderr[-10:])) from None
                raise resposta
            if resposta.get("id") == identificador:
                assert "error" not in resposta, resposta
                return resposta["result"]
            assert "method" in resposta, resposta

    def iniciar(self):
        resultado = self.pedir("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "orquestra-teste-stdio", "version": "1.0"},
        })
        assert resultado["serverInfo"]["name"] == "orquestra"
        assert "tools" in resultado["capabilities"]
        self.enviar({"method": "notifications/initialized"})

    def chamar(self, nome, argumentos=None, *, erro=False):
        self.chamadas.add(nome)
        resultado = self.pedir("tools/call", {"name": nome, "arguments": argumentos or {}})
        assert bool(resultado.get("isError")) == erro, resultado
        if erro:
            return "\n".join(bloco.get("text", "") for bloco in resultado["content"])
        if resultado.get("structuredContent") is not None:
            valor = resultado["structuredContent"]
            return valor["result"] if set(valor) == {"result"} else valor
        textos = [bloco["text"] for bloco in resultado.get("content", []) if bloco["type"] == "text"]
        if not textos:
            return []
        try:
            valores = [json.loads(texto) for texto in textos]
        except ValueError:
            return "\n".join(textos)
        return valores[0] if len(valores) == 1 else valores


@contextmanager
def servidor_stdio(vault, cwd):
    cliente = ClienteStdio(vault, cwd)
    try:
        cliente.iniciar()
        yield cliente
        cliente.processo.stdin.close()
        assert cliente.processo.wait(timeout=10) == 0, "".join(cliente.stderr[-10:])
        for leitor in cliente.leitores:
            leitor.join(timeout=2)
        # Também checa qualquer saída posterior à última resposta.
        while not cliente.fila.empty():
            restante = cliente.fila.get_nowait()
            assert not isinstance(restante, AssertionError), restante
    finally:
        if cliente.processo.poll() is None:
            cliente.processo.terminate()
            cliente.processo.wait(timeout=10)
        for fluxo in (cliente.processo.stdin, cliente.processo.stdout, cliente.processo.stderr):
            fluxo.close()


def test_cli_mcp_stdio_executa_as_17_ferramentas(vault, tmp_path):
    with servidor_stdio(vault, tmp_path) as cliente:
        ferramentas = cliente.pedir("tools/list")["tools"]
        assert {ferramenta["name"] for ferramenta in ferramentas} == set(FERRAMENTAS)
        for ferramenta in ferramentas:
            schema = ferramenta["inputSchema"]
            assert schema["type"] == "object"
            assert not {"self", "args", "kwargs", "_ja_em_dia"} & schema.get("properties", {}).keys()

        assert "**tarefas**" in cliente.chamar("regras")
        assert "numeros" in {area["id"] for area in cliente.chamar("listar_areas")}
        criado = cliente.chamar("criar_item", {
            "area": "tarefas", "titulo": "Ação de teste via MCP", "campos": {"status": "fazendo", "origem": "humano"},
            "texto": "Rascunho do agente.",
        })
        caminho = criado["caminho"]
        assert criado["campos"]["origem"] == "agente"
        assert cliente.chamar("ler_nota", {"caminho": caminho})["texto"].strip() == "Rascunho do agente."
        assert any(item["caminho"] == caminho for item in cliente.chamar("listar_itens", {"area": "tarefas", "status": "fazendo"}))
        assert any(item["caminho"] == caminho for item in cliente.chamar("buscar", {"termo": "Ação de teste via MCP"}))

        cliente.chamar("atualizar_item", {"caminho": caminho, "campos": {"data": dt.date.today().isoformat()}, "novo_texto": "Texto revisto pelo agente."})
        assert any(item["caminho"] == caminho for item in cliente.chamar("agenda"))
        cliente.chamar("perguntar", {"caminho": caminho, "pergunta": "Pode publicar?"})
        assert any(item["caminho"] == caminho for item in cliente.chamar("fila_de_decisoes"))
        arquivo = vault / caminho
        arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("pergunta: Pode publicar?", "pergunta: Pode publicar?\nresposta: Sim"), encoding="utf-8")
        assert any(item["caminho"] == caminho for item in cliente.chamar("respostas"))

        captura = cliente.chamar("capturar", {"texto": "Lembrete sintético"})
        assert captura["campos"]["origem"] == "agente"
        numeros = cliente.chamar("registrar_numeros", {"valores": {"inscritos": 42}})
        assert numeros["campos"]["inscritos"] == 42
        cliente.chamar("registrar_aprendizado", {"area": "tarefas", "aprendizado": "Use perguntas claras."})
        assert "Use perguntas claras." in cliente.chamar("aprendizados", {"area": "tarefas"})
        cliente.chamar("registrar_sessao", {"agente": "teste-mcp", "pedido": "Verificar protocolo", "feito": "Ferramentas exercitadas"})
        assert "Ferramentas exercitadas" in cliente.chamar("sessoes_recentes", {"dias": 1})
        assert cliente.chamadas == set(FERRAMENTAS)


def test_mcp_stdio_preserva_notas_humanas_e_recusa_pedidos_invalidos(vault, tmp_path):
    humana = vault / "tarefas/itens/Nota humana.md"
    original = b"---\r\norigem: humano\r\nstatus: a_fazer\r\n---\r\nTexto original da pessoa.\r\n\r\n\r\n"
    humana.write_bytes(original)
    with servidor_stdio(vault, tmp_path) as cliente:
        erro = cliente.chamar("atualizar_item", {"caminho": "tarefas/itens/Nota humana.md", "novo_texto": "Substituir"}, erro=True)
        assert "não pode ser substituído" in erro
        assert "Texto original da pessoa." in humana.read_text(encoding="utf-8")
        cliente.chamar("atualizar_item", {"caminho": "tarefas/itens/Nota humana.md", "acrescentar": "Observação do agente."})
        texto = humana.read_text(encoding="utf-8")
        assert humana.read_bytes().startswith(original), "Acrescentar texto deve preservar também as linhas vazias da pessoa."
        assert "Texto original da pessoa." in texto and "## Notas do agente" in texto and "Observação do agente." in texto
        assert "sem '..'" in cliente.chamar("ler_nota", {"caminho": "../fora.md"}, erro=True)
        assert "não é uma opção" in cliente.chamar("criar_item", {"area": "tarefas", "titulo": "Inválida", "campos": {"status": "inexistente"}}, erro=True)
        assert "AAAA-MM-DD" in cliente.chamar("agenda", {"dia": "ontem"}, erro=True)
        assert "não pode ser alterado" in cliente.chamar("atualizar_item", {"caminho": "tarefas/itens/Nota humana.md", "campos": {"origem": "agente"}}, erro=True)
        assert cliente.chamar("capturar", {"texto": "Frase literal da pessoa.", "palavras_da_pessoa": True})["campos"]["origem"] == "humano"
        externa = vault / "tarefas/itens/Mudança externa.md"
        externa.write_text("---\nstatus: a_fazer\n---\nCriada fora do MCP.\n", encoding="utf-8")
        assert any(item["titulo"] == "Mudança externa" for item in cliente.chamar("listar_itens", {"area": "tarefas"}))


def test_sdk_incompativel_da_orientacao_de_reparo_sem_traceback(vault, monkeypatch):
    importar = builtins.__import__

    def sdk_quebrado(nome, *args, **kwargs):
        if nome.startswith("mcp.server."):
            raise ImportError("API interna de uma dependência mudou")
        return importar(nome, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sdk_quebrado)
    with pytest.raises(RuntimeError, match="uv sync --frozen") as erro:
        criar_servidor(vault)
    assert "API interna" not in str(erro.value)
