"""Diário: o registro do que mudou no vault.

São duas camadas, que o painel mostra juntas:

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

from orquestra.notas import Nota, simples
from orquestra import armazenamento
from orquestra.caminhos import CaminhoInseguro, caminho_no_vault

PASTA_REGISTRO = "diario/registro"
PASTA_SESSOES = "diario/sessoes"


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
        partes = [p.strip() for p in linha[2:].split(" | ")] if linha.startswith("- ") else []
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
        partes = [p.strip() for p in linha[2:].split(" | ")]
        if len(partes) >= 5:
            entradas.append(Entrada(*partes[:5]))
    entradas.reverse()  # mais recentes primeiro
    return entradas


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
