"""Uma central de orientações, preservando os contratos e as notas existentes."""

from __future__ import annotations

from urllib.parse import quote

from orquestra import armazenamento
from orquestra.caminhos import caminho_no_vault

ARQUIVO = "AGENTS.md"
LIMITE = 512 * 1024
INICIO = b"<!-- orquestra:orientacoes:inicio -->"
FIM = b"<!-- orquestra:orientacoes:fim -->"
LINKS_INICIO = b"<!-- orquestra:orientacoes-vinculadas:inicio -->"
LINKS_FIM = b"<!-- orquestra:orientacoes-vinculadas:fim -->"
MARCADORES = (INICIO, FIM, LINKS_INICIO, LINKS_FIM)


def _ler(painel) -> bytes | None:
    caminho = caminho_no_vault(painel.vault, ARQUIVO)
    try:
        with caminho.open("rb") as entrada:
            dados = entrada.read(LIMITE + 1)
    except FileNotFoundError:
        return None
    if len(dados) > LIMITE:
        raise ValueError("O contrato excede 512 KB. Abra o arquivo no seu editor para revisá-lo.")
    try:
        dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Salve o AGENTS.md em UTF-8 antes de editar pela central.") from None
    intervalos = [_intervalo(dados, a, b) for a, b in ((INICIO, FIM), (LINKS_INICIO, LINKS_FIM))]
    if all(intervalos) and max(i[0] for i in intervalos) < min(i[1] for i in intervalos):
        raise ValueError("Os delimitadores das orientações estão sobrepostos. Revise o AGENTS.md.")
    return dados


def _intervalo(dados: bytes, inicio: bytes, fim: bytes) -> tuple[int, int] | None:
    if inicio not in dados and fim not in dados:
        return None
    if dados.count(inicio) != 1 or dados.count(fim) != 1:
        raise ValueError("Os delimitadores das orientações estão inválidos. Revise o AGENTS.md antes de salvar.")
    a, b = dados.index(inicio), dados.index(fim)
    if b < a:
        raise ValueError("Os delimitadores das orientações estão fora de ordem.")
    return a, b + len(fim)


def fontes(painel, area: str | None = None) -> list[tuple[str, object]]:
    """Notas anteriores são vinculadas na central; seu texto não é copiado."""
    saida = []
    for nota in painel.indice.notas.values():
        if nota.rel.casefold() == "preferencias.md":
            caminho_no_vault(painel.vault, nota.caminho)
            saida.append(("", nota))
    modulos = [painel.modulo(area)] if area else painel.indice.modulos.values()
    for modulo in modulos:
        for nota in painel.indice.notas_em(modulo.id, "humano"):
            caminho_no_vault(painel.vault, nota.caminho)
            saida.append((modulo.id, nota))
    return sorted(saida, key=lambda par: (par[0], par[1].rel.casefold(), par[1].rel))


def contexto(painel) -> dict:
    dados = _ler(painel)
    bruto = dados or b""
    intervalo = _intervalo(bruto, INICIO, FIM)
    _intervalo(bruto, LINKS_INICIO, LINKS_FIM)
    conteudo = bruto[intervalo[0] + len(INICIO):intervalo[1] - len(FIM)] if intervalo else b""
    if conteudo.startswith(b"\r\n"):
        conteudo = conteudo[2:]
    elif conteudo.startswith(b"\n"):
        conteudo = conteudo[1:]
    if conteudo.endswith(b"\r\n"):
        conteudo = conteudo[:-2]
    elif conteudo.endswith(b"\n"):
        conteudo = conteudo[:-1]
    texto = conteudo.decode("utf-8")
    versao = armazenamento.versao(dados) if dados is not None else "ausente"
    anteriores = fontes(painel)
    geral = next((nota for area, nota in anteriores if not area), None) if not intervalo else None
    return {"texto": geral.corpo if geral else texto, "versao": versao,
            "geral_versao": geral.versao if geral else versao, "geral_rel": geral.rel if geral else "",
            "contrato": bruto.decode("utf-8-sig"),
            "fontes": [{"area": area, "nome_area": painel.modulo(area).nome if area else "Geral",
                        "rel": nota.rel, "titulo": nota.titulo, "texto": nota.corpo, "versao": nota.versao}
                       for area, nota in anteriores if nota is not geral]}


def _substituir(dados: bytes, inicio: bytes, fim: bytes, conteudo: bytes) -> bytes:
    intervalo = _intervalo(dados, inicio, fim)
    bloco = inicio + b"\n" + conteudo + b"\n" + fim
    if intervalo:
        return dados[:intervalo[0]] + bloco + dados[intervalo[1]:]
    separador = b"" if not dados else b"\n" if dados.endswith(b"\n") else b"\n\n"
    return dados + separador + bloco + b"\n"


def salvar(painel, texto: str, versao: str) -> dict:
    if len(texto.encode("utf-8")) > 100_000 or any(m.decode() in texto for m in MARCADORES):
        raise ValueError("Use até 100 KB de texto, sem os delimitadores internos do aplicativo.")
    caminho = caminho_no_vault(painel.vault, ARQUIVO)
    with painel._trava, armazenamento.trava(caminho):
        anterior = _ler(painel)
        atual = armazenamento.versao(anterior) if anterior is not None else "ausente"
        if versao != atual:
            raise armazenamento.ConflitoDeEscrita("As instruções mudaram em outra janela. Reabra a central; seu texto continua nesta tela.")
        dados = anterior if anterior is not None else "# Instruções deste vault\n".encode("utf-8")
        # Só o bloco explicitamente editado na central pode ser substituído.
        dados = _substituir(dados, INICIO, FIM, texto.encode("utf-8"))
        links = ["## Orientações existentes vinculadas", "",
                 "Estas notas fazem parte da central. Leia o contexto geral e o da área em que vai trabalhar; preserve os textos originais.", ""]
        for area, nota in fontes(painel):
            nome = painel.modulo(area).nome if area else "Geral"
            links.append(f"- {nome}: [{quote(nota.rel, safe='/')}](./{quote(nota.rel, safe='/')})")
        dados = _substituir(dados, LINKS_INICIO, LINKS_FIM, "\n".join(links).encode("utf-8"))
        if len(dados) > LIMITE:
            raise ValueError("O contrato excederia 512 KB. Reduza as orientações antes de salvar.")
        armazenamento.gravar_bytes(caminho, dados, esperado=anterior, validar=lambda: caminho_no_vault(painel.vault, ARQUIVO))
    painel.apos_escrita(caminho, "painel")
    return {"versao": armazenamento.versao(dados)}


def salvar_fonte(painel, rel: str, texto: str, versao: str) -> dict:
    with painel._trava:
        if rel not in {nota.rel for _, nota in fontes(painel)}:
            raise ValueError("Esta nota não faz parte das orientações existentes da central.")
        nota = painel.editar_nota(rel, versao, corpo=texto)
        return {"versao": nota.versao}
