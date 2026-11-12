"""Fronteira única de arquivos: o vault escolhido nunca segue links abaixo da raiz."""

from __future__ import annotations

import os
import stat
from pathlib import Path, PureWindowsPath
from typing import Iterator

PASTAS_IGNORADAS = {".git", ".obsidian", ".trash", "__pycache__", "node_modules", ".venv", ".pytest_cache"}


class CaminhoInseguro(ValueError):
    """O caminho sai do vault ou atravessa um link/junction."""


def eh_link(caminho: Path) -> bool:
    try:
        info = caminho.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def caminho_no_vault(vault: Path, caminho: str | Path) -> Path:
    """Aceita relativo ou absoluto interno. Não normaliza traversal nem segue links.

    A raiz é a pasta que a pessoa escolheu (já resolvida). Links abaixo dela são
    recusados, mesmo quando apontam para dentro, para haver uma política igual nas
    três plataformas. Deve ser chamado novamente imediatamente antes de escrever.
    """
    raiz_original = Path(os.path.abspath(vault))
    raiz = raiz_original.resolve()
    if eh_link(raiz_original) or raiz != raiz_original:
        raise CaminhoInseguro("A pasta do vault foi substituída por um link. Reabra a pasta correta.")
    texto = os.fspath(caminho)
    if any(ord(c) < 32 for c in texto):
        raise CaminhoInseguro("O caminho contém caracteres inválidos.")
    entrada = Path(texto)
    if not entrada.is_absolute():
        win = PureWindowsPath(texto)
        if win.drive or win.root or texto.startswith(("/", "\\")):
            raise CaminhoInseguro("Use um caminho relativo dentro do vault.")
        entrada = raiz / texto.replace("\\", "/")
    try:
        relativo = entrada.relative_to(raiz)
    except ValueError:
        raise CaminhoInseguro("O caminho precisa ficar dentro do vault.") from None
    if any(p in ("..", ".") or ":" in p for p in relativo.parts):
        raise CaminhoInseguro("O caminho precisa ficar dentro do vault, sem '..' ou unidades.")
    atual = raiz
    try:
        for parte in relativo.parts:
            atual /= parte
            if eh_link(atual):
                raise CaminhoInseguro("Links simbólicos e junctions dentro do vault não são seguidos.")
        resolvido = entrada.resolve()
        if not resolvido.is_relative_to(raiz):
            raise CaminhoInseguro("O caminho precisa ficar dentro do vault.")
    except OSError:
        raise CaminhoInseguro("Não foi possível validar o caminho dentro do vault.") from None
    return entrada


def ignorar(rel: str, *, configuracao: bool = False) -> bool:
    partes = rel.replace("\\", "/").lower().strip("/").split("/")
    if any(p in PASTAS_IGNORADAS or p.startswith(".") for p in partes):
        return True
    if partes[-1].endswith(".orq-tmp"):
        return True
    if partes[0] == "_orquestra":
        return not (configuracao and (len(partes) == 1 or partes[1] == "temas"))
    return partes[:2] == ["diario", "registro"]


def arquivos_do_vault(vault: Path) -> Iterator[tuple[str, Path, os.stat_result]]:
    """scandir preserva o stat de cada entrada e poda árvores antes de descer."""
    raiz = Path(os.path.abspath(vault))
    try:
        caminho_no_vault(raiz, raiz)
    except (CaminhoInseguro, OSError):
        return
    pendentes = [raiz]
    while pendentes:
        pasta = pendentes.pop()
        try:
            caminho_no_vault(raiz, pasta)
            with os.scandir(pasta) as entradas:
                for entrada in entradas:
                    caminho = Path(entrada.path)
                    rel = caminho.relative_to(raiz).as_posix()
                    if ignorar(rel):
                        continue
                    try:
                        info = entrada.stat(follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            pendentes.append(caminho)
                        elif stat.S_ISREG(info.st_mode):
                            yield rel, caminho, info
                    except OSError:
                        continue
        except (OSError, CaminhoInseguro):
            continue
