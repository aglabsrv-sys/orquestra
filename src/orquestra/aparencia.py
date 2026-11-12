"""Aparência: o que a pessoa escolhe por cima do tema.

O tema (tema.yaml) define as cores e as capas. A aparência são quatro escolhas
pessoais, guardadas em `aparencia:` no orquestra.yaml:

    modo      escuro | claro | auto (segue o sistema)
    destaque  uma cor em hexadecimal; vazio usa a do tema
    cantos    reto | discreto | medio | redondo
    fonte     sistema | serifada | arredondada | mono

Tudo vira variáveis de CSS escritas no topo de cada página (`estilo`). O arquivo de
estilos não sabe qual é o tema nem o modo: ele só usa as variáveis.

As fontes são as que já existem no computador de quem abre o painel. Nada é
baixado da internet: o painel funciona sem conexão.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MODOS = ["escuro", "claro", "auto"]
CANTOS = {"reto": 0.0, "discreto": 0.45, "medio": 1.0, "redondo": 1.45}
FONTES = {
    "sistema": 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
    "serifada": '"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif',
    "arredondada": 'ui-rounded, "SF Pro Rounded", "Nunito", "Segoe UI Variable Display", "Trebuchet MS", system-ui, sans-serif',
    "mono": 'ui-monospace, "Cascadia Code", "SF Mono", Consolas, "Liberation Mono", monospace',
}
NOMES = {
    "escuro": "Escuro", "claro": "Claro", "auto": "Igual ao sistema",
    "reto": "Retos", "discreto": "Discretos", "medio": "Médios", "redondo": "Redondos",
    "sistema": "Padrão", "serifada": "Serifada", "arredondada": "Arredondada", "mono": "Monoespaçada",
}
# Sugestões de cor de destaque. Qualquer outra cor também vale.
SUGESTOES = ["#f4b183", "#ff8a65", "#f2c14e", "#9bd49b", "#86e3ce", "#7cc4ff", "#c4a7ff", "#ff9ecb"]

_COR = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass
class Aparencia:
    modo: str = "escuro"
    destaque: str = ""
    cantos: str = "medio"
    fonte: str = "sistema"


def ler(bruto: Any) -> Aparencia:
    """Lê `aparencia:` do orquestra.yaml. Valor estranho vira o padrão, sem reclamar."""
    a = Aparencia()
    if not isinstance(bruto, dict):
        return a
    if str(bruto.get("modo")) in MODOS:
        a.modo = str(bruto["modo"])
    if str(bruto.get("cantos")) in CANTOS:
        a.cantos = str(bruto["cantos"])
    if str(bruto.get("fonte")) in FONTES:
        a.fonte = str(bruto["fonte"])
    if _COR.fullmatch(str(bruto.get("destaque") or "")):
        a.destaque = str(bruto["destaque"]).lower()
    return a


def validar(dados: dict[str, Any]) -> dict[str, str]:
    """Confere o que veio da tela de Ajustes. Devolve só as chaves válidas; erro vira ValueError."""
    limpo: dict[str, str] = {}
    for chave, opcoes in (("modo", MODOS), ("cantos", CANTOS), ("fonte", FONTES)):
        if chave in dados:
            if str(dados[chave]) not in opcoes:
                raise ValueError(f"'{dados[chave]}' não é uma opção de {chave}. Opções: {', '.join(opcoes)}.")
            limpo[chave] = str(dados[chave])
    if "destaque" in dados:
        cor = str(dados["destaque"] or "").strip()
        if cor and not _COR.fullmatch(cor):
            raise ValueError("A cor de destaque precisa estar no formato #rrggbb.")
        limpo["destaque"] = cor.lower()
    return limpo


# ---------------------------------------------------------------- cores


def _rgb(cor: str) -> tuple[int, int, int]:
    h = cor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    n = int(h[:6], 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def misturar(a: str, b: str, t: float) -> str:
    A, B = _rgb(a), _rgb(b)
    return "#" + "".join(f"{max(0, min(255, round(x + (y - x) * t))):02x}" for x, y in zip(A, B))


def luminancia(cor: str) -> float:
    """Luminância relativa (0 = preto, 1 = branco), como define a WCAG."""

    def canal(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _rgb(cor)
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def legivel_sobre(cor: str, fundo: str, minimo: float = 3.2) -> str:
    """Escurece ou clareia a cor, aos poucos, até ela aparecer bem em cima do fundo.

    Uma cor de destaque pastel funciona no escuro e some no claro (e vice-versa).
    Em vez de recusar a escolha da pessoa, ajustamos o tom para o modo em uso.
    """
    alvo = "#000000" if luminancia(fundo) > 0.4 else "#ffffff"
    ajustada = cor
    for passo in range(1, 13):
        if contraste(ajustada, fundo) >= minimo:
            break
        ajustada = misturar(cor, alvo, passo * 0.07)
    return ajustada


def texto_sobre(cor: str) -> str:
    """Preto ou branco: o que se lê melhor em cima de uma cor."""
    return "#1a1410" if contraste(cor, "#1a1410") >= contraste(cor, "#ffffff") else "#ffffff"


def claras_a_partir_de(escuras: dict[str, str]) -> dict[str, str]:
    """Versão clara de um tema que só definiu as cores escuras: papel levemente tingido pelo destaque."""
    tinta = escuras["destaque"]
    fundo = misturar("#faf8f5", tinta, 0.05)
    return {
        "fundo": fundo,
        "superficie": misturar("#ffffff", tinta, 0.02),
        "superficie_alta": misturar("#f1ede8", tinta, 0.07),
        "borda": misturar("#ddd6ce", tinta, 0.10),
        "texto": misturar("#1d1a17", escuras["fundo"], 0.4),
        "texto_suave": misturar("#6b635b", tinta, 0.08),
        "destaque": legivel_sobre(tinta, fundo, 3.6),
        "sobre_destaque": "#ffffff",
        "alerta": legivel_sobre(escuras["alerta"], fundo, 3.6),
        "ok": legivel_sobre(escuras["ok"], fundo, 3.6),
    }


def cores(tema: dict[str, Any], aparencia: Aparencia, claro: bool) -> dict[str, str]:
    """As cores finais de um modo: as do tema, com o destaque escolhido pela pessoa por cima."""
    base = dict(tema.get("cores_claras") or claras_a_partir_de(tema["cores"])) if claro else dict(tema["cores"])
    if aparencia.destaque:
        base["destaque"] = legivel_sobre(aparencia.destaque, base["fundo"])
    superficies = [base[chave] for chave in ("fundo", "superficie", "superficie_alta")]
    # As mesmas cores aparecem em links, ajuda, alertas e etiquetas. A paleta
    # precisa funcionar também nas superfícies elevadas e nos fundos tingidos,
    # especialmente no modo claro. Só a saída CSS muda; o tema do vault é intacto.
    for chave in ("texto", "texto_suave", "destaque", "alerta", "ok"):
        original = base[chave]
        alvo = "#000000" if claro else "#ffffff"
        for passo in range(101):
            ajustada = misturar(original, alvo, passo / 100)
            fundos = superficies
            if chave in ("destaque", "alerta", "ok"):
                fundos = [*superficies, *(misturar(fundo, ajustada, 0.20) for fundo in superficies)]
            if all(contraste(ajustada, fundo) >= 4.5 for fundo in fundos):
                break
        base[chave] = ajustada
    base["sobre_destaque"] = texto_sobre(base["destaque"])
    return base


def _variaveis(paleta: dict[str, str], claro: bool) -> str:
    partes = [f"--{nome.replace('_', '-')}:{cor}" for nome, cor in paleta.items()]
    partes.append("color-scheme:" + ("light" if claro else "dark"))
    # A sombra e o brilho de fundo pesam demais numa tela clara.
    partes.append("--sombra:" + ("rgb(60 45 30 / 0.28)" if claro else "#000"))
    partes.append("--ambiente:" + ("0.22" if claro else "0.5"))
    partes.append("--campo-borda:" + legivel_sobre(paleta["borda"], paleta["fundo"], 3.0))
    partes.append("--sobre-alerta:" + texto_sobre(paleta["alerta"]))
    return ";".join(partes)


def estilo(tema: dict[str, Any], aparencia: Aparencia) -> str:
    """O bloco de CSS do topo da página. Só entram cores em hexadecimal e valores desta lista."""
    escuro = _variaveis(cores(tema, aparencia, False), False)
    claro = _variaveis(cores(tema, aparencia, True), True)
    fixas = f"--cantos:{CANTOS[aparencia.cantos]};--fonte:{FONTES[aparencia.fonte]}"
    if aparencia.modo == "claro":
        return f":root{{{claro};{fixas}}}"
    if aparencia.modo == "auto":
        return f":root{{{escuro};{fixas}}}@media (prefers-color-scheme: light){{:root{{{claro}}}}}"
    return f":root{{{escuro};{fixas}}}"


def cor_do_navegador(tema: dict[str, Any], aparencia: Aparencia) -> str:
    """Cor da barra do navegador no celular."""
    return cores(tema, aparencia, aparencia.modo == "claro")["fundo"]
