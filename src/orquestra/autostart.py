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
import subprocess
import sys
from pathlib import Path

from orquestra.armazenamento import atualizar_bytes

ROTULO = "dev.orquestra.painel"


def _comando(vault: Path) -> list[str]:
    return [sys.executable, "-m", "orquestra", "iniciar", "--vault", str(vault)]


def _arquivo() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Orquestra.vbs"
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


def executar(acao: str, vault: Path) -> str:
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
        conteudo = _conteudo(vault).encode("utf-8")
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
