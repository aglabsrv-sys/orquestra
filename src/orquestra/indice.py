"""Índice em memória do vault.

O índice é só um espelho rápido dos arquivos: a verdade está sempre no disco.
Ele é montado ao iniciar e atualizado arquivo por arquivo quando o vigia avisa
que algo mudou. Se for apagado, basta reconstruir.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

from orquestra.modulos import Modulo, descobrir
from orquestra.notas import Nota, ler_nota

EXT_MIDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm"}
PASTAS_IGNORADAS = {".git", ".obsidian", ".trash", "__pycache__", "node_modules", ".venv"}


def deve_ignorar(rel: str) -> bool:
    """Arquivos que o painel não indexa nem registra no diário."""
    partes = rel.split("/")
    if any(p in PASTAS_IGNORADAS for p in partes):
        return True
    if partes[0] == "_orquestra":
        return True
    if partes[:2] == ["diario", "registro"]:
        return True  # o registro é escrito pelo próprio painel
    return partes[-1].endswith(".orq-tmp")


@dataclass
class Mudanca:
    tipo: str  # criado | editado | removido
    rel: str
    antes: Nota | None
    depois: Nota | None


@dataclass
class Resumo:
    total: int = 0
    abertos: int = 0  # ainda não concluídos
    hoje: int = 0  # com data de hoje ou atrasados
    decidir: int = 0  # esperando decisão humana


class Indice:
    def __init__(self, vault: Path):
        self.vault = vault.resolve()
        self.modulos: dict[str, Modulo] = {}
        self.notas: dict[str, Nota] = {}
        self.midias: dict[str, str] = {}  # nome do arquivo em minúsculas -> caminho relativo

    # ------------------------------------------------------------ carga

    def carregar(self) -> None:
        self.modulos = descobrir(self.vault)
        self.notas = {}
        self.midias = {}
        for raiz, pastas, arquivos in os.walk(self.vault):
            base = Path(raiz).relative_to(self.vault).as_posix()
            prefixo = "" if base == "." else base + "/"
            pastas[:] = [p for p in pastas if not deve_ignorar(prefixo + p)]
            for nome in arquivos:
                rel = prefixo + nome
                if deve_ignorar(rel):
                    continue
                sufixo = Path(nome).suffix.lower()
                if sufixo == ".md":
                    try:
                        self.notas[rel] = ler_nota(self.vault / rel, self.vault)
                    except OSError:
                        pass
                elif sufixo in EXT_MIDIA:
                    self.midias[nome.lower()] = rel

    def recarregar_modulos(self) -> None:
        self.modulos = descobrir(self.vault)

    def atualizar(self, caminho: Path) -> Mudanca | None:
        """Relê um arquivo que mudou no disco. Devolve o que mudou (ou None)."""
        try:
            rel = caminho.resolve().relative_to(self.vault).as_posix()
        except ValueError:
            return None
        if deve_ignorar(rel):
            return None
        sufixo = caminho.suffix.lower()
        if sufixo in EXT_MIDIA:
            if caminho.is_file():
                self.midias[caminho.name.lower()] = rel
            else:
                self.midias.pop(caminho.name.lower(), None)
            return None
        if sufixo != ".md":
            return None

        antes = self.notas.get(rel)
        if not caminho.is_file():
            if antes is None:
                return None
            del self.notas[rel]
            return Mudanca("removido", rel, antes, None)
        try:
            depois = ler_nota(caminho, self.vault)
        except OSError:
            return None
        if antes is not None and antes.versao == depois.versao:
            return None  # o arquivo foi tocado, mas o conteúdo é o mesmo
        self.notas[rel] = depois
        return Mudanca("editado" if antes else "criado", rel, antes, depois)

    # ------------------------------------------------------------ consultas

    def modulo_de(self, rel: str) -> Modulo | None:
        return self.modulos.get(rel.split("/", 1)[0])

    @staticmethod
    def zona_de(rel: str) -> str:
        """Segunda parte do caminho: itens, humano, maquina, arquivo..."""
        partes = rel.split("/")
        return partes[1] if len(partes) > 2 else ""

    def notas_em(self, modulo_id: str, zona: str) -> list[Nota]:
        prefixo = f"{modulo_id}/{zona}/"
        achadas = [n for rel, n in self.notas.items() if rel.startswith(prefixo)]
        achadas.sort(key=lambda n: n.titulo.lower())
        return achadas

    def itens(self, modulo_id: str) -> list[Nota]:
        """Registros do módulo (pasta itens/), ordenados por data e depois por título."""
        modulo = self.modulos.get(modulo_id)
        notas = self.notas_em(modulo_id, "itens")
        if modulo and modulo.campo_data:
            notas.sort(key=lambda n: (data_de(n, modulo) or dt.date.max, n.titulo.lower()))
        return notas

    def ids_externos(self, modulo_id: str) -> set[str]:
        """IDs já coletados neste módulo (inclusive arquivados), para não duplicar."""
        prefixo = modulo_id + "/"
        return {
            str(n.meta["id_externo"])
            for rel, n in self.notas.items()
            if rel.startswith(prefixo) and n.meta.get("id_externo")
        }

    def resumo(self, modulo: Modulo, hoje: dt.date | None = None) -> Resumo:
        hoje = hoje or dt.date.today()
        r = Resumo()
        for nota in self.notas_em(modulo.id, "itens"):
            r.total += 1
            status = str(nota.campo(modulo.campo_status) or "")
            if espera_decisao(nota, modulo):
                r.decidir += 1
            if status in modulo.concluidos:
                continue
            r.abertos += 1
            data = data_de(nota, modulo)
            if data and data <= hoje:
                r.hoje += 1
        return r

    def buscar(self, termo: str, limite: int = 60) -> list[Nota]:
        termo = termo.lower().strip()
        if not termo:
            return []
        no_titulo, no_corpo = [], []
        for nota in self.notas.values():
            if termo in nota.titulo.lower():
                no_titulo.append(nota)
            elif termo in nota.corpo.lower():
                no_corpo.append(nota)
        return (no_titulo + no_corpo)[:limite]

    def resolver_link(self, nome: str) -> str | None:
        """Resolve um [[wikilink]] do Obsidian para o caminho relativo da nota."""
        alvo = nome.strip().lower().removesuffix(".md")
        for rel, nota in self.notas.items():
            if rel.lower().removesuffix(".md") == alvo or nota.caminho.stem.lower() == alvo:
                return rel
        return None


def espera_decisao(nota: Nota, modulo: Modulo) -> bool:
    """Uma nota entra na fila Decidir por dois caminhos:

    - o status dela está na lista `decidir` do módulo (ex.: item recém-coletado);
    - um agente deixou uma `pergunta` no frontmatter, esperando resposta humana.
    """
    if str(nota.meta.get("pergunta") or "").strip():
        return True
    return str(nota.campo(modulo.campo_status) or "") in modulo.decidir


def data_de(nota: Nota, modulo: Modulo) -> dt.date | None:
    """Data principal da nota (o campo indicado em `campo_data` do módulo)."""
    if not modulo.campo_data:
        return None
    valor = nota.meta.get(modulo.campo_data)
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    if valor:
        try:
            return dt.date.fromisoformat(str(valor)[:10])
        except ValueError:
            return None
    return None
