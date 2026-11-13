"""Agenda do vault: datas civis locais, sem banco paralelo ao Markdown."""
from __future__ import annotations

import calendar
import datetime as dt
import re
import unicodedata
from collections import defaultdict
from urllib.parse import urlencode

from orquestra.apresentacao import url_nota
from orquestra.indice import data_de

VISOES = ("mes", "semana", "dia", "lista")
CORES = {"azul": "Azul", "verde": "Verde", "lilas": "Lilás", "laranja": "Laranja", "rosa": "Rosa", "vermelho": "Vermelho"}
CATEGORIAS = ("Compromisso", "Trabalho", "Pessoal", "Lembrete")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")


def data(valor) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return None


def hora(valor) -> str:
    texto = str(valor or "")
    return texto if re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", texto) else ""


def texto_busca(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto.casefold()) if not unicodedata.combining(c))


def fontes(painel) -> list[tuple]:
    """Fontes datadas reais e saídas reconhecidas das automações de tarefas.

    A presença de uma automação não transforma a pasta toda em tarefas. O caminho
    direto e os metadados emitidos pelo importador precisam corresponder. Notas de
    módulos continuam usando seu contrato original, inclusive status e conclusão.
    """
    from orquestra import automacoes

    resultado = [(modulo, list(painel.indice.registros_em(modulo.id)))
                 for modulo in painel.indice.modulos.values()]
    cobertas = {nota.rel for _, notas in resultado for nota in notas}
    por_pasta = defaultdict(list)
    for nota in painel.indice.notas.values():
        if nota.rel not in cobertas and nota.campo("origem") == "coletor":
            por_pasta[nota.caminho.parent].append(nota)
    for destino in automacoes.destinos_tarefas(painel):
        modulo = destino["modulo"]
        notas = [nota for nota in por_pasta[modulo.pasta_itens]
                 if nota.rel not in cobertas and not nota.erro
                 and str(nota.campo("coletor") or "").removesuffix(".py") == destino["coletor"]
                 and data_de(nota, modulo) is not None]
        if notas:
            resultado.append((modulo, notas))
            cobertas.update(nota.rel for nota in notas)
    return resultado


def evento(nota, modulo) -> dict | None:
    inicio = data_de(nota, modulo)
    # Notas antigas podem conter qualquer ano válido para datetime. Datas fora
    # da navegação suportada não podem derrubar toda a agenda ao estimar o fim.
    if inicio is None or not 2 <= inicio.year <= 9998:
        return None
    comeco = hora(nota.campo("hora"))
    # Reconhece os compromissos importados pelo coletor iCal anterior.
    if not comeco and str(nota.campo("coletor") or "").removesuffix(".py") == "agenda_ics":
        m = re.match(r"^(\d{2}:\d{2})\s", nota.titulo)
        comeco = hora(m.group(1)) if m else ""
    fim = max(inicio, data(nota.campo("data_fim")) or inicio)
    termino = hora(nota.campo("hora_fim"))
    if comeco and (not termino or dt.datetime.combine(fim, dt.time.fromisoformat(termino)) <= dt.datetime.combine(inicio, dt.time.fromisoformat(comeco))):
        estimado = dt.datetime.combine(inicio, dt.time.fromisoformat(comeco)) + dt.timedelta(hours=1)
        fim, termino = estimado.date(), estimado.strftime("%H:%M")
    cor = str(nota.campo("cor") or "")
    if cor not in CORES:
        cor = list(CORES)[sum(modulo.id.encode("utf-8")) % len(CORES)]
    tags = nota.campo("tags") or []
    return {"rel": nota.rel, "versao": nota.versao, "titulo": nota.titulo,
            "data": inicio.isoformat(), "data_fim": fim.isoformat(), "hora": comeco,
            "hora_fim": termino if comeco else "", "dia_inteiro": not comeco,
            "categoria": str(nota.campo("categoria") or modulo.nome), "modulo": modulo.id,
            "pasta": modulo.nome, "cor": cor, "tags": [str(t) for t in tags] if isinstance(tags, list) else [],
            "concluido": str(nota.campo(modulo.campo_status) or "") in modulo.concluidos,
            "editavel": not nota.erro and not modulo.invalido and not modulo.id.startswith("@automacao:"), "url": url_nota(nota.rel)}


def periodo(alvo: dt.date, visao: str) -> tuple[dt.date, dt.date]:
    if visao == "mes":
        primeiro = alvo.replace(day=1)
        comeco = primeiro - dt.timedelta(days=primeiro.weekday())
        return comeco, comeco + dt.timedelta(days=41)
    if visao == "semana":
        comeco = alvo - dt.timedelta(days=alvo.weekday())
        return comeco, comeco + dt.timedelta(days=6)
    if visao == "lista":
        return alvo.replace(day=1), alvo.replace(day=calendar.monthrange(alvo.year, alvo.month)[1])
    return alvo, alvo


def deslocar(alvo: dt.date, visao: str, passo: int) -> dt.date:
    if visao in ("mes", "lista"):
        n = alvo.year * 12 + alvo.month - 1 + passo
        ano, mes = divmod(n, 12)
        return dt.date(ano, mes + 1, min(alvo.day, calendar.monthrange(ano, mes + 1)[1]))
    return alvo + dt.timedelta(days=passo * (7 if visao == "semana" else 1))


def blocos(dia: dict) -> list[dict]:
    """Divide sobreposições em faixas sem atribuir um horário a itens sem hora."""
    resultado, grupo, fins = [], [], []

    def concluir():
        for item in grupo:
            item["largura"] = 100 / len(fins)
            item["esquerda"] = item["faixa"] * item["largura"]
        resultado.extend(grupo)

    itens = sorted((e for e in dia["eventos"] if not e["dia_inteiro"]), key=lambda e: (e["data"], e["hora"], e["rel"]))
    for e in itens:
        h, m = map(int, e["hora"].split(":"))
        hf, mf = map(int, e["hora_fim"].split(":"))
        inicio = h * 60 + m if e["data"] == dia["iso"] else 0
        fim = hf * 60 + mf if e["data_fim"] == dia["iso"] else 1440
        fim = min(1440, max(inicio + 30, fim))
        if fins and inicio >= max(fins):
            concluir(); grupo, fins = [], []
        faixa = next((i for i, limite in enumerate(fins) if inicio >= limite), len(fins))
        if faixa == len(fins):
            fins.append(fim)
        else:
            fins[faixa] = fim
        grupo.append({**e, "topo": round(inicio * 64 / 60, 2), "altura": round((fim - inicio) * 64 / 60, 2), "faixa": faixa})
    if grupo:
        concluir()
    return resultado


def montar(painel, alvo: dt.date, visao="mes", q="", pasta="", categoria="", cor="", tag="", concluidos=False) -> dict:
    if visao not in VISOES:
        raise ValueError("Escolha Mês, Semana, Dia ou Lista.")
    # Margem para navegação de mês e grade antes/depois da data selecionada.
    if not 2 <= alvo.year <= 9998:
        raise ValueError("Escolha uma data entre os anos 2 e 9998.")
    hoje = dt.date.today()
    de, ate = periodo(alvo, visao)
    opcoes_pastas, categorias, tags = [], set(), set()
    todos = []
    for modulo, notas in fontes(painel):
        if not modulo.campo_data:
            continue
        opcoes_pastas.append({"id": modulo.id, "nome": modulo.nome})
        for nota in notas:
            e = evento(nota, modulo)
            if not e:
                continue
            categorias.add(e["categoria"])
            tags.update(e["tags"])
            if e["concluido"] and not concluidos:
                continue
            if e["data"] > ate.isoformat() or e["data_fim"] < de.isoformat():
                continue
            if (pasta and e["modulo"] != pasta) or (categoria and e["categoria"] != categoria) or (cor and e["cor"] != cor) or (tag and tag not in e["tags"]):
                continue
            if q and texto_busca(q) not in texto_busca(" ".join([e["titulo"], e["categoria"], e["pasta"], *e["tags"], nota.corpo])):
                continue
            todos.append(e)
    todos.sort(key=lambda e: (e["data"], e["hora"], e["titulo"].casefold(), e["rel"]))
    total = len(todos)
    eventos = todos[:500]
    por_dia = defaultdict(list)
    for e in eventos:
        inicio, fim = max(de, data(e["data"])), min(ate, data(e["data_fim"]))
        while inicio <= fim:
            # Horário de término é exclusivo; meia-noite não ocupa o dia seguinte.
            if not (not e["dia_inteiro"] and inicio.isoformat() == e["data_fim"] and e["hora_fim"] == "00:00" and inicio.isoformat() != e["data"]):
                por_dia[inicio].append(e)
            inicio += dt.timedelta(days=1)
    dias = [{"iso": (d := de + dt.timedelta(days=i)).isoformat(), "num": d.day, "nome": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][d.weekday()],
             "hoje": d == hoje, "fora": d.month != alvo.month, "eventos": por_dia[d]} for i in range((ate - de).days + 1)]
    if visao in ("dia", "semana"):
        for dia in dias:
            dia["blocos"] = blocos(dia)
    filtros = {"visao": visao, "q": q, "pasta": pasta, "categoria": categoria, "cor": cor, "tag": tag, "concluidos": "1" if concluidos else ""}

    def url(d=alvo, v=visao):
        return "/agenda/" + d.isoformat() + "?" + urlencode({k: val for k, val in {**filtros, "visao": v}.items() if val})

    if visao in ("mes", "lista"):
        titulo = f"{MESES[alvo.month - 1].capitalize()} {alvo.year}"
    elif visao == "semana":
        if de.year != ate.year:
            titulo = f"{de.day} {MESES[de.month - 1][:3]} {de.year} – {ate.day} {MESES[ate.month - 1][:3]} {ate.year}"
        elif de.month != ate.month:
            titulo = f"{de.day} {MESES[de.month - 1][:3]} – {ate.day} {MESES[ate.month - 1][:3]} {ate.year}"
        else:
            titulo = f"{de.day}–{ate.day} de {MESES[ate.month - 1]} {ate.year}"
    else:
        titulo = f"{alvo.day} de {MESES[alvo.month - 1]} {alvo.year}"
    return {"visao": visao, "data": alvo.isoformat(), "titulo": titulo, "dias": dias, "eventos": eventos, "total": total, "limitado": total > 500,
            "anterior": url(deslocar(alvo, visao, -1)), "proximo": url(deslocar(alvo, visao, 1)), "url_hoje": url(hoje),
            "visoes": [{"id": v, "nome": n, "url": url(v=v)} for v, n in zip(VISOES, ("Mês", "Semana", "Dia", "Lista"))],
            "filtros": filtros, "pastas": opcoes_pastas, "categorias": sorted(categorias), "tags": sorted(tags), "cores": CORES,
            "horas": range(24), "categorias_evento": sorted(set(CATEGORIAS) | categorias)}


def validar_evento(dados: dict) -> dict:
    inicio, fim = data(dados["data"]), data(dados.get("data_fim") or dados["data"])
    if not inicio or not fim or not 2 <= inicio.year <= 9998 or not 2 <= fim.year <= 9998 or fim < inicio:
        raise ValueError("Confira as datas de início e término.")
    if (fim - inicio).days > 366:
        raise ValueError("Um compromisso pode ocupar até 366 dias.")
    h, hf = hora(dados.get("hora")), hora(dados.get("hora_fim"))
    if not dados.get("dia_inteiro"):
        if not h or not hf or dt.datetime.combine(fim, dt.time.fromisoformat(hf)) <= dt.datetime.combine(inicio, dt.time.fromisoformat(h)):
            raise ValueError("O término precisa ser posterior ao início. Confira os horários.")
    else:
        h = hf = ""
    tags = list(dict.fromkeys(t.strip() for t in dados.get("tags", []) if t.strip()))
    if len(tags) > 20 or any(len(t) > 80 for t in tags):
        raise ValueError("Use até 20 tags com no máximo 80 caracteres cada.")
    return {"data": inicio.isoformat(), "data_fim": fim.isoformat(), "hora": h, "hora_fim": hf,
            "categoria": dados.get("categoria", "Compromisso").strip() or "Compromisso", "cor": dados.get("cor", "azul"), "tags": tags}
