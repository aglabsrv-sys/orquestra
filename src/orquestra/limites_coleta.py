"""Limites locais de coleta, compartilhados entre pastas, vaults e processos.

Este módulo usa somente a biblioteca padrão: uma cópia acompanha o snapshot
temporário dos coletores, sem acrescentar caminhos Python vindos do vault.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from pathlib import Path

LIMITE_DOWNLOAD = 8 * 1024 * 1024
LIMITE_FONTES = 50
LIMITE_BUSCAS = 25
LIMITE_ITENS = 2000
ESPERA_MANUAL = 30
MAXIMO_SIMULTANEAS = 2
PREFIXO = "Limite de coleta: "
_agora = time.time
_trava = threading.RLock()
_chamadas = 0  # orçamento do processo coletor, incluindo redirecionamentos


class LimiteColeta(ValueError):
    """Uma operação deve aguardar; a mensagem pode ser mostrada sem segredos."""


def minimo_intervalo(definicao: str) -> int:
    return 60 if definicao.endswith("recorrentes.py") else 21600 if definicao.endswith("youtube_api.py") else 3600


def maximo_parametro(nome: str) -> int:
    return {"maximo_por_termo": 50, "maximo_por_canal": 100, "maximo_por_feed": 100,
            "maximo": 100, "dias_a_frente": 90}.get(nome, 10000)


def validar_config(config: dict) -> None:
    """Também valida configurações existentes antes de qualquer acesso à rede."""
    if len(json.dumps(config, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 100_000:
        raise ValueError("A configuração está muito grande.")
    for nome, valor in config.items():
        if nome in {"canais", "feeds", "termos", "agendas", "repositorios", "moedas", "tarefas", "titulos_contem"}:
            maximo = LIMITE_BUSCAS if nome == "termos" else 200 if nome == "tarefas" else LIMITE_FONTES
            if not isinstance(valor, (list, dict)) or len(valor) > maximo:
                raise ValueError(f"Use no máximo {maximo} itens em {nome.replace('_', ' ')}.")
            identidades = []
            for item in valor:
                identidade = item.get("repo", "") if isinstance(item, dict) and nome == "repositorios" else item
                if isinstance(identidade, str):
                    if len(identidade) > 2000:
                        raise ValueError("Cada fonte ou texto de configuração pode ter até 2.000 caracteres.")
                    identidade = identidade.strip()
                    if nome in {"canais", "termos", "repositorios", "titulos_contem"}:
                        identidade = identidade.casefold()
                    if identidade and identidade in identidades:
                        raise ValueError(f"Remova os itens repetidos de {nome.replace('_', ' ')}.")
                    identidades.append(identidade)
        if nome.startswith("maximo") or nome == "dias_a_frente":
            maximo = maximo_parametro(nome)
            if isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= maximo:
                raise ValueError(f"{nome.replace('_', ' ').capitalize()} precisa ficar entre 1 e {maximo}.")
    for fontes, quantidade in (("canais", "maximo_por_canal"), ("feeds", "maximo_por_feed"), ("termos", "maximo_por_termo")):
        if len(config.get(fontes, [])) * config.get(quantidade, 1) > LIMITE_ITENS:
            raise ValueError("Reduza as fontes ou os resultados para no máximo 2.000 itens por coleta.")


def _pasta() -> Path:
    pasta = Path(os.environ.get("ORQUESTRA_HOME") or Path.home() / ".orquestra").resolve()
    vault = os.environ.get("ORQUESTRA_VAULT")
    if vault and pasta.is_relative_to(Path(vault).resolve()):
        raise ValueError("Os limites locais precisam ser guardados fora do vault.")
    pasta = pasta / "limites-coleta"
    pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
    if pasta.is_symlink():
        raise ValueError("O registro de limites não pode ser um link.")
    return pasta


@contextmanager
def _estado():
    """Transação curta; não mantém a trava durante downloads ou esperas."""
    with _trava:
        pasta = _pasta()
        caminho = pasta / "estado.json"
        lock = pasta / "estado.lock"
        if caminho.is_symlink() or lock.is_symlink():
            raise ValueError("O registro de limites não pode ser um link.")
        fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(fd, "r+b") as trava:
            if os.fstat(trava.fileno()).st_size == 0:
                trava.write(b"0")
                trava.flush()
            inicio = time.monotonic()
            while True:
                try:
                    trava.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(trava.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(trava.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() - inicio > 2:
                        raise LimiteColeta(PREFIXO + "outro processo está atualizando os limites. Tente novamente.") from None
                    time.sleep(0.02)
            try:
                try:
                    with caminho.open("rb") as entrada:
                        dados = entrada.read(1024 * 1024 + 1)
                    if len(dados) > 1024 * 1024:
                        raise ValueError
                    estado = json.loads(dados)
                    if not isinstance(estado, dict) or any(not isinstance(estado.get(k), dict) for k in ("servicos", "execucoes")):
                        raise ValueError
                    for grupo in ("servicos", "execucoes"):
                        for registro in estado[grupo].values():
                            if not isinstance(registro, dict):
                                raise ValueError
                            valores = [registro[k] for k in ("ate", "proxima", "usada", "janela", "falhas") if k in registro]
                            chamadas = registro.get("chamadas", [])
                            if not isinstance(chamadas, list) or len(chamadas) > 1000:
                                raise ValueError
                            if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in valores + chamadas):
                                raise ValueError
                except FileNotFoundError:
                    estado = {"servicos": {}, "execucoes": {}}
                except (ValueError, TypeError, OverflowError):
                    raise ValueError("O registro local de limites está inválido; nenhuma consulta foi feita.") from None
                agora = _agora()
                estado["servicos"] = {k: v for k, v in estado["servicos"].items()
                                      if max(v.get("ate", 0), v.get("proxima", 0), v.get("usada", 0) + v.get("janela", 3600)) > agora}
                estado["execucoes"] = {k: v for k, v in estado["execucoes"].items()
                                       if max(v.get("ate", 0), v.get("proxima", 0)) > agora}
                yield estado
                descritor, nome = tempfile.mkstemp(dir=pasta, prefix=".limites-")
                try:
                    with os.fdopen(descritor, "w", encoding="utf-8") as saida:
                        json.dump(estado, saida, separators=(",", ":"), allow_nan=False)
                        saida.flush()
                        os.fsync(saida.fileno())
                    os.replace(nome, caminho)
                finally:
                    Path(nome).unlink(missing_ok=True)
            finally:
                trava.seek(0)
                if os.name == "nt":
                    msvcrt.locking(trava.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(trava.fileno(), fcntl.LOCK_UN)


def _aguardar(ate: float, motivo: str) -> None:
    segundos = max(1, math.ceil(ate - _agora()))
    raise LimiteColeta(f"{PREFIXO}{motivo}. Aguarde {segundos}s antes de tentar novamente.")


@contextmanager
def execucao(chave: str):
    identidade = hashlib.sha256(os.path.normcase(chave).encode()).hexdigest()
    token = uuid.uuid4().hex
    with _estado() as estado:
        agora = _agora()
        execucoes = estado["execucoes"]
        atual = execucoes.get(identidade, {})
        if atual.get("ate", 0) > agora or atual.get("proxima", 0) > agora:
            _aguardar(max(atual.get("ate", 0), atual.get("proxima", 0)), "esta automação já executou ou ainda está rodando")
        if sum(v.get("ate", 0) > agora for v in execucoes.values()) >= MAXIMO_SIMULTANEAS:
            raise LimiteColeta(PREFIXO + "há duas coletas em andamento. Aguarde uma delas terminar.")
        execucoes[identidade] = {"token": token, "ate": agora + 210, "usada": agora}
    try:
        yield
    finally:
        with _estado() as estado:
            atual = estado["execucoes"].get(identidade, {})
            if atual.get("token") == token:
                atual.update(ate=0, proxima=_agora() + ESPERA_MANUAL, usada=_agora())


def _servico(url: str) -> tuple[str, int, int]:
    partes = urllib.parse.urlsplit(url)
    host = (partes.hostname or "").lower().rstrip(".")
    if partes.scheme not in {"http", "https"} or not host:
        raise ValueError("A fonte precisa usar um endereço HTTP ou HTTPS.")
    if host == "api.github.com":
        return "github", 55, 3600
    if host == "www.googleapis.com" and partes.path.startswith("/youtube/"):
        return ("youtube-busca", 100, 86400) if partes.path.rstrip("/").endswith("/search") else ("youtube-api", 1000, 86400)
    if host == "youtube.com" or host.endswith(".youtube.com"):
        return "youtube-publico", 120, 3600
    return "fonte-" + hashlib.sha256(host.encode()).hexdigest(), 120, 3600


def _reservar(url: str) -> str:
    global _chamadas
    servico, limite, janela = _servico(url)
    if _chamadas >= 120:
        raise LimiteColeta(PREFIXO + "esta coleta atingiu 120 consultas. Reduza as fontes.")
    while True:
        with _estado() as estado:
            agora = _agora()
            registro = estado["servicos"].setdefault(servico, {})
            ritmo = estado["servicos"].setdefault(_origem(url), {})
            if ritmo.get("ate", 0) > agora:
                _aguardar(ritmo["ate"], "o serviço está em pausa")
            if registro.get("ate", 0) > agora:
                _aguardar(registro["ate"], "o serviço está em pausa")
            chamadas = [t for t in registro.get("chamadas", []) if t > agora - janela]
            if len(chamadas) >= limite:
                _aguardar(chamadas[0] + janela, "a cota local deste serviço foi atingida")
            geral = estado["servicos"].setdefault("total", {})
            todas = [t for t in geral.get("chamadas", []) if t > agora - 3600]
            if len(todas) >= 1000:
                _aguardar(todas[0] + 3600, "a cota total de consultas foi atingida")
            espera = ritmo.get("proxima", 0) - agora
            if espera <= 0:
                registro.update(chamadas=chamadas + [agora], proxima=agora + 1, usada=agora, janela=janela)
                ritmo.update(proxima=agora + 1, usada=agora)
                geral.update(chamadas=todas + [agora], usada=agora)
        if espera <= 0:
            _chamadas += 1
            return servico
        time.sleep(min(espera, 1))


def _origem(url: str) -> str:
    host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    if host.endswith(".youtube.com"):
        host = "youtube.com"
    return "ritmo-" + hashlib.sha256(host.encode()).hexdigest()


def _pausar(url: str, erro: urllib.error.HTTPError) -> None:
    servico, _, _ = _servico(url)
    cabecalhos = erro.headers or {}
    youtube = servico in {"youtube-api", "youtube-busca"}
    cota_youtube = limite_youtube = False
    if erro.code == 403 and youtube:
        corpo = erro.read(65536)
        cota_youtube = any(m in corpo for m in (b'quotaExceeded', b'dailyLimitExceeded'))
        limite_youtube = any(m in corpo for m in (b'rateLimitExceeded', b'userRateLimitExceeded'))
    bloqueado = erro.code == 429 or cota_youtube or limite_youtube or (erro.code == 403 and cabecalhos.get("X-RateLimit-Remaining") == "0")
    if not bloqueado and not (erro.code == 503 and cabecalhos.get("Retry-After")):
        return
    with _estado() as estado:
        agora = _agora()
        registro = estado["servicos"].setdefault(servico, {})
        falhas = min(7, registro.get("falhas", 0) + 1)
        ate = agora + (86400 if cota_youtube else min(3600, 60 * 2 ** (falhas - 1)))
        retry = cabecalhos.get("Retry-After", "")
        try:
            segundos = float(retry)
            if math.isfinite(segundos) and segundos >= 0 and math.isfinite(agora + segundos):
                ate = max(ate, agora + segundos)
        except ValueError:
            try:
                informado = parsedate_to_datetime(retry).timestamp()
                if math.isfinite(informado) and agora <= informado:
                    ate = max(ate, informado)
            except (ValueError, TypeError, OverflowError):
                pass
        if cabecalhos.get("X-RateLimit-Remaining") == "0":
            try:
                informado = float(cabecalhos.get("X-RateLimit-Reset", ""))
                if math.isfinite(informado) and agora <= informado:
                    ate = max(ate, informado)
            except ValueError:
                pass
        registro.update(ate=ate, falhas=falhas, usada=agora)
        if not cota_youtube:
            # Um bloqueio HTTP pode abranger também outros recursos da mesma API.
            ritmo = estado["servicos"].setdefault(_origem(url), {})
            ritmo.update(ate=max(ate, ritmo.get("ate", 0)), usada=agora)
    _aguardar(ate, "o serviço pediu uma pausa nas consultas")


class _Redirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _reservar(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def baixar(url: str, tempo: int = 20, *, headers: dict | None = None, limite: int = LIMITE_DOWNLOAD) -> bytes:
    _reservar(url)
    try:
        opener = urllib.request.build_opener(_Redirecionamento())
        with opener.open(urllib.request.Request(url, headers=headers or {}), timeout=tempo) as resposta:
            dados = resposta.read(limite + 1)
            if len(dados) > limite:
                raise ValueError("A resposta da fonte excede o limite de 8 MB.")
            return dados
    except urllib.error.HTTPError as erro:
        _pausar(erro.url, erro)
        raise


def preparar_snapshot(pasta: Path, ambiente: dict, chave: str) -> None:
    """O runtime vem da instalação; o restante do snapshot mantém os bytes aceitos."""
    alvo = pasta / "_orquestra_limites.py"
    if not alvo.exists():
        alvo.write_bytes(Path(__file__).read_bytes())
    ambiente.update(ORQUESTRA_HOME=str(Path(os.environ.get("ORQUESTRA_HOME") or Path.home() / ".orquestra").resolve()),
                    ORQUESTRA_EXECUCAO=chave)
