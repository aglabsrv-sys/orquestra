"""Identificação dos recursos estáticos, inclusive em pacotes reproduzíveis."""

from __future__ import annotations

import hashlib
from pathlib import Path


def marca_estaticos(pasta: Path) -> str:
    # Wheels normalizam mtimes. O conteúdo, e não a data de instalação, precisa
    # mudar a URL quando uma atualização traz CSS ou JavaScript novos.
    resumo = hashlib.sha256()
    for arquivo in sorted(p for p in pasta.rglob("*") if p.is_file()):
        resumo.update(arquivo.relative_to(pasta).as_posix().encode("utf-8"))
        resumo.update(b"\0")
        dados = arquivo.read_bytes()
        resumo.update(len(dados).to_bytes(8, "big"))
        resumo.update(dados)
    return resumo.hexdigest()[:16]
