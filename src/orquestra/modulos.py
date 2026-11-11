"""Módulos: cada pasta do vault com um `_modulo.yaml` vira uma área do painel.

O `_modulo.yaml` é o contrato do módulo: quais campos as notas têm (schema),
como elas aparecem (visões), o que conta como concluído, o que espera uma decisão
humana e quais coletores alimentam a pasta. Como é só um arquivo no vault, criar
um módulo novo não exige mexer no código: basta criar a pasta e o YAML.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orquestra.config import ler_yaml

TIPOS_DE_CAMPO = {"texto", "escolha", "data", "lista", "numero", "booleano", "link", "imagem"}
ARQUIVO_MODULO = "_modulo.yaml"


class ValorInvalido(ValueError):
    """Um valor não respeita o schema do módulo."""


@dataclass
class Campo:
    nome: str
    tipo: str = "texto"
    opcoes: list[str] = field(default_factory=list)
    padrao: Any = None
    obrigatorio: bool = False
    rotulo: str = ""


@dataclass
class Visao:
    tipo: str  # kanban | tabela
    nome: str
    agrupar_por: str = "status"
    colunas: list[str] = field(default_factory=list)


@dataclass
class Acao:
    """Botão de ação rápida na fila Decidir: aplica valores a campos da nota."""

    rotulo: str
    definir: dict[str, Any]
    estilo: str = ""  # "principal" | "discreto"


@dataclass
class ColetorDef:
    script: str
    nome: str
    ativo: bool = False
    a_cada: str | None = None  # ex.: "6h", "30m", "1d"
    diario_as: str | None = None  # ex.: "07:00"
    config: dict[str, Any] = field(default_factory=dict)
    requer: list[str] = field(default_factory=list)  # chaves de API esperadas no .env


@dataclass
class Modulo:
    id: str
    pasta: Path
    nome: str
    descricao: str = ""
    icone: str = "pasta"
    capa: Any = None
    ordem: int = 100
    campos: dict[str, Campo] = field(default_factory=dict)
    visoes: list[Visao] = field(default_factory=list)
    campo_status: str = "status"
    campo_data: str | None = None
    concluidos: list[str] = field(default_factory=list)
    decidir: list[str] = field(default_factory=list)
    acoes: list[Acao] = field(default_factory=list)
    coletores: list[ColetorDef] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def pasta_itens(self) -> Path:
        return self.pasta / "itens"


def rotulo(valor: Any) -> str:
    """'a_fazer' -> 'A fazer'. Usado para mostrar opções e nomes de campos."""
    texto = str(valor).replace("_", " ").strip()
    return texto[:1].upper() + texto[1:] if texto else ""


def _lista(valor: Any) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return [str(v) for v in valor]
    return [str(valor)]


def carregar_modulo(pasta: Path) -> Modulo:
    """Lê o `_modulo.yaml` de uma pasta. É tolerante: problemas viram avisos."""
    avisos: list[str] = []
    try:
        bruto = ler_yaml(pasta / ARQUIVO_MODULO)
    except Exception as e:
        bruto = {}
        avisos.append("Não consegui ler o _modulo.yaml: " + str(e).strip().splitlines()[0])

    m = Modulo(id=pasta.name, pasta=pasta, nome=str(bruto.get("nome") or rotulo(pasta.name)))
    m.descricao = str(bruto.get("descricao") or "")
    m.icone = str(bruto.get("icone") or "pasta")
    m.capa = bruto.get("capa")
    try:
        m.ordem = int(bruto.get("ordem", 100))
    except (TypeError, ValueError):
        avisos.append("'ordem' precisa ser um número.")

    # ---- campos (schema)
    for nome, definicao in (bruto.get("campos") or {}).items():
        d = definicao if isinstance(definicao, dict) else {"tipo": definicao}
        tipo = str(d.get("tipo") or "texto")
        if tipo not in TIPOS_DE_CAMPO:
            avisos.append(f"Campo '{nome}': tipo '{tipo}' não existe; tratei como texto.")
            tipo = "texto"
        campo = Campo(
            nome=str(nome),
            tipo=tipo,
            opcoes=_lista(d.get("opcoes")),
            padrao=d.get("padrao"),
            obrigatorio=bool(d.get("obrigatorio", False)),
            rotulo=str(d.get("rotulo") or rotulo(nome)),
        )
        if tipo == "escolha" and not campo.opcoes:
            avisos.append(f"Campo '{nome}' é do tipo escolha, mas não tem 'opcoes'.")
        m.campos[campo.nome] = campo

    # ---- regras de status
    regras = bruto.get("status") if isinstance(bruto.get("status"), dict) else {}
    m.campo_status = str(regras.get("campo") or "status")
    m.concluidos = _lista(regras.get("concluidos"))
    m.decidir = _lista(regras.get("decidir"))
    for a in regras.get("acoes") or []:
        if isinstance(a, dict) and a.get("rotulo") and isinstance(a.get("definir"), dict):
            m.acoes.append(Acao(str(a["rotulo"]), dict(a["definir"]), str(a.get("estilo") or "")))

    campo_data = bruto.get("campo_data")
    if campo_data:
        m.campo_data = str(campo_data)
    elif "data" in m.campos and m.campos["data"].tipo == "data":
        m.campo_data = "data"

    # ---- visões
    for v in bruto.get("visoes") or []:
        if not isinstance(v, dict):
            continue
        tipo = str(v.get("tipo") or "tabela")
        if tipo not in ("kanban", "tabela"):
            avisos.append(f"Visão '{tipo}' não existe; use kanban ou tabela.")
            continue
        m.visoes.append(
            Visao(
                tipo=tipo,
                nome=str(v.get("nome") or rotulo(tipo)),
                agrupar_por=str(v.get("agrupar_por") or m.campo_status),
                colunas=_lista(v.get("colunas")),
            )
        )
    if not m.visoes:
        if m.campo_status in m.campos and m.campos[m.campo_status].opcoes:
            m.visoes.append(Visao("kanban", "Quadro", m.campo_status))
        m.visoes.append(Visao("tabela", "Lista"))

    # ---- coletores
    for c in bruto.get("coletores") or []:
        if not isinstance(c, dict) or not c.get("script"):
            continue
        script = str(c["script"])
        m.coletores.append(
            ColetorDef(
                script=script,
                nome=str(c.get("nome") or rotulo(Path(script).stem)),
                ativo=bool(c.get("ativo", False)),
                a_cada=str(c["a_cada"]) if c.get("a_cada") else None,
                diario_as=str(c["diario_as"]) if c.get("diario_as") else None,
                config=dict(c.get("config") or {}),
                requer=_lista(c.get("requer")),
            )
        )

    m.avisos = avisos
    return m


def descobrir(vault: Path) -> dict[str, Modulo]:
    """Procura módulos: pastas na raiz do vault que tenham um `_modulo.yaml`."""
    encontrados = []
    for pasta in sorted(vault.iterdir()):
        if pasta.is_dir() and not pasta.name.startswith((".", "_")) and (pasta / ARQUIVO_MODULO).is_file():
            encontrados.append(carregar_modulo(pasta))
    encontrados.sort(key=lambda m: (m.ordem, m.nome.lower()))
    return {m.id: m for m in encontrados}


# ---------------------------------------------------------------- valores


def converter(campo: Campo, valor: Any) -> Any:
    """Converte um valor vindo do painel para o tipo do campo.

    Devolve None quando o valor está vazio (o campo é removido do frontmatter).
    Levanta ValorInvalido com uma mensagem em português quando não dá para converter.
    """
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.strip()
        if valor == "" and campo.tipo != "lista":
            return None

    if campo.tipo == "escolha":
        valor = str(valor)
        if campo.opcoes and valor not in campo.opcoes:
            raise ValorInvalido(
                f"'{valor}' não é uma opção de {campo.rotulo}. Opções: {', '.join(campo.opcoes)}."
            )
        return valor

    if campo.tipo == "data":
        if isinstance(valor, dt.datetime):
            return valor.date()
        if isinstance(valor, dt.date):
            return valor
        if str(valor) == "hoje":
            return dt.date.today()
        try:
            return dt.date.fromisoformat(str(valor)[:10])
        except ValueError:
            raise ValorInvalido(f"{campo.rotulo}: use uma data no formato AAAA-MM-DD.") from None

    if campo.tipo == "lista":
        if isinstance(valor, str):
            itens = [p.strip() for p in valor.split(",")]
        elif isinstance(valor, (list, tuple)):
            itens = [str(p).strip() for p in valor]
        else:
            itens = [str(valor)]
        itens = [i for i in itens if i]
        return itens or None

    if campo.tipo == "numero":
        try:
            numero = float(str(valor).replace(",", "."))
        except ValueError:
            raise ValorInvalido(f"{campo.rotulo}: precisa ser um número.") from None
        return int(numero) if numero.is_integer() else numero

    if campo.tipo == "booleano":
        if isinstance(valor, bool):
            return valor
        return str(valor).lower() in ("1", "true", "sim", "verdadeiro", "on")

    return str(valor)


def padroes(modulo: Modulo) -> dict[str, Any]:
    """Valores iniciais de uma nota nova, segundo o schema."""
    valores: dict[str, Any] = {}
    for campo in modulo.campos.values():
        if campo.padrao is None:
            continue
        try:
            valor = converter(campo, campo.padrao)
        except ValorInvalido:
            continue
        if valor is not None:
            valores[campo.nome] = valor
    return valores


def validar(modulo: Modulo, meta: dict[str, Any]) -> list[str]:
    """Confere o frontmatter de uma nota contra o schema. Devolve avisos em português.

    Campos que não estão no schema são permitidos: o usuário pode acrescentar o que
    quiser pelo Obsidian sem quebrar nada.
    """
    problemas: list[str] = []
    for campo in modulo.campos.values():
        valor = meta.get(campo.nome)
        vazio = valor is None or valor == "" or valor == []
        if vazio:
            if campo.obrigatorio:
                problemas.append(f"Falta o campo obrigatório '{campo.nome}'.")
            continue
        if campo.tipo == "escolha" and campo.opcoes and str(valor) not in campo.opcoes:
            problemas.append(
                f"'{campo.nome}: {valor}' não está nas opções ({', '.join(campo.opcoes)})."
            )
        elif campo.tipo == "data" and not isinstance(valor, dt.date):
            try:
                dt.date.fromisoformat(str(valor)[:10])
            except ValueError:
                problemas.append(f"'{campo.nome}: {valor}' não é uma data AAAA-MM-DD.")
        elif campo.tipo == "lista" and not isinstance(valor, (list, tuple)):
            problemas.append(f"'{campo.nome}' deveria ser uma lista.")
        elif campo.tipo == "numero" and (isinstance(valor, bool) or not isinstance(valor, (int, float))):
            problemas.append(f"'{campo.nome}: {valor}' deveria ser um número.")
    return problemas
