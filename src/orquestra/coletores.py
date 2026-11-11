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
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap

from orquestra.config import carregar_env
from orquestra.indice import Indice
from orquestra.modulos import ColetorDef, Modulo, ValorInvalido, converter, padroes
from orquestra.notas import Nota, caminho_livre, gravar_nota, nome_de_arquivo

TEMPO_LIMITE = 180  # segundos por execução
CHAVES_RESERVADAS = {"id", "titulo", "corpo", "campos"}


@dataclass
class Resultado:
    ok: bool
    novos: int = 0
    repetidos: int = 0
    erro: str = ""


def caminho_script(modulo: Modulo, coletor: ColetorDef) -> Path:
    return modulo.pasta / "maquina" / "coletores" / coletor.script


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
    if ultima is None:
        return True
    intervalo = intervalo_em_segundos(coletor.a_cada)
    if intervalo:
        return (agora - ultima).total_seconds() >= intervalo
    if coletor.diario_as:
        try:
            hora, minuto = (int(p) for p in coletor.diario_as.split(":")[:2])
        except ValueError:
            return False
        alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if agora < alvo:
            alvo -= dt.timedelta(days=1)  # o horário de hoje ainda não chegou: vale o de ontem
        return ultima < alvo
    return False


def rodar_script(vault: Path, modulo: Modulo, coletor: ColetorDef) -> tuple[list[dict[str, Any]], str]:
    """Executa o script e devolve (itens, erro). Pode demorar: chame fora do laço principal."""
    script = caminho_script(modulo, coletor)
    if not script.is_file():
        return [], f"Script não encontrado: {script.relative_to(vault).as_posix()}"

    uv = shutil.which("uv")
    comando = [uv, "run", "--quiet", "--no-project", "--script", str(script)] if uv else [sys.executable, str(script)]

    ambiente = os.environ.copy()
    ambiente.update(carregar_env())  # chaves de API de ~/.orquestra/.env
    ambiente.update(
        {
            "ORQUESTRA_CONFIG": json.dumps(coletor.config, ensure_ascii=False),
            "ORQUESTRA_VAULT": str(vault),
            "ORQUESTRA_MODULO": str(modulo.pasta),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    ambiente.pop("VIRTUAL_ENV", None)  # o script roda no ambiente dele, não no do painel
    try:
        processo = subprocess.run(
            comando, capture_output=True, timeout=TEMPO_LIMITE, cwd=script.parent, env=ambiente
        )
    except subprocess.TimeoutExpired:
        return [], f"O coletor passou de {TEMPO_LIMITE}s e foi interrompido."
    except OSError as e:
        return [], f"Não consegui executar o coletor: {e}"

    saida = processo.stdout.decode("utf-8", errors="replace")
    if processo.returncode != 0:
        erros = processo.stderr.decode("utf-8", errors="replace").strip().splitlines()
        return [], (erros[-1] if erros else f"O coletor terminou com erro (código {processo.returncode}).")

    itens: list[dict[str, Any]] = []
    for linha in saida.splitlines():
        linha = linha.strip()
        if not linha.startswith("{"):
            continue  # o script pode imprimir outras coisas; só linhas JSON contam
        try:
            item = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("id") and item.get("titulo"):
            itens.append(item)
    return itens, ""


def importar(indice: Indice, modulo: Modulo, coletor: ColetorDef, itens: list[dict[str, Any]]) -> tuple[list[Nota], int]:
    """Transforma itens coletados em notas. Devolve (notas criadas, quantos já existiam)."""
    conhecidos = indice.ids_externos(modulo.id)
    criadas: list[Nota] = []
    repetidos = 0
    for item in itens:
        id_externo = str(item["id"])
        if id_externo in conhecidos:
            repetidos += 1
            continue
        conhecidos.add(id_externo)

        titulo = str(item["titulo"]).strip()
        meta = CommentedMap()
        if nome_de_arquivo(titulo) != titulo:
            meta["titulo"] = titulo  # o nome do arquivo precisou ser adaptado; guardamos o original
        meta.update(padroes(modulo))

        campos = item.get("campos") if isinstance(item.get("campos"), dict) else {
            k: v for k, v in item.items() if k not in CHAVES_RESERVADAS
        }
        for nome, valor in campos.items():
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
        caminho = caminho_livre(modulo.pasta_itens, titulo)
        nota = Nota(
            caminho=caminho,
            rel=caminho.relative_to(indice.vault).as_posix(),
            meta=meta,
            corpo=("\n" + corpo + "\n") if corpo else "",
        )
        gravar_nota(nota, criar=True)
        criadas.append(nota)
    return criadas, repetidos
