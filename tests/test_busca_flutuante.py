"""API da busca flutuante: resultados curtos, trecho em volta do termo e limite."""


def test_busca_traz_titulo_trecho_e_total(cliente, vault):
    (vault / "tarefas" / "itens" / "Planejar viagem.md").write_text(
        "---\nstatus: a_fazer\n---\n" + "Texto longo de abertura. " * 10 + "Reservar o hotel em Lisboa antes de maio.",
        encoding="utf-8")
    cliente.painel.indice.carregar()
    dados = cliente.get("/api/buscar", params={"q": "lisboa"}).json()
    assert dados["total"] >= 1
    item = next(r for r in dados["resultados"] if r["titulo"] == "Planejar viagem")
    assert "Lisboa" in item["trecho"] and item["trecho"].startswith("…")
    assert item["url"].startswith("/n/") and item["onde"] == "tarefas/itens"


def test_busca_vazia_e_limite(cliente):
    assert cliente.get("/api/buscar", params={"q": "   "}).json() == {"total": 0, "resultados": []}
    dados = cliente.get("/api/buscar", params={"q": "a", "limite": 2}).json()
    assert len(dados["resultados"]) <= 2 and dados["total"] >= len(dados["resultados"])
    assert cliente.get("/api/buscar", params={"q": "a", "limite": 500}).json()["resultados"].__len__() <= 30
