"""Anotações diárias e registro do que mudou no vault.

- `diario/notas/AAAA-MM-DD.md`: a anotação pessoal daquele dia.

- `diario/registro/AAAA-MM-DD.md`: escrito pelo painel a cada arquivo criado,
  editado ou removido. É factual (o quê e quando), e funciona com qualquer
  agente porque vem do vigia de arquivos, não de um gancho de um agente específico.
- `diario/sessoes/AAAA-MM-DD.md`: escrito pelos agentes ao fim de cada sessão de
  trabalho (regra do AGENTS.md). Conta o porquê.
"""

from __future__ import annotations

import datetime as dt
import difflib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from orquestra.notas import Nota, simples
from orquestra import armazenamento
from orquestra.caminhos import CaminhoInseguro, caminho_no_vault

PASTA_REGISTRO = "diario/registro"
PASTA_SESSOES = "diario/sessoes"
PASTA_ANOTACOES = "diario/notas"


def caminho_anotacao(data: dt.date) -> str:
    return f"{PASTA_ANOTACOES}/{data.isoformat()}.md"


def data_da_anotacao(rel: str) -> dt.date | None:
    if not rel.startswith(PASTA_ANOTACOES + "/"):
        return None
    try:
        data = dt.date.fromisoformat(Path(rel).stem)
    except ValueError:
        return None
    return data if rel == caminho_anotacao(data) else None


@dataclass
class Entrada:
    hora: str
    tipo: str
    rel: str
    detalhe: str
    autor: str


def resumir(antes: Nota | None, depois: Nota | None) -> str:
    """Descreve em uma linha o que mudou entre duas versões de uma nota."""
    if antes is None or depois is None:
        return ""
    partes: list[str] = []
    chaves = list(dict.fromkeys([*antes.meta.keys(), *depois.meta.keys()]))
    for chave in chaves:
        a, d = simples(antes.meta.get(chave)), simples(depois.meta.get(chave))
        if a == d:
            continue
        if a is None:
            partes.append(f"{chave}: {_curto(d)} (novo)")
        elif d is None:
            partes.append(f"{chave} removido")
        else:
            partes.append(f"{chave}: {_curto(a)} → {_curto(d)}")
    if len(partes) > 4:
        partes = partes[:4] + [f"+{len(partes) - 4} campos"]

    if antes.corpo != depois.corpo:
        mais = menos = 0
        for linha in difflib.unified_diff(antes.corpo.splitlines(), depois.corpo.splitlines(), lineterm="", n=0):
            if linha.startswith("+") and not linha.startswith("+++"):
                mais += 1
            elif linha.startswith("-") and not linha.startswith("---"):
                menos += 1
        partes.append(f"texto: +{mais} −{menos} linhas")
    return "; ".join(partes)


def _curto(valor: object) -> str:
    texto = ", ".join(map(str, valor)) if isinstance(valor, list) else str(valor)
    return texto if len(texto) <= 40 else texto[:37] + "..."


def registrar(vault: Path, tipo: str, rel: str, detalhe: str = "", autor: str = "externo") -> None:
    """Acrescenta uma linha ao registro do dia."""
    agora = dt.datetime.now()
    caminho = caminho_no_vault(vault, Path(PASTA_REGISTRO) / f"{agora:%Y-%m-%d}.md")
    limpo = lambda s: str(s).replace("|", "/").replace("\n", " ")  # noqa: E731
    linha = f"- {agora:%H:%M:%S} | {tipo} | {limpo(rel)} | {limpo(detalhe)} | {limpo(autor)}\n"
    with armazenamento.trava(caminho):
        if autor == "externo" and caminho.exists() and _ja_registrado(caminho, tipo, limpo(rel), agora):
            return
        # Registro gerado pelo app: append de uma linha sob trava evita reler/regravar o dia inteiro.
        caminho_no_vault(vault, caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("ab") as arquivo:
            if arquivo.tell() == 0:
                arquivo.write((f"# Registro de {agora:%d/%m/%Y}\n\n"
                               "Gerado automaticamente pelo painel. Formato: hora | ação | arquivo | detalhe | autor.\n\n").encode("utf-8"))
            arquivo.write(linha.encode("utf-8"))


def _ja_registrado(caminho: Path, tipo: str, rel: str, agora: dt.datetime, janela: int = 6) -> bool:
    """Diz se outro processo acabou de registrar esta mesma mudança, com o autor certo.

    Acontece quando o servidor MCP grava uma nota com o painel aberto: o MCP registra
    "feito pelo agente" e, um instante depois, o vigia do painel vê o mesmo arquivo
    mudar. Sem esta conferência a mudança apareceria duas vezes, a segunda como "externo".
    """
    try:
        with caminho.open("rb") as arquivo:
            arquivo.seek(0, 2)
            arquivo.seek(max(0, arquivo.tell() - 16384))
            ultimas = arquivo.read().decode("utf-8", errors="replace").splitlines()[-12:]
    except OSError:
        return False
    for linha in ultimas:
        partes = [p.strip() for p in linha[2:].split("|")] if linha.startswith("- ") else []
        if len(partes) < 5 or partes[1] != tipo or partes[2] != rel or partes[4] == "externo":
            continue
        try:
            hora = dt.datetime.combine(agora.date(), dt.time.fromisoformat(partes[0]))
        except ValueError:
            continue
        if 0 <= (agora - hora).total_seconds() <= janela:
            return True
    return False


def ler_registro(vault: Path, dia: dt.date) -> list[Entrada]:
    try:
        caminho = caminho_no_vault(vault, Path(PASTA_REGISTRO) / f"{dia.isoformat()}.md")
    except CaminhoInseguro:
        return []
    if not caminho.is_file():
        return []
    entradas: list[Entrada] = []
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linha.startswith("- "):
            continue
        partes = [p.strip() for p in linha[2:].split("|")]
        if len(partes) >= 5:
            entradas.append(Entrada(*partes[:5]))
    entradas.reverse()  # mais recentes primeiro
    return entradas


def consultar_registro(vault: Path, dia: dt.date, q: str = "", autor: str = "", tipo: str = "", pagina: int = 1) -> dict:
    """Filtra e pagina a apresentação, preservando o registro completo no disco."""
    from orquestra.calendario import texto_busca

    entradas = ler_registro(vault, dia)
    autores = sorted({e.autor for e in entradas})
    tipos = sorted({e.tipo for e in entradas})
    termo = texto_busca(q.strip()[:200])
    filtradas = [e for e in entradas if (not autor or e.autor == autor) and (not tipo or e.tipo == tipo)
                 and (not termo or termo in texto_busca(" ".join((e.rel, e.detalhe, e.autor, e.tipo))))]
    tamanho = 80
    paginas = max(1, (len(filtradas) + tamanho - 1) // tamanho)
    pagina = min(max(1, pagina), paginas)
    inicio = (pagina - 1) * tamanho

    def url(numero):
        return "?" + urlencode({k: v for k, v in {"dia": dia.isoformat(), "q": q[:200], "autor": autor,
                                                   "tipo": tipo, "pagina": numero}.items() if v})

    return {"entradas": filtradas[inicio:inicio + tamanho], "total": len(entradas), "encontradas": len(filtradas),
            "arquivos": len({e.rel for e in entradas}), "autores": autores, "tipos": tipos,
            "q": q[:200], "autor": autor, "tipo": tipo, "pagina": pagina, "paginas": paginas,
            "anterior": url(pagina - 1) if pagina > 1 else "", "proximo": url(pagina + 1) if pagina < paginas else ""}


def ler_sessoes(vault: Path, dia: dt.date) -> str:
    try:
        caminho = caminho_no_vault(vault, Path(PASTA_SESSOES) / f"{dia.isoformat()}.md")
    except CaminhoInseguro:
        return ""
    if not caminho.is_file():
        return ""
    return caminho.read_text(encoding="utf-8-sig", errors="replace")


def dias_com_registro(vault: Path) -> list[dt.date]:
    dias: set[dt.date] = set()
    for pasta in (PASTA_REGISTRO, PASTA_SESSOES):
        try:
            diretorio = caminho_no_vault(vault, pasta)
        except CaminhoInseguro:
            continue
        for arquivo in diretorio.glob("*.md"):
            try:
                caminho_no_vault(vault, arquivo)
                dias.add(dt.date.fromisoformat(arquivo.stem))
            except ValueError:
                pass
    return sorted(dias, reverse=True)


def resumo_dia(painel, alvo: dt.date, hoje: dt.date | None = None, pagina: int = 1) -> dict:
    """Retrato dos itens do dia com o estado atual das notas.

    Datas antigas usam as datas das notas e seu estado *atual*. Pendências sem
    data e atrasados só pertencem à visão de hoje.
    """
    from orquestra import calendario, habitos
    from orquestra.apresentacao import url_nota
    from orquestra.indice import data_de
    from orquestra.modulos import rotulo
    from orquestra.tarefas import sem_data

    hoje = hoje or dt.date.today()
    itens, atrasados, sem_agendamento = [], [], []
    for modulo, notas in calendario.fontes(painel):
        for nota in notas:
            if nota.erro or calendario.e_compromisso(nota, modulo):
                continue
            status = str(nota.campo(modulo.campo_status) or "")
            concluido = status in modulo.concluidos
            item = {"rel": nota.rel, "titulo": nota.titulo, "url": url_nota(nota.rel),
                    "pasta": modulo.nome, "status": rotulo(status), "concluido": concluido,
                    "hora": "", "data": ""}
            data = data_de(nota, modulo)
            if data is None:
                if alvo == hoje and not concluido and sem_data(nota, modulo):
                    sem_agendamento.append(item)
                continue
            item["data"] = data.isoformat()
            evento = calendario.evento(nota, modulo)
            if evento:
                item["hora"] = evento["hora"]
                no_dia = calendario.no_dia(evento, alvo)
            else:
                no_dia = data == alvo
            if no_dia and (alvo < hoje or not concluido):
                itens.append(item)
            elif alvo == hoje and data < hoje and modulo.tem_status and not concluido:
                atrasados.append(item)
    itens.sort(key=lambda i: (not bool(i["hora"]), i["hora"], i["titulo"].casefold(), i["rel"]))
    atrasados.sort(key=lambda i: (i["data"], i["titulo"].casefold(), i["rel"]))
    sem_agendamento.sort(key=lambda i: (i["titulo"].casefold(), i["rel"]))
    itens_habitos = []
    modulo_habitos = painel.indice.modulos.get("habitos")
    if alvo <= hoje and modulo_habitos and "registros" in modulo_habitos.campos:
        itens_habitos = [habitos.apresentar(nota, alvo) for nota in painel.indice.registros_em("habitos") if not nota.erro]
        itens_habitos.sort(key=lambda item: (not item["marcado"], item["titulo"].casefold(), item["rel"]))

    totais = {"itens": len(itens), "atrasados": len(atrasados),
              "sem_data": len(sem_agendamento),
              "habitos": len(itens_habitos),
              "habitos_feitos": sum(item["marcado"] for item in itens_habitos)}
    tamanho = 80
    paginas = max(1, (max(len(itens), len(atrasados), len(sem_agendamento), len(itens_habitos)) + tamanho - 1) // tamanho)
    pagina = min(max(1, pagina), paginas)
    inicio = (pagina - 1) * tamanho
    paginacao = {"pagina": pagina, "paginas": paginas,
                 "anterior": f"/dia/{alvo}?pagina={pagina - 1}" if pagina > 1 else "",
                 "proximo": f"/dia/{alvo}?pagina={pagina + 1}" if pagina < paginas else ""}
    return {"itens": itens[inicio:inicio + tamanho], "atrasados": atrasados[inicio:inicio + tamanho],
            "sem_data": sem_agendamento[inicio:inicio + tamanho],
            "paginacao": paginacao, "habitos": itens_habitos[inicio:inicio + tamanho], "totais": totais,
            "anterior": f"/dia/{alvo - dt.timedelta(days=1)}" if alvo > dt.date.min else "",
            "proximo": f"/dia/{alvo + dt.timedelta(days=1)}" if alvo < dt.date.max else "",
            "historico": alvo < hoje, "tem_conteudo": any(totais.values())}
