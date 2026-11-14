"""Linha de comando do Orquestra.

    orquestra                   inicia o painel; na primeira vez, a tela pergunta qual vault usar
    orquestra criar [pasta]     cria um vault a partir do modelo
    orquestra adotar PASTA      prepara um vault do Obsidian que já existe
    orquestra mcp               servidor MCP: o vault vira um conector para agentes
    orquestra doctor            confere a instalação e explica o que falta
    orquestra coletar [módulo]  roda os coletores agora
    orquestra backup            faz commit do vault (e envia, com --enviar)
    orquestra autostart ...     liga/desliga o início automático com o computador
    orquestra status            mostra se o painel está rodando, em que porta e com qual vault
    orquestra parar             encerra o painel, mesmo que aberto por outro terminal ou agente
    orquestra reiniciar         para e abre de novo (para pegar uma atualização)
    orquestra atualizar         baixa a versão nova do GitHub e reabre o painel
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from orquestra import __version__, backup, preparo
from orquestra.config import ConfigInvalida, PORTA_PADRAO, lembrar_vault, ler_config_painel, localizar_vault, pasta_app

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
            "  Para escolher pela tela:     orquestra\n"
            "  Para criar um novo:          orquestra criar\n"
            "  Para usar um que já existe:  orquestra adotar CAMINHO"
        )
    if not vault.is_dir():
        sys.exit(f"A pasta do vault não existe: {vault}\nCrie com `orquestra criar` ou aponte outra com --vault.")
    return vault


# ---------------------------------------------------------------- criar e adotar


def _contar(relatorio: preparo.Relatorio) -> None:
    for aviso in relatorio.avisos:
        print("  Aviso: " + aviso)
    print("  Histórico (git): " + ("ligado" if relatorio.com_git else "desligado"))
    print(f"  Chaves de API:   {pasta_app() / '.env'}")
    print("\nPróximos passos:")
    print("  1. Inicie o painel:  orquestra (ou `uv run --frozen orquestra` no projeto)")
    print("  2. Abra no Obsidian: 'Abrir pasta como cofre' e escolha a pasta acima (opcional)")
    print("  3. Aponte seu agente (Claude, Codex...) para essa pasta: ele lê o AGENTS.md sozinho")


def criar_vault(destino: Path, perfil: str | None = None, exemplos: bool = True) -> Path:
    """Cria um vault novo a partir de um perfil do catálogo."""
    try:
        destino = preparo.conferir_pasta(destino)
        modulos = preparo.modulos_do_perfil(perfil)
    except preparo.PastaRecusada as e:
        sys.exit(str(e))
    if (destino / "orquestra.yaml").is_file():
        print(f"Já existe um vault em {destino}. Vou usar esse.")
        lembrar_vault(destino)
        return destino
    if destino.exists() and any(destino.iterdir()):
        sys.exit(
            f"A pasta {destino} já tem arquivos.\n"
            "  Para criar do zero, escolha uma pasta vazia ou nova.\n"
            f"  Para usar essa pasta como está (um vault do Obsidian, por exemplo): orquestra adotar \"{destino}\""
        )
    relatorio = preparo.preparar(destino, modulos, exemplos=exemplos, com_backup=True)
    lembrar_vault(destino)
    print(f"Vault criado em: {destino}")
    _contar(relatorio)
    return destino


def adotar_vault(destino: Path, modulos: list[str], pastas: list[str], com_backup: bool = False) -> Path:
    """Prepara uma pasta que já tem notas, sem alterar nenhuma delas."""
    try:
        destino = preparo.conferir_pasta(destino)
        if not destino.is_dir():
            sys.exit(f"A pasta {destino} não existe. Para criar um vault novo: orquestra criar \"{destino}\"")
        relatorio = preparo.preparar(
            destino, modulos, exemplos=False, com_backup=com_backup, pastas=[{"pasta": p} for p in pastas]
        )
    except preparo.PastaRecusada as e:
        sys.exit(str(e))
    lembrar_vault(destino)
    print(f"Vault pronto em: {destino}")
    print(f"  Criei {len(relatorio.criados)} arquivo(s); nenhuma nota sua foi alterada.")
    _contar(relatorio)
    return destino


# ---------------------------------------------------------------- iniciar


def _porta_livre(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name != "nt":
            # Como o servidor asyncio no Unix: aceita TIME_WAIT de conexões
            # encerradas, mas continua recusando uma porta com listener ativo.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", porta))
            return True
        except OSError:
            return False


def iniciar(args: argparse.Namespace) -> None:
    from orquestra import processo
    import uvicorn

    from orquestra.hospedeiro import Hospedeiro

    try:
        vault = localizar_vault(getattr(args, "vault", None))
    except ConfigInvalida:
        print("A configuração local está inválida. Corrija config.yaml na pasta do Orquestra; abrindo as boas-vindas.")
        vault = None
    processo.preparar_saida(vault)
    if vault is not None and not vault.is_dir():
        if getattr(args, "vault", None):
            sys.exit(f"A pasta do vault não existe: {vault}\nCrie com `orquestra criar` ou aponte outra com --vault.")
        print(f"A pasta do vault não existe mais: {vault}\nAbrindo a tela de boas-vindas para você escolher outra.\n")
        vault = None
    if vault is not None and getattr(args, "vault", None):
        lembrar_vault(vault)  # indicou um vault na mão: passa a ser o padrão das próximas vezes
    porta = getattr(args, "porta", None)
    if porta is None:
        try:
            porta = ler_config_painel(vault).porta if vault else PORTA_PADRAO
        except ConfigInvalida:
            porta = PORTA_PADRAO
            print("orquestra.yaml precisa de correção. Abrindo o painel com configurações seguras na porta padrão.")
    if not 1 <= porta <= 65535:
        sys.exit("Use uma porta entre 1 e 65535.")
    if not _porta_livre(porta):
        from orquestra import processo

        aberto = processo.consultar(porta)
        if aberto:
            sys.exit(
                f"O Orquestra já está rodando em http://localhost:{porta} (vault: {aberto.get('vault') or 'nenhum'}).\n"
                "Abra esse endereço no navegador, ou use `orquestra reiniciar` para pegar uma atualização "
                "e `orquestra parar` para encerrá-lo."
            )
        sys.exit(
            f"A porta {porta} está em uso por outro programa.\n"
            f"Mude 'porta' no orquestra.yaml ou use: orquestra iniciar --porta {porta + 1 if porta < 65535 else 8420}"
        )
    from orquestra import autostart, processo
    if vault and autostart.resumo(vault)["ativo"] and not processo.em_segundo_plano():
        processo.destacar(vault, porta, 0)
        print(f"Abrindo o painel em segundo plano em http://localhost:{porta}. Você pode fechar este terminal.")
        return
    app = Hospedeiro(vault)
    url = f"http://localhost:{porta}"
    print(f"Orquestra {__version__}")
    print(f"  Vault:  {vault or 'ainda não escolhido (a tela de boas-vindas vai perguntar)'}")
    print(f"  Painel: {url}")
    print("  O painel escuta só neste computador. Para o celular, veja docs/tailscale.md.")
    print("  Ctrl+C (ou `orquestra parar`, de qualquer terminal) para encerrar.\n")
    # Na primeira vez não há vault: abrimos o navegador sozinhos, porque é lá que a pessoa escolhe.
    if getattr(args, "abrir", False) or vault is None:
        threading.Timer(1.2, webbrowser.open, [url]).start()
    # 127.0.0.1 de propósito: o painel não tem senha e não deve ficar visível na rede.
    from orquestra import processo

    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning", timeout_graceful_shutdown=2))
    app.servidor = servidor  # permite `orquestra parar` fechar este processo pelo endpoint local
    processo.registrar(porta, vault)
    try:
        servidor.run()
    finally:
        processo.esquecer(os.getpid())


# ---------------------------------------------------------------- status, parar, reiniciar, atualizar


def status(args: argparse.Namespace) -> None:
    from orquestra import processo

    info = processo.localizar(getattr(args, "porta", None))
    if info is None:
        print("O painel não está rodando. Para abrir: uv run --frozen orquestra")
        return
    if info.get("antigo"):
        print(f"Há um painel de uma versão anterior rodando em http://localhost:{info['porta']} (processo {info['pid']}).")
        print("Use `orquestra reiniciar` para trocá-lo pela versão atual.")
        return
    if not info["respondendo"]:
        print(f"Há um painel registrado (processo {info['pid']}, porta {info['porta']}) que não responde.")
        print("Se ele travou: uv run --frozen orquestra parar --forcar")
        return
    print(f"Rodando em http://localhost:{info['porta']} (Orquestra {info.get('versao', '?')}, processo {info.get('pid')})")
    print(f"  Vault: {info.get('vault') or 'ainda não escolhido'}")
    if info.get("versao") and info["versao"] != __version__:
        print(f"  Esta instalação é a {__version__}: rode `orquestra reiniciar` para usar a versão nova.")


def parar(args: argparse.Namespace) -> dict | None:
    from orquestra import processo

    try:
        info = processo.parar(getattr(args, "porta", None), getattr(args, "forcar", False))
    except RuntimeError as erro:
        sys.exit(str(erro))
    if info is None:
        print("O painel não estava rodando.")
    else:
        print(f"Painel encerrado (porta {info['porta']}).")
    return info


def reiniciar(args: argparse.Namespace) -> None:
    info = parar(args)
    if info and getattr(args, "vault", None) is None and info.get("vault"):
        args.vault = info["vault"]
    if info and getattr(args, "porta", None) is None:
        args.porta = info["porta"]
    print("Abrindo de novo…\n")
    iniciar(args)


def _git(*partes: str, pasta: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *partes], cwd=pasta, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)


def atualizar(args: argparse.Namespace) -> None:
    """Baixa a versão nova (git pull) e, se o painel estava aberto, reabre já atualizado."""
    import shutil

    from orquestra import processo

    raiz = Path(__file__).resolve().parents[2]
    if not (raiz / ".git").exists() or not (raiz / "pyproject.toml").is_file():
        sys.exit("Esta instalação não veio de um `git clone`; atualize pelo mesmo caminho em que instalou.")
    if not shutil.which("git"):
        sys.exit("O git não foi encontrado. Instale-o e tente de novo.")
    alteradas = _git("status", "--porcelain", "--untracked-files=no", pasta=raiz).stdout.strip()
    if alteradas:
        sys.exit("Há arquivos do aplicativo alterados nesta pasta. Guarde ou desfaça essas mudanças antes de atualizar:\n"
                 + alteradas)
    print("Procurando a versão nova…")
    busca = _git("fetch", "--quiet", pasta=raiz)
    if busca.returncode != 0:
        sys.exit("Não consegui falar com o GitHub:\n" + (busca.stderr.strip() or busca.stdout.strip()))
    antes = _git("rev-parse", "HEAD", pasta=raiz).stdout.strip()
    novos = _git("log", "--oneline", "HEAD..@{u}", pasta=raiz)
    if novos.returncode != 0:
        sys.exit("Esta pasta não acompanha um branch remoto. Use `git pull` manualmente.")
    if not novos.stdout.strip():
        print(f"Você já está na versão mais recente ({__version__}).")
        return
    aberto = processo.localizar()
    if aberto:
        parar(argparse.Namespace(porta=aberto["porta"], forcar=False))
    puxar = _git("pull", "--ff-only", "--quiet", pasta=raiz)
    if puxar.returncode != 0:
        sys.exit("A atualização não pôde ser aplicada sem mesclar mudanças:\n" + puxar.stderr.strip())
    depois = _git("log", "--oneline", f"{antes}..HEAD", pasta=raiz).stdout.strip().splitlines()
    print(f"Atualizado: {len(depois)} mudança(s). Veja o que mudou no CHANGELOG.md.")
    uv = os.environ.get("UV") or shutil.which("uv")
    if aberto and uv:
        # Um `uv run` novo instala as dependências da versão nova antes de abrir o painel.
        comando = [uv, "run", "--frozen", "orquestra", "iniciar", "--porta", str(aberto["porta"])]
        if aberto.get("vault"):
            comando += ["--vault", aberto["vault"]]
        print("Abrindo o painel atualizado…\n")
        sys.exit(subprocess.call(comando, cwd=raiz))
    print("Para abrir: uv run --frozen orquestra")


# ---------------------------------------------------------------- outros comandos


def coletar(args: argparse.Namespace) -> None:
    from orquestra.painel import Painel

    painel = Painel(_exigir_vault(args))
    alvo = getattr(args, "modulo", None)
    if alvo and alvo not in painel.indice.modulos:
        sys.exit(f"O módulo '{alvo}' não existe. Confira as áreas do vault no painel.")
    rodou = False
    falhou = False
    for modulo in painel.indice.modulos.values():
        if alvo and modulo.id != alvo:
            continue
        for coletor in modulo.coletores:
            rodou = True
            print(f"{modulo.nome} · {coletor.nome}... ", end="", flush=True)
            r = painel.rodar_coletor_agora(modulo, coletor)
            print(f"{r.novos} novos, {r.repetidos} já conhecidos" if r.ok else f"falhou: {r.erro}")
            falhou = falhou or not r.ok
    if not rodou:
        print("Nenhum coletor encontrado" + (f" no módulo '{alvo}'." if alvo else "."))
    if falhou:
        sys.exit(1)


def fazer_backup(args: argparse.Namespace) -> None:
    vault = _exigir_vault(args)
    if not backup.git_disponivel():
        sys.exit("O git não está instalado. Instale em https://git-scm.com e rode de novo.")
    if not backup.e_repositorio(vault):
        backup.iniciar(vault)
        print("Repositório preparado. Revise e autorize com `orquestra confiar backup` antes da primeira cópia.")
    resultado = backup.commit(vault)
    print({"feito": "Commit feito.", "nada": "Nada mudou desde o último commit."}.get(resultado, resultado))
    if resultado not in ("feito", "nada"):
        sys.exit(1)
    if getattr(args, "enviar", False):
        envio = backup.push(vault)
        print(
            {
                "feito": "Enviado para o repositório remoto.",
                "sem_remoto": "Não há repositório remoto. Veja docs/backup.md para configurar um (privado).",
            }.get(envio, envio)
        )
        if envio != "feito":
            sys.exit(1)


def confiar(args: argparse.Namespace) -> None:
    """Exibe o que será autorizado; só aceita a assinatura revisada explicitamente."""
    vault = _exigir_vault(args)
    if args.alvo == "backup":
        obter = lambda: backup.resumo(vault)
        aprovar = lambda assinatura: backup.autorizar(vault, assinatura)
        revogar = lambda: backup.revogar(vault)
    else:
        from orquestra import confianca
        from orquestra.painel import NaoEncontrado, Painel
        if not args.modulo or not args.script:
            sys.exit("Use: orquestra confiar coletor MODULO SCRIPT [--assinatura HASH | --revogar]")
        painel = Painel(vault)
        try:
            modulo, coletor = painel.coletor(args.modulo, args.script)
        except NaoEncontrado as erro:
            raise ValueError(str(erro)) from None
        obter = lambda: confianca.resumo(vault, modulo, coletor)
        aprovar = lambda assinatura: confianca.autorizar(vault, modulo, coletor, assinatura)
        revogar = lambda: confianca.revogar(vault, modulo, coletor)
    if args.revogar:
        revogar()
        print("Autorização local revogada.")
        return
    if args.assinatura:
        aprovar(args.assinatura)
        print("Autorização local registrada para esta assinatura.")
        return
    estado = obter()
    # Não despejar valores da configuração de coletores ou credenciais no terminal.
    visivel = {k: estado[k] for k in ("assinatura", "confiavel", "arquivos", "requer", "remotos", "avisos", "erro") if k in estado}
    print(json.dumps(visivel, ensure_ascii=False, indent=2))
    print("Confira os arquivos e permissões. Para autorizar, repita este comando com --assinatura HASH usando a assinatura acima.")


def _main(argv: list[str] | None = None) -> None:
    _preparar_saida()
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--vault", default=argparse.SUPPRESS, help="pasta do vault (por padrão, a última usada)")

    p = argparse.ArgumentParser(prog="orquestra", description="Painel operacional local para trabalhar com agentes de IA.")
    p.add_argument("--vault", help="pasta do vault (por padrão, a última usada)")
    p.add_argument("--version", action="version", version=f"orquestra {__version__}")
    sub = p.add_subparsers(dest="comando", metavar="comando")

    c = sub.add_parser("criar", aliases=["init"], help="cria um vault novo a partir do modelo")
    c.add_argument("caminho", nargs="?", help="onde criar (padrão: pasta Orquestra na sua pasta pessoal)")
    c.add_argument("--perfil", help="ponto de partida: " + ", ".join(preparo.perfis()) + f" (padrão: {preparo.PERFIL_PADRAO})")
    c.add_argument("--sem-exemplos", action="store_true", help="cria os módulos vazios, sem as notas de exemplo")

    d = sub.add_parser("adotar", help="prepara uma pasta que já tem notas (um vault do Obsidian), sem alterar nenhuma")
    d.add_argument("caminho", help="a pasta do vault que já existe")
    d.add_argument("--modulos", default="", help="módulos prontos a acrescentar, separados por vírgula: " + ", ".join(preparo.catalogo()))
    d.add_argument("--pastas", default="", help="pastas suas a mostrar no painel, separadas por vírgula")
    d.add_argument("--backup", action="store_true", help="liga o histórico em git nesse vault")

    sub.add_parser("mcp", parents=[comum], help="inicia o servidor MCP, para agentes usarem o vault como conector")

    i = sub.add_parser("iniciar", parents=[comum], help="inicia o painel (é o padrão)")
    i.add_argument("--porta", type=int, help="porta local (padrão: a do orquestra.yaml, 8420)")
    i.add_argument("--abrir", action="store_true", help="abre o navegador ao iniciar")

    sub.add_parser("doctor", aliases=["diagnostico"], parents=[comum], help="confere a instalação e explica o que falta")

    k = sub.add_parser("coletar", parents=[comum], help="roda os coletores agora")
    k.add_argument("modulo", nargs="?", help="só os coletores deste módulo")

    b = sub.add_parser("backup", parents=[comum], help="faz commit do vault no git")
    b.add_argument("--enviar", action="store_true", help="também envia para o repositório remoto")

    t = sub.add_parser("confiar", parents=[comum], help="revisa e autoriza coletores ou histórico somente neste computador")
    t.add_argument("alvo", choices=["coletor", "backup"])
    t.add_argument("modulo", nargs="?")
    t.add_argument("script", nargs="?")
    escolha_confianca = t.add_mutually_exclusive_group()
    escolha_confianca.add_argument("--assinatura", default="", help="assinatura exata dos arquivos revisados")
    escolha_confianca.add_argument("--revogar", action="store_true")

    s = sub.add_parser("status", help="mostra se o painel está rodando, em que porta e com qual vault")
    s.add_argument("--porta", type=int, help="consultar esta porta em vez da registrada")
    pa = sub.add_parser("parar", aliases=["stop"], help="encerra o painel, mesmo que aberto por outro terminal ou agente")
    pa.add_argument("--porta", type=int, help="parar o painel desta porta")
    pa.add_argument("--forcar", action="store_true", help="encerrar o processo registrado mesmo que ele não responda")
    r = sub.add_parser("reiniciar", aliases=["restart"], parents=[comum], help="para o painel e abre de novo, com o código atual")
    r.add_argument("--porta", type=int, help="porta do painel (padrão: a que estava em uso)")
    r.add_argument("--abrir", action="store_true", help="abre o navegador ao iniciar")
    r.add_argument("--forcar", action="store_true", help="encerrar o processo registrado mesmo que ele não responda")
    sub.add_parser("atualizar", aliases=["update"], help="baixa a versão nova do GitHub e reabre o painel, se estava aberto")

    a = sub.add_parser("autostart", parents=[comum], help="início automático com o computador")
    a.add_argument("acao", choices=["ativar", "desativar", "status"])

    remover = sub.add_parser("desinstalar", aliases=["uninstall"], parents=[comum], help="desliga o início automático e orienta a remoção preservando suas notas")
    remover.add_argument("--confirmar", action="store_true", help="remover a entrada de início automático; preserva vault, configurações e secrets")

    args = p.parse_args(argv)
    comando = args.comando or "iniciar"
    if args.vault is not None and not args.vault.strip():
        p.error("--vault precisa de um caminho; não use um valor vazio.")
    if comando in ("criar", "init", "adotar") and args.vault is not None:
        p.error(f"{comando} recebe a pasta como argumento: `orquestra {comando} PASTA`, sem --vault.")
    if comando == "confiar" and args.alvo == "backup" and (args.modulo or args.script):
        t.error("backup não recebe módulo nem script; use `orquestra confiar backup`.")

    if comando in ("criar", "init"):
        criar_vault(Path(args.caminho) if args.caminho else Path.home() / "Orquestra", args.perfil, not args.sem_exemplos)
    elif comando == "adotar":
        separar = lambda texto: [p.strip() for p in texto.split(",") if p.strip()]  # noqa: E731
        adotar_vault(Path(args.caminho), separar(args.modulos), separar(args.pastas), args.backup)
    elif comando == "mcp":
        from orquestra.mcp_servidor import executar as executar_mcp

        executar_mcp(_exigir_vault(args))
    elif comando == "iniciar":
        iniciar(args)
    elif comando == "status":
        status(args)
    elif comando in ("parar", "stop"):
        parar(args)
    elif comando in ("reiniciar", "restart"):
        reiniciar(args)
    elif comando in ("atualizar", "update"):
        atualizar(args)
    elif comando in ("doctor", "diagnostico"):
        from orquestra.doctor import executar

        sys.exit(executar(localizar_vault(getattr(args, "vault", None))))
    elif comando == "coletar":
        coletar(args)
    elif comando == "backup":
        fazer_backup(args)
    elif comando == "confiar":
        confiar(args)
    elif comando in ("desinstalar", "uninstall"):
        if args.confirmar:
            from orquestra import autostart
            print(autostart.executar("desativar"))
        print("Encerre o painel com Ctrl+C. Para remover o início automático, use orquestra desinstalar --confirmar. Depois remova a pasta clonada do programa pelo seu gerenciador de arquivos. Seu vault e ~/.orquestra são preservados; confira seus backups antes de removê-los manualmente.")
    elif comando == "autostart":
        from orquestra import autostart

        vault = _exigir_vault(args) if args.acao == "ativar" else None
        print(autostart.executar(args.acao, vault))


def main(argv: list[str] | None = None) -> None:
    try:
        _main(argv)
    except subprocess.TimeoutExpired:
        sys.exit("O comando auxiliar não respondeu dentro do prazo. Confira o serviço e tente novamente.")
    except (ValueError, OSError, RuntimeError) as erro:
        sys.exit(f"Não foi possível concluir: {erro}")


if __name__ == "__main__":
    main()
