"""Tudo que transforma dados do vault em algo pronto para os templates:
ícones, datas em português, cartões, a faixa da semana, o dock e o markdown.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any
from urllib.parse import quote

from markdown_it import MarkdownIt
from markupsafe import Markup, escape

from orquestra import temas
from orquestra.indice import Indice, data_de
from orquestra.modulos import Modulo, rotulo, validar
from orquestra.notas import Nota
from orquestra.painel import Painel

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Ícones de traço, desenhados para uma grade de 24x24. Para usar um ícone num
# módulo, coloque o nome dele em `icone:` no _modulo.yaml.
ICONES = {
    "inicio": '<path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9h12v-9"/><path d="M10 19v-5h4v5"/>',
    "check": '<path d="m4 6 1.5 1.5L8 5"/><path d="m4 12 1.5 1.5L8 11"/><path d="m4 18 1.5 1.5L8 17"/><path d="M11 6h9M11 12h9M11 18h9"/>',
    "video": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/>',
    "radar": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12 18.5 5.5"/><circle cx="12" cy="12" r="1"/>',
    "entrada": '<path d="M4 13 6.5 5h11L20 13v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"/><path d="M4 13h4.5l1 2h5l1-2H20"/>',
    "sino": '<path d="M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "pulso": '<path d="M3 12h4l2.5-6 4 12 2.5-6h5"/>',
    "ajustes": '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
    "mais": '<path d="M12 5v14M5 12h14"/>',
    "seta_dir": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "seta_esq": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "chevron_dir": '<path d="m9 6 6 6-6 6"/>',
    "chevron_esq": '<path d="m15 6-6 6 6 6"/>',
    "busca": '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
    "paleta": '<path d="M12 3a9 9 0 1 0 0 18c1.5 0 2-1 2-2s-.5-1.5-.5-2.5S14.5 15 16 15h2a3 3 0 0 0 3-3c0-5-4-9-9-9z"/><circle cx="8" cy="10" r="1"/><circle cx="12" cy="7.5" r="1"/><circle cx="16" cy="10" r="1"/>',
    "pasta": '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
    "pessoa": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/>',
    "pessoas": '<circle cx="9" cy="9" r="3"/><path d="M3 19a6 6 0 0 1 12 0"/><path d="M16 6.5a3 3 0 0 1 0 5.5M17.5 14.5A5.5 5.5 0 0 1 21 19"/>',
    "chip": '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="10" y="10" width="4" height="4"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>',
    "lampada": '<path d="M9 17h6M10 20h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
    "calendario": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>',
    "externo": '<path d="M14 5h5v5M19 5l-8 8"/><path d="M11 7H6a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-5"/>',
    "caixa": '<rect x="3" y="5" width="18" height="4" rx="1"/><path d="M5 9v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9M10 13h4"/>',
    "editar": '<path d="m5 19 1-4L16 5l3 3L9 18z"/><path d="m14 7 3 3"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "raio": '<path d="M13 3 5 13h6l-1 8 8-10h-6z"/>',
    "moeda": '<circle cx="12" cy="12" r="9"/><path d="M15 9.5c-.5-1-1.600-1.500-3-1.500-1.700 0-3 .8-3 2s1.300 1.700 3 2 3 .8 3 2-1.300 2-3 2c-1.400 0-2.500-.5-3-1.500M12 6v2M12 16v2"/>',
    "livro": '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
    "grafico": '<path d="M4 20V4M4 20h16"/><path d="m7 15 4-4 3 3 5-6"/>',
    "estrela": '<path d="m12 4 2.500 5 5.500.8-4 3.900.9 5.500L12 16.600l-4.900 2.600.9-5.500-4-3.900L9.500 9z"/>',
    "relogio": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "tocar": '<path d="m8 5 11 7-11 7z"/>',
    "atualizar": '<path d="M20 11A8 8 0 0 0 5.500 7M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.500 4M20 20v-4h-4"/>',
    "nuvem": '<path d="M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9.500a4.300 4.300 0 0 1-.5 8.500z"/>',
    "nota": '<path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "celular": '<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M11 18h2"/>',
    "aviso": '<path d="M12 4 3 20h18z"/><path d="M12 10v4M12 17v.5"/>',
    "coracao": '<path d="M12 20s-7-4.400-7-10a4 4 0 0 1 7-2.500A4 4 0 0 1 19 10c0 5.600-7 10-7 10z"/>',
    "casa": '<path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9h12v-9"/>',
}


def icone(nome: str, tamanho: int = 20) -> Markup:
    desenho = ICONES.get(nome) or ICONES["pasta"]
    return Markup(
        f'<svg class="icone" width="{int(tamanho)}" height="{int(tamanho)}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{desenho}</svg>'
    )


# ---------------------------------------------------------------- datas


def data_curta(dia: dt.date, hoje: dt.date) -> str:
    diferenca = (dia - hoje).days
    if diferenca == 0:
        return "hoje"
    if diferenca == 1:
        return "amanhã"
    if diferenca == -1:
        return "ontem"
    texto = f"{dia.day} {MESES[dia.month - 1]}"
    return texto if dia.year == hoje.year else f"{texto} {dia.year}"


def data_longa(dia: dt.date) -> str:
    nomes = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    return f"{nomes[dia.weekday()]}, {dia.day} de {meses[dia.month - 1]}"


def url_midia(valor: str) -> str:
    valor = str(valor).strip()
    if valor.startswith(("http://", "https://")):
        return valor
    return "/arquivo/" + quote(valor.lstrip("/"))


def link_seguro(valor: Any) -> str | None:
    """Só links http(s) viram clicáveis.

    O campo `link` pode vir de um feed coletado da internet. Um endereço como
    `javascript:...` executaria código dentro do painel ao ser clicado.
    """
    texto = str(valor or "").strip()
    return texto if texto.lower().startswith(("http://", "https://")) else None


def url_nota(rel: str) -> str:
    return "/n/" + quote(rel)


# ---------------------------------------------------------------- markdown

_md = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable(["table", "strikethrough"])
_EMBUTIDO = re.compile(r"!\[\[([^\]]+)\]\]")
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(#[^\]|]*)?(?:\|([^\]]+))?\]\]")
_IMG_RELATIVA = re.compile(r'<img src="(?!https?:|/|data:)([^"]+)"')


def render_markdown(texto: str, indice: Indice) -> Markup:
    """Markdown -> HTML seguro (HTML cru é desativado), entendendo [[links]] do Obsidian."""

    def embutir(m: re.Match) -> str:
        nome = m.group(1).split("|")[0].strip()
        rel = indice.midias.get(nome.split("/")[-1].lower())
        return f"![{nome}](/arquivo/{quote(rel)})" if rel else m.group(0)

    def ligar(m: re.Match) -> str:
        alvo = m.group(1).strip()
        texto_link = (m.group(3) or alvo).strip()
        rel = indice.resolver_link(alvo)
        return f"[{texto_link}]({url_nota(rel)})" if rel else texto_link

    texto = _EMBUTIDO.sub(embutir, texto)
    texto = _WIKILINK.sub(ligar, texto)
    html = _md.render(texto)
    html = _IMG_RELATIVA.sub(lambda m: f'<img src="/arquivo/{m.group(1)}"', html)
    html = html.replace("<li>[ ] ", '<li class="tarefa"><input type="checkbox" disabled> ')
    html = html.replace("<li>[x] ", '<li class="tarefa"><input type="checkbox" disabled checked> ')
    return Markup(html)


def trecho(nota: Nota, tamanho: int = 140) -> str:
    """Primeiras palavras do corpo, sem marcação, para listas e buscas."""
    texto = re.sub(r"[#>*_`\[\]]", "", nota.corpo)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto if len(texto) <= tamanho else texto[: tamanho - 1].rstrip() + "…"


# ---------------------------------------------------------------- cartões


def cartao(nota: Nota, modulo: Modulo | None, hoje: dt.date, omitir: str | None = None) -> dict[str, Any]:
    """Resumo de uma nota para quadros, listas e a fila Decidir."""
    c: dict[str, Any] = {
        "rel": nota.rel,
        "url": url_nota(nota.rel),
        "titulo": nota.titulo,
        "versao": nota.versao,
        "etiquetas": [],
        "imagem": None,
        "link": None,
        "origem": nota.campo("origem"),
        "pergunta": nota.campo("pergunta"),
        "status": None,
        "concluido": False,
        "com_aviso": bool(nota.erro),
        "modulo": modulo.id if modulo else "",
    }
    if modulo is None:
        return c

    c["status"] = nota.campo(modulo.campo_status)
    c["concluido"] = str(c["status"] or "") in modulo.concluidos
    c["com_aviso"] = c["com_aviso"] or bool(validar(modulo, nota.meta))

    for campo in modulo.campos.values():
        if campo.nome in (omitir, "origem"):
            continue
        valor = nota.campo(campo.nome)
        if valor in (None, "", []):
            continue
        if campo.tipo == "escolha":
            c["etiquetas"].append({"texto": rotulo(valor), "classe": f"et-{campo.nome} v-{valor}"})
        elif campo.tipo == "data":
            dia = data_de(nota, modulo) if campo.nome == modulo.campo_data else None
            if dia is None:
                try:
                    dia = dt.date.fromisoformat(str(valor)[:10])
                except ValueError:
                    continue
            classe = "et-data"
            if campo.nome == modulo.campo_data and not c["concluido"]:
                classe += " atrasado" if dia < hoje else (" e-hoje" if dia == hoje else "")
            c["etiquetas"].append({"texto": data_curta(dia, hoje), "classe": classe})
        elif campo.tipo == "lista" and isinstance(valor, list):
            for item in valor[:3]:
                c["etiquetas"].append({"texto": f"#{item}", "classe": "et-tag"})
        elif campo.tipo == "imagem":
            c["imagem"] = url_midia(valor)
        elif campo.tipo == "link":
            c["link"] = link_seguro(valor)
        elif campo.tipo == "booleano":
            if valor:
                c["etiquetas"].append({"texto": campo.rotulo, "classe": "et-tag"})
        elif campo.tipo == "numero":
            c["etiquetas"].append({"texto": f"{campo.rotulo}: {valor}", "classe": "et-tag"})
    return c


def valor_para_formulario(nota: Nota, nome: str, tipo: str) -> str:
    valor = nota.campo(nome)
    if valor is None:
        return ""
    if tipo == "lista" and isinstance(valor, list):
        return ", ".join(map(str, valor))
    if tipo == "booleano":
        return "true" if valor else ""
    return str(valor)


# ---------------------------------------------------------------- navegação


def texto_selo(resumo, modulo: Modulo) -> str:
    """Frase curta do cartão do módulo no início: '2 para hoje', '4 para decidir'..."""
    if modulo.campo_data and resumo.hoje:
        return f"{resumo.hoje} para hoje"
    if resumo.decidir:
        return f"{resumo.decidir} para decidir"
    if resumo.abertos:
        return f"{resumo.abertos} em aberto"
    return "tudo em dia" if resumo.total else "vazio"


def montar_dock(painel: Painel, ativo: str, hoje: dt.date) -> dict[str, Any]:
    """Itens do dock: início, módulos e as telas do sistema, com contadores."""
    modulos = []
    total_decidir = 0
    for modulo in painel.indice.modulos.values():
        resumo = painel.indice.resumo(modulo, hoje)
        total_decidir += resumo.decidir
        modulos.append(
            {
                "id": modulo.id,
                "nome": modulo.nome,
                "icone": modulo.icone,
                "url": f"/m/{quote(modulo.id)}",
                # O número do dock: "para hoje" se o módulo tem datas; senão o que espera
                # decisão; e, se o módulo não usa nem um nem outro, o que está em aberto.
                "selo": resumo.hoje if modulo.campo_data else (resumo.decidir if modulo.decidir else resumo.abertos),
                "ativo": ativo == f"m:{modulo.id}",
            }
        )
    sistema = [
        {"id": "decidir", "nome": "Decidir", "icone": "sino", "url": "/decidir", "selo": total_decidir},
        {"id": "diario", "nome": "Diário", "icone": "pulso", "url": "/diario", "selo": 0},
        {"id": "ajustes", "nome": "Ajustes", "icone": "ajustes", "url": "/ajustes", "selo": 0},
    ]
    for item in sistema:
        item["ativo"] = ativo == item["id"]
    return {"modulos": modulos, "sistema": sistema, "decidir": total_decidir, "inicio_ativo": ativo == "inicio"}


def montar_semana(painel: Painel, hoje: dt.date) -> tuple[list[dict[str, Any]], int]:
    """Os próximos 7 dias com a quantidade de itens em aberto em cada um."""
    por_dia: dict[dt.date, int] = {}
    atrasados = 0
    for modulo in painel.indice.modulos.values():
        if not modulo.campo_data:
            continue
        for nota in painel.indice.notas_em(modulo.id, "itens"):
            if str(nota.campo(modulo.campo_status) or "") in modulo.concluidos:
                continue
            dia = data_de(nota, modulo)
            if dia is None:
                continue
            if dia < hoje:
                atrasados += 1
            por_dia[dia] = por_dia.get(dia, 0) + 1
    semana = []
    for i in range(7):
        dia = hoje + dt.timedelta(days=i)
        semana.append(
            {"iso": dia.isoformat(), "nome": DIAS[dia.weekday()], "num": dia.day, "n": por_dia.get(dia, 0), "hoje": i == 0}
        )
    return semana, por_dia.get(hoje, 0) + atrasados


def capa_de(painel: Painel, alvo: str, propria: Any = None) -> dict[str, Any]:
    return temas.resolver_capa(painel.tema, alvo, propria)


def e(valor: Any) -> str:
    return str(escape(valor))
