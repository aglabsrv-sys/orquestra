"""Hábitos são notas do módulo: metas semanais e realizações confirmadas."""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from typing import Any

from orquestra import apoios, armazenamento, apresentacao as ap, preparo
from orquestra.notas import Conflito, ler_nota
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


def _datas(nota) -> Counter[str]:
    registros = nota.campo("registros")
    if registros is None:
        registros = []
    if not isinstance(registros, list):
        raise Recusado("Os registros deste hábito precisam ser uma lista de datas. Confira a nota no editor.")
    if len(registros) > 20000:
        raise Recusado("Este hábito contém registros demais para editar pelo painel.")
    resultado: Counter[str] = Counter()
    for valor in registros:
        if isinstance(valor, dt.datetime):
            raise Recusado("Use datas sem horário nos registros do hábito.")
        try:
            dia = dt.date.fromisoformat(str(valor))
        except (ValueError, TypeError):
            raise Recusado("Há um registro fora do formato AAAA-MM-DD. Confira a nota antes de marcar.") from None
        resultado[dia.isoformat()] += 1
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
        registros, aviso = Counter(), str(erro)
    segunda = hoje - dt.timedelta(days=hoje.weekday())
    dias_semana = [segunda + dt.timedelta(days=i) for i in range(7)]
    semana = sum(d.isoformat() in registros for d in dias_semana if d <= hoje)
    tags = nota.campo("tags") or []
    return {"rel": nota.rel, "versao": nota.versao, "titulo": nota.titulo, "url": ap.url_nota(nota.rel), "descricao": nota.corpo,
            "dias_com_notas": [],
            "meta": meta, "semana": semana, "percentual": min(100, round(semana / meta * 100)),
            "marcado": hoje.isoformat() in registros, "registros": sorted(registros),
            "contagens": dict(registros), "contagem_hoje": registros[hoje.isoformat()],
            "tem_repeticoes": any(total > 1 and dia <= hoje.isoformat() for dia, total in registros.items()),
            "dias": [{"iso": d.isoformat(), "nome": "STQQSSD"[d.weekday()], "rotulo": ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")[d.weekday()], "feito": d.isoformat() in registros, "futuro": d > hoje, "hoje": d == hoje} for d in dias_semana],
            "tags": [str(t) for t in tags] if isinstance(tags, list) else [], "aviso": aviso,
            "editavel": not bool(nota.erro), "total_registros": sum(d <= hoje.isoformat() for d in registros)}


def resumo(itens: list[dict]) -> dict:
    return {"total": len(itens), "hoje": sum(i["marcado"] for i in itens),
            "metas": sum(i["semana"] >= i["meta"] for i in itens), "semana": sum(i["semana"] for i in itens)}


def _ordem(painel) -> list[str]:
    secao = painel.ler_estado().get("habitos", {})
    ordem = secao.get("ordem", []) if isinstance(secao, dict) else []
    return list(dict.fromkeys(ordem)) if isinstance(ordem, list) and all(isinstance(r, str) for r in ordem) else []


def _versao_ordem(ordem: list[str]) -> str:
    return armazenamento.versao(json.dumps(ordem, ensure_ascii=False).encode("utf-8"))


def reordenar(painel, ordem: list[str], versao: str) -> dict:
    with painel._trava:
        if versao != _versao_ordem(_ordem(painel)):
            raise Conflito("A ordem mudou em outra janela. Atualize o painel antes de reorganizar.")
        existentes = {n.rel for n in painel.indice.itens("habitos")}
        if len(ordem) != len(set(ordem)) or set(ordem) != existentes:
            raise Conflito("A lista de hábitos mudou. Atualize o painel antes de reorganizar.")
        painel.gravar_estado("habitos", "ordem", ordem)
        painel.eventos.publicar({"tipo": "config"})
        return {"ordem": ordem, "versao": _versao_ordem(ordem)}


def montar(painel, aba="progresso", hoje: dt.date | None = None) -> dict:
    hoje = hoje or dt.date.today()
    instalado = "habitos" in painel.indice.modulos
    modulo = painel.modulo("habitos") if instalado else preparo.catalogo()["habitos"]
    itens = [apresentar(n, hoje) for n in painel.indice.itens("habitos")] if instalado else []
    execucoes = apoios.por_item(painel, "habitos", "execucoes") if instalado else {}
    for item in itens:
        notas = execucoes.get(item["rel"], [])
        item["dias_com_notas"] = sorted({n["data"] for n in notas if n["data"]})
    ordem = _ordem(painel)
    posicoes = {rel: i for i, rel in enumerate(ordem)}
    itens.sort(key=lambda i: (posicoes.get(i["rel"], len(ordem)), i["titulo"].casefold(), i["rel"]) if ordem else (i["marcado"], i["titulo"].casefold(), i["rel"]))
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
    return {"modulo": modulo, "versao_ordem": _versao_ordem(ordem),
            "aba": "lista" if aba in ("lista", "v1") else "progresso", "itens": itens,
            "resumo_habitos": resumo(itens), "modelos": MODELOS, "dias_mapa": dias,
            "meses_mapa": meses, "n_humano": len(painel.indice.notas_em("habitos", "humano")) if instalado else 0,
            "instalado": instalado, "hoje_habitos": hoje.isoformat()}


def _modulo_compativel(painel):
    modulo = painel._modulo_para_escrita(painel.modulo("habitos"))
    tipos = {"meta_semanal": "numero", "registros": "lista", "tags": "lista"}
    if any(nome not in modulo.campos or modulo.campos[nome].tipo != tipo for nome, tipo in tipos.items()):
        raise Recusado("A pasta habitos existente tem outro formato. Confira meta_semanal, registros e tags no _modulo.yaml.")
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


def anotar_realizacao(painel, rel: str, texto: str, data: str = "", *, origem: str = "humano", autor: str = "painel"):
    """Guarda o texto da execução sem alterar a descrição nem as marcações."""
    texto = texto.strip()
    if not texto or len(texto) > 1_000_000:
        raise Recusado("Escreva uma nota de até um milhão de caracteres.")
    hoje = dt.date.today()
    try:
        dia = dt.date.fromisoformat(data) if data else hoje
        if data and dia.isoformat() != data:
            raise ValueError
    except ValueError:
        raise Recusado("Use uma data no formato AAAA-MM-DD.") from None
    if dia > hoje:
        raise Recusado("Escolha hoje ou um dia anterior para anotar a realização.")
    titulo = texto.splitlines()[0].lstrip("# ").strip() or "Realização"
    titulo = titulo if len(titulo) <= 65 else titulo[:62].rstrip() + "..."
    with painel._trava:
        item = _nota(painel, rel)
        pasta = f"habitos/execucoes/{item.caminho.stem}"
        painel.caminho_seguro(pasta).mkdir(parents=True, exist_ok=True)
        return painel.criar_nota_em_pasta(pasta, f"{titulo} - {dia}", texto, origem, autor,
                                         {"habito": f"[[{item.rel.removesuffix('.md')}]]"}, data=dia)


def salvar(painel, dados: dict, hoje: dt.date | None = None) -> dict:
    """Edita o hábito sem substituir registros ou propriedades desconhecidas."""
    hoje = hoje or dt.date.today()
    titulo = str(dados.get("titulo") or "").strip()
    if not titulo or len(titulo) > 120:
        raise Recusado("Dê um nome ao hábito, com até 120 caracteres.")
    meta = meta_valida(dados.get("meta_semanal", 3))
    tags = dados.get("tags") or []
    if not isinstance(tags, list) or len(tags) > 12 or any(not isinstance(t, str) or len(t) > 60 for t in tags):
        raise Recusado("Use até 12 tags com até 60 caracteres cada.")
    tags = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
    descricao = dados.get("descricao")
    if descricao is not None and (not isinstance(descricao, str) or len(descricao) > 1000000):
        raise Recusado("Use uma descrição de até um milhão de caracteres.")
    with painel._trava:
        rel = str(dados.get("rel") or "")
        if rel:
            _nota(painel, rel)
            nota = painel.editar_nota(rel, str(dados.get("versao") or ""), titulo=titulo, corpo=descricao, campos={"meta_semanal": meta, "tags": tags})
        else:
            if "habitos" not in painel.indice.modulos:
                painel.adicionar_modulo("habitos", exemplos=False)
            _modulo_compativel(painel)
            nota = painel.criar_nota("habitos", titulo, {"meta_semanal": meta, "registros": [], "tags": tags}, corpo=descricao or "")
        itens = [apresentar(n, hoje) for n in painel.indice.itens("habitos")]
        item = apresentar(nota, hoje)
        return {"rel": nota.rel, "versao": nota.versao, "item": item, "resumo": resumo(itens), "hoje": hoje.isoformat()}


criar = salvar


def marcar(painel, dados: dict, hoje: dt.date | None = None) -> dict:
    """Registra mais uma realização hoje, usando a trava e a versão da nota."""
    hoje = hoje or dt.date.today()
    rel, versao = str(dados.get("rel") or ""), str(dados.get("versao") or "")
    with painel._trava:
        nota = _nota(painel, rel)
        registros = _datas(nota)
        meta_valida(nota.campo("meta_semanal") if nota.campo("meta_semanal") is not None else 3)
        iso = hoje.isoformat()
        if registros.total() >= 20000:
            raise Recusado("Este hábito contém registros demais para editar pelo painel.")
        registros[iso] += 1
        atualizada = painel.editar_nota(rel, versao, campos={"registros": sorted(registros.elements())})
        item = apresentar(atualizada, hoje)
        itens = [apresentar(n, hoje) for n in painel.indice.itens("habitos")]
        return {"rel": atualizada.rel, "versao": atualizada.versao, "marcado": item["marcado"], "item": item, "resumo": resumo(itens), "hoje": iso}
