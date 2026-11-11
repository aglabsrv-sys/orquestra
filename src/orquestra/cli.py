"""Linha de comando do Orquestra.

    orquestra criar [pasta]     cria um vault a partir do modelo
    orquestra                   inicia o painel (mesmo que `orquestra iniciar`)
    orquestra doctor            confere a instalação e explica o que falta
    orquestra coletar [módulo]  roda os coletores agora
    orquestra backup            faz commit do vault (e envia, com --enviar)
    orquestra autostart ...     liga/desliga o início automático com o computador
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import socket
import sys
import threading
import webbrowser
from importlib import resources
from pathlib import Path

from orquestra import __version__, backup
from orquestra.config import lembrar_vault, ler_config_painel, localizar_vault, pasta_app

MODELO_ENV = """\
# Chaves de API usadas pelos coletores. Este arquivo fica fora do vault de propósito:
# o vault vai para backup, e segredo não deve ir junto.
#
# YOUTUBE_API_KEY=
"""

_MARCADOR_DATA = re.compile(r"\{\{hoje(?:([+-])(\d+))?\}\}")


def _preparar_saida() -> None:
    """No Windows o terminal pode não estar em UTF-8; evita erro ao imprimir acentos."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass


def _exigir_vault(args: argparse.Namespace) -> Path:
    vault = localizar_vault(getattr(args, "vault", None))
    if vault is None:
        sys.exit(
            "Ainda não sei onde fica o seu vault.\n"
            "  Para criar um novo:        orquestra criar\n"
            "  Para usar um que já existe: orquestra --vault CAMINHO"
        )
    if not vault.is_dir():
        sys.exit(f"A pasta do vault não existe: {vault}\nCrie com `orquestra criar` ou aponte outra com --vault.")
    return vault


# ---------------------------------------------------------------- criar


def _datas_relativas(texto: str, hoje: dt.date) -> str:
    """Troca {{hoje}}, {{hoje+2}}, {{hoje-1}} por datas reais, para o exemplo nascer atual."""

    def trocar(m: re.Match) -> str:
        dias = int(m.group(2) or 0) * (-1 if m.group(1) == "-" else 1)
        return (hoje + dt.timedelta(days=dias)).isoformat()

    return _MARCADOR_DATA.sub(trocar, texto)


def criar_vault(destino: Path) -> Path:
    destino = destino.expanduser().resolve()
    if (destino / "orquestra.yaml").is_file():
        print(f"Já existe um vault em {destino}. Vou usar esse.")
        lembrar_vault(destino)
        return destino
    if destino.exists() and any(destino.iterdir()):
        sys.exit(f"A pasta {destino} já tem arquivos. Escolha uma pasta vazia ou nova.")

    modelo = resources.files("orquestra") / "modelo_vault"
    with resources.as_file(modelo) as origem:
        shutil.copytree(origem, destino, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))

    hoje = dt.date.today()
    for arquivo in destino.rglob("*.md"):
        texto = arquivo.read_text(encoding="utf-8")
        novo = _datas_relativas(texto, hoje)
        if novo != texto:
            arquivo.write_text(novo, encoding="utf-8")
        if arquivo.stem == "_HOJE_":
            arquivo.rename(arquivo.with_name(f"{hoje.isoformat()}.md"))

    lembrar_vault(destino)
    env = pasta_app() / ".env"
    if not env.exists():
        env.write_text(MODELO_ENV, encoding="utf-8")

    com_git = backup.iniciar(destino)
    if com_git:
        backup.commit(destino, "Vault criado pelo Orquestra")

    print(f"Vault criado em: {destino}")
    print("  Histórico (git): " + ("ligado" if com_git else "desligado, porque o git não está instalado"))
    print(f"  Chaves de API:   {env}")
    print("\nPróximos passos:")
    print("  1. Inicie o painel:  uv run orquestra")
    print("  2. Abra no Obsidian: 'Abrir pasta como cofre' e escolha a pasta acima (opcional)")
    print("  3. Aponte seu agente (Claude, Codex...) para essa pasta: ele lê o AGENTS.md sozinho")
    return destino


# ---------------------------------------------------------------- iniciar


def _porta_livre(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", porta))
            return True
        except OSError:
            return False


def iniciar(args: argparse.Namespace) -> None:
    import uvicorn

    from orquestra.servidor import criar_app

    vault = _exigir_vault(args)
    if getattr(args, "vault", None):
        lembrar_vault(vault)  # indicou um vault na mão: passa a ser o padrão das próximas vezes
    porta = getattr(args, "porta", None) or ler_config_painel(vault).porta
    if not _porta_livre(porta):
        sys.exit(
            f"A porta {porta} já está em uso. O painel talvez já esteja aberto em http://localhost:{porta}\n"
            f"Se for outro programa, mude 'porta' no orquestra.yaml ou use: orquestra iniciar --porta {porta + 1}"
        )
    app = criar_app(vault)
    url = f"http://localhost:{porta}"
    print(f"Orquestra {__version__}")
    print(f"  Vault:  {vault}")
    print(f"  Painel: {url}")
    print("  O painel escuta só neste computador. Para o celular, veja docs/tailscale.md.")
    print("  Ctrl+C para encerrar.\n")
    if getattr(args, "abrir", False):
        threading.Timer(1.2, webbrowser.open, [url]).start()
    # 127.0.0.1 de propósito: o painel não tem senha e não deve ficar visível na rede.
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning", timeout_graceful_shutdown=2)


# ---------------------------------------------------------------- outros comandos


def coletar(args: argparse.Namespace) -> None:
    from orquestra.painel import Painel

    painel = Painel(_exigir_vault(args))
    alvo = getattr(args, "modulo", None)
    rodou = False
    for modulo in painel.indice.modulos.values():
        if alvo and modulo.id != alvo:
            continue
        for coletor in modulo.coletores:
            rodou = True
            print(f"{modulo.nome} · {coletor.nome}... ", end="", flush=True)
            r = painel.rodar_coletor_agora(modulo, coletor)
            print(f"{r.novos} novos, {r.repetidos} já conhecidos" if r.ok else f"falhou: {r.erro}")
    if not rodou:
        print("Nenhum coletor encontrado" + (f" no módulo '{alvo}'." if alvo else "."))


def fazer_backup(args: argparse.Namespace) -> None:
    vault = _exigir_vault(args)
    if not backup.git_disponivel():
        sys.exit("O git não está instalado. Instale em https://git-scm.com e rode de novo.")
    if not backup.e_repositorio(vault):
        backup.iniciar(vault)
        print("Repositório git criado no vault.")
    resultado = backup.commit(vault)
    print({"feito": "Commit feito.", "nada": "Nada mudou desde o último commit."}.get(resultado, resultado))
    if getattr(args, "enviar", False):
        envio = backup.push(vault)
        print(
            {
                "feito": "Enviado para o repositório remoto.",
                "sem_remoto": "Não há repositório remoto. Veja docs/backup.md para configurar um (privado).",
            }.get(envio, envio)
        )


def main(argv: list[str] | None = None) -> None:
    _preparar_saida()
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--vault", default=argparse.SUPPRESS, help="pasta do vault (por padrão, a última usada)")

    p = argparse.ArgumentParser(prog="orquestra", description="Painel operacional local para trabalhar com agentes de IA.")
    p.add_argument("--vault", help="pasta do vault (por padrão, a última usada)")
    p.add_argument("--version", action="version", version=f"orquestra {__version__}")
    sub = p.add_subparsers(dest="comando", metavar="comando")

    c = sub.add_parser("criar", aliases=["init"], help="cria um vault novo a partir do modelo")
    c.add_argument("caminho", nargs="?", help="onde criar (padrão: pasta Orquestra na sua pasta pessoal)")

    i = sub.add_parser("iniciar", parents=[comum], help="inicia o painel (é o padrão)")
    i.add_argument("--porta", type=int, help="porta local (padrão: a do orquestra.yaml, 8420)")
    i.add_argument("--abrir", action="store_true", help="abre o navegador ao iniciar")

    sub.add_parser("doctor", aliases=["diagnostico"], parents=[comum], help="confere a instalação e explica o que falta")

    k = sub.add_parser("coletar", parents=[comum], help="roda os coletores agora")
    k.add_argument("modulo", nargs="?", help="só os coletores deste módulo")

    b = sub.add_parser("backup", parents=[comum], help="faz commit do vault no git")
    b.add_argument("--enviar", action="store_true", help="também envia para o repositório remoto")

    a = sub.add_parser("autostart", parents=[comum], help="início automático com o computador")
    a.add_argument("acao", choices=["ativar", "desativar", "status"])

    args = p.parse_args(argv)
    comando = args.comando or "iniciar"

    if comando in ("criar", "init"):
        criar_vault(Path(args.caminho) if args.caminho else Path.home() / "Orquestra")
    elif comando == "iniciar":
        iniciar(args)
    elif comando in ("doctor", "diagnostico"):
        from orquestra.doctor import executar

        sys.exit(executar(localizar_vault(getattr(args, "vault", None))))
    elif comando == "coletar":
        coletar(args)
    elif comando == "backup":
        fazer_backup(args)
    elif comando == "autostart":
        from orquestra import autostart

        print(autostart.executar(args.acao, _exigir_vault(args)))


if __name__ == "__main__":
    main()
