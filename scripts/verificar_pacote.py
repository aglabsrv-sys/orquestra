"""Instala cada distribuição em ambiente novo e testa os recursos empacotados.

Não abre portas, não roda coletores e mantém configuração/vault em temporários.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


VERIFICAR = r'''
import os
import subprocess
import sys
from pathlib import Path
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from orquestra import preparo
from orquestra.hospedeiro import Hospedeiro
from orquestra.mcp_servidor import FERRAMENTAS
from orquestra.painel import Painel

pacote = Path(preparo.__file__).parent
for relativo in ("templates/base.html", "templates/boasvindas.html", "static/icone.svg", "static/css/app.css", "static/js/notas-seguras.js", "static/js/interface.js", "static/js/app.js", "static/js/boasvindas.js", "catalogo/perfis.yaml", "modelo_vault/orquestra.yaml"):
    assert (pacote / relativo).is_file(), relativo
vault = Path.cwd() / "Meu vault com espaços e acentos"
preparo.preparar(vault, preparo.modulos_do_perfil("essencial"), exemplos=False, com_backup=False)
painel = Painel(vault)
assert set(painel.indice.modulos) == {"tarefas", "notas", "entrada"}
assert Hospedeiro(None, vigiar=False, agendar=False).boas_vindas

# Testar o entry point instalado, sem depender do checkout ou de uma ativação do shell.
executavel = Path(sys.executable).parent / ("orquestra.exe" if os.name == "nt" else "orquestra")
for argumentos in (["--help"], ["mcp", "--help"], ["--version"]):
    resposta = subprocess.run([str(executavel), *argumentos], capture_output=True, timeout=20)
    assert resposta.returncode == 0, resposta.stderr.decode("utf-8", errors="replace")

async def conferir_mcp():
    projeto = os.environ.get("ORQUESTRA_TESTE_PROJETO")
    parametros = StdioServerParameters(
        command=os.environ["ORQUESTRA_TESTE_UV"] if projeto else sys.executable,
        args=(["run", "--frozen", "--no-dev", "--directory", projeto, "orquestra", "mcp", "--vault", str(vault)]
              if projeto else ["-m", "orquestra", "mcp", "--vault", str(vault)]),
        env=dict(os.environ),
    )
    with anyio.fail_after(45):
        async with stdio_client(parametros) as (leitura, escrita):
            async with ClientSession(leitura, escrita) as sessao:
                inicio = (await sessao.initialize()).model_dump(by_alias=True)
                assert inicio["serverInfo"]["name"] == "orquestra"
                ferramentas = await sessao.list_tools()
                assert {f.name for f in ferramentas.tools} == set(FERRAMENTAS)
                regras = (await sessao.call_tool("regras", {})).model_dump(by_alias=True)
                assert not regras.get("isError") and regras["content"]
                captura = (await sessao.call_tool("capturar", {"texto": "Conferência do pacote instalado"})).model_dump(by_alias=True)
                assert not captura.get("isError"), captura
    assert list((vault / "entrada" / "itens").glob("*.md"))

anyio.run(conferir_mcp)
print("Pacote, catálogo, CLI instalada e MCP stdio (inicialização, ferramentas, leitura e gravação): OK")
'''


def ambiente_isolado(raiz: Path) -> dict[str, str]:
    ignorar = {"PYTHONPATH", "PYTHONHOME", "ORQUESTRA_VAULT", "VIRTUAL_ENV", "UV_PROJECT", "UV_PROJECT_ENVIRONMENT"}
    env = {k: v for k, v in os.environ.items() if k not in ignorar and not k.startswith("ORQUESTRA_TESTE_")}
    env["ORQUESTRA_HOME"] = str(raiz / "configuracao")
    env["PYTHONUTF8"] = "1"
    return env


def verificar_fonte() -> None:
    """Reproduz a instalação e o launcher documentados fora do checkout original."""
    with tempfile.TemporaryDirectory(prefix="orquestra-fonte-", ignore_cleanup_errors=True) as temporario:
        raiz = Path(temporario)
        projeto = raiz / "Aplicativo com espaços e acentuação"
        projeto.mkdir()
        fonte = Path(__file__).resolve().parents[1]
        for nome in ("pyproject.toml", "uv.lock", "README.md", "LICENSE"):
            shutil.copy2(fonte / nome, projeto / nome)
        shutil.copytree(fonte / "src", projeto / "src", ignore=shutil.ignore_patterns("__pycache__"))
        env = ambiente_isolado(raiz)
        subprocess.run(["uv", "sync", "--locked", "--no-dev", "--python", sys.executable, "--directory", str(projeto)],
                       cwd=raiz, env=env, check=True)
        python = projeto / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env["ORQUESTRA_TESTE_PROJETO"] = str(projeto)
        env["ORQUESTRA_TESTE_UV"] = shutil.which("uv") or "uv"
        env["UV_PYTHON"] = str(python)
        subprocess.run([str(python), "-c", VERIFICAR], cwd=raiz, env=env, check=True)
    if raiz.exists():
        print(f"Aviso: um arquivo temporário está ocupado; limpeza pendente em {raiz}", flush=True)
    print("Instalação editável sem dependências de desenvolvimento e launcher uv em caminho Unicode: OK", flush=True)


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
            env = ambiente_isolado(raiz)
            subprocess.run([str(python), "-m", "orquestra", "--version"], cwd=raiz, env=env, check=True)
            subprocess.run([str(python), "-c", VERIFICAR], cwd=raiz, env=env, check=True)
        if raiz.exists():
            print(f"Aviso: um arquivo temporário está ocupado; limpeza pendente em {raiz}", flush=True)
        print(f"Distribuição validada: {arquivo.name}", flush=True)
    verificar_fonte()


if __name__ == "__main__":
    main()
