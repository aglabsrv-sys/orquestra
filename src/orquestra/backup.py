"""Histórico e backup do vault com git.

O vault é um repositório git próprio (separado do repositório do app). O painel
faz commits automáticos locais, que funcionam como "desfazer" de qualquer
alteração de um agente, e opcionalmente envia para um repositório remoto privado.
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
from pathlib import Path

GITIGNORE_DO_VAULT = """\
# Estado do painel e do Obsidian que muda o tempo todo e não precisa de backup
_orquestra/estado.json
.obsidian/workspace*.json
.obsidian/cache
.trash/
*.orq-tmp

# Segredos nunca ficam no vault, mas por garantia:
.env
"""


def git_disponivel() -> bool:
    return shutil.which("git") is not None


def git(vault: Path, *args: str, tempo: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=vault, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=tempo
    )


def e_repositorio(vault: Path) -> bool:
    return (vault / ".git").exists()


def tem_remoto(vault: Path) -> bool:
    return e_repositorio(vault) and bool(git(vault, "remote").stdout.strip())


def _identidade(vault: Path) -> list[str]:
    """Se o git não tem nome/e-mail configurados, usa uma identidade local só para o commit."""
    if git(vault, "config", "user.name").stdout.strip() and git(vault, "config", "user.email").stdout.strip():
        return []
    return ["-c", "user.name=Orquestra", "-c", "user.email=orquestra@localhost"]


def iniciar(vault: Path) -> bool:
    """Cria o repositório do vault (se ainda não existir) com um .gitignore adequado."""
    if not git_disponivel():
        return False
    ignorar = vault / ".gitignore"
    if not ignorar.exists():
        ignorar.write_text(GITIGNORE_DO_VAULT, encoding="utf-8")
    if not e_repositorio(vault):
        if git(vault, "init", "-b", "main").returncode != 0:
            git(vault, "init")
    return e_repositorio(vault)


def commit(vault: Path, mensagem: str | None = None) -> str:
    """Faz um commit com tudo que mudou. Devolve 'feito', 'nada', 'sem_git' ou 'erro: ...'."""
    if not git_disponivel() or not e_repositorio(vault):
        return "sem_git"
    try:
        git(vault, "add", "-A")
        if git(vault, "diff", "--cached", "--quiet").returncode == 0:
            return "nada"
        mensagem = mensagem or f"orquestra: backup automático {dt.datetime.now():%Y-%m-%d %H:%M}"
        r = git(vault, *_identidade(vault), "commit", "-m", mensagem)
        if r.returncode != 0:
            return "erro: " + (r.stderr.strip().splitlines() or ["falha no commit"])[-1]
        return "feito"
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"erro: {e}"


def push(vault: Path) -> str:
    """Envia os commits para o repositório remoto. Devolve 'feito', 'sem_remoto' ou 'erro: ...'."""
    if not git_disponivel() or not tem_remoto(vault):
        return "sem_remoto"
    try:
        r = git(vault, "push", tempo=180)
        if r.returncode != 0:
            # Primeiro envio de um branch novo: define o destino.
            r = git(vault, "push", "-u", "origin", "HEAD", tempo=180)
        if r.returncode != 0:
            return "erro: " + (r.stderr.strip().splitlines() or ["falha no envio"])[-1]
        return "feito"
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"erro: {e}"


def ultimo_commit(vault: Path) -> str:
    if not git_disponivel() or not e_repositorio(vault):
        return ""
    r = git(vault, "log", "-1", "--format=%cd", "--date=format:%d/%m/%Y %H:%M")
    return r.stdout.strip() if r.returncode == 0 else ""
