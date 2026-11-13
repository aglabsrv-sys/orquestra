"""O conector compartilha a navegação do painel sem expor caminhos reservados."""

from __future__ import annotations

import json

import pytest

from orquestra.caminhos import CaminhoInseguro
from orquestra.mcp_contexto import conexoes_nota
from orquestra.mcp_servidor import ErroDeFerramenta, Ferramentas


def arquivo(vault, rel, texto=""):
    destino = vault / rel
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return destino


def consultar(ferramentas, caminho, limite=30):
    ferramentas._em_dia()
    return conexoes_nota(ferramentas, caminho, limite)


def test_conexoes_preservam_estados_wiki_markdown_ancoras_e_arquivo(vault):
    fonte = arquivo(vault, "Pasta/Fonte.md", """# Aqui

[[#Aqui]]
[[Alvo#Seção]]
[outra](../Outra/Alvo.md#Ausente)
[[Futura]]
![[sumiu.png]]
[[Repetida]]
[[tarefas/arquivo/Antiga.md]]
`[[Ignorada]]` e [web](https://exemplo.test)
""")
    arquivo(vault, "Outra/Alvo.md", "# Seção\n")
    arquivo(vault, "Um/Repetida.md")
    arquivo(vault, "Dois/Repetida.md")
    arquivo(vault, "tarefas/arquivo/Antiga.md", "[[Pasta/Fonte]]\n[[Fonte#Ausente]]")
    arquivo(vault, "Outra/Origem.md", "[fonte](../Pasta/Fonte.md#Aqui)\n[[Fonte]]")
    antes = fonte.read_bytes()
    resultado = consultar(Ferramentas(vault), "Pasta/Fonte.md")
    saidas = resultado["saidas"]
    assert saidas["total"] == 7 and not saidas["limitado"]
    assert [item["estado"] for item in saidas["itens"]] == [
        "valido", "valido", "ancora_ausente", "futuro", "ausente", "ambiguo", "valido",
    ]
    assert saidas["itens"][2]["tipo"] == "markdown"
    assert saidas["itens"][2]["caminho"] == "Outra/Alvo.md"
    assert saidas["itens"][4]["embutido"]
    assert saidas["itens"][5]["candidatos"] == ["Dois/Repetida.md", "Um/Repetida.md"]
    entradas = resultado["entradas"]
    assert entradas["total"] == 2 and not entradas["limitado"]
    assert [(item["caminho"], item["ocorrencias"]) for item in entradas["itens"]] == [
        ("Outra/Origem.md", 2), ("tarefas/arquivo/Antiga.md", 2),
    ]
    assert entradas["itens"][0]["linhas"] == [1, 2]
    assert fonte.read_bytes() == antes


def test_conexoes_ocultam_destinos_reservados_e_nao_incluem_fontes_ocultas(vault):
    arquivo(vault, "Origem.md", """[[AGENTS.md]]
[[AGENTS.orquestra.md]]
[privado](.env)
[estado](_orquestra/estado.json)
[editor](.obsidian/workspace.json)
[fora](../privado-fora.md)
""")
    arquivo(vault, "AGENTS.orquestra.md", "[[Origem]]")
    arquivo(vault, ".oculto/Fonte.md", "[[Origem]]")
    arquivo(vault, "_orquestra/Fonte.md", "[[Origem]]")
    arquivo(vault, "Leitor.md", "[[Origem]]")
    ferramentas = Ferramentas(vault)
    resultado = consultar(ferramentas, "Origem.md")
    assert resultado["saidas"]["total"] == 6
    for item in resultado["saidas"]["itens"]:
        assert item["estado"] == "bloqueado"
        assert set(item) == {"estado", "linha", "tipo", "embutido"}
    assert [item["caminho"] for item in resultado["entradas"]["itens"]] == ["Leitor.md"]
    serializado = json.dumps(resultado, ensure_ascii=False)
    for reservado in (".env", "_orquestra", ".obsidian", "AGENTS.md", "AGENTS.orquestra.md", "privado-fora"):
        assert reservado not in serializado
    with pytest.raises(ErroDeFerramenta, match="reservado"):
        consultar(ferramentas, "AGENTS.md")


def test_limites_preservam_totais_e_ordem_das_duas_direcoes(vault):
    arquivo(vault, "Central.md", "\n".join(f"[[Futura{i}]]" for i in range(5)))
    for nome in ("Z", "A", "M"):
        arquivo(vault, f"{nome}.md", "[[Central]]\n[[Central]]\n[[Central]]")
    resultado = consultar(Ferramentas(vault), "Central.md", limite=1)
    assert resultado["saidas"]["total"] == 5 and resultado["saidas"]["limitado"]
    assert resultado["saidas"]["itens"][0]["alvo"] == "Futura0"
    assert resultado["entradas"]["total"] == 3 and resultado["entradas"]["limitado"]
    entrada = resultado["entradas"]["itens"][0]
    assert entrada["caminho"] == "A.md"
    assert entrada["ocorrencias"] == 3 and entrada["linhas"] == [1] and entrada["linhas_limitadas"]


def test_nova_consulta_revalida_edicoes_externas_e_ambiguidade(vault):
    arquivo(vault, "Origem.md", "[[Alvo#Seção]]")
    ferramentas = Ferramentas(vault)
    assert consultar(ferramentas, "Origem.md")["saidas"]["itens"][0]["estado"] == "futuro"
    alvo = arquivo(vault, "Alvo.md", "# Seção")
    assert consultar(ferramentas, "Origem.md")["saidas"]["itens"][0]["estado"] == "valido"
    alvo.write_text("# Outra seção", encoding="utf-8")
    assert consultar(ferramentas, "Origem.md")["saidas"]["itens"][0]["estado"] == "ancora_ausente"
    alvo.unlink()
    assert consultar(ferramentas, "Origem.md")["saidas"]["itens"][0]["estado"] == "futuro"


def test_destino_e_fonte_substituidos_por_links_nao_vazam_do_cache(vault, monkeypatch):
    from orquestra import mcp_contexto, vinculos

    arquivo(vault, "Origem.md", "[[Alvo]]")
    arquivo(vault, "Alvo.md")
    arquivo(vault, "Leitor.md", "[[Origem]]")
    ferramentas = Ferramentas(vault)
    assert consultar(ferramentas, "Origem.md")["saidas"]["itens"][0]["estado"] == "valido"
    validar = vinculos.caminho_no_vault

    def bloqueado(raiz, caminho):
        if str(caminho) in {"Alvo", "Alvo.md", "Leitor.md"}:
            raise CaminhoInseguro("Substituído por link depois da indexação.")
        return validar(raiz, caminho)

    monkeypatch.setattr(vinculos, "caminho_no_vault", bloqueado)
    monkeypatch.setattr(mcp_contexto, "caminho_no_vault", bloqueado)
    resultado = conexoes_nota(ferramentas, "Origem.md")
    assert resultado["saidas"]["itens"][0]["estado"] == "bloqueado"
    assert "alvo" not in resultado["saidas"]["itens"][0]
    assert resultado["entradas"]["total"] == 0
