"""Conexões do vault para agentes: consulta o índice, sem reescrever notas."""

from __future__ import annotations

import posixpath
from pathlib import Path
from urllib.parse import unquote

from orquestra.caminhos import CaminhoInseguro, caminho_no_vault, ignorar
from orquestra.vinculos import resolver_em_lote


def conexoes_nota(ferramentas, caminho: str, limite: int = 30) -> dict:
    """Links locais e backlinks, com estados do mesmo resolvedor do painel.

    O chamador mantém o lock e sincroniza o índice antes desta consulta. Os
    limites são por direção; totais continuam contando todos os resultados.
    """
    limite = max(1, min(int(limite), 100))
    nota = ferramentas._nota(caminho)
    indice = ferramentas.painel.indice
    contratos = {"agents.md", "agents.orquestra.md", "claude.md", "gemini.md"}

    def permitido(rel: str) -> bool:
        if ignorar(rel) or Path(rel).name.lower() in contratos:
            return False
        try:
            caminho_no_vault(indice.vault, rel)
        except (CaminhoInseguro, OSError):
            return False
        return True

    saidas, entradas = [], []
    with resolver_em_lote(indice):
        for referencia in indice.referencias_de(nota.rel):
            resolucao = indice.resolver_referencia(referencia, nota.rel)
            if resolucao.estado == "externo":
                continue
            item = {
                "estado": resolucao.estado,
                "linha": referencia.linha,
                "tipo": referencia.tipo,
                "embutido": referencia.embutido,
            }
            alvo = unquote(referencia.alvo.partition("#")[0].split("?", 1)[0]).replace("\\", "/")
            nome = posixpath.basename(alvo).lower()
            bloqueado = (
                resolucao.estado == "bloqueado"
                or nome in contratos
                or bool(resolucao.rel and not permitido(resolucao.rel))
            )
            if bloqueado:
                # A referência pode conter nomes de arquivos privados ou caminhos
                # externos. Não devolver nem o rótulo arbitrário desses links.
                item["estado"] = "bloqueado"
            else:
                item.update(alvo=referencia.alvo, texto=referencia.texto)
                if resolucao.rel:
                    item["caminho"] = resolucao.rel
                if resolucao.fragmento:
                    item["fragmento"] = resolucao.fragmento
                if resolucao.candidatos:
                    candidatos = [rel for rel in resolucao.candidatos if permitido(rel)]
                    if candidatos:
                        item["candidatos"] = candidatos[:limite]
                        item["candidatos_limitados"] = len(candidatos) > limite
                    else:
                        item = {**item, "estado": "bloqueado"}
                        item.pop("alvo", None)
                        item.pop("texto", None)
            saidas.append(item)

        for rel, origem in sorted(indice.notas.items()):
            if rel == nota.rel or not ferramentas._visivel(origem) or not permitido(rel):
                continue
            referencias = []
            for referencia in indice.referencias_de(rel):
                resolucao = indice.resolver_referencia(referencia, rel)
                if resolucao.rel == nota.rel and resolucao.estado in {"valido", "ancora_ausente"}:
                    referencias.append(referencia)
            if referencias:
                entradas.append({
                    **ferramentas._resumo(origem),
                    "ocorrencias": len(referencias),
                    "linhas": sorted({referencia.linha for referencia in referencias})[:limite],
                    "linhas_limitadas": len({referencia.linha for referencia in referencias}) > limite,
                })

    # Linhas do corpo Markdown, sem contar o frontmatter. A ordem de saída segue
    # a posição no texto; entradas seguem o caminho, sem depender do scandir.
    saidas.sort(key=lambda item: item["linha"])
    return {
        "nota": ferramentas._resumo(nota),
        "saidas": {"total": len(saidas), "itens": saidas[:limite], "limitado": len(saidas) > limite},
        "entradas": {"total": len(entradas), "itens": entradas[:limite], "limitado": len(entradas) > limite},
    }
