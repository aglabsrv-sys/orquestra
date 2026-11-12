"""Hábitos são notas do módulo: metas semanais e realizações confirmadas."""
from __future__ import annotations

import datetime as dt
from typing import Any

from orquestra import apresentacao as ap, preparo
from orquestra.notas import ler_nota
from orquestra.painel import NaoEncontrado, Recusado

MODELOS = (
    {"id": "academia", "titulo": "Academia", "meta": 3, "icone": "pulso", "descricao": "Movimento em três dias da semana.", "tags": ["saude"]},
    {"id": "leitura", "titulo": "Leitura", "meta": 5, "icone": "livro", "descricao": "Um pouco de leitura, cinco vezes por semana.", "tags": ["aprendizado"]},
    {"id": "caminhada", "titulo": "Caminhada", "meta": 4, "icone": "coracao", "descricao": "Reserve quatro dias para caminhar.", "tags": ["saude"]},
)


def meta_valida(valor: Any) -> int:
    if isinstance(valor, bool):
        raise Recusado("Escolha uma meta inteira entre 1 e 7 dias por semana.")
    try:
        numero = float(valor)
        inteiro = int(numero)
    except (ValueError, TypeError, OverflowError):
        raise Recusado("Escolha uma meta inteira entre 1 e 7 dias por semana.") from None
    if numero != inteiro or not 1 <= inteiro <= 7:
        raise Recusado("Escolha uma meta inteira entre 1 e 7 dias por semana.")
    return inteiro


def _datas(nota) -> set[str]:
    registros = nota.campo("registros")
    if registros is None:
        registros = []
    if not isinstance(registros, list):
        raise Recusado("Os registros deste hábito precisam ser uma lista de datas. Confira a nota no editor.")
    if len(registros) > 20000:
        raise Recusado("Este hábito contém registros demais para editar pelo painel.")
    resultado = set()
    for valor in registros:
        if isinstance(valor, dt.datetime):
            raise Recusado("Use datas sem horário nos registros do hábito.")
        try:
            dia = dt.date.fromisoformat(str(valor))
        except (ValueError, TypeError):
            raise Recusado("Há um registro fora do formato AAAA-MM-DD. Confira a nota antes de marcar.") from None
        resultado.add(dia.isoformat())
    return resultado


def apresentar(nota, hoje: dt.date) -> dict:
    aviso = ""
    try:
        meta = meta_valida(nota.campo("meta_semanal") if nota.campo("meta_semanal") is not None else 3)
    except Recusado as erro:
        meta, aviso = 3, str(erro)
    try:
        registros = _datas(nota)
    except Recusado as erro:
        registros, aviso = set(), str(erro)
    segunda = hoje - dt.timedelta(days=hoje.weekday())
    dias_semana = [segunda + dt.timedelta(days=i) for i in range(7)]
    semana = sum(d.isoformat() in registros for d in dias_semana if d <= hoje)
    tags = nota.campo("tags") or []
    return {"rel": nota.rel, "versao": nota.versao, "titulo": nota.titulo, "url": ap.url_nota(nota.rel),
            "meta": meta, "semana": semana, "percentual": min(100, round(semana / meta * 100)),
            "marcado": hoje.isoformat() in registros, "registros": sorted(registros),
            "dias": [{"iso": d.isoformat(), "nome": "STQQSSD"[d.weekday()], "rotulo": ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")[d.weekday()], "feito": d.isoformat() in registros, "futuro": d > hoje, "hoje": d == hoje} for d in dias_semana],
            "tags": [str(t) for t in tags] if isinstance(tags, list) else [], "aviso": aviso,
            "editavel": not bool(nota.erro), "total_registros": sum(d <= hoje.isoformat() for d in registros)}


def resumo(itens: list[dict]) -> dict:
    return {"total": len(itens), "hoje": sum(i["marcado"] for i in itens),
            "metas": sum(i["semana"] >= i["meta"] for i in itens), "semana": sum(i["semana"] for i in itens)}


def montar(painel, aba="progresso", hoje: dt.date | None = None) -> dict:
    hoje = hoje or dt.date.today()
    instalado = "habitos" in painel.indice.modulos
    modulo = painel.modulo("habitos") if instalado else preparo.catalogo()["habitos"]
    itens = [apresentar(n, hoje) for n in painel.indice.itens("habitos")] if instalado else []
    itens.sort(key=lambda i: (i["marcado"], i["titulo"].casefold(), i["rel"]))
    segunda = hoje - dt.timedelta(days=hoje.weekday())
    inicio = segunda - dt.timedelta(weeks=12)
    dias = [inicio + dt.timedelta(days=i) for i in range(91)]
    meses = []
    anterior = None
    for semana in range(13):
        dia = inicio + dt.timedelta(weeks=semana)
        nome = ap.MESES[dia.month - 1]
        meses.append(nome if nome != anterior else "")
        anterior = nome
    return {"modulo": modulo,
            "aba": "lista" if aba in ("lista", "v1") else "progresso", "itens": itens,
            "resumo_habitos": resumo(itens), "modelos": MODELOS, "dias_mapa": dias,
            "meses_mapa": meses, "n_humano": len(painel.indice.notas_em("habitos", "humano")) if instalado else 0,
            "instalado": instalado, "hoje_habitos": hoje.isoformat()}


def _modulo_compativel(painel):
    modulo = painel._modulo_para_escrita(painel.modulo("habitos"))
    tipos = {"meta_semanal": "numero", "registros": "lista", "tags": "lista"}
    if any(nome not in modulo.campos or modulo.campos[nome].tipo != tipo for nome, tipo in tipos.items()):
        raise Recusado("A pasta habitos existente tem outro formato. Em Personalizar, use meta_semanal como número e registros e tags como listas.")
    return modulo


def _nota(painel, rel: str):
    modulo = painel.indice.modulo_de(rel)
    if modulo is None or modulo.id != "habitos" or painel.indice.zona_de(rel) != "itens":
        raise NaoEncontrado("Hábito inexistente nesta pasta.")
    _modulo_compativel(painel)
    nota = ler_nota(painel.caminho_seguro(rel), painel.vault)
    if nota.erro:
        raise Recusado("Esta nota tem erro no frontmatter. Confira o arquivo antes de editar.")
    return nota


def salvar(painel, dados: dict, hoje: dt.date | None = None) -> dict:
    """Cria ou edita só título/meta/tags; os registros existentes são preservados."""
    hoje = hoje or dt.date.today()
    titulo = str(dados.get("titulo") or "").strip()
    if not titulo or len(titulo) > 120:
        raise Recusado("Dê um nome ao hábito, com até 120 caracteres.")
    meta = meta_valida(dados.get("meta_semanal", 3))
    tags = dados.get("tags") or []
    if not isinstance(tags, list) or len(tags) > 12 or any(not isinstance(t, str) or len(t) > 60 for t in tags):
        raise Recusado("Use até 12 tags com até 60 caracteres cada.")
    tags = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
    with painel._trava:
        rel = str(dados.get("rel") or "")
        if rel:
            _nota(painel, rel)
            nota = painel.editar_nota(rel, str(dados.get("versao") or ""), titulo=titulo, campos={"meta_semanal": meta, "tags": tags})
        else:
            if "habitos" not in painel.indice.modulos:
                painel.adicionar_modulo("habitos", exemplos=False)
            _modulo_compativel(painel)
            nota = painel.criar_nota("habitos", titulo, {"meta_semanal": meta, "registros": [], "tags": tags})
        itens = [apresentar(n, hoje) for n in painel.indice.itens("habitos")]
        item = apresentar(nota, hoje)
        return {"rel": nota.rel, "versao": nota.versao, "item": item, "resumo": resumo(itens), "hoje": hoje.isoformat()}


criar = salvar


def marcar(painel, dados: dict, hoje: dt.date | None = None) -> dict:
    """Alterna somente hoje, com a versão fornecida e a trava comum de notas."""
    hoje = hoje or dt.date.today()
    rel, versao = str(dados.get("rel") or ""), str(dados.get("versao") or "")
    with painel._trava:
        nota = _nota(painel, rel)
        registros = _datas(nota)
        meta_valida(nota.campo("meta_semanal") if nota.campo("meta_semanal") is not None else 3)
        iso = hoje.isoformat()
        if iso in registros:
            registros.remove(iso)
        else:
            registros.add(iso)
        atualizada = painel.editar_nota(rel, versao, campos={"registros": sorted(registros)})
        item = apresentar(atualizada, hoje)
        itens = [apresentar(n, hoje) for n in painel.indice.itens("habitos")]
        return {"rel": atualizada.rel, "versao": atualizada.versao, "marcado": item["marcado"], "item": item, "resumo": resumo(itens), "hoje": iso}
