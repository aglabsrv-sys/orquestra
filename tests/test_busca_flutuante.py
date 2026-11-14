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


def test_busca_atualiza_texto_e_remove_resultados(vault):
    from orquestra.indice import Indice

    caminho = vault / "Busca regressão.md"
    caminho.write_text("Texto com agulha exclusiva", encoding="utf-8")
    indice = Indice(vault)
    indice.carregar()
    assert indice.buscar_com_total("AGULHA EXCLUSIVA", 1)[1] == 1
    caminho.write_text("Texto com outra expressão", encoding="utf-8")
    indice.atualizar(caminho)
    assert indice.buscar("agulha exclusiva") == []
    assert indice.buscar_com_total("outra expressão", 1)[1] == 1
    caminho.unlink()
    indice.sincronizar()
    assert indice.buscar("outra expressão") == []


def test_busca_limita_sem_perder_total_e_prioriza_titulo(vault):
    from orquestra.indice import Indice

    for i in range(40):
        (vault / f"Corpo {i}.md").write_text("marcador-exclusivo", encoding="utf-8")
    (vault / "marcador-exclusivo.md").write_text("Outro texto", encoding="utf-8")
    indice = Indice(vault)
    indice.carregar()
    notas, total = indice.buscar_com_total("marcador-exclusivo", 2)
    assert total == 41
    assert len(notas) == 2
    assert notas[0].titulo == "marcador-exclusivo"
    assert len(indice.buscar("marcador-exclusivo", None)) == total


def test_pagina_de_busca_renderiza_e_escapa_termo(cliente):
    resposta = cliente.get("/buscar", params={"q": "<script>alert(1)</script>"})
    assert resposta.status_code == 200
    assert "&lt;script&gt;" in resposta.text
