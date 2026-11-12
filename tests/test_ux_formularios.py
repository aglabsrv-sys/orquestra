"""Contratos de navegação e ajuda dos formulários de configuração."""

from html.parser import HTMLParser

from fastapi.testclient import TestClient

from orquestra import preparo
from orquestra.hospedeiro import Hospedeiro


class Elementos(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.itens = []
        self.feed(html)

    def handle_starttag(self, tag, atributos):
        self.itens.append((tag, dict(atributos)))

    def id(self, identificador):
        return next(a for _, a in self.itens if a.get("id") == identificador)

    def conferir_ajuda(self):
        ids = {a["id"] for _, a in self.itens if "id" in a}
        for _, atributos in self.itens:
            for atributo in ("aria-describedby", "aria-labelledby"):
                for referencia in atributos.get(atributo, "").split():
                    assert referencia in ids, referencia


def test_boasvindas_tem_labels_visiveis_e_erros_persistentes(monkeypatch):
    monkeypatch.setattr(preparo, "cofres_obsidian", lambda: [])
    with TestClient(Hospedeiro(None, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        pagina = Elementos(cliente.get("/boas-vindas").text)
    pagina.conferir_ajuda()
    for campo in ("caminho-existente", "caminho-novo"):
        assert any(tag == "label" and a.get("for") == campo for tag, a in pagina.itens)
        assert "required" in pagina.id(campo)
        assert "hidden" in pagina.id("erro-" + campo)
    assert pagina.id("bv-erro")["role"] == "alert"
    assert pagina.id("bv-estado")["role"] == "status"
    assert pagina.id("nome")["aria-labelledby"] == "rotulo-nome"
    assert len([a for _, a in pagina.itens if a.get("aria-current") == "step"]) == 1


def test_ajustes_e_personalizacao_preservam_navegacao_e_ajuda(cliente):
    ajustes = Elementos(cliente.get("/ajustes").text)
    ajustes.conferir_ajuda()
    assert ajustes.id("estado-config")["role"] == "status"
    for secao, alvo in (("painel", "painel"), ("areas", "areas"), ("aparencia", "aparencia-secao"), ("backup", "backup-secao"), ("coletores", "coletores-secao"), ("vault", "vault-secao")):
        pagina = Elementos(cliente.get("/ajustes/" + secao).text)
        pagina.conferir_ajuda()
        assert pagina.id(alvo)
        assert any(tag == "a" and a.get("href") == "/ajustes/" + secao and a.get("aria-current") == "page" for tag, a in pagina.itens)
        assert not any(a.get("href", "").startswith("#backup") for _, a in pagina.itens)
    assert "required" in ajustes.id("cfg-nome")
    assert ajustes.id("cfg-nome")["aria-labelledby"] == "rotulo-cfg-nome"
    assert ajustes.id("cfg-captura")["aria-labelledby"] == "rotulo-cfg-captura"

    personalizar = Elementos(cliente.get("/m/tarefas/personalizar").text)
    personalizar.conferir_ajuda()
    assert "required" in personalizar.id("p-nome")
    assert personalizar.id("p-concluidos")["aria-labelledby"] == "rotulo-concluidos"
    existentes = [a for tag, a in personalizar.itens if tag == "input" and "data-nome" in a and "value" in a]
    assert existentes
    assert all("readonly" in campo and "disabled" not in campo for campo in existentes)
