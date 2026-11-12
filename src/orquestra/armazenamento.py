"""Escrita coordenada e recuperável de arquivos locais.

As travas coordenam processos do Orquestra, não editores externos. Conferimos a
pré-condição novamente antes da publicação e guardamos as versões fora do vault;
nenhuma API portátil de arquivos oferece compare-and-swap com o Obsidian.
"""

from __future__ import annotations

import contextlib
import ctypes
import datetime as dt
import errno
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import threading
import time
import uuid
import weakref
from pathlib import Path
from typing import Callable, Iterator

SEM_CONFERIR = object()


class ConflitoDeEscrita(Exception):
    """A pré-condição não corresponde mais ao arquivo do disco."""


class ArquivoOcupado(TimeoutError):
    """Outro processo não liberou a trava no prazo esperado."""


_travas: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
_guarda_travas = threading.Lock()
_locais = threading.local()


def pasta_local() -> Path:
    return Path(os.environ.get("ORQUESTRA_HOME") or Path.home() / ".orquestra")


def versao(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _chave(caminho: Path) -> str:
    return versao(os.path.normcase(str(caminho.resolve())).encode("utf-8"))


def _pasta_privada(caminho: Path) -> None:
    caminho.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        caminho.chmod(0o700)


@contextlib.contextmanager
def trava(caminho: Path, *, timeout: float = 15) -> Iterator[None]:
    """Trava por caminho, entre threads e processos, fora do vault."""
    chave = _chave(caminho)
    with _guarda_travas:
        local = _travas.get(chave)
        if local is None:
            local = threading.RLock()
            _travas[chave] = local
    if not local.acquire(timeout=timeout):
        raise ArquivoOcupado("Outro processo está gravando este arquivo. Tente novamente.")
    em_uso = getattr(_locais, "em_uso", set())
    if chave in em_uso:
        try:
            yield
        finally:
            local.release()
        return
    descritor = None
    adquirido = False
    try:
        pasta = pasta_local() / "locks"
        _pasta_privada(pasta)
        descritor = os.open(pasta / (chave + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
        if os.fstat(descritor).st_size == 0:
            os.write(descritor, b"0")
        limite = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(descritor, 0, os.SEEK_SET)
                    msvcrt.locking(descritor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descritor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                adquirido = True
                em_uso.add(chave)
                _locais.em_uso = em_uso
                break
            except OSError as erro:
                if erro.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= limite:
                    raise ArquivoOcupado("Outro processo está gravando este arquivo. Tente novamente.") from erro
                time.sleep(0.025)
        yield
    finally:
        if descritor is not None:
            if adquirido:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(descritor, 0, os.SEEK_SET)
                    msvcrt.locking(descritor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descritor, fcntl.LOCK_UN)
            os.close(descritor)
        em_uso.discard(chave)
        local.release()


def _sincronizar_pasta(pasta: Path) -> None:
    # Windows não permite abrir diretórios com os.open; ReplaceFile/NTFS ainda
    # publica a troca inteira. Alguns filesystems Unix não implementam fsync(dir).
    if os.name == "nt":
        return
    descritor = os.open(pasta, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        try:
            os.fsync(descritor)
        except OSError as erro:
            if erro.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EBADF):
                raise
    finally:
        os.close(descritor)


def _ler_existente(caminho: Path) -> bytes | None:
    try:
        return caminho.read_bytes()
    except FileNotFoundError:
        return None


def _confere(atual: bytes | None, esperado: object) -> bool:
    if esperado is None:
        return atual is None
    if atual is None:
        return False
    if isinstance(esperado, bytes):
        return atual == esperado
    if isinstance(esperado, str):
        return versao(atual) == esperado
    return False


def _gravar_privado(caminho: Path, dados: bytes) -> None:
    descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descritor, "wb") as arquivo:
        arquivo.write(dados)
        arquivo.flush()
        os.fsync(arquivo.fileno())


def preservar(caminho: Path, dados: bytes | None, proposta: bytes, *, motivo: str) -> Path:
    """Guarda preimagem/proposta privadas; não remove versões automaticamente."""
    pasta = pasta_local() / "recuperacao" / _chave(caminho)
    _pasta_privada(pasta)
    identificador = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ-") + uuid.uuid4().hex
    base = pasta / identificador
    if dados is not None:
        _gravar_privado(Path(str(base) + ".antes"), dados)
    _gravar_privado(Path(str(base) + ".proposta"), proposta)
    registro = {"caminho": str(caminho.resolve()), "motivo": motivo, "versao_anterior": versao(dados) if dados is not None else None,
                "versao_proposta": versao(proposta)}
    _gravar_privado(Path(str(base) + ".json"), json.dumps(registro, ensure_ascii=False, indent=2).encode("utf-8"))
    _sincronizar_pasta(pasta)
    return base


def _trocar_com_captura(temporario: Path, destino: Path) -> Path:
    """Publica e retém o arquivo efetivamente deslocado, sem janela de cópia.

    Windows: ReplaceFileW com backup. Linux/macOS: troca de nomes atômica.
    Filesystems sem a primitiva falham sem fallback que perderia uma versão.
    """
    if os.name == "nt":
        from ctypes import wintypes

        backup = destino.with_name("." + destino.name + "." + uuid.uuid4().hex + ".deslocado.orq-tmp")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        funcao = kernel.ReplaceFileW
        funcao.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        funcao.restype = wintypes.BOOL

        def longo(caminho: Path) -> str:
            texto = str(caminho.absolute())
            if texto.startswith("\\\\?\\"):
                return texto
            return "\\\\?\\UNC\\" + texto[2:] if texto.startswith("\\\\") else "\\\\?\\" + texto

        if not funcao(longo(destino), longo(temporario), longo(backup), 0, None, None):
            codigo = ctypes.get_last_error()
            # Alguns erros de ReplaceFile mantêm o deslocado no nome de backup.
            # Ele nunca pode ser apagado como se fosse um temporário descartável.
            if backup.exists():
                preservar(destino, backup.read_bytes(), temporario.read_bytes() if temporario.exists() else b"",
                          motivo="falha_na_publicacao")
                backup.unlink()
            raise ctypes.WinError(codigo)
        return backup
    biblioteca = ctypes.CDLL(None, use_errno=True)
    origem, alvo = os.fsencode(temporario), os.fsencode(destino)
    if sys.platform.startswith("linux") and hasattr(biblioteca, "renameat2"):
        funcao = biblioteca.renameat2
        funcao.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        funcao.restype = ctypes.c_int
        resultado = funcao(-100, origem, -100, alvo, 2)  # AT_FDCWD, RENAME_EXCHANGE
    elif sys.platform == "darwin" and hasattr(biblioteca, "renamex_np"):
        funcao = biblioteca.renamex_np
        funcao.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        funcao.restype = ctypes.c_int
        resultado = funcao(origem, alvo, 2)  # RENAME_SWAP
    else:
        raise OSError(errno.ENOTSUP, "Este sistema não oferece a troca de arquivos com recuperação exigida pelo Orquestra.")
    if resultado:
        codigo = ctypes.get_errno()
        raise OSError(codigo, os.strerror(codigo), str(destino))
    return temporario  # depois do exchange contém o arquivo antigo


def _renomear_exclusivo(origem: Path, destino: Path) -> None:
    if os.name == "nt":
        os.rename(origem, destino)  # Windows sempre recusa destino existente
        return
    biblioteca = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(biblioteca, "renameat2"):
        funcao = biblioteca.renameat2
        funcao.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        resultado = funcao(-100, os.fsencode(origem), -100, os.fsencode(destino), 1)  # RENAME_NOREPLACE
    elif sys.platform == "darwin" and hasattr(biblioteca, "renamex_np"):
        funcao = biblioteca.renamex_np
        funcao.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        resultado = funcao(os.fsencode(origem), os.fsencode(destino), 4)  # RENAME_EXCL
    else:
        raise OSError(errno.ENOTSUP, "O filesystem não oferece movimento exclusivo seguro.")
    if resultado:
        codigo = ctypes.get_errno()
        raise OSError(codigo, os.strerror(codigo), str(destino))


def gravar_bytes(caminho: Path, dados: bytes, *, esperado: object = SEM_CONFERIR, criar: bool = False, backup: bool = True,
                 validar: Callable[[], object] | None = None) -> None:
    """Publica bytes completos. Atualização exige bytes/hash lidos anteriormente.

    ``esperado=None`` ou ``criar=True`` exige inexistência. Criação usa rename
    exclusivo no mesmo filesystem: falha segura se ele não oferecer esse recurso.
    A chamada não aceita atualização incondicional. Recuperação fica em
    ORQUESTRA_HOME/recuperacao, com permissões privadas quando disponíveis.
    """
    caminho = Path(caminho)
    if esperado is SEM_CONFERIR and not criar:
        raise ConflitoDeEscrita("Informe a versão que foi lida antes de gravar.")
    if criar:
        esperado = None
    with trava(caminho):
        if validar:
            validar()
        atual = _ler_existente(caminho)
        if not _confere(atual, esperado):
            if criar and atual is not None:
                raise FileExistsError(str(caminho))
            if backup:
                preservar(caminho, atual, dados, motivo="conflito")
            raise ConflitoDeEscrita("O arquivo mudou ou foi removido. Reabra a versão atual.")
        if atual == dados:
            return
        caminho.parent.mkdir(parents=True, exist_ok=True)
        descritor, nome = tempfile.mkstemp(prefix="." + caminho.name + ".", suffix=".orq-tmp", dir=caminho.parent)
        temporario = Path(nome)
        deslocado = None
        deslocado_preservado = False
        try:
            with os.fdopen(descritor, "wb") as arquivo:
                if atual is not None:
                    os.chmod(temporario, stat.S_IMODE(caminho.stat().st_mode))
                arquivo.write(dados)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            if backup and atual is not None:
                preservar(caminho, atual, dados, motivo="antes_da_escrita")
            for tentativa in range(6):
                if validar:
                    validar()
                observado = _ler_existente(caminho)
                if not _confere(observado, esperado):
                    if backup:
                        preservar(caminho, observado, dados, motivo="conflito_durante_escrita")
                    if criar and observado is not None:
                        raise FileExistsError(str(caminho))
                    raise ConflitoDeEscrita("O arquivo mudou enquanto estava sendo gravado.")
                try:
                    if esperado is None:
                        _renomear_exclusivo(temporario, caminho)
                    else:
                        deslocado = _trocar_com_captura(temporario, caminho)
                    break
                except FileNotFoundError as erro:
                    raise ConflitoDeEscrita("O arquivo foi removido durante a gravação.") from erro
                except PermissionError:
                    if tentativa == 5:
                        raise
                    time.sleep(0.05 * (tentativa + 1))
            _sincronizar_pasta(caminho.parent)
            if deslocado is not None:
                anterior_real = deslocado.read_bytes()
                corresponde = _confere(anterior_real, esperado)
                if not corresponde or (backup and anterior_real != atual):
                    preservar(caminho, anterior_real, dados,
                              motivo="versao_deslocada" if corresponde else "conflito_na_publicacao")
                deslocado_preservado = True
                deslocado.unlink()
                if not corresponde:
                    raise ConflitoDeEscrita("Outro programa gravou no instante da publicação. As duas versões estão na recuperação local.")
            publicado = _ler_existente(caminho)
            if publicado != dados:
                if backup:
                    preservar(caminho, publicado, dados, motivo="edicao_externa_apos_publicacao")
                raise ConflitoDeEscrita("Outro programa alterou o arquivo durante a gravação. Há cópias na recuperação local.")
        finally:
            if deslocado != temporario or deslocado_preservado:
                temporario.unlink(missing_ok=True)


def acrescentar_bytes(caminho: Path, dados: bytes, *, validar: Callable[[], object] | None = None) -> None:
    """Append coordenado, sem perder outro append feito pelo Orquestra."""
    with trava(caminho):
        if validar:
            validar()
        antes = _ler_existente(caminho)
        gravar_bytes(caminho, (antes or b"") + dados, esperado=antes, validar=validar)


def atualizar_bytes(caminho: Path, transformar: Callable[[bytes], bytes], *, backup: bool = True,
                    validar: Callable[[], object] | None = None) -> None:
    """Lê/transforma/grava sob a mesma trava; arquivo ausente vira bytes vazios."""
    with trava(caminho):
        if validar:
            validar()
        antes = _ler_existente(caminho)
        gravar_bytes(caminho, transformar(antes or b""), esperado=antes, backup=backup, validar=validar)


def listar_recuperacoes(caminho: Path, *, limite: int = 30) -> list[dict]:
    """Metadados das versões de um arquivo já validado pelo domínio chamador."""
    pasta = pasta_local() / "recuperacao" / _chave(caminho)
    registros = []
    for arquivo in sorted(pasta.glob("*.json"), reverse=True):
        try:
            registro = json.loads(arquivo.read_text(encoding="utf-8"))
            if registro.get("caminho") != str(caminho.resolve()):
                continue
            identificador = arquivo.name.removesuffix(".json")
            registros.append({"id": identificador, "motivo": registro.get("motivo", ""),
                              "versao_anterior": registro.get("versao_anterior"),
                              "versao_proposta": registro.get("versao_proposta"),
                              "tem_anterior": (pasta / (identificador + ".antes")).is_file()})
            if len(registros) >= max(1, min(limite, 100)):
                break
        except (OSError, ValueError, TypeError):
            continue
    return registros


def ler_recuperacao(caminho: Path, identificador: str, *, tipo: str = "antes") -> bytes:
    if tipo not in ("antes", "proposta") or not re.fullmatch(r"[A-Za-z0-9.-]{20,100}", identificador):
        raise ValueError("Versão de recuperação inválida.")
    pasta = pasta_local() / "recuperacao" / _chave(caminho)
    registro = json.loads((pasta / (identificador + ".json")).read_text(encoding="utf-8"))
    if registro.get("caminho") != str(caminho.resolve()):
        raise ValueError("Esta recuperação pertence a outro arquivo.")
    return (pasta / (identificador + "." + tipo)).read_bytes()


def mover_seguro(origem: Path, destino: Path, *, esperado: object, validar: Callable[[], object] | None = None) -> None:
    """Move sem substituir destino, conservando preimagem fora do vault.

    O rename exclusivo move o arquivo efetivo sem apagar uma criação concorrente.
    Se o conteúdo mudou no instante do rename, ele fica no destino e na recuperação;
    nenhum rollback substitui uma eventual nova edição na origem.
    """
    origem, destino = Path(origem), Path(destino)
    if origem.resolve() == destino.resolve():
        raise ValueError("Origem e destino precisam ser diferentes.")
    with contextlib.ExitStack() as pilha:
        for caminho in sorted((origem, destino), key=_chave):
            pilha.enter_context(trava(caminho))
        if validar:
            validar()
        antes = _ler_existente(origem)
        if antes is None or not _confere(antes, esperado):
            raise ConflitoDeEscrita("O arquivo de origem mudou ou foi removido.")
        preservar(origem, antes, antes, motivo="antes_de_mover")
        destino.parent.mkdir(parents=True, exist_ok=True)
        if validar:
            validar()
        _renomear_exclusivo(origem, destino)
        _sincronizar_pasta(origem.parent)
        _sincronizar_pasta(destino.parent)
        movido = _ler_existente(destino)
        if movido != antes:
            preservar(destino, movido, antes, motivo="conflito_ao_mover")
            raise ConflitoDeEscrita("O conteúdo mudou durante o movimento. Confira o destino e a recuperação local.")
