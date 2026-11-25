"""Ações do menu de notas e pastas, com as mesmas fronteiras do painel."""
from __future__ import annotations

from urllib.parse import quote, urlencode

from orquestra import apoios, apresentacao as ap, lixeira
from orquestra.indice import deve_ignorar
from orquestra.notas import Conflito, ler_nota
from orquestra.painel import NaoEncontrado, Recusado


def consultar(painel, rel: str = "", modulo: str = "", chave: str = "") -> dict:
    with painel._trava:
        if chave:
            area = painel.modulo(modulo)
            if chave.startswith("diretorio:"):
                rel = chave.removeprefix("diretorio:")
                painel.diretorio_de_pasta(area, rel)
                return consultar(painel, rel)
            if area.id not in ("projetos", "estudos"):
                raise NaoEncontrado(chave)
            pasta = apoios.dentro(painel, area, chave)
            url = f"/m/{quote(modulo, safe='')}?" + urlencode({"abrir": chave})
            if pasta["tipo_acao"] == "diretorio":
                dados = consultar(painel, pasta["diretorio"])
                return {**dados, "titulo": pasta["titulo"], "url": url, "propriedades": url + "&propriedades=1"}
            return {"tipo": "pasta", "titulo": pasta["titulo"], "rel": "", "modulo": modulo, "chave": chave,
                    "url": url, "propriedades": url + "&propriedades=1", "versao": pasta["versao"],
                    "arquivar": True, "excluir": True, "aviso": "", "caminho": chave,
                    "descricao": "A nota principal e as notas exclusivas serão movidas. Anexos e notas compartilhadas ficam onde estão."}
        caminho = painel.caminho_seguro(rel)
        if not rel or deve_ignorar(rel + ("/x.md" if caminho.is_dir() else "")) or not caminho.exists():
            raise NaoEncontrado(rel)
        area = painel.indice.modulo_de(rel)
        if caminho.is_file():
            if caminho.suffix.lower() != ".md":
                raise NaoEncontrado(rel)
            nota = ler_nota(caminho, painel.vault)
            permitida = lixeira.pode_excluir(painel, rel)
            return {"tipo": "nota", "titulo": nota.titulo, "rel": rel, "modulo": "", "chave": "",
                    "url": ap.url_nota(rel), "propriedades": ap.url_nota(rel) + "?propriedades=1", "versao": nota.versao,
                    "arquivar": permitida and not _arquivada(rel), "excluir": permitida,
                    "aviso": "Arquivo protegido." if not permitida else "", "caminho": rel,
                    "descricao": "Somente esta nota será movida. Anexos e outras notas ficam onde estão."}
        permitida, aviso = lixeira.pode_excluir_pasta(painel.vault, rel)
        propriedades = f"/m/{quote(area.id, safe='')}/personalizar" if area and rel == area.id else ""
        if area and area.itens_na_raiz and rel.startswith(area.id + "/"):
            propriedades = f"/m/{quote(area.id, safe='')}?" + urlencode({"pasta": rel[len(area.id) + 1:], "propriedades": "1"})
        return {"tipo": "pasta", "titulo": caminho.name, "rel": rel, "modulo": "", "chave": "",
                "url": ap.url_pasta(rel), "propriedades": propriedades, "versao": lixeira.versao_pasta(caminho) if permitida else "",
                "arquivar": permitida and not _arquivada(rel), "excluir": permitida, "aviso": aviso,
                "caminho": rel, "descricao": "A pasta inteira será movida, incluindo notas, subpastas e anexos."}


def _arquivada(rel: str) -> bool:
    return "arquivo" in rel.casefold().split("/")


def agir(painel, acao: str, versao: str, rel: str = "", modulo: str = "", chave: str = "") -> dict:
    with painel._trava:
        dados = consultar(painel, rel, modulo, chave)
        if acao not in ("arquivar", "excluir") or not dados[acao]:
            raise Recusado(dados["aviso"] or "Esta ação não está disponível para este item.")
        if dados["versao"] != versao:
            raise Conflito("Este item mudou. Abra o menu novamente antes de continuar.")
        if dados["chave"]:
            return painel.agir_pasta(dados["modulo"], dados["chave"], acao, versao)
        rel = dados["rel"]
        if dados["tipo"] == "nota":
            if acao == "arquivar":
                return {"rel": painel.arquivar(rel, versao=versao)}
            return {"id": painel.excluir(rel, versao)}
        origem = painel.caminho_seguro(rel)
        if acao == "excluir":
            resultado = {"id": lixeira.excluir_pasta(painel.vault, rel, versao, dados["titulo"])}
        else:
            area = painel.indice.modulo_de(rel)
            raiz = painel.caminho_seguro(area.pasta / "arquivo" if area else origem.parent / "arquivo")
            destino, numero = raiz / origem.name, 2
            while destino.exists():
                destino = raiz / f"{origem.name} {numero}"
                numero += 1
            lixeira.mover_pasta(painel.vault, origem, destino, versao)
            resultado = {"rel": destino.relative_to(painel.vault).as_posix()}
        painel.recarregar_tudo()
        painel.mudou_desde_o_backup = True
        return resultado
