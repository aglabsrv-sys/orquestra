"""Consulta revisões publicadas e aplica atualizações locais sem tocar no vault."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
REMOTOS = {"https://github.com/aglabsrv-sys/orquestra.git", "https://github.com/aglabsrv-sys/orquestra", "git@github.com:aglabsrv-sys/orquestra.git"}


def marca_codigo() -> str:
    fonte = RAIZ / "src" / "orquestra"
    if not (RAIZ / ".git").exists() or not fonte.is_dir():
        return ""
    arquivos = [RAIZ / "pyproject.toml", RAIZ / "uv.lock"]
    for pasta, filhas, nomes in os.walk(fonte):
        filhas[:] = sorted(filha for filha in filhas if filha != "__pycache__")
        arquivos.extend(Path(pasta) / nome for nome in sorted(nomes) if not nome.endswith((".pyc", ".pyo")))
    marca = hashlib.sha256()
    for arquivo in arquivos:
        try:
            estado = arquivo.stat()
        except OSError:
            continue
        marca.update(f"{arquivo.relative_to(RAIZ).as_posix()}\0{estado.st_size}:{estado.st_mtime_ns}\n".encode())
    return marca.hexdigest()


def executar(*args: str, pasta: Path | None = None, timeout: int = 20) -> str:
    resultado = subprocess.run(list(args), cwd=pasta or RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                               env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                               **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
    if resultado.returncode:
        raise RuntimeError("Não foi possível concluir a atualização. Confira sua conexão e a instalação do aplicativo.")
    return resultado.stdout.strip()


def conferir_instalacao() -> str:
    if not (RAIZ / ".git").exists() or not shutil.which("git"):
        raise RuntimeError("Atualize pelo mesmo caminho usado para instalar o Orquestra.")
    if executar("git", "remote", "get-url", "origin") not in REMOTOS or executar("git", "branch", "--show-current") != "main":
        raise RuntimeError("A atualização pelo painel está disponível na main do repositório oficial.")
    return executar("git", "rev-parse", "HEAD")


def conferir_limpa() -> None:
    if executar("git", "status", "--porcelain"):
        raise RuntimeError("Há alterações locais no aplicativo. Guarde essas mudanças antes de atualizar.")


class Atualizador:
    def __init__(self):
        self.trava = threading.Lock()
        self.verificado: float | None = None
        self.cache = {"disponivel": False}
        self.processo = None
        self.codigo_em_uso = marca_codigo()
        try:
            self.revisao_iniciada = conferir_instalacao()
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            self.revisao_iniciada = ""

    def consultar(self) -> dict:
        with self.trava:
            if self.processo is not None:
                codigo = self.processo.poll()
                if codigo is not None:
                    self.processo = None
                    self.verificado = None
                return {**self.cache, "estado": "atualizando" if codigo is None else "falhou", "mensagem": "A atualização não terminou. Confira a instalação e tente novamente." if codigo is not None else "Atualizando o aplicativo…"}
            if self.codigo_em_uso and (codigo := marca_codigo()) and codigo != self.codigo_em_uso:
                return {"disponivel": True, "estado": "disponivel", "modo": "reiniciar"}
            if self.verificado is not None and time.monotonic() - self.verificado < 1800:
                return dict(self.cache)
            try:
                atual = conferir_instalacao()
                remoto = executar("git", "ls-remote", "--exit-code", "origin", "refs/heads/main").split()[0]
                # A comparação acompanha commits, mesmo quando a versão do pacote não muda.
                disponivel = remoto != atual
                if disponivel:
                    try:
                        executar("git", "merge-base", "--is-ancestor", remoto, atual)
                        disponivel = False  # desenvolvimento local à frente da publicação
                    except RuntimeError:
                        pass
                self.cache = {"disponivel": disponivel, "revisao": remoto, "instalada": self.revisao_iniciada, "estado": "disponivel" if disponivel else "atualizado"}
            except (OSError, RuntimeError, subprocess.TimeoutExpired, IndexError):
                self.cache = {"disponivel": False, "estado": "indisponivel"}
            self.verificado = time.monotonic()
            return dict(self.cache)

    def iniciar(self, vault: Path, porta: int, pid: int, modo: str | None = None) -> dict:
        estado = self.consultar()
        with self.trava:
            if self.processo is not None and self.processo.poll() is None:
                return {"estado": "atualizando"}
            reinicio = estado.get("modo") == "reiniciar"
            if modo is not None and modo != ("reiniciar" if reinicio else "baixar"):
                raise RuntimeError("A atualização disponível mudou. Confira o aviso e tente novamente.")
            if not reinicio:
                conferir_instalacao()
                conferir_limpa()
            uv = shutil.which("uv")
            if not uv:
                raise RuntimeError("Instale o uv para atualizar pelo painel.")
            if not estado.get("disponivel"):
                raise RuntimeError("Não há atualização disponível. Reabra a página para verificar novamente.")
            opcoes = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB} if os.name == "nt" else {"start_new_session": True}
            executavel = Path(sys.executable)
            if os.name == "nt" and executavel.with_name("pythonw.exe").is_file():
                executavel = executavel.with_name("pythonw.exe")
            revisao = "--local" if reinicio else estado["revisao"]
            self.processo = subprocess.Popen([str(executavel), "-m", "orquestra.atualizacao", str(vault), str(porta), str(pid), revisao, uv], cwd=RAIZ,
                                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                                             env={**os.environ, "ORQUESTRA_EM_SEGUNDO_PLANO": "1"}, **opcoes)
            return {"estado": "atualizando", **({"modo": "reiniciar"} if reinicio else {"revisao": revisao})}


def aplicar(vault: Path, porta: int, pid: int, revisao: str, uv: str) -> None:
    from orquestra import processo

    def conferir_painel():
        info = processo.consultar(porta)
        if not info or info.get("pid") != pid or Path(info.get("vault") or "").resolve() != vault.resolve():
            raise RuntimeError("O painel ou o vault mudou. A atualização foi cancelada.")

    time.sleep(1)  # deixa a resposta HTTP chegar antes de reiniciar
    conferir_painel()
    if revisao != "--local":
        conferir_instalacao()
        conferir_limpa()
        executar("git", "fetch", "--quiet", "origin", "main", timeout=120)
        if executar("git", "rev-parse", "FETCH_HEAD") != revisao:
            raise RuntimeError("Uma nova revisão foi publicada. Verifique novamente.")
        executar("git", "merge", "--ff-only", revisao, timeout=120)
    executar(uv, "sync", "--locked", timeout=300)
    conferir_painel()
    processo.parar(porta, pid_esperado=pid)
    # Um interpretador novo carrega o código e as dependências recém instalados.
    subprocess.check_call([uv, "run", "--frozen", "orquestra", "iniciar", "--vault", str(vault), "--porta", str(porta)], cwd=RAIZ,
                          **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))


if __name__ == "__main__":
    aplicar(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5])
