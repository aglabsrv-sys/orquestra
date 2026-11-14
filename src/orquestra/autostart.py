"""Início automático do painel junto com o computador (opcional).

O painel não depende disto: é só uma conveniência para quem deixa a máquina
ligada e quer os coletores rodando sozinhos. Cada sistema tem o seu jeito, e
nenhum deles pede permissão de administrador:

- Windows: um pequeno .vbs na pasta Inicializar, que abre o painel sem janela;
- macOS: um LaunchAgent em ~/Library/LaunchAgents;
- Linux: um .desktop em ~/.config/autostart.
"""

from __future__ import annotations

import os
import plistlib
import re
import shlex
import subprocess
import sys
from pathlib import Path

from orquestra.armazenamento import atualizar_bytes

ROTULO = "dev.orquestra.painel"


def _comando(vault: Path) -> list[str]:
    return [sys.executable, "-m", "orquestra", "iniciar", "--vault", str(vault)]


def _arquivo() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Orquestra.vbs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / f"{ROTULO}.plist"
    return Path.home() / ".config" / "autostart" / "orquestra.desktop"


def _conteudo(vault: Path) -> str:
    comando = _comando(vault)
    if sys.platform == "win32":
        # pythonw.exe roda sem abrir janela de terminal.
        executavel = Path(comando[0]).with_name("pythonw.exe")
        if executavel.is_file():
            comando[0] = str(executavel)
        if any("\n" in parte or "\r" in parte or '"' in parte for parte in comando):
            raise ValueError("O caminho do início automático não pode conter aspas ou quebras de linha.")
        # WScript.Shell.Run expande %VAR%; escapar como Chr(37) impediria apenas
        # a expansão do VBS, não a do Run. Recusamos esse caso explicitamente.
        if any("%" in parte for parte in comando):
            raise ValueError("O início automático do Windows não aceita caminhos com %. Escolha outra pasta.")
        linha = subprocess.list2cmdline(comando).replace('"', '""')
        return f'CreateObject("WScript.Shell").Run "{linha}", 0, False\r\n'
    if sys.platform == "darwin":
        return plistlib.dumps({"Label": ROTULO, "ProgramArguments": comando, "RunAtLoad": True},
                              fmt=plistlib.FMT_XML).decode("utf-8")
    def argumento(parte: str) -> str:
        if any(c in parte for c in ("\n", "\r", "\0")):
            raise ValueError("O caminho do início automático contém caracteres inválidos.")
        # Desktop Entry tem duas camadas de escape: valor da chave e argumento
        # Exec. %% é um percentual literal, nunca um field code da especificação.
        escapado = parte.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
        return '"' + escapado.replace("\\", "\\\\") + '"'
    linha = " ".join(argumento(parte) for parte in comando)
    return f"[Desktop Entry]\nType=Application\nName=Orquestra\nExec={linha}\nX-GNOME-Autostart-enabled=true\n"


def _argumentos_configurados(texto: str) -> list[str] | None:
    """Reconhece apenas nossos lançadores, sem executar seu conteúdo."""
    if sys.platform == "darwin":
        try:
            dados = plistlib.loads(texto.encode("utf-8"))
        except (ValueError, plistlib.InvalidFileException):
            return None
        if not isinstance(dados, dict) or dados.get("Label") != ROTULO or dados.get("RunAtLoad") is not True:
            return None
        argumentos = dados.get("ProgramArguments")
    elif sys.platform == "win32":
        linha = re.fullmatch(r'\s*CreateObject\("WScript\.Shell"\)\.Run "((?:""|[^"])*)", 0, False\s*', texto, re.I)
        if not linha:
            return None
        comando = linha.group(1).replace('""', '"')
        partes = re.fullmatch(r'(?P<exe>"[^"]+"|[^"\s]+) -m orquestra iniciar --vault (?P<vault>"[^"]+"|[^"\s]+)', comando)
        if not partes:
            return None
        argumentos = [partes.group("exe").strip('"'), "-m", "orquestra", "iniciar", "--vault", partes.group("vault").strip('"')]
    else:
        dados = dict(linha.split("=", 1) for linha in texto.splitlines() if "=" in linha)
        if dados.get("Type") != "Application" or dados.get("X-GNOME-Autostart-enabled", "true").lower() != "true" or dados.get("Hidden", "false").lower() == "true":
            return None
        try:
            argumentos = [p.replace("\\$", "$").replace("\\`", "`").replace("%%", "%")
                          for p in shlex.split(dados.get("Exec", "").replace("\\\\", "\\"))]
        except ValueError:
            return None
    if not isinstance(argumentos, list) or len(argumentos) != 6 or argumentos[1:5] != ["-m", "orquestra", "iniciar", "--vault"] or not all(isinstance(a, str) for a in argumentos):
        return None
    return argumentos


def resumo(vault: Path) -> dict:
    """Estado local do lançador e vínculo com o cofre aberto; não expõe caminhos."""
    resultado = {"presente": False, "ativo": False, "neste_cofre": False,
                 "estado": "desligado", "descricao": "Desativado neste computador."}
    try:
        arquivo = _arquivo()
        if not arquivo.is_file():
            return resultado
        resultado["presente"] = True
        if arquivo.stat().st_size > 64 * 1024:
            return {**resultado, "estado": "revisar", "descricao": "A configuração de inicialização precisa ser atualizada."}
        bruto = arquivo.read_bytes()
        argumentos = _argumentos_configurados(bruto.decode("utf-16" if bruto.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"))
        if not argumentos:
            return {**resultado, "estado": "revisar", "descricao": "A configuração de inicialização precisa ser atualizada."}
        if not Path(argumentos[0]).is_file():
            return {**resultado, "estado": "revisar", "descricao": "A instalação mudou. Ative novamente para atualizar a inicialização."}
        neste_cofre = os.path.normcase(str(Path(argumentos[5]).resolve())) == os.path.normcase(str(vault.resolve()))
        resultado["neste_cofre"] = neste_cofre
        if not neste_cofre:
            return {**resultado, "estado": "outro_cofre", "descricao": "Ativado para outro cofre neste computador."}
        if sys.platform == "win32" and not bruto.startswith((b"\xff\xfe", b"\xfe\xff")):
            return {**resultado, "estado": "revisar", "descricao": "Atualize a inicialização para preservar caminhos acentuados e iniciar sem console."}
        if sys.platform == "darwin":
            r = subprocess.run(["launchctl", "list", ROTULO], capture_output=True, timeout=15)
            if r.returncode != 0:
                return {**resultado, "estado": "pendente", "descricao": "Configurado; o macOS ainda não confirmou a ativação."}
        return {**resultado, "ativo": True, "estado": "ativo", "descricao": "Ativado para este cofre."}
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
        return {**resultado, "estado": "indisponivel", "descricao": "Não consegui conferir a inicialização. Tente novamente."}


def executar(acao: str, vault: Path | None = None) -> str:
    if acao not in ("status", "ativar", "desativar"):
        raise ValueError("Use status, ativar ou desativar para o início automático.")
    arquivo = _arquivo()
    if acao == "status":
        if sys.platform == "darwin" and arquivo.exists():
            r = subprocess.run(["launchctl", "list", ROTULO], capture_output=True, timeout=15)
            if r.returncode != 0:
                return f"Arquivo de início automático presente, mas o macOS não confirmou o carregamento ({arquivo})."
        return f"Início automático ligado ({arquivo})." if arquivo.exists() else "Início automático desligado."

    if acao == "ativar":
        if vault is None:
            raise ValueError("Escolha um vault com --vault antes de ativar o início automático.")
        if resumo(vault)["ativo"]:
            return "O início automático já está ligado para este cofre."
        # WScript lê Unicode com BOM; UTF-8 sem BOM corrompe caminhos acentuados.
        conteudo = _conteudo(vault).encode("utf-16" if sys.platform == "win32" else "utf-8")
        if sys.platform == "darwin" and arquivo.exists():
            carregado = subprocess.run(["launchctl", "list", ROTULO], capture_output=True, timeout=15)
            if carregado.returncode == 0:
                r = subprocess.run(["launchctl", "unload", str(arquivo)], capture_output=True, timeout=15)
                if r.returncode != 0:
                    raise RuntimeError("O macOS não confirmou a atualização do início automático. A configuração foi preservada.")
        atualizar_bytes(arquivo, lambda anterior: conteudo)
        if sys.platform == "darwin":
            r = subprocess.run(["launchctl", "load", str(arquivo)], capture_output=True, timeout=15)
            if r.returncode != 0:
                raise RuntimeError("O arquivo foi criado, mas o macOS não ativou o início automático. Confira LaunchAgents e tente novamente.")
        return f"Pronto: o painel vai iniciar junto com o computador.\nArquivo criado: {arquivo}\nPara desfazer: orquestra autostart desativar"

    if not arquivo.exists():
        return "O início automático já estava desligado."
    if sys.platform == "darwin":
        r = subprocess.run(["launchctl", "unload", str(arquivo)], capture_output=True, timeout=15)
        if r.returncode != 0:
            raise RuntimeError("O macOS não confirmou a desativação. O arquivo foi preservado para você tentar novamente.")
    arquivo.unlink()
    return "Início automático desligado."
