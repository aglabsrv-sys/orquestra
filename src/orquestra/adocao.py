"""Adoção: transformar uma pasta que já existe em um módulo do painel.

Quem chega com um vault do Obsidian já tem suas pastas e seu jeito de anotar. Em
vez de pedir que a pessoa mude tudo de lugar, o painel olha as notas da pasta,
descobre quais campos elas usam no frontmatter e escreve um `_modulo.yaml` que
descreve o que já está lá. As notas não são tocadas: o único arquivo criado é o
`_modulo.yaml`, com `itens: .` (os registros são as notas da própria pasta).

Também mora aqui o reconhecimento do estilo de organização do vault (PARA,
Zettelkasten, Johnny Decimal...), usado na tela de boas-vindas.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from pathlib import Path
from typing import Any

from orquestra.config import gravar_yaml
from orquestra import armazenamento
from orquestra.caminhos import CaminhoInseguro, arquivos_do_vault, caminho_no_vault
from orquestra.modulos import ARQUIVO_DESLIGADO, ARQUIVO_MODULO, NOTAS_DE_CONTRATO, ZONAS, rotulo
from orquestra.notas import ler_nota, simples

LIMITE_DA_AMOSTRA = 80
PASTAS_PULADAS = {".git", ".obsidian", ".trash", "__pycache__", "node_modules", ".venv"}

# Chaves do frontmatter que não viram campo do módulo.
CHAVES_IGNORADAS = {
    "titulo", "title", "aliases", "alias", "cssclass", "cssclasses", "publish", "permalink",
    "id_externo", "coletor", "coletado_em", "criado_em", "pergunta", "resposta", "position",
}
NOMES_DE_STATUS = ["status", "estado", "situacao", "situação", "state", "stage", "etapa", "fase"]
NOMES_DE_DATA = ["data", "date", "due", "prazo", "vencimento", "deadline", "scheduled", "quando", "dia", "entrega"]
PALAVRAS_DE_CONCLUIDO = {
    "feito", "feita", "concluido", "concluida", "finalizado", "finalizada", "completo", "completa",
    "done", "complete", "completed", "finished", "closed", "fechado", "fechada", "publicado",
    "publicada", "arquivado", "arquivada", "archived", "cancelado", "cancelada", "cancelled", "canceled",
    "entregue", "pago", "paga", "lido", "lida", "visto", "vista",
}
ICONES_POR_PALAVRA = [
    (("tarefa", "todo", "task", "afazer"), "check"),
    (("projet", "project", "esforc", "effort"), "raio"),
    (("area", "space", "espac"), "casa"),
    (("recurso", "resource", "referenc", "source", "fonte", "leitura", "livro", "book", "biblioteca"), "livro"),
    (("arquiv", "archive"), "caixa"),
    (("diario", "daily", "journal", "calend", "agenda"), "calendario"),
    (("pessoa", "people", "contato", "contact", "cliente", "client", "crm"), "pessoas"),
    (("finan", "money", "dinheiro", "conta", "orcamento"), "moeda"),
    (("ideia", "idea", "insight"), "lampada"),
    (("inbox", "entrada", "captura"), "entrada"),
    (("video", "conteudo", "content", "post"), "video"),
    (("estudo", "study", "curso", "course", "aula"), "livro"),
    (("meta", "goal", "objetivo", "okr"), "estrela"),
    (("numero", "metric", "kpi", "dado"), "grafico"),
]

_DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_PREFIXO_NUMERICO = re.compile(r"^[\d\s.\-–_]+(?=\D)")


def sem_acento(texto: str) -> str:
    bruto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in bruto if not unicodedata.combining(c)).lower()


def nome_legivel(pasta: str) -> str:
    """'1. Projetos' -> 'Projetos'; '10-19 Finanças' -> 'Finanças'; 'meus_estudos' -> 'Meus estudos'."""
    limpo = _PREFIXO_NUMERICO.sub("", pasta).strip() or pasta
    return rotulo(limpo.replace("-", " "))


def icone_para(pasta: str) -> str:
    alvo = sem_acento(pasta)
    for palavras, icone in ICONES_POR_PALAVRA:
        if any(p in alvo for p in palavras):
            return icone
    return "nota"


# ---------------------------------------------------------------- amostra


def notas_da_pasta(pasta: Path, limite: int = LIMITE_DA_AMOSTRA) -> list[Path]:
    """Notas que seriam itens do módulo: tudo na pasta, menos humano/, maquina/ e arquivo/."""
    achadas: list[Path] = []
    for rel, caminho, _info in arquivos_do_vault(pasta):
        if rel.split("/", 1)[0] in ZONAS:
            continue
        if caminho.suffix.lower() == ".md" and caminho.name.lower() not in NOTAS_DE_CONTRATO:
            achadas.append(caminho)
            if len(achadas) >= limite:
                break
    # Mantém a amostra limitada, mas a primeira aparição de campos e opções não
    # pode depender da ordem de enumeração do filesystem. Só ordena as notas
    # selecionadas; não amplia a varredura para montar um inventário completo.
    achadas.sort(key=lambda caminho: (caminho.relative_to(pasta).as_posix().casefold(), caminho.relative_to(pasta).as_posix()))
    return achadas


def _tipo_de(chave: str, valores: list[Any]) -> tuple[str, list[str]]:
    """Adivinha o tipo de um campo a partir dos valores encontrados. Devolve (tipo, opções)."""
    if any(isinstance(v, (list, tuple)) for v in valores):
        return "lista", []
    if all(isinstance(v, bool) for v in valores):
        return "booleano", []
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in valores):
        return "numero", []
    textos = [str(v).strip() for v in valores]
    if all(_DATA_ISO.match(t) for t in textos):
        return "data", []
    if all(t.lower().startswith(("http://", "https://")) for t in textos):
        return "link", []
    distintos = list(dict.fromkeys(textos))
    curto = all(len(t) <= 32 and "\n" not in t for t in distintos)
    e_status = sem_acento(chave) in {sem_acento(n) for n in NOMES_DE_STATUS}
    repetem = len(textos) >= 2 * len(distintos)
    if curto and len(distintos) <= 9 and (e_status or (repetem and len(textos) >= 3)):
        return "escolha", distintos
    return "texto", []


def inferir(pasta: Path, com_quadro: bool = False) -> dict[str, Any]:
    """Olha as notas da pasta e monta a definição do módulo (o conteúdo do _modulo.yaml)."""
    valores: dict[str, list[Any]] = {}
    arquivos = notas_da_pasta(pasta)
    for arquivo in arquivos:
        try:
            nota = ler_nota(arquivo, pasta)
        except OSError:
            continue
        for chave, valor in nota.meta.items():
            chave = str(chave)
            valor = simples(valor)
            if chave.lower() in CHAVES_IGNORADAS or valor in (None, "", []) or isinstance(valor, dict):
                continue
            valores.setdefault(chave, []).append(valor)

    # Um campo entra no schema se aparece em mais de uma nota (ou se a pasta é pequena).
    minimo = 1 if len(arquivos) < 5 else 2
    campos: dict[str, dict[str, Any]] = {}
    for chave, achados in valores.items():
        if len(achados) < minimo:
            continue
        tipo, opcoes = _tipo_de(chave, achados)
        campos[chave] = {"tipo": tipo, **({"opcoes": opcoes} if opcoes else {})}

    nomes = {sem_acento(c): c for c in campos}
    campo_status = next(
        (nomes[sem_acento(n)] for n in NOMES_DE_STATUS if sem_acento(n) in nomes and campos[nomes[sem_acento(n)]]["tipo"] == "escolha"),
        None,
    )
    if campo_status is None and com_quadro:
        campo_status = "status" if "status" not in campos else "andamento"
        campos = {campo_status: {"tipo": "escolha", "opcoes": ["a_fazer", "fazendo", "feito"], "padrao": "a_fazer"}, **campos}
    campo_data = next(
        (nomes[sem_acento(n)] for n in NOMES_DE_DATA if sem_acento(n) in nomes and campos[nomes[sem_acento(n)]]["tipo"] == "data"),
        None,
    )
    if "origem" not in campos:
        campos["origem"] = {"tipo": "escolha", "opcoes": ["humano", "agente", "coletor"], "padrao": "humano"}

    definicao: dict[str, Any] = {
        "nome": nome_legivel(pasta.name),
        "descricao": "",
        "icone": icone_para(pasta.name),
        "itens": ".",
        "campos": campos,
    }
    if campo_data:
        definicao["campo_data"] = campo_data
    visoes: list[dict[str, Any]] = []
    if campo_status:
        opcoes = campos[campo_status].get("opcoes", [])
        definicao["status"] = {
            "campo": campo_status,
            "concluidos": [o for o in opcoes if sem_acento(o).replace("_", " ").split(" ")[0] in PALAVRAS_DE_CONCLUIDO],
            "decidir": [],
        }
        visoes.append({"tipo": "kanban", "nome": "Quadro", "agrupar_por": campo_status})
    colunas = ["titulo", *[c for c in campos if c != "origem"][:5]]
    visoes.append({"tipo": "tabela", "nome": "Lista", "colunas": colunas})
    definicao["visoes"] = visoes
    return definicao


def resumo_da_pasta(pasta: Path) -> dict[str, Any]:
    """O que o painel entendeu da pasta, para mostrar antes de adotar."""
    d = inferir(pasta)
    return {
        "nome": d["nome"],
        "icone": d["icone"],
        "campos": [{"nome": n, "tipo": c["tipo"], "opcoes": c.get("opcoes", [])} for n, c in d["campos"].items() if n != "origem"],
        "tem_status": "status" in d,
        "campo_data": d.get("campo_data"),
    }


# ---------------------------------------------------------------- adotar / desligar

CABECALHO = """\
# Módulo criado pelo Orquestra a partir de uma pasta que já existia.
# Nenhuma nota foi alterada: este arquivo só descreve o que o painel encontrou.
#   itens: .   quer dizer que os registros são as notas desta própria pasta
#              (e das subpastas, menos humano/, maquina/ e arquivo/).
# Ajuste à vontade, aqui ou em "Personalizar" no painel. Tipos de campo:
# texto, escolha, data, lista, numero, booleano, link, imagem.

"""


class NaoPodeAdotar(Exception):
    """A pasta não pode virar módulo; a mensagem explica por quê."""


def _pasta_da_raiz(vault: Path, nome: str) -> Path:
    nome = nome.strip().strip("/\\")
    if not nome or "/" in nome or "\\" in nome or nome.startswith((".", "_")) or nome == "diario":
        raise NaoPodeAdotar("Só pastas da raiz do vault podem virar área do painel (e não as que começam com . ou _).")
    try:
        pasta = caminho_no_vault(vault, nome)
    except CaminhoInseguro as erro:
        raise NaoPodeAdotar(str(erro)) from None
    if not pasta.is_dir():
        raise NaoPodeAdotar(f"A pasta '{nome}' não existe.")
    return pasta


def adotar(vault: Path, nome_pasta: str, com_quadro: bool = False) -> Path:
    """Escreve o `_modulo.yaml` de uma pasta da raiz. Se ela já foi módulo, religa o antigo."""
    pasta = _pasta_da_raiz(vault, nome_pasta)
    destino = caminho_no_vault(vault, pasta / ARQUIVO_MODULO)
    if destino.exists():
        return destino
    desligado = caminho_no_vault(vault, pasta / ARQUIVO_DESLIGADO)
    if desligado.exists():
        armazenamento.mover_seguro(desligado, destino, esperado=desligado.read_bytes(),
                                   validar=lambda: (caminho_no_vault(vault, desligado), caminho_no_vault(vault, destino)))
        return destino
    with armazenamento.trava(destino):
        gravar_yaml(destino, inferir(pasta, com_quadro))
        armazenamento.atualizar_bytes(destino, lambda bruto: (CABECALHO + f"# Adotado em {dt.date.today().isoformat()}.\n\n").encode("utf-8") + bruto,
                                      validar=lambda: caminho_no_vault(vault, destino))
    return destino


def desligar(vault: Path, modulo_id: str) -> None:
    """Tira o módulo do painel sem apagar nada: só renomeia o `_modulo.yaml`."""
    pasta = _pasta_da_raiz(vault, modulo_id)
    atual = caminho_no_vault(vault, pasta / ARQUIVO_MODULO)
    if atual.exists():
        destino = caminho_no_vault(vault, pasta / ARQUIVO_DESLIGADO)
        armazenamento.mover_seguro(atual, destino, esperado=atual.read_bytes(),
                                   validar=lambda: (caminho_no_vault(vault, atual), caminho_no_vault(vault, destino)))


# ---------------------------------------------------------------- estilo do vault

ESTILOS = {
    "para": ("PARA", "Projetos, Áreas, Recursos e Arquivo. Cada pasta pode virar uma área do painel."),
    "ace": ("ACE (Atlas, Calendar, Efforts)", "Mapas, calendário e esforços. Efforts e Calendar costumam virar boas áreas."),
    "johnny": ("Johnny Decimal", "Pastas numeradas por categoria (10-19, 20-29...)."),
    "zettel": ("Zettelkasten", "Notas pequenas e ligadas entre si, com pouca hierarquia de pastas."),
    "diario": ("Diário", "Quase tudo gira em torno de notas diárias."),
    "livre": ("Organização própria", "Pastas do seu jeito. Escolha quais quer ver no painel."),
    "vazio": ("Pasta vazia", "Ainda não há notas aqui."),
}


def detectar_estilo(pastas: list[str], nomes_de_notas: list[str]) -> str:
    """Reconhece os jeitos mais comuns de organizar um vault pelo nome das pastas e notas."""
    if not pastas and not nomes_de_notas:
        return "vazio"
    limpas = [sem_acento(_PREFIXO_NUMERICO.sub("", p).strip() or p) for p in pastas]

    def tem(*palavras: str) -> bool:
        return any(any(nome.startswith(p) for p in palavras) for nome in limpas)

    if sum([tem("projet", "project"), tem("area"), tem("recurso", "resource"), tem("arquiv", "archive")]) >= 3:
        return "para"
    if sum(tem(p) for p in ("atlas", "calendar", "cards", "effort", "extras", "sources", "spaces")) >= 3:
        return "ace"
    if sum(1 for p in pastas if re.match(r"^\d0\s?[-–]\s?\d9\b", p)) >= 2:
        return "johnny"
    if nomes_de_notas:
        zettels = sum(1 for n in nomes_de_notas if re.match(r"^\d{12,14}", n))
        diarias = sum(1 for n in nomes_de_notas if re.fullmatch(r"\d{4}-\d{2}-\d{2}", n))
        if zettels / len(nomes_de_notas) > 0.3 or tem("zettel", "permanent", "fleeting", "literature"):
            return "zettel"
        if diarias / len(nomes_de_notas) > 0.5:
            return "diario"
    return "livre"
