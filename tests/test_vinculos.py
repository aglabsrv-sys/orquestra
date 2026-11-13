"""Diagnóstico e navegação usam as mesmas referências, sem alterar o cofre."""
from urllib.parse import quote

from orquestra import vinculos
from orquestra.apresentacao import render_markdown
from orquestra.caminhos import CaminhoInseguro
from orquestra.indice import Indice
from orquestra.vinculos import extrair_referencias, verificar_links


def arquivo(vault, rel, texto=""):
    caminho = vault / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def test_parser_exclui_codigo_escapes_e_urls_externas():
    fonte = r'''[[Uma|nome]] e [outra](<Pasta/Outra.md#Seção>)
![[foto.png|200]]
`[[inline]]` e \[[escapado]]
```md
[[exemplo]]
[exemplo](inexistente.md)
```
    [[indentado]]

[web](https://exemplo.test) e ![remota](https://exemplo.test/a.png)
[[#Aqui]]
'''
    refs = extrair_referencias(fonte)
    assert [(r.alvo, r.tipo, r.embutido) for r in refs] == [
        ("Uma", "wiki", False), ("Pasta/Outra.md#Se%C3%A7%C3%A3o", "markdown", False),
        ("foto.png", "wiki", True), ("#Aqui", "wiki", False),
    ]
    assert refs[2].linha == 2 and refs[-1].linha == 11


def test_resolve_relativos_aliases_subpastas_ancoras_e_anexos(tmp_path):
    arquivo(tmp_path, "A/Origem.md", "# Aqui\n\n[[#Aqui]]\n[Alvo](../B/Alvo.md#Seção)\n![[foto.png]]\n")
    arquivo(tmp_path, "B/Alvo.md", "---\naliases: [Apelido]\n---\n# Seção\n\nTexto. ^bloco-a\n")
    arquivo(tmp_path, "A/foto.png")
    arquivo(tmp_path, "B/foto.png")
    arquivo(tmp_path, "Anexos/manual.pdf")
    indice = Indice(tmp_path)
    indice.carregar()
    assert indice.resolver_referencia("Apelido").rel == "B/Alvo.md"
    assert indice.resolver_referencia("Alvo#^bloco-a", "A/Origem.md").fragmento == "bloco-bloco-a"
    assert indice.resolver_referencia("#Aqui", "A/Origem.md").estado == "valido"
    assert indice.resolver_referencia("Alvo#Ausente").estado == "ancora_ausente"
    assert indice.resolver_referencia("foto.png").estado == "ambiguo"
    assert indice.resolver_referencia("foto.png", "A/Origem.md").rel == "A/foto.png"
    assert indice.resolver_referencia("manual.pdf").estado == "valido"
    html = str(render_markdown(indice.notas["A/Origem.md"].corpo, indice, "A/Origem.md"))
    assert 'id="aqui"' in html and 'href="/n/A/Origem.md#aqui"' in html
    assert 'href="/n/B/Alvo.md#' + quote("seção") + '"' in html
    assert 'src="/arquivo/A/foto.png"' in html
    html_alvo = str(render_markdown(indice.notas["B/Alvo.md"].corpo, indice, "B/Alvo.md"))
    assert 'id="bloco-bloco-a"' in html_alvo and "^bloco-a" not in html_alvo


def test_relatorio_distingue_futuro_revisao_e_escopo_sem_reescrever(tmp_path):
    origem = arquivo(tmp_path, "Projeto/Origem.md", "[[Futura]]\n![[sumiu.png]]\n[[Alvo#Ausente]]\n[[Repetida]]\n[privado](../.obsidian/workspace.json)\n[fora](../../fora.md)\n[[Alvo]]\n")
    arquivo(tmp_path, "Alvo.md", "# Existe")
    arquivo(tmp_path, "Um/Repetida.md")
    arquivo(tmp_path, "Dois/Repetida.md")
    arquivo(tmp_path, "Outro.md", "[[Outra futura]]")
    antes = origem.read_bytes()
    indice = Indice(tmp_path)
    indice.carregar()
    resultado = verificar_links(indice, "Projeto")
    assert resultado["notas"] == 1 and resultado["total"] == 7
    assert resultado["resumo"] == {"valido": 1, "futuro": 1, "ausente": 1, "ambiguo": 1, "ancora_ausente": 1, "bloqueado": 2, "revisao": 5}
    assert origem.read_bytes() == antes
    assert verificar_links(indice, "Projeto", limite=1)["limitado"]


def test_criar_renomear_editar_e_remover_revalida_sem_reanalisar_notas_intactas(tmp_path):
    arquivo(tmp_path, "Origem.md", "[[Alvo#Seção]]")
    indice = Indice(tmp_path)
    indice.carregar()
    refs = indice.referencias_de("Origem.md")
    assert verificar_links(indice)["resumo"]["futuro"] == 1
    destino = arquivo(tmp_path, "Alvo.md", "# Seção")
    indice.atualizar(destino)
    assert verificar_links(indice)["resumo"]["valido"] == 1
    assert indice.referencias_de("Origem.md") is refs
    destino.write_text("# Outra", encoding="utf-8")
    indice.atualizar(destino)
    assert verificar_links(indice)["resumo"]["ancora_ausente"] == 1
    destino.rename(tmp_path / "Renomeado.md")
    indice.sincronizar()
    assert verificar_links(indice)["resumo"]["futuro"] == 1


def test_markdown_referencia_nomeado_e_codigo_sao_renderizados_com_seguranca(tmp_path):
    arquivo(tmp_path, "Alvo.md", "# Seção")
    indice = Indice(tmp_path)
    indice.carregar()
    fonte = '[texto][id]\n\n[id]: Alvo.md#Seção\n\n`[[Alvo]]`\n\n[[Alvo|<img onerror=alert(1)>]]'
    html = str(render_markdown(fonte, indice))
    assert 'href="/n/Alvo.md#' + quote("seção") in html
    assert "<code>[[Alvo]]</code>" in html
    assert "&lt;img onerror=alert(1)&gt;" in html


def test_limite_prioriza_revisoes_sem_ocultar_totais(tmp_path):
    arquivo(tmp_path, "A.md", "\n".join(f"[[Futura{i}]]" for i in range(20)))
    arquivo(tmp_path, "Z.md", "![[sumiu.png]]")
    indice = Indice(tmp_path)
    indice.carregar()
    resultado = verificar_links(indice, limite=1)
    assert resultado["resumo"]["futuro"] == 20
    assert resultado["resumo"]["revisao"] == 1
    assert resultado["ocorrencias"][0]["estado"] == "ausente"
    assert resultado["limitado"]
    futuros = verificar_links(indice, limite=1, filtro="futuro")
    assert futuros["resumo"] == resultado["resumo"]
    assert futuros["ocorrencias"][0]["estado"] == "futuro"
    assert futuros["limitado"]
    revisoes = verificar_links(indice, limite=1, filtro="revisao")
    assert revisoes["resumo"] == resultado["resumo"]
    assert not revisoes["limitado"]


def test_percent_encoded_no_nome_nao_vira_fragmento_e_url_malformada_nao_quebra(tmp_path):
    arquivo(tmp_path, "Versão #1.md", "# C# guide\n")
    indice = Indice(tmp_path)
    indice.carregar()
    fonte = "[documento](<Versão%20%231.md#C%23%20guide>)\n[[http://[]]\n[[//[]]"
    refs = extrair_referencias(fonte)
    assert len(refs) == 1
    resolucao = indice.resolver_referencia(refs[0])
    assert resolucao.estado == "valido" and resolucao.rel == "Versão #1.md"
    assert resolucao.fragmento == "c-guide"
    html = str(render_markdown(fonte, indice))
    assert 'href="/n/' + quote("Versão #1.md") + '#c-guide"' in html


def test_validacao_de_caminhos_e_reutilizada_so_dentro_da_operacao(tmp_path, monkeypatch):
    arquivo(tmp_path, "Origem.md", "\n".join(["[[Alvo]]"] * 100))
    arquivo(tmp_path, "Alvo.md")
    indice = Indice(tmp_path)
    indice.carregar()
    validar = vinculos.caminho_no_vault
    chamadas = []

    def contar(vault, rel):
        chamadas.append(str(rel))
        return validar(vault, rel)

    monkeypatch.setattr(vinculos, "caminho_no_vault", contar)
    assert verificar_links(indice)["resumo"]["valido"] == 100
    primeira = chamadas[:]
    assert primeira and len(primeira) == len(set(primeira))
    assert verificar_links(indice)["resumo"]["valido"] == 100
    assert chamadas[len(primeira):] == primeira  # a próxima requisição revalida


def test_lote_nao_reaproveita_aceite_de_caminho_que_foi_bloqueado(tmp_path, monkeypatch):
    arquivo(tmp_path, "Origem.md", "[[Alvo]]")
    arquivo(tmp_path, "Alvo.md")
    indice = Indice(tmp_path)
    indice.carregar()
    assert verificar_links(indice)["resumo"]["valido"] == 1
    validar = vinculos.caminho_no_vault

    def bloqueado(vault, rel):
        if str(rel) == "Alvo.md":
            raise CaminhoInseguro("O destino foi substituído por um link.")
        return validar(vault, rel)

    monkeypatch.setattr(vinculos, "caminho_no_vault", bloqueado)
    resultado = verificar_links(indice)
    assert resultado["resumo"]["valido"] == 0
    assert resultado["resumo"]["bloqueado"] == 1
