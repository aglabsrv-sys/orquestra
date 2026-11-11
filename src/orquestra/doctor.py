"""`orquestra doctor`: confere a instalação e explica, em português, o que falta.

Cada verificação devolve um item com estado "ok", "aviso" (funciona, mas vale
olhar) ou "erro" (algo não vai funcionar) e, quando faz sentido, o que fazer.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from orquestra import backup
from orquestra.config import carregar_env, ler_config_painel, pasta_app
from orquestra.coletores import caminho_script

MARCAS = {"ok": "[ok]   ", "aviso": "[!]    ", "erro": "[erro] "}


@dataclass
class Item:
    estado: str
    titulo: str
    detalhe: str = ""


def _rodar(*comando: str, tempo: int = 8) -> tuple[int, str]:
    try:
        r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=tempo)
        return r.returncode, (r.stdout or r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def localizar_tailscale() -> str | None:
    achado = shutil.which("tailscale")
    if achado:
        return achado
    for candidato in (
        r"C:\Program Files\Tailscale\tailscale.exe",
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    ):
        if Path(candidato).is_file():
            return candidato
    return None


def verificar_ferramentas() -> list[Item]:
    itens = []
    v = sys.version_info
    if v >= (3, 11):
        itens.append(Item("ok", f"Python {v.major}.{v.minor}"))
    else:
        itens.append(Item("erro", f"Python {v.major}.{v.minor} é antigo demais", "O Orquestra precisa do 3.11 ou mais novo. Com o uv: `uv python install 3.12`."))

    if shutil.which("uv"):
        itens.append(Item("ok", "uv instalado"))
    else:
        itens.append(Item("aviso", "uv não encontrado", "Os coletores com dependências precisam dele. Instale em https://docs.astral.sh/uv/"))

    if backup.git_disponivel():
        itens.append(Item("ok", "git instalado"))
    else:
        itens.append(Item("aviso", "git não encontrado", "Sem ele não há histórico nem backup do vault. Instale em https://git-scm.com"))
    return itens


def verificar_vault(vault: Path | None) -> list[Item]:
    if vault is None:
        return [Item("erro", "Nenhum vault configurado", "Crie um com `orquestra criar` ou aponte um existente com `orquestra --vault CAMINHO`.")]
    if not vault.is_dir():
        return [Item("erro", f"A pasta do vault não existe: {vault}", "Confira o caminho em " + str(pasta_app() / "config.yaml"))]

    itens = [Item("ok", f"Vault: {vault}")]
    try:
        teste = vault / ".orquestra-teste.orq-tmp"
        teste.write_text("ok", encoding="utf-8")
        teste.unlink()
    except OSError:
        itens.append(Item("erro", "Sem permissão para gravar no vault", "O painel precisa criar e alterar arquivos nessa pasta."))

    if (vault / "AGENTS.md").is_file():
        itens.append(Item("ok", "AGENTS.md presente (é o que os agentes leem)"))
    else:
        itens.append(Item("aviso", "Falta o AGENTS.md na raiz do vault", "Sem ele os agentes não conhecem as regras. Copie o do vault modelo."))

    from orquestra.modulos import validar
    from orquestra.painel import Painel

    try:
        painel = Painel(vault)
    except Exception as e:
        return itens + [Item("erro", "Não consegui ler o vault", str(e))]

    modulos = painel.indice.modulos
    if modulos:
        itens.append(Item("ok", f"{len(modulos)} módulo(s): {', '.join(modulos)} · {len(painel.indice.notas)} notas"))
    else:
        itens.append(Item("aviso", "Nenhum módulo encontrado", "Um módulo é uma pasta na raiz do vault com um arquivo _modulo.yaml."))
    for modulo in modulos.values():
        for aviso in modulo.avisos:
            itens.append(Item("aviso", f"{modulo.id}/_modulo.yaml", aviso))

    quebradas = [n.rel for n in painel.indice.notas.values() if n.erro]
    if quebradas:
        itens.append(Item("aviso", f"{len(quebradas)} nota(s) com frontmatter ilegível", "O painel não grava nelas até corrigir: " + ", ".join(quebradas[:3])))
    fora = 0
    for modulo in modulos.values():
        fora += sum(1 for n in painel.indice.notas_em(modulo.id, "itens") if validar(modulo, n.meta))
    if fora:
        itens.append(Item("aviso", f"{fora} nota(s) com campos fora do schema", "Abra o módulo no painel: elas aparecem com um sinal de aviso."))

    if painel.config.captura not in modulos:
        itens.append(Item("aviso", f"Módulo de captura '{painel.config.captura}' não existe", "Ajuste 'captura' no orquestra.yaml; sem isso o botão Capturar some."))

    # ---- coletores e chaves
    segredos = {**carregar_env(), **os.environ}
    for modulo in modulos.values():
        for coletor in modulo.coletores:
            nome = f"Coletor {modulo.id}/{coletor.script}"
            if not caminho_script(modulo, coletor).is_file():
                itens.append(Item("erro", nome, "O script não existe em maquina/coletores/."))
                continue
            faltam = [c for c in coletor.requer if not segredos.get(c)]
            if faltam:
                itens.append(Item("aviso", nome, f"Falta a chave {', '.join(faltam)} em {pasta_app() / '.env'}"))
            else:
                ultima = painel.ultima_coleta(modulo.id, coletor.script)
                if ultima and not ultima.get("ok"):
                    itens.append(Item("aviso", nome, "A última execução falhou: " + str(ultima.get("erro"))))
                else:
                    itens.append(Item("ok", nome + (" (automático)" if coletor.ativo else " (manual)")))

    # ---- backup
    if backup.git_disponivel():
        if not backup.e_repositorio(vault):
            itens.append(Item("aviso", "O vault não tem histórico git", "Rode `orquestra backup` para criar. É o seu 'desfazer' para qualquer alteração de um agente."))
        elif not backup.tem_remoto(vault):
            itens.append(Item("aviso", "Backup só local", "O histórico existe, mas só neste computador. Veja docs/backup.md para enviar a um repositório privado."))
        else:
            itens.append(Item("ok", "Backup: repositório remoto configurado" + ("" if painel.config.backup.push else " (envio automático desligado)")))

    itens.extend(verificar_acesso(painel.config.porta))
    return itens


def verificar_acesso(porta: int) -> list[Item]:
    itens = []
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        aberto = s.connect_ex(("127.0.0.1", porta)) == 0
    itens.append(Item("ok", f"Painel {'rodando' if aberto else 'parado'} em http://localhost:{porta}"))

    tailscale = localizar_tailscale()
    if not tailscale:
        itens.append(Item("aviso", "Tailscale não instalado", "É o que permite abrir o painel no celular com segurança. Veja docs/tailscale.md."))
        return itens
    codigo, saida = _rodar(tailscale, "status", "--json")
    try:
        estado = json.loads(saida) if codigo == 0 else {}
    except ValueError:
        estado = {}
    if estado.get("BackendState") != "Running":
        itens.append(Item("aviso", "Tailscale instalado, mas desconectado", "Abra o Tailscale e entre na sua conta."))
        return itens
    nome = str((estado.get("Self") or {}).get("DNSName") or "").rstrip(".")
    itens.append(Item("ok", f"Tailscale conectado ({nome})"))

    _, serve = _rodar(tailscale, "serve", "status")
    if "funnel on" in serve.lower():
        itens.append(Item("erro", "Tailscale Funnel está LIGADO", "Isso expõe o painel para a internet inteira, sem senha. Desligue com `tailscale funnel reset`."))
    elif str(porta) in serve:
        itens.append(Item("ok", f"Acesso pelo celular: https://{nome}"))
    else:
        itens.append(Item("aviso", "Tailscale ainda não aponta para o painel", f"Rode uma vez: tailscale serve --bg {porta}"))
    return itens


def executar(vault: Path | None) -> int:
    print("Diagnóstico do Orquestra\n")
    itens = verificar_ferramentas() + verificar_vault(vault)
    for item in itens:
        print(MARCAS[item.estado] + item.titulo)
        if item.detalhe:
            print("         " + item.detalhe)
    erros = sum(1 for i in itens if i.estado == "erro")
    avisos = sum(1 for i in itens if i.estado == "aviso")
    print()
    if erros:
        print(f"{erros} problema(s) para resolver e {avisos} aviso(s).")
    elif avisos:
        print(f"Tudo funcionando. {avisos} aviso(s) acima para olhar quando puder.")
    else:
        print("Tudo certo.")
    return 1 if erros else 0
