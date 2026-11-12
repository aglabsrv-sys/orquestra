"""Semântica das telas: contexto para controles e caminhos para estados vazios."""

from html.parser import HTMLParser
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from orquestra.modulos import Campo, rotulo


class Elementos(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.itens = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.itens.append((tag, dict(attrs)))


@pytest.fixture
def entrada():
    pasta = Path(__file__).parents[1] / "src/orquestra/templates"
    env = Environment(loader=FileSystemLoader(pasta), autoescape=select_autoescape(["html"]))
    env.globals["rotulo"] = rotulo
    return env.get_template("partes.html").module.entrada


@pytest.mark.parametrize("url", ["/m/tarefas", "/pastas", "/n/tarefas/itens/Responder%20coment%C3%A1rios%20do%20%C3%BAltimo%20v%C3%ADdeo.md"])
def test_dialogos_e_ajudas_apontam_para_elementos_unicos(cliente, url):
    resposta = cliente.get(url)
    assert resposta.status_code == 200
    elementos = Elementos(resposta.text).itens
    ids = [attrs["id"] for _, attrs in elementos if "id" in attrs]
    assert len(ids) == len(set(ids)), "IDs repetidos quebram rótulos e foco"
    for _, attrs in elementos:
        for referencia in ("aria-labelledby", "aria-describedby", "aria-controls"):
            for destino in attrs.get(referencia, "").split():
                assert destino in ids, f"{referencia} aponta para {destino}, que não existe"


def test_campo_booleano_obrigatorio_permite_falso_e_ajuda_nao_depende_de_placeholder(entrada):
    html = entrada(Campo("confirmado", tipo="booleano", obrigatorio=True, rotulo="Confirmado"), False)
    checkbox = next(attrs for tag, attrs in Elementos(html).itens if tag == "input")
    assert "required" not in checkbox  # required num checkbox tornaria false impossível
    assert "checked" not in checkbox

    html = entrada(Campo("tags", tipo="lista", rotulo="Tags"), "pessoal")
    elementos = Elementos(html).itens
    campo = next(attrs for tag, attrs in elementos if tag == "input")
    assert campo["aria-describedby"] == next(attrs["id"] for tag, attrs in elementos if tag == "small")
    assert "Separe os itens por vírgulas" in html

    html = entrada(Campo("status", tipo="escolha", rotulo="Status", obrigatorio=True, opcoes=["feito"]), "")
    seletor = next(attrs for tag, attrs in Elementos(html).itens if tag == "select")
    assert "required" in seletor
    assert "Selecione uma opção" in html


def test_campos_distintos_tem_ids_unicos_e_rotulo_separado_da_ajuda(entrada):
    nomes = ["a b", "a-b", "a\tb", "a%20b", "ação", "acao"]
    html = "".join(entrada(Campo(nome, tipo="lista", rotulo=nome)) for nome in nomes)
    elementos = Elementos(html).itens
    ids = [attrs["id"] for _, attrs in elementos if "id" in attrs]
    assert len(ids) == len(set(ids))
    assert all(not any(c.isspace() for c in id_) for id_ in ids)
    tags_por_id = {attrs["id"]: tag for tag, attrs in elementos if "id" in attrs}
    for tag, campo in elementos:
        if tag == "input":
            assert tags_por_id[campo["aria-labelledby"]] == "span"
            assert tags_por_id[campo["aria-describedby"]] == "small"
            assert campo["aria-labelledby"] != campo["aria-describedby"]


def test_busca_vazia_e_sem_resultados_oferecem_proximo_passo(cliente):
    sem_termo = cliente.get("/buscar").text
    sem_resultado = cliente.get("/buscar", params={"q": "palavra-inexistente-no-vault"}).text
    assert "Encontre o que você já escreveu" in sem_termo
    assert "Nenhuma nota encontrada" in sem_resultado
    assert "Tente uma palavra mais curta" in sem_resultado
    for html in (sem_termo, sem_resultado):
        elementos = Elementos(html).itens
        assert any(tag == "form" and attrs.get("role") == "search" for tag, attrs in elementos)
        assert any(tag == "button" and attrs.get("type") == "submit" for tag, attrs in elementos)
        assert any(tag == "h1" for tag, _ in elementos)
