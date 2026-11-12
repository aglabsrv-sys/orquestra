"""Coletores: scripts que buscam informação e a transformam em notas.

O contrato é de propósito o mais simples possível:

    um coletor é um script Python que imprime uma linha de JSON por item.

    {"id": "yt:abc123", "titulo": "Nome do vídeo", "link": "https://...", "corpo": "..."}

O script não sabe nada do painel. É o painel que roda o script, descarta o que já
foi coletado (pelo `id`), aplica o schema do módulo e grava as notas com
`origem: coletor` e o status inicial do módulo. Não há IA nesta etapa: é só
buscar e guardar. A triagem vem depois.

Os scripts ficam em `<modulo>/maquina/coletores/` e podem declarar dependências no
próprio arquivo (bloco `# /// script`, padrão PEP 723); o `uv` instala sozinho.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap

from orquestra import confianca
from orquestra.caminhos import caminho_no_vault
from orquestra.config import carregar_env
from orquestra.indice import Indice
from orquestra.modulos import ColetorDef, Modulo, ValorInvalido, converter, padroes
from orquestra.notas import Nota, caminho_livre, gravar_nota, ler_nota, nome_de_arquivo

TEMPO_LIMITE = 180  # segundos por execução
LIMITE_SAIDA = 4 * 1024 * 1024  # stdout + stderr; não cresce com o vault
LIMITE_ITENS = 2000
CHAVES_RESERVADAS = {"id", "titulo", "corpo", "campos", "atualizar"}
CAMPOS_DE_CONTROLE = {"origem", "coletor", "id_externo", "coletado_em", "criado_em", "_orquestra_coleta"}
_execucoes: dict[str, set[threading.Event]] = {}
_trava_execucoes = threading.Lock()
registro = logging.getLogger(__name__)
ERRO_SAIDA_EXCESSIVA = "O coletor excedeu 4 MB de saída e foi interrompido. Reduza a quantidade de itens ou mensagens."


@dataclass
class Resultado:
    ok: bool
    novos: int = 0
    repetidos: int = 0
    erro: str = ""


def caminho_script(modulo: Modulo, coletor: ColetorDef) -> Path:
    return confianca.caminho_script(modulo.pasta.parent, modulo, coletor)


def intervalo_em_segundos(texto: str | None) -> int | None:
    """'30m' -> 1800, '6h' -> 21600, '1d' -> 86400."""
    if not texto:
        return None
    achado = re.fullmatch(r"\s*(\d+)\s*([mhd])\s*", str(texto).lower())
    if not achado:
        return None
    return int(achado.group(1)) * {"m": 60, "h": 3600, "d": 86400}[achado.group(2)]


def devido(coletor: ColetorDef, ultima: dt.datetime | None, agora: dt.datetime) -> bool:
    """Diz se já passou da hora de rodar o coletor.

    Como comparamos com a última execução (e não com o relógio), um computador que
    ficou desligado roda o que perdeu assim que o painel volta.
    """
    intervalo = intervalo_em_segundos(coletor.a_cada)
    if intervalo:
        return ultima is None or (agora - ultima).total_seconds() >= intervalo
    if coletor.diario_as:
        try:
            hora, minuto = (int(p) for p in coletor.diario_as.split(":")[:2])
            alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        except (TypeError, ValueError):
            return False
        if ultima is None:
            return True
        if agora < alvo:
            alvo -= dt.timedelta(days=1)  # o horário de hoje ainda não chegou: vale o de ontem
        return ultima < alvo
    return False


_AMBIENTE_BASICO = {
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "LANG", "LC_ALL", "LC_CTYPE", "SSL_CERT_FILE", "SSL_CERT_DIR",
}


def _ocultar(texto: str, segredos: dict[str, str]) -> str:
    from urllib.parse import quote, quote_plus

    valores = {v for v in segredos.values() if v}
    for segredo in sorted(valores, key=len, reverse=True):
        for valor in (segredo, quote(segredo, safe=""), quote_plus(segredo), json.dumps(segredo, ensure_ascii=True)[1:-1]):
            texto = texto.replace(valor, "[segredo omitido]")
    return texto


def _job_windows(processo: subprocess.Popen):
    """Job Object mata os descendentes ao fechar; não é isolamento de permissões.

    https://learn.microsoft.com/windows/win32/procthread/job-objects
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes as w

    class Basico(ctypes.Structure):
        _fields_ = [("tempo_processo", ctypes.c_int64), ("tempo_job", ctypes.c_int64), ("flags", w.DWORD),
                    ("minimo", ctypes.c_size_t), ("maximo", ctypes.c_size_t), ("ativos", w.DWORD),
                    ("afinidade", ctypes.c_size_t), ("prioridade", w.DWORD), ("agendamento", w.DWORD)]

    class Estendido(ctypes.Structure):
        _fields_ = [("basico", Basico), ("io", ctypes.c_uint64 * 6), ("memoria_processo", ctypes.c_size_t),
                    ("memoria_job", ctypes.c_size_t), ("pico_processo", ctypes.c_size_t), ("pico_job", ctypes.c_size_t)]

    class Contabilidade(ctypes.Structure):
        _fields_ = [("usuario", ctypes.c_int64), ("kernel", ctypes.c_int64),
                    ("usuario_periodo", ctypes.c_int64), ("kernel_periodo", ctypes.c_int64),
                    ("faltas_pagina", w.DWORD), ("total", w.DWORD), ("ativos", w.DWORD), ("encerrados", w.DWORD)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    kernel.TerminateJobObject.restype = w.BOOL
    kernel.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    kernel.QueryInformationJobObject.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise OSError("Não consegui criar o grupo de processos do coletor.")
    info = Estendido()
    info.basico.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(job, w.HANDLE(processo._handle)):
        kernel.CloseHandle(job)
        raise OSError("Não consegui acompanhar os processos filhos do coletor. Tente iniciar o painel diretamente pelo terminal.")

    def encerrar():
        try:
            if not kernel.TerminateJobObject(job, 1):
                raise OSError("Não consegui interromper o grupo de processos do coletor.")
            limite = time.monotonic() + 10
            while True:
                estado = Contabilidade()
                if not kernel.QueryInformationJobObject(job, 1, ctypes.byref(estado), ctypes.sizeof(estado), None):
                    raise OSError("Não consegui confirmar o encerramento dos processos do coletor.")
                if not estado.ativos:
                    return
                if time.monotonic() >= limite:
                    raise OSError("O grupo de processos do coletor não encerrou dentro do prazo.")
                time.sleep(0.01)
        finally:
            # KILL_ON_JOB_CLOSE continua valendo inclusive se a confirmação falhar.
            kernel.CloseHandle(job)

    return encerrar


def _executar_limitado(comando: list[str], pasta: Path, ambiente: dict[str, str], cancelamento: threading.Event | None = None) -> tuple[bytes, bytes, int, str]:
    kwargs: dict[str, Any] = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    }
    processo = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, cwd=pasta, env=ambiente, **kwargs)
    fechar_job = None
    saidas = [bytearray(), bytearray()]
    excesso = threading.Event()
    trava = threading.Lock()

    def ler(canal, indice):
        try:
            while trecho := canal.read1(65536):
                with trava:
                    restante = LIMITE_SAIDA - sum(map(len, saidas))
                    saidas[indice].extend(trecho[:max(0, restante)])
                    if len(trecho) > restante:
                        excesso.set()
                        return
        finally:
            canal.close()

    threads = [threading.Thread(target=ler, args=(canal, i), daemon=True) for i, canal in enumerate((processo.stdout, processo.stderr))]
    erro = ""
    try:
        fechar_job = _job_windows(processo)
        for thread in threads:
            thread.start()
        inicio = time.monotonic()
        while processo.poll() is None or any(t.is_alive() for t in threads):
            if cancelamento is not None and cancelamento.is_set():
                erro = "A execução foi interrompida porque o vault foi fechado."
                break
            if excesso.wait(0.03):
                erro = ERRO_SAIDA_EXCESSIVA
                break
            if time.monotonic() - inicio >= TEMPO_LIMITE:
                erro = f"O coletor passou de {TEMPO_LIMITE}s e foi interrompido. Reduza o trabalho por execução."
                break
    finally:
        try:
            if fechar_job:
                fechar_job()
            elif os.name != "nt":
                try:
                    os.killpg(processo.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif processo.poll() is None:
                subprocess.run([str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "taskkill.exe"), "/PID", str(processo.pid), "/T", "/F"], capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        finally:
            if processo.poll() is None:
                processo.kill()
            processo.wait(timeout=10)
            for thread in threads:
                if thread.ident is not None:
                    thread.join(timeout=2)
            for canal in (processo.stdout, processo.stderr):
                if canal and not canal.closed:
                    canal.close()
    # O processo pode ter acabado antes de o loop observar o sinal dos leitores.
    # Ainda assim, saída truncada nunca pode ser importada como coleta completa.
    if excesso.is_set() and not erro:
        erro = ERRO_SAIDA_EXCESSIVA
    return bytes(saidas[0]), bytes(saidas[1]), processo.returncode, erro


@contextmanager
def _pasta_temporaria():
    temporaria = tempfile.TemporaryDirectory(prefix="orquestra-coletor-")
    try:
        yield temporaria.name
    finally:
        try:
            temporaria.cleanup()
        except OSError as erro:
            if getattr(erro, "winerror", None) not in (32, 33):
                raise
            # Mesmo após todos os processos terminarem, antivírus/indexadores
            # podem reter o diretório por instantes. Não substituir o resultado
            # da execução por essa falha de limpeza de um snapshot descartável.
            registro.warning("O snapshot temporário do coletor ficou ocupado e foi preservado na pasta temporária do sistema.")


def cancelar_execucoes(vault: Path) -> None:
    """Sinaliza threads de coletores antes de encerrar/trocar o painel desse vault."""
    with _trava_execucoes:
        for evento in _execucoes.get(os.path.normcase(os.path.abspath(vault)), set()):
            evento.set()


def rodar_script(vault: Path, modulo: Modulo, coletor: ColetorDef) -> tuple[list[dict[str, Any]], str]:
    evento = threading.Event()
    chave = os.path.normcase(os.path.abspath(vault))
    with _trava_execucoes:
        _execucoes.setdefault(chave, set()).add(evento)
    try:
        return _rodar_autorizado(vault, modulo, coletor, evento)
    finally:
        with _trava_execucoes:
            _execucoes.get(chave, set()).discard(evento)
            if not _execucoes.get(chave):
                _execucoes.pop(chave, None)


def _rodar_autorizado(vault: Path, modulo: Modulo, coletor: ColetorDef, cancelamento: threading.Event) -> tuple[list[dict[str, Any]], str]:
    """Executa somente os bytes autorizados localmente, com limites de tempo e saída."""
    segredos: dict[str, str] = {}
    try:
        segredos = carregar_env()
        segredos.update({k: v for k, v in os.environ.items() if re.search(r"key|token|secret|password|credential", k, re.I)})
        estado, arquivos = confianca.preparar(vault, modulo, coletor)
        if not estado["confiavel"]:
            return [], "Este coletor ainda não foi autorizado nesta versão. No próprio computador, revise e autorize em Ajustes > Coletores."
        disponiveis = {**carregar_env(), **os.environ}
        faltam = [k for k in estado["requer"] if not disponiveis.get(k)]
        if faltam:
            return [], "Faltam as chaves autorizadas: " + ", ".join(faltam) + ". Configure-as no .env local."
        ambiente = {k: v for k, v in os.environ.items() if k.upper() in _AMBIENTE_BASICO}
        ambiente.update({k: disponiveis[k] for k in estado["requer"]})
        ambiente.update({"ORQUESTRA_CONFIG": json.dumps(estado["config"], ensure_ascii=False), "ORQUESTRA_VAULT": str(vault.resolve()),
                         "ORQUESTRA_MODULO": str(caminho_no_vault(vault, modulo.pasta)), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
        # Executa a cópia dos bytes que compõem o hash; mudanças concorrentes no
        # vault e caches .pyc não podem trocar código após a autorização.
        with _pasta_temporaria() as temporaria:
            pasta = Path(temporaria)
            for nome, dados in arquivos.items():
                destino = pasta / nome
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(dados)
            script = pasta / Path(estado["caminho"]).relative_to(Path(modulo.id) / "maquina" / "coletores")
            uv = shutil.which("uv")
            comando = [uv, "run", "--quiet", "--no-project", "--script", str(script)] if uv else [sys.executable, str(script)]
            if cancelamento.is_set():
                return [], "A execução foi interrompida porque o vault foi fechado."
            stdout, stderr, codigo, erro = _executar_limitado(comando, script.parent, ambiente, cancelamento)
        if erro:
            return [], erro
        saida = _ocultar(stdout.decode("utf-8", errors="replace"), segredos)
        if codigo != 0:
            erros = _ocultar(stderr.decode("utf-8", errors="replace"), segredos).strip().splitlines()
            return [], (erros[-1][:1000] if erros else f"O coletor terminou com erro (código {codigo}).")
    except (OSError, ValueError, TypeError, RecursionError, subprocess.SubprocessError) as erro:
        return [], _ocultar(f"Não consegui executar o coletor: {erro}", segredos)[:1000]

    itens: list[dict[str, Any]] = []
    for linha in saida.splitlines():
        linha = linha.strip()
        if not linha.startswith("{"):
            continue  # o script pode imprimir outras coisas; só linhas JSON contam
        try:
            item = json.loads(linha)
        except (ValueError, RecursionError):
            continue
        if isinstance(item, dict) and item.get("id") and item.get("titulo"):
            if len(itens) >= LIMITE_ITENS:
                return [], "O coletor excedeu 2.000 itens. Reduza a quantidade por execução."
            itens.append(item)
    return ([], "A execução foi interrompida porque o vault foi fechado.") if cancelamento.is_set() else (itens, "")


def _campos_do_item(item: dict[str, Any]) -> dict[str, Any]:
    if isinstance(item.get("campos"), dict):
        return item["campos"]
    return {k: v for k, v in item.items() if k not in CHAVES_RESERVADAS}


def _nota_para_atualizar(indice: Indice, modulo: Modulo, id_externo: str, titulo: str) -> Nota | None:
    """Acha a nota que um item com "atualizar" deve completar: pelo id ou pelo nome do arquivo."""
    prefixo = modulo.id + "/"
    for rel, nota in indice.notas.items():
        if rel.startswith(prefixo) and str(nota.meta.get("id_externo") or "") == id_externo:
            caminho = caminho_no_vault(indice.vault, nota.caminho)
            return ler_nota(caminho, indice.vault) if caminho.is_file() else None
    caminho = caminho_no_vault(indice.vault, modulo.pasta_itens / f"{nome_de_arquivo(titulo)}.md")
    return ler_nota(caminho, indice.vault) if caminho.is_file() else None


def _atualizar(nota: Nota, modulo: Modulo, coletor: ColetorDef, item: dict[str, Any], id_externo: str) -> bool:
    """Completa dados sem tomar posse de campos que a pessoa já preencheu.

    Depois da primeira coleta, só campos ainda iguais ao último valor coletado
    podem acompanhar a fonte. Uma edição manual posterior sempre ganha.
    """
    if nota.erro:
        return False
    vinculos = nota.meta.get("_orquestra_coleta", CommentedMap())
    if not isinstance(vinculos, dict):
        return False  # não substitui metadado existente com formato desconhecido
    chave = f"{modulo.id}/{coletor.script}"
    rastreio = vinculos.get(chave, CommentedMap())
    if not isinstance(rastreio, dict):
        return False
    protegida = str(nota.meta.get("origem") or "humano") != "coletor"
    mudou = False
    for nome, valor in _campos_do_item(item).items():
        if nome in CAMPOS_DE_CONTROLE:
            continue
        campo = modulo.campos.get(nome)
        if campo is None:
            continue
        try:
            convertido = converter(campo, valor)
        except ValorInvalido:
            continue
        atual = nota.meta.get(nome)
        vazio = atual in (None, "", [])
        da_coleta = nome in rastreio and atual == rastreio[nome]
        if protegida and not (vazio or da_coleta):
            continue
        if convertido is not None and atual != convertido:
            nota.meta[nome] = convertido
            rastreio[nome] = convertido
            mudou = True
    if not mudou:
        return False
    vinculos[chave] = rastreio
    nota.meta["_orquestra_coleta"] = vinculos
    nota.meta.setdefault("id_externo", id_externo)
    nota.meta["coletado_em"] = dt.date.today()
    gravar_nota(nota, versao_esperada=nota.versao)
    return True


def importar(indice: Indice, modulo: Modulo, coletor: ColetorDef, itens: list[dict[str, Any]]) -> tuple[list[Nota], int]:
    """Transforma itens coletados em notas. Devolve (notas criadas, quantos já existiam)."""
    conhecidos = indice.ids_externos(modulo.id)
    criadas: list[Nota] = []
    repetidos = 0
    for item in itens:
        id_externo = str(item["id"])
        titulo = str(item["titulo"]).strip()
        if item.get("atualizar"):
            # Item que representa um estado (os números de hoje, por exemplo): se a nota
            # já existe, completamos os campos em vez de criar outra ou ignorar.
            existente = _nota_para_atualizar(indice, modulo, id_externo, titulo)
            if existente is not None:
                if _atualizar(existente, modulo, coletor, item, id_externo):
                    criadas.append(existente)
                else:
                    repetidos += 1
                conhecidos.add(id_externo)
                continue
        if id_externo in conhecidos:
            repetidos += 1
            continue
        conhecidos.add(id_externo)

        meta = CommentedMap()
        if nome_de_arquivo(titulo) != titulo:
            meta["titulo"] = titulo  # o nome do arquivo precisou ser adaptado; guardamos o original
        meta.update(padroes(modulo))

        for nome, valor in _campos_do_item(item).items():
            if nome in CAMPOS_DE_CONTROLE:
                continue
            campo = modulo.campos.get(nome)
            if campo is None:
                if isinstance(valor, (str, int, float, bool)):
                    meta[nome] = valor
                continue
            try:
                convertido = converter(campo, valor)
            except ValorInvalido:
                continue  # valor fora do schema: ignoramos o campo, não o item
            if convertido is not None:
                meta[nome] = convertido

        meta["origem"] = "coletor"
        meta["coletor"] = Path(coletor.script).stem
        meta["id_externo"] = id_externo
        meta["coletado_em"] = dt.date.today()

        corpo = str(item.get("corpo") or "").strip()
        pasta = caminho_no_vault(indice.vault, modulo.pasta_itens)
        caminho = caminho_no_vault(indice.vault, caminho_livre(pasta, titulo))
        nota = Nota(
            caminho=caminho,
            rel=caminho.relative_to(indice.vault).as_posix(),
            meta=meta,
            corpo=("\n" + corpo + "\n") if corpo else "",
            vault=indice.vault,
        )
        gravar_nota(nota, criar=True)
        criadas.append(nota)
    return criadas, repetidos
