"""Variáveis locais: nunca retornam valores ao navegador nem entram no vault."""
from __future__ import annotations

import os
import re
from pathlib import Path

from orquestra import armazenamento
from orquestra.caminhos import eh_link
from orquestra.config import pasta_app

NOME = re.compile(r"[A-Z][A-Z0-9_]{1,79}\Z")


def arquivo(vault: Path) -> Path:
    casa = pasta_app()
    if eh_link(casa) or eh_link(casa / ".env"):
        raise ValueError("A pasta de variáveis não pode ser um link.")
    casa = casa.resolve()
    if casa == vault.resolve() or casa.is_relative_to(vault.resolve()):
        raise ValueError("Guarde as variáveis fora do vault.")
    return casa / ".env"


def nomes(vault: Path) -> list[str]:
    p = arquivo(vault)
    if not p.exists():
        return []
    return sorted({linha.split("=", 1)[0].strip() for linha in p.read_text(encoding="utf-8-sig").splitlines()
                   if "=" in linha and NOME.fullmatch(linha.split("=", 1)[0].strip())})


def salvar(vault: Path, nome: str, valor: str | None) -> None:
    if not NOME.fullmatch(nome):
        raise ValueError("Use de 2 a 80 caracteres: letras maiúsculas, números e sublinhado.")
    if nome.startswith(("ORQUESTRA_", "PYTHON", "LD_", "DYLD_", "GIT_")) or nome in {"PATH", "HOME", "APPDATA", "SYSTEMROOT"}:
        raise ValueError("Este nome é reservado ao sistema.")
    if valor is not None and (not valor or len(valor) > 8192 or any(c in valor for c in '\r\n\0') or valor != valor.strip() or valor[:1] in "\"'" or valor[-1:] in "\"'"):
        raise ValueError("Use um valor de uma linha, sem aspas externas, de até 8192 caracteres.")
    p = arquivo(vault)
    p.parent.mkdir(parents=True, exist_ok=True)

    def transformar(antes: bytes) -> bytes:
        linhas = antes.decode("utf-8-sig").splitlines()
        linhas = [linha for linha in linhas if linha.split("=", 1)[0].strip() != nome]
        if valor is not None:
            linhas.append(nome + "=" + valor)
        return ("\n".join(linhas) + "\n").encode("utf-8")

    armazenamento.atualizar_bytes(p, transformar, backup=False, validar=lambda: arquivo(vault))
    os.chmod(p, 0o600)
