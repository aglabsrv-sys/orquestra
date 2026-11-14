"""O painel em execução: onde ele está e como pará-lo.

Ao subir, o painel grava `~/.orquestra/painel.json` com o pid, a porta e o vault.
Com isso `orquestra status`, `parar`, `reiniciar` e `atualizar` acham a instância
certa mesmo quando ela foi aberta por outro terminal, por um agente ou pelo início
automático: nesses casos o Ctrl+C do seu terminal não chega até ela.

Parar é educado primeiro: o comando pede a credencial local ao próprio painel e
chama `/api/local/encerrar`, que fecha o servidor como o Ctrl+C faria (vigia,
agendador e gravações pendentes terminam). Só com `--forcar`, ou quando o painel
confirmou quem é mas não fechou a tempo, o processo é encerrado à força.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from orquestra import __version__
from orquestra.config import pasta_app
from orquestra.caminhos import eh_link

ESPERA_ENCERRAR = 10.0
_trava_destacar = threading.Lock()
_retomada: tuple[tuple[str, int, int], int] | None = None


def em_segundo_plano() -> bool:
    if os.environ.get("ORQUESTRA_EM_SEGUNDO_PLANO") == "1":
        return True
    if sys.platform == "win32":
        import ctypes
        return not bool(ctypes.windll.kernel32.GetConsoleWindow())
    return os.getsid(0) == os.getpid() and (sys.stdin is None or not sys.stdin.isatty())


def destacar(vault: Path, porta: int, pid: int) -> int:
    """Prepara a retomada independente; não encerra o painel nesta requisição."""
    global _retomada
    chave = (str(vault.resolve()), porta, pid)
    with _trava_destacar:
        if _retomada and _retomada[0] == chave and vivo(_retomada[1]):
            return _retomada[1]
        casa = pasta_app().resolve()
        log = casa / "painel.log"
        if casa == vault.resolve() or casa.is_relative_to(vault.resolve()) or eh_link(log):
            raise RuntimeError("Os registros do painel em segundo plano precisam ficar fora do cofre e sem links.")
        opcoes = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB} if sys.platform == "win32" else {"start_new_session": True}
        ambiente = {**os.environ, "ORQUESTRA_EM_SEGUNDO_PLANO": "1"}
        try:
            casa.mkdir(parents=True, exist_ok=True)
            descritor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descritor, "ab") as saida:
                novo = subprocess.Popen([sys.executable, "-m", "orquestra.segundo_plano", str(vault.resolve()), str(porta), str(pid)],
                                        stdin=subprocess.DEVNULL, stdout=saida, stderr=saida, close_fds=True,
                                        env=ambiente, **opcoes)
        except OSError as erro:
            raise RuntimeError("A inicialização foi configurada, mas não consegui liberar o terminal agora. Mantenha-o aberto e tente Aplicar agora novamente.") from erro
        _retomada = (chave, novo.pid)
        return novo.pid


def arquivo() -> Path:
    return pasta_app() / "painel.json"


def registrar(porta: int, vault: Path | None) -> None:
    """Anota a instância que acabou de subir. Falhar aqui não impede o painel de abrir."""
    dados = {"pid": os.getpid(), "porta": porta, "vault": str(vault) if vault else "",
             "versao": __version__, "iniciado_em": dt.datetime.now().isoformat(timespec="seconds")}
    try:
        destino = arquivo()
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(".tmp")
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporario, destino)
    except OSError:
        pass


def esquecer(pid: int | None = None) -> None:
    """Apaga o registro, se ele ainda for desta instância (outra pode ter subido depois)."""
    try:
        atual = ler()
        if atual is not None and (pid is None or atual.get("pid") == pid):
            arquivo().unlink(missing_ok=True)
    except OSError:
        pass


def ler() -> dict[str, Any] | None:
    try:
        dados = json.loads(arquivo().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict) or not isinstance(dados.get("pid"), int) or not isinstance(dados.get("porta"), int):
        return None
    return dados


def vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32
        alca = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not alca:
            return False
        try:
            codigo = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(alca, ctypes.byref(codigo))) and codigo.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(alca)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------- conversa com o painel


def _pedir(porta: int, caminho: str, metodo: str = "GET", token: str = "", tempo: float = 3.0) -> dict[str, Any]:
    pedido = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}", method=metodo,
                                    data=b"{}" if metodo == "POST" else None)
    pedido.add_header("Content-Type", "application/json")
    if token:
        pedido.add_header("X-Orquestra-Local", token)
    with urllib.request.urlopen(pedido, timeout=tempo) as resposta:  # noqa: S310 (sempre 127.0.0.1)
        return json.loads(resposta.read().decode("utf-8") or "{}")


def _token(porta: int) -> str:
    return str(_pedir(porta, "/api/local/capacidade").get("token") or "")


def consultar(porta: int) -> dict[str, Any] | None:
    """O que o Orquestra nessa porta diz de si; None se não houver um Orquestra respondendo."""
    try:
        dados = _pedir(porta, "/api/local/painel", token=_token(porta))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return dados if dados.get("app") == "orquestra" else None


def _porta_padrao() -> int:
    from orquestra.config import PORTA_PADRAO, ConfigInvalida, ler_config_painel, localizar_vault

    try:
        vault = localizar_vault(None)
        return ler_config_painel(vault).porta if vault else PORTA_PADRAO
    except (ConfigInvalida, OSError, ValueError):
        return PORTA_PADRAO


def _pid_na_porta(porta: int) -> int | None:
    """O processo que escuta em 127.0.0.1:porta (para painéis antigos, sem registro)."""
    try:
        if sys.platform == "win32":
            saida = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=15).stdout
            for linha in saida.splitlines():
                partes = linha.split()
                if len(partes) >= 5 and partes[1].endswith(f":{porta}") and partes[3].upper() == "LISTENING":
                    return int(partes[4])
            return None
        saida = subprocess.run(["lsof", "-ti", f"tcp:{porta}", "-sTCP:LISTEN"], capture_output=True, text=True, timeout=15).stdout
        return int(saida.split()[0]) if saida.split() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def localizar(porta: int | None = None) -> dict[str, Any] | None:
    """A instância em execução: pela porta indicada, pelo registro ou pela porta do vault."""
    registro = ler()
    portas = [porta] if porta else ([registro["porta"]] if registro else [])
    for candidata in portas:
        info = consultar(candidata)
        if info:
            return {**info, "porta": candidata, "respondendo": True}
    if registro and not porta and vivo(registro["pid"]):
        return {**registro, "respondendo": False}
    if registro and not porta:
        esquecer(registro["pid"])  # sobrou de um painel que já fechou
    # Painel de uma versão anterior a este registro: ele responde à credencial local,
    # que só o Orquestra oferece, mas não sabe se encerrar sozinho.
    alvo = porta or _porta_padrao()
    try:
        antigo = bool(_token(alvo))
    except (OSError, ValueError, urllib.error.URLError):
        antigo = False
    pid = _pid_na_porta(alvo) if antigo else None
    if pid:
        return {"pid": pid, "porta": alvo, "vault": "", "versao": "anterior", "respondendo": False, "antigo": True}
    return None


def _forcar(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=20)
        return
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if not vivo(pid):
                return
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def parar(porta: int | None = None, forcar: bool = False, *, pid_esperado: int | None = None) -> dict[str, Any] | None:
    """Encerra o painel em execução e devolve o que se sabia dele (vault e porta), ou None.

    Lança RuntimeError com uma explicação quando não consegue parar.
    """
    info = localizar(porta)
    if info is None:
        return None
    pid = int(info.get("pid") or 0)
    if pid_esperado is not None and pid != pid_esperado:
        raise RuntimeError("O painel mudou durante a retomada; a outra instância foi preservada.")
    if info["respondendo"]:
        try:
            _pedir(info["porta"], "/api/local/encerrar", "POST", _token(info["porta"]))
        except (OSError, ValueError, urllib.error.URLError):
            pass  # a conexão pode cair justamente porque o painel fechou
        prazo = time.monotonic() + ESPERA_ENCERRAR
        while time.monotonic() < prazo:
            if consultar(info["porta"]) is None and not vivo(pid):
                esquecer(pid)
                return info
            time.sleep(0.25)
        # Confirmou que é o Orquestra, mas não fechou a tempo: encerra o processo.
        _forcar(pid)
    elif forcar or info.get("antigo"):
        _forcar(pid)
    else:
        raise RuntimeError(
            f"Há um Orquestra registrado (processo {pid}, porta {info['porta']}) que não responde. "
            "Se ele travou, use `orquestra parar --forcar`."
        )
    for _ in range(40):
        if not vivo(pid):
            esquecer(pid)
            return info
        time.sleep(0.25)
    raise RuntimeError(f"Não consegui encerrar o processo {pid}. Feche-o pelo gerenciador de tarefas.")
