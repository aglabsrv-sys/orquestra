"""Blocos do live preview apontam para linhas do Markdown original."""

from html.parser import HTMLParser

from orquestra import apresentacao


class Mapas(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.blocos = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-md-inicio" in attrs:
            self.blocos.append((tag, int(attrs["data-md-inicio"]), int(attrs["data-md-fim"])))


def test_heading_paragrafo_lista_codigo_e_tabela_apontam_para_a_fonte(painel):
    fonte = "# Título\n\nParágrafo com [[Referência|alias]].\n\n- Um\n- Dois\n\n```js\nconst x = 1;\n```\n\n| A | B |\n| - | - |\n| 1 | 2 |\n"
    html = str(apresentacao.render_markdown(fonte, painel.indice))
    assert Mapas(html).blocos == [("h1", 0, 1), ("p", 2, 3), ("ul", 4, 7), ("code", 7, 10), ("table", 11, 14)]


def test_alias_multilinha_usa_fallback_quando_a_transformacao_muda_linhas(painel):
    fonte = "Antes.\n\n[[Referência|\nNome visível\n]]\n\nDepois."
    html = str(apresentacao.render_markdown(fonte, painel.indice))
    assert Mapas(html).blocos == []
    assert "Nome visível" in html

