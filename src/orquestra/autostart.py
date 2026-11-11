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
import subprocess
import sys
from pathlib import Path

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
        linha = " ".join(f'""{parte}""' for parte in comando)
        return f'CreateObject("WScript.Shell").Run "{linha}", 0, False\r\n'
    if sys.platform == "darwin":
        argumentos = "\n".join(f"    <string>{parte}</string>" for parte in comando)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            f"  <key>Label</key><string>{ROTULO}</string>\n"
            f"  <key>ProgramArguments</key>\n  <array>\n{argumentos}\n  </array>\n"
            "  <key>RunAtLoad</key><true/>\n"
            "</dict>\n</plist>\n"
        )
    linha = " ".join(f'"{parte}"' for parte in comando)
    return f"[Desktop Entry]\nType=Application\nName=Orquestra\nExec={linha}\nX-GNOME-Autostart-enabled=true\n"


def executar(acao: str, vault: Path) -> str:
    arquivo = _arquivo()
    if acao == "status":
        return f"Início automático ligado ({arquivo})." if arquivo.exists() else "Início automático desligado."

    if acao == "ativar":
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(_conteudo(vault), encoding="utf-8")
        if sys.platform == "darwin":
            subprocess.run(["launchctl", "load", str(arquivo)], capture_output=True)
        return f"Pronto: o painel vai iniciar junto com o computador.\nArquivo criado: {arquivo}\nPara desfazer: orquestra autostart desativar"

    if not arquivo.exists():
        return "O início automático já estava desligado."
    if sys.platform == "darwin":
        subprocess.run(["launchctl", "unload", str(arquivo)], capture_output=True)
    arquivo.unlink()
    return "Início automático desligado."
