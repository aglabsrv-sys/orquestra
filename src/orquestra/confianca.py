"""Aceite local de código de coletores, separado dos dados compartilháveis do vault.

O aceite cobre o script, seus arquivos auxiliares e a configuração que ele recebe.
É uma autorização para executar Python com as permissões da pessoa, não uma sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from typing import Any

from orquestra.caminhos import caminho_no_vault, eh_link
from orquestra.config import pasta_app
from orquestra.modulos import ColetorDef, Modulo, carregar_modulo
from orquestra.notas import simples

LIMITE_ARQUIVOS = 1000
LIMITE_BYTES = 32 * 1024 * 1024
_trava = threading.RLock()


def _original(modulo: Modulo, coletor: ColetorDef, arquivos: dict[str, bytes]) -> bool:
    """Confiança limitada ao código E configuração distribuídos nesta instalação."""
    pasta = Path(__file__).parent / "catalogo" / modulo.id
    if not pasta.is_dir():
        return False
    try:
        original = carregar_modulo(pasta)
        definicao = next((c for c in original.coletores if c.script == coletor.script), None)
        if definicao is None or simples(definicao.config) != simples(coletor.config) or sorted(definicao.requer) != sorted(coletor.requer):
            return False
        base = pasta / "maquina" / "coletores"
        esperado = {p.relative_to(base).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        return esperado == arquivos
    except (OSError, ValueError):
        return False


def caminho_script(vault: Path, modulo: Modulo, coletor: ColetorDef) -> Path:
    nome = str(coletor.script)
    relativo = Path(nome)
    if (
        not nome or relativo.is_absolute() or PureWindowsPath(nome).is_absolute()
        or "\\" in nome or any(p in ("..", ".") or p.startswith(".") for p in nome.split("/"))
        or relativo.suffix.lower() != ".py"
    ):
        raise ValueError("O coletor precisa ser um arquivo .py dentro de maquina/coletores, sem .. ou caminho absoluto.")
    pasta_modulo = caminho_no_vault(vault, modulo.pasta)
    pasta = caminho_no_vault(vault, pasta_modulo / "maquina" / "coletores")
    script = caminho_no_vault(vault, pasta / relativo)
    if not script.is_relative_to(pasta) or script == pasta:
        raise ValueError("O coletor fica fora de maquina/coletores.")
    if not script.is_file():
        raise ValueError("Script não encontrado em maquina/coletores.")
    return script


def _chave(vault: Path, modulo: Modulo, coletor: ColetorDef) -> str:
    texto = "\0".join((os.path.normcase(str(vault.resolve())), modulo.id, str(coletor.script)))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _arquivo(vault: Path) -> Path:
    casa = pasta_app().resolve()
    if casa == vault.resolve() or casa.is_relative_to(vault.resolve()):
        raise ValueError("ORQUESTRA_HOME precisa ficar fora do vault para guardar as autorizações locais.")
    arquivo = casa / "confianca-coletores.json"
    if eh_link(arquivo):
        raise ValueError("O registro de autorizações locais não pode ser um link.")
    return arquivo


@contextmanager
def _transacao(vault: Path):
    """Serializa também dois processos do painel/CLI alterando aceites locais."""
    with _trava:
        arquivo = _arquivo(vault)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        lock = arquivo.with_suffix(".lock")
        if eh_link(lock):
            raise ValueError("O registro de autorizações locais não pode usar um lock vinculado.")
        with os.fdopen(os.open(lock, os.O_CREAT | os.O_RDWR, 0o600), "r+b") as trava:
            if os.name == "nt":
                import msvcrt
                if not trava.read(1):
                    trava.write(b"0")
                    trava.flush()
                trava.seek(0)
                msvcrt.locking(trava.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(trava.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    trava.seek(0)
                    msvcrt.locking(trava.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(trava.fileno(), fcntl.LOCK_UN)


def _ler(vault: Path) -> dict[str, str]:
    try:
        bruto = json.loads(_arquivo(vault).read_text(encoding="utf-8"))
        aceites = bruto.get("aceites", {})
        return {str(k): str(v) for k, v in aceites.items()} if isinstance(aceites, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _gravar(vault: Path, aceites: dict[str, str]) -> None:
    arquivo = _arquivo(vault)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix=".confianca-", dir=arquivo.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as saida:
            json.dump({"versao": 1, "aceites": aceites}, saida, ensure_ascii=False, sort_keys=True)
            saida.flush()
            os.fsync(saida.fileno())
        os.replace(temporario, arquivo)
    finally:
        Path(temporario).unlink(missing_ok=True)


def preparar(vault: Path, modulo: Modulo, coletor: ColetorDef) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Lê uma cópia imutável dos bytes que serão mostrados, aprovados e executados."""
    script = caminho_script(vault, modulo, coletor)
    pasta = caminho_no_vault(vault, modulo.pasta / "maquina" / "coletores")
    arquivos: dict[str, bytes] = {}
    total = 0
    for raiz, pastas, nomes in os.walk(pasta, followlinks=False):
        base = Path(raiz)
        pastas[:] = sorted(p for p in pastas if p != "__pycache__")
        for sub in pastas:
            candidato = base / sub
            seguro = caminho_no_vault(vault, candidato)
            if candidato.is_symlink() or getattr(candidato, "is_junction", lambda: False)():
                raise ValueError("Coletores não podem importar pastas vinculadas. Copie os auxiliares para maquina/coletores.")
            if not seguro.is_relative_to(pasta):
                raise ValueError("Um auxiliar do coletor fica fora de maquina/coletores.")
        for nome in sorted(nomes):
            if nome.endswith(".orq-tmp"):
                continue
            original = base / nome
            caminho = caminho_no_vault(vault, original)
            if original.is_symlink() or not caminho.is_relative_to(pasta):
                raise ValueError("Coletores não podem importar arquivos vinculados ou externos.")
            if caminho.suffix.lower() in (".pyc", ".pyo", ".pyd", ".so", ".dll"):
                raise ValueError("Auxiliares compilados não são aceitos na pasta do coletor. Use dependências declaradas no script.")
            info = caminho.stat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("A pasta de coletores deve conter apenas arquivos comuns, sem dispositivos ou pipes.")
            if len(arquivos) >= LIMITE_ARQUIVOS or info.st_size + total > LIMITE_BYTES:
                raise ValueError("A pasta de coletores excede o limite de 1.000 arquivos ou 32 MB.")
            with caminho.open("rb") as entrada:
                dados = entrada.read(LIMITE_BYTES - total + 1)
            total += len(dados)
            if total > LIMITE_BYTES:
                raise ValueError("A pasta de coletores excede 32 MB.")
            arquivos[original.relative_to(pasta).as_posix()] = dados
    rel_script = script.relative_to(pasta).as_posix()
    if rel_script not in arquivos:
        raise ValueError("O script não está entre os arquivos locais aprováveis.")
    configuracao = simples(coletor.config)
    requer = sorted(set(str(chave) for chave in coletor.requer))
    manifesto = {
        "script": rel_script,
        "arquivos": {nome: hashlib.sha256(dados).hexdigest() for nome, dados in sorted(arquivos.items())},
        "config": configuracao,
        "requer": requer,
    }
    assinatura = hashlib.sha256(json.dumps(manifesto, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    aceite = _ler(vault).get(_chave(vault, modulo, coletor))
    original = _original(modulo, coletor, arquivos)
    estado = {
        "script": str(coletor.script),
        "caminho": script.relative_to(vault.resolve()).as_posix(),
        "assinatura": assinatura,
        "requer": requer,
        "arquivos": list(manifesto["arquivos"]),
        "config": configuracao,
        "original": original,
        "confiavel": secrets.compare_digest(aceite or "", assinatura) or (aceite is None and original),
    }
    return estado, arquivos


def resumo(vault: Path, modulo: Modulo, coletor: ColetorDef) -> dict[str, Any]:
    try:
        return preparar(vault, modulo, coletor)[0]
    except (OSError, ValueError, TypeError, RecursionError) as erro:
        return {"confiavel": False, "script": str(coletor.script), "assinatura": "", "erro": str(erro), "requer": list(coletor.requer), "arquivos": [], "config": {}}


def autorizar(vault: Path, modulo: Modulo, coletor: ColetorDef, assinatura_esperada: str) -> dict[str, Any]:
    with _transacao(vault):
        estado, _ = preparar(vault, modulo, coletor)
        if not assinatura_esperada or not secrets.compare_digest(estado["assinatura"], str(assinatura_esperada)):
            raise ValueError("O código ou a configuração mudou. Confira a versão nova antes de autorizar.")
        aceites = _ler(vault)
        aceites[_chave(vault, modulo, coletor)] = estado["assinatura"]
        _gravar(vault, aceites)
        return {**estado, "confiavel": True}


def revogar(vault: Path, modulo: Modulo, coletor: ColetorDef) -> None:
    with _transacao(vault):
        aceites = _ler(vault)
        aceites[_chave(vault, modulo, coletor)] = "revogado"
        _gravar(vault, aceites)
