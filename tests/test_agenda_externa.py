"""Assinatura de leitura: recorrências, mudanças, isolamento e falhas de rede."""
import datetime as dt

import pytest

from orquestra import agenda_externa as ae


ICAL = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:semanal
DTSTART;TZID=America/Sao_Paulo:20261116T100000
DTEND;TZID=America/Sao_Paulo:20261116T110000
RRULE:FREQ=WEEKLY;COUNT=4
EXDATE;TZID=America/Sao_Paulo:20261123T100000
SUMMARY:Reuniao da semana
END:VEVENT
BEGIN:VEVENT
UID:feriado
DTSTART;VALUE=DATE:20261120
DTEND;VALUE=DATE:20261122
SUMMARY:Dois dias
END:VEVENT
BEGIN:VEVENT
UID:cancelado
DTSTART;VALUE=DATE:20261121
STATUS:CANCELLED
SUMMARY:Cancelado
END:VEVENT
END:VCALENDAR
"""


def test_recorrencias_excecoes_fuso_e_dia_inteiro():
    itens, limitado = ae.eventos(ae.ler(ICAL), dt.date(2026, 11, 1), dt.date(2026, 12, 15))
    assert not limitado
    repetidas = [e for e in itens if e['titulo'] == 'Reuniao da semana']
    assert len(repetidas) == 3
    assert '2026-11-23' not in {e['data'] for e in repetidas}
    instante = dt.datetime(2026, 11, 16, 13, tzinfo=dt.timezone.utc).astimezone()
    assert repetidas[0]['hora'] == instante.strftime('%H:%M')
    assert {e['data_fim'] for e in itens if e['titulo'] == 'Dois dias'} == {'2026-11-21'}
    assert all(not e['editavel'] and e['externo'] for e in itens)
    assert not any(e['titulo'] == 'Cancelado' for e in itens)


def test_cache_atualiza_sem_duplicar_e_falha_preserva_ultima_leitura(tmp_path, monkeypatch):
    relogio = [1000]
    bruto = [ICAL]
    monkeypatch.setattr(ae.time, 'monotonic', lambda: relogio[0])
    monkeypatch.setattr(ae, 'baixar', lambda _: bruto[0])
    assinatura = ae.Assinatura(tmp_path)
    assinatura.conectar('https://agenda.example.test/segredo.ics')
    de, ate = dt.date(2026, 11, 1), dt.date(2026, 12, 15)
    inicial = assinatura.consultar(de, ate)
    bruto[0] = ICAL.replace(b'Reuniao da semana', b'Reuniao alterada')
    assert assinatura.consultar(de, ate)['eventos'] == inicial['eventos']
    relogio[0] += 301
    alterada = assinatura.consultar(de, ate)
    assert len(alterada['eventos']) == len(inicial['eventos'])
    assert any(e['titulo'] == 'Reuniao alterada' for e in alterada['eventos'])
    bruto[0] = b'fora do ar, segredo nao pode aparecer'
    relogio[0] += 301
    falha = assinatura.consultar(de, ate)
    assert falha['eventos'] == alterada['eventos'] and falha['aviso']
    assert 'segredo' not in falha['aviso']
    with pytest.raises(ValueError):
        assinatura.conectar('https://outra.example.test/nao-funciona.ics')
    assert assinatura.consultar(de, ate)['eventos'] == alterada['eventos']
    assinatura.desconectar()
    assert not assinatura.consultar(de, ate)['conectada']
    assert ae.Assinatura(tmp_path / 'outro').chave != assinatura.chave


@pytest.mark.parametrize('url', ['file:///privado.ics', 'http://agenda.test/a.ics', 'https://pessoa:senha@agenda.test/a', 'https://agenda.test:8420/a', 'https://agenda.test/a#fragmento'])
def test_endereco_inseguro_recusado(url):
    with pytest.raises(ValueError):
        ae.validar_url(url)


@pytest.mark.parametrize('ip', ['127.0.0.1', '192.168.0.1', '169.254.169.254', '::1'])
def test_rede_privada_nunca_e_consultada(ip, monkeypatch):
    monkeypatch.setattr(ae.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', (ip, 443))])
    monkeypatch.setattr(ae.http.client, 'HTTPSConnection', lambda *a, **k: pytest.fail('rede privada acessada'))
    with pytest.raises(ValueError):
        ae.baixar('https://agenda.test/privado.ics')


def test_recorrencia_muito_frequente_e_limitada():
    bruto = ICAL.replace(b'FREQ=WEEKLY;COUNT=4', b'FREQ=SECONDLY')
    itens, limitado = ae.eventos(ae.ler(bruto), dt.date(2026, 11, 16), dt.date(2026, 11, 17))
    assert limitado and len(itens) <= 500
