"""Instala cada distribuição em ambiente novo e testa os recursos empacotados.

Não abre portas, não roda coletores e mantém configuração/vault em temporários.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


VERIFICAR = r'''
from pathlib import Path
from orquestra import preparo
from orquestra.hospedeiro import Hospedeiro
from orquestra.mcp_servidor import criar_servidor
from orquestra.painel import Painel

pacote = Path(preparo.__file__).parent
for relativo in ("templates/base.html", "templates/boasvindas.html", "static/icone.svg", "static/css/app.css", "static/js/notas-seguras.js", "static/js/interface.js", "static/js/app.js", "static/js/boasvindas.js", "catalogo/perfis.yaml", "modelo_vault/orquestra.yaml"):
    assert (pacote / relativo).is_file(), relativo
vault = Path.cwd() / "Meu vault com espaços e acentos"
preparo.preparar(vault, preparo.modulos_do_perfil("essencial"), exemplos=False, com_backup=False)
painel = Painel(vault)
assert set(painel.indice.modulos) == {"tarefas", "notas", "entrada"}
assert Hospedeiro(None, vigiar=False, agendar=False).boas_vindas
assert criar_servidor(vault)
print("Pacote, catálogo, primeira execução e MCP: OK")
'''


def main() -> None:
    pasta = Path(sys.argv[1] if len(sys.argv) > 1 else "dist").resolve()
    arquivos = sorted([*pasta.glob("*.whl"), *pasta.glob("*.tar.gz")])
    if not arquivos:
        raise SystemExit("Nenhuma distribuição encontrada; execute uv build primeiro.")
    for arquivo in arquivos:
        # Antivírus pode reter uma extensão .pyd por instantes no Windows, mesmo
        # depois do subprocesso encerrar. Isso não transforma validação em falha.
        with tempfile.TemporaryDirectory(prefix="orquestra-pacote-", ignore_cleanup_errors=True) as temporario:
            raiz = Path(temporario)
            ambiente = raiz / "ambiente"
            subprocess.run(["uv", "venv", "--python", sys.executable, str(ambiente)], check=True)
            python = ambiente / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            subprocess.run(["uv", "pip", "install", "--python", str(python), str(arquivo)], check=True)
            env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME", "ORQUESTRA_VAULT"}}
            env["ORQUESTRA_HOME"] = str(raiz / "configuracao")
            subprocess.run([str(python), "-m", "orquestra", "--version"], cwd=raiz, env=env, check=True)
            subprocess.run([str(python), "-c", VERIFICAR], cwd=raiz, env=env, check=True)
        if raiz.exists():
            print(f"Aviso: um arquivo temporário está ocupado; limpeza pendente em {raiz}", flush=True)
        print(f"Distribuição validada: {arquivo.name}", flush=True)


if __name__ == "__main__":
    main()
