"""Vínculos entre registros de Projetos e Tarefas, usando os links do cofre."""

from collections import defaultdict

from orquestra.caminhos import CaminhoInseguro, caminho_no_vault
from orquestra.indice import Indice
from orquestra.modulos import NOTAS_DE_CONTRATO
from orquestra.notas import Nota
from orquestra.vinculos import resolver_em_lote


def vinculos_de_trabalho(indice: Indice, caminhos: set[str]) -> dict[str, list[Nota]]:
    """Retorna os itens do outro módulo ligados a cada caminho solicitado."""
    contratos = NOTAS_DE_CONTRATO | {"agents.orquestra.md"}
    projetos, tarefas = (
        {nota.rel: nota for nota in indice.itens(area) if not nota.erro
         and nota.caminho.name.lower() not in contratos}
        for area in ("projetos", "tarefas")
    )
    if not projetos or not tarefas or caminhos.isdisjoint(projetos.keys() | tarefas.keys()):
        return {}
    pares: dict[str, set[str]] = defaultdict(set)
    with resolver_em_lote(indice):
        for fontes, alvos in ((projetos, tarefas), (tarefas, projetos)):
            alvos_solicitados = caminhos.intersection(alvos)
            for rel in fontes:
                destinos = alvos if rel in caminhos else alvos_solicitados
                if not destinos:
                    continue
                ligados = {
                    destino.rel for ref in indice.referencias_de(rel)
                    if (destino := indice.resolver_referencia(ref, rel)).rel in destinos
                    and destino.estado in ("valido", "ancora_ausente")
                }
                if not ligados:
                    continue
                try:
                    if not caminho_no_vault(indice.vault, rel).is_file():
                        continue
                except (CaminhoInseguro, OSError):
                    continue
                for destino in ligados:
                    if rel in caminhos:
                        pares[rel].add(destino)
                    if destino in caminhos:
                        pares[destino].add(rel)
    notas = {**projetos, **tarefas}
    ordem = {rel: posicao for posicao, rel in enumerate(notas)}
    return {rel: [notas[alvo] for alvo in sorted(ligados, key=ordem.__getitem__)] for rel, ligados in pares.items()}
