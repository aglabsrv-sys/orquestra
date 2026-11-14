"""Cadastro de pessoas independente do acompanhamento comercial."""
from __future__ import annotations

from uuid import UUID
import unicodedata
from collections import Counter

from orquestra.painel import Recusado
from orquestra.notas import ler_nota


def listar(painel) -> list[dict]:
    resultado = []
    for nota in painel.indice.registros_em("contatos"):
        identificador = nota.campo("contato_id")
        if identificador:
            resultado.append({"id": str(identificador), "titulo": nota.titulo, "rel": nota.rel,
                              "telefone": nota.campo("telefone") or "", "email": nota.campo("email") or ""})
    return sorted(resultado, key=lambda c: (c["titulo"].casefold(), c["rel"]))


def validar_vinculo(painel, valor) -> str | None:
    if valor in (None, ""):
        return None
    try:
        identificador = str(UUID(str(valor)))
    except ValueError:
        raise Recusado("Selecione um contato cadastrado.") from None
    encontrados = [c for c in listar(painel) if c["id"] == identificador]
    if len(encontrados) != 1:
        raise Recusado("O contato não está disponível ou tem identificador duplicado. Reabra Contatos.")
    try:
        atual = ler_nota(painel.caminho_seguro(encontrados[0]["rel"]), painel.vault)
    except FileNotFoundError:
        raise Recusado("O contato foi movido ou excluído. Reabra Contatos.") from None
    if atual.erro or atual.campo("contato_id") != identificador:
        raise Recusado("O cadastro do contato mudou. Reabra Contatos.")
    return identificador


def contexto(painel, nota=None) -> dict:
    opcoes = listar(painel)
    contagens = Counter(c["id"] for c in opcoes)
    opcoes = [c for c in opcoes if contagens[c["id"]] == 1]
    identificador = str(nota.campo("contato_id") or "") if nota else ""
    return {"opcoes_contatos": opcoes,
            "contato_vinculado": next((c for c in opcoes if c["id"] == identificador), None),
            "clientes_vinculados": [n for n in painel.indice.registros_em("clientes")
                                    if identificador and n.campo("contato_id") == identificador]}


def filtrar(painel, itens, parametros) -> tuple[list, dict]:
    def normalizar_busca(texto):
        return "".join(c for c in unicodedata.normalize("NFKD", texto.casefold()) if not unicodedata.combining(c))
    busca = str(parametros.get("q", "")).strip()
    grupo = str(parametros.get("grupo", ""))
    favoritos = parametros.get("favoritos") == "1"
    grupos = sorted({str(g) for n in itens for g in (n.campo("grupos") or []) if isinstance(n.campo("grupos"), list)}, key=str.casefold)
    resultado = []
    for nota in itens:
        if favoritos and nota.campo("favorito") is not True:
            continue
        if grupo and grupo not in (nota.campo("grupos") or []):
            continue
        texto = " ".join([nota.titulo, str(nota.campo("telefone") or ""), str(nota.campo("email") or ""), str(nota.campo("organizacao") or "")])
        if busca and normalizar_busca(busca) not in normalizar_busca(texto):
            continue
        resultado.append(nota)
    return resultado, {"busca_contato": busca, "grupo_contato": grupo, "favoritos_contato": favoritos, "grupos_contatos": grupos}
