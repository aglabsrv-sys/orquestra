"""Assinatura iCal de leitura: cache em memória, sem cópias em notas ou tarefas."""
from __future__ import annotations

import datetime as dt
import hashlib
import http.client
import ipaddress
import socket
import threading
import time
from itertools import islice
from urllib.parse import urljoin, urlsplit

import recurring_ical_events
from icalendar import Calendar

from orquestra import segredos
from orquestra.config import carregar_env

LIMITE = 2 * 1024 * 1024


def validar_url(endereco: str) -> str:
    endereco = endereco.strip().replace("webcal://", "https://", 1)
    try:
        url = urlsplit(endereco)
        valido = url.scheme == "https" and url.hostname and not url.username and not url.password and not url.fragment and url.port in (None, 443)
    except ValueError:
        valido = False
    if not valido or len(endereco) > 8192 or any(ord(c) < 33 for c in endereco):
        raise ValueError("Use um endereço iCal HTTPS, sem usuário, senha ou fragmento na URL.")
    return endereco


def baixar(endereco: str) -> bytes:
    """HTTPS público, sem proxy, com IP fixado e redirecionamentos revalidados."""
    for _ in range(4):
        url = urlsplit(validar_url(endereco))
        ips = socket.getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)
        if not ips or any(not ipaddress.ip_address(i[4][0]).is_global for i in ips):
            raise ValueError("Use uma agenda hospedada em um endereço público HTTPS.")
        conexao = http.client.HTTPSConnection(url.hostname, timeout=10)
        ip = ips[0][4][0]
        # HTTPSConnection mantém o hostname original na validação TLS/SNI.
        conexao._create_connection = lambda destino, timeout, source_address=None: socket.create_connection((ip, 443), timeout, source_address)
        try:
            conexao.request("GET", (url.path or "/") + ("?" + url.query if url.query else ""), headers={"Accept": "text/calendar", "User-Agent": "Orquestra/0.4"})
            resposta = conexao.getresponse()
            if resposta.status in (301, 302, 303, 307, 308):
                endereco = urljoin(endereco, resposta.getheader("Location") or "")
                continue
            if resposta.status != 200:
                raise ValueError("Não consegui ler a agenda. Confira se o link iCal continua válido.")
            bruto = resposta.read(LIMITE + 1)
            if len(bruto) > LIMITE:
                raise ValueError("A agenda excede o limite de 2 MB.")
            return bruto
        finally:
            conexao.close()
    raise ValueError("O endereço da agenda redirecionou muitas vezes.")


def ler(bruto: bytes) -> Calendar:
    bruto = bruto.removeprefix(b"\xef\xbb\xbf")
    if len(bruto) > LIMITE or not bruto.lstrip().startswith(b"BEGIN:VCALENDAR"):
        raise ValueError("O endereço precisa devolver um calendário iCal (.ics).")
    calendario = Calendar.from_ical(bruto)
    if len(calendario.walk("VEVENT")) > 10000:
        raise ValueError("A agenda tem eventos demais para esta assinatura.")
    return calendario


def eventos(calendario: Calendar, de: dt.date, ate: dt.date) -> tuple[list[dict], bool]:
    inicio_periodo = dt.datetime.combine(de, dt.time.min).astimezone()
    fim_periodo = dt.datetime.combine(ate + dt.timedelta(days=1), dt.time.min).astimezone()
    resultado, vistos = [], set()
    # A consulta é incremental: uma regra a cada segundo não expande o mês inteiro.
    consulta = recurring_ical_events.of(calendario).after(inicio_periodo)
    for numero, item in enumerate(islice(consulta, 2001)):
        if numero == 2000:
            return resultado, True
        inicio = item.decoded("DTSTART")
        inteiro = not isinstance(inicio, dt.datetime)
        fim = item.decoded("DTEND", inicio + dt.timedelta(days=1) if inteiro else inicio + dt.timedelta(hours=1))
        if not inteiro:
            inicio = inicio.astimezone()
            fim = fim.astimezone() if isinstance(fim, dt.datetime) else dt.datetime.combine(fim, dt.time.min).astimezone()
            if inicio >= fim_periodo:
                break
            dia, ultimo, hora, hora_fim = inicio.date(), fim.date(), inicio.strftime("%H:%M"), fim.strftime("%H:%M")
        else:
            if inicio > ate:
                break
            dia, ultimo, hora, hora_fim = inicio, max(inicio, fim - dt.timedelta(days=1)), "", ""
        if ultimo < de or str(item.get("STATUS", "")).upper() == "CANCELLED":
            continue
        identificador = hashlib.sha256((str(item.get("UID") or item.get("SUMMARY") or "evento") + str(inicio)).encode()).hexdigest()[:24]
        if identificador in vistos:
            continue
        vistos.add(identificador)
        resultado.append({"rel": "ical:" + identificador, "versao": "", "titulo": str(item.get("SUMMARY", "Sem título"))[:500],
                          "data": dia.isoformat(), "data_fim": ultimo.isoformat(), "hora": hora, "hora_fim": hora_fim,
                          "dia_inteiro": inteiro, "categoria": "Agenda externa", "modulo": "@ical", "pasta": "Agenda externa",
                          "cor": "azul", "tags": [], "concluido": False, "editavel": False, "externo": True,
                          "corpo": str(item.get("DESCRIPTION", ""))[:10000], "local": str(item.get("LOCATION", ""))[:1000], "url": ""})
        if len(resultado) == 500:
            return resultado, True
    return resultado, False


class Assinatura:
    def __init__(self, vault):
        self.vault = vault
        self.chave = "AGENDA_ICAL_" + hashlib.sha256(str(vault.resolve()).encode()).hexdigest()[:16].upper()
        self._trava = threading.Lock()
        self._calendario = None
        self._endereco = ""
        self._tentativa = 0
        self._aviso = ""

    def conectar(self, endereco: str):
        endereco = validar_url(endereco)
        try:
            calendario = ler(baixar(endereco))
            eventos(calendario, dt.date.today(), dt.date.today() + dt.timedelta(days=7))
        except Exception:
            raise ValueError("Não consegui ler este iCal. Confira o link e tente novamente. Nenhuma conexão foi alterada.") from None
        with self._trava:
            segredos.salvar(self.vault, self.chave, endereco)
            self._calendario, self._endereco, self._tentativa, self._aviso = calendario, endereco, time.monotonic(), ""

    def desconectar(self):
        with self._trava:
            segredos.salvar(self.vault, self.chave, None)
            self._calendario, self._endereco, self._aviso = None, "", ""

    def consultar(self, de: dt.date, ate: dt.date) -> dict:
        with self._trava:
            endereco = carregar_env().get(self.chave, "")
            if not endereco:
                return {"conectada": False, "eventos": [], "aviso": "", "limitado": False}
            if endereco != self._endereco:
                self._calendario, self._endereco, self._tentativa, self._aviso = None, endereco, 0, ""
            if not self._tentativa or time.monotonic() - self._tentativa >= 300:
                self._tentativa = time.monotonic()
                try:
                    atualizado = ler(baixar(endereco))
                    eventos(atualizado, de, ate)
                    self._calendario = atualizado
                    self._aviso = ""
                except Exception:
                    self._aviso = "Não consegui atualizar a agenda externa. A última leitura pode estar desatualizada; tente novamente em alguns minutos."
            try:
                itens, limitado = eventos(self._calendario, de, ate) if self._calendario is not None else ([], False)
            except Exception:
                itens, limitado = [], False
                self._aviso = "Não consegui interpretar os eventos desta agenda externa. Confira o calendário de origem."
            return {"conectada": True, "eventos": itens, "aviso": self._aviso, "limitado": limitado}
