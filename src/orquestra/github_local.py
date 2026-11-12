"""Login oficial via GitHub CLI; o token permanece no gerenciador do CLI."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path


class LoginGitHub:
    def __init__(self):
        self._trava = threading.Lock()
        self._processo = None
        self._estado = {"estado": "inativo", "codigo": ""}

    @staticmethod
    def comando(args: list[str], timeout: int = 20) -> str:
        gh = shutil.which("gh")
        if not gh:
            raise ValueError("Instale o GitHub CLI em cli.github.com e reinicie o Orquestra.")
        env = {k: v for k, v in os.environ.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN", "GH_DEBUG", "GH_BROWSER", "BROWSER"}}
        env["GH_HOST"] = "github.com"
        resultado = subprocess.run([gh, *args], cwd=Path.home(), env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                                   **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        if resultado.returncode:
            raise ValueError("O GitHub CLI não concluiu. Confira seu login e sua conexão.")
        return resultado.stdout

    def estado(self) -> dict:
        with self._trava:
            return dict(self._estado)

    def iniciar(self) -> dict:
        gh = shutil.which("gh")
        if not gh:
            raise ValueError("Instale o GitHub CLI em cli.github.com e reinicie o Orquestra.")
        with self._trava:
            if self._processo is not None and self._processo.poll() is None:
                return dict(self._estado)
            env = {k: v for k, v in os.environ.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN", "GH_DEBUG", "GH_BROWSER", "BROWSER"}}
            self._processo = subprocess.Popen([gh, "auth", "login", "--hostname", "github.com", "--web", "--git-protocol", "https"],
                cwd=Path.home(), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            self._estado = {"estado": "aguardando", "codigo": ""}
            processo = self._processo
            processo.stdin.write("\n"); processo.stdin.flush(); processo.stdin.close()
            threading.Thread(target=self._acompanhar, args=(processo,), daemon=True).start()
            return dict(self._estado)

    def _acompanhar(self, processo):
        prazo = threading.Timer(180, lambda: processo.terminate() if processo.poll() is None else None)
        prazo.daemon = True; prazo.start()
        try:
            for linha in processo.stdout:
                codigo = re.search(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", linha[:2048])
                if codigo:
                    with self._trava:
                        self._estado["codigo"] = codigo.group(0)
            retorno = processo.wait(timeout=5)
            with self._trava:
                self._estado = {"estado": "conectado" if retorno == 0 else "falhou", "codigo": ""}
        finally:
            prazo.cancel()
            processo.stdout.close()

    def fechar(self):
        with self._trava:
            if self._processo is not None and self._processo.poll() is None:
                self._processo.terminate()
