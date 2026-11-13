"""Jornadas públicas: catálogo sem módulos, teste sem gravação e diagnóstico nativo."""

from __future__ import annotations

import datetime as dt


def _local(cliente):
    return {"X-Orquestra-Local": cliente.get("/api/local/capacidade").json()["token"]}


def test_catalogo_visivel_sem_areas_e_destinos_reais(cliente, vault):
    for configuracao in vault.glob("*/_modulo.yaml"):
        configuracao.unlink()
    destino = vault / "Clientes" / "Empresa" / "Pesquisa"
    destino.mkdir(parents=True)
    (vault / "_templates").mkdir()
    cliente.painel.recarregar_tudo()
    resposta = cliente.get("/api/automacoes/catalogo")
    assert resposta.status_code == 200
    catalogo = resposta.json()
    assert len(catalogo["catalogo"]) == 9
    assert "Clientes/Empresa/Pesquisa" in catalogo["pastas"]
    assert "_templates" not in catalogo["pastas"]
    for url in ("/ajustes/coletores", "/ajustes/automacoes?destino=Clientes/Empresa/Pesquisa"):
        pagina = cliente.get(url)
        assert pagina.status_code == 200
        assert "Blogs e newsletters" in pagina.text
        assert 'id="automacao-dialogo"' in pagina.text


def test_fluxo_automacao_local_sem_escrever_na_previa(cliente, vault):
    destino = vault / "Projeto" / "Rotinas"
    destino.mkdir(parents=True)
    pedido = {"definicao": "tarefas/recorrentes.py", "destino": "Projeto/Rotinas", "nome": "Rotina do projeto",
              "config": {"tarefas": [{"titulo": "Conferir o projeto", "quando": "todo dia"}]}, "a_cada": "", "diario_as": ""}
    assert cliente.post("/api/automacoes/prever", json=pedido).status_code == 200
    assert not list(destino.glob("*.md"))
    criada = cliente.post("/api/automacoes/criar", json=pedido)
    assert criada.status_code == 200
    instancia = criada.json()
    assert not instancia["ativo"] and not instancia["confianca"]["confiavel"]
    assert cliente.post("/api/automacoes/rodar", json={"id": instancia["id"]}).status_code == 502
    assinatura = instancia["confianca"]["assinatura"]
    assert cliente.post("/api/automacoes/confiar", json={"id": instancia["id"], "assinatura": assinatura}, headers=_local(cliente)).status_code == 200
    teste = cliente.post("/api/automacoes/rodar", json={"id": instancia["id"], "previa": True})
    assert teste.status_code == 200 and teste.json()["total"] == 1, teste.text
    assert not list(destino.glob("*.md"))
    primeira = cliente.post("/api/automacoes/rodar", json={"id": instancia["id"]})
    assert primeira.status_code == 200 and primeira.json()["novos"] == 1
    segunda = cliente.post("/api/automacoes/rodar", json={"id": instancia["id"]})
    assert segunda.status_code == 200 and segunda.json()["repetidos"] == 1
    assert len(list(destino.glob("*.md"))) == 1
    assert cliente.post("/api/automacoes/remover", json={"id": instancia["id"]}).status_code == 200
    assert len(list(destino.glob("*.md"))) == 1


def test_opcionais_e_erros_de_automacao_sao_json(cliente):
    assert cliente.post("/api/automacoes/prever", json={"definicao": "tarefas/recorrentes.py"}).status_code == 200
    assert cliente.post("/api/automacoes/prever", json={"definicao": "nao-existe"}).status_code == 400
    assert cliente.post("/api/automacoes/criar", json={"definicao": "tarefas/recorrentes.py", "destino": "../fora"}).status_code == 400


def test_vinculos_e_grafo_compartilham_markdown_e_ignoram_codigo(cliente, vault):
    pasta = vault / "Pesquisa"
    pasta.mkdir()
    (pasta / "Origem.md").write_text("[Destino](Destino.md#Seção)\n[[Futura]]\n![[faltante.png]]\n`[[Fantasma]]`\n", encoding="utf-8")
    (pasta / "Destino.md").write_text("# Seção\n\nConteúdo.\n", encoding="utf-8")
    cliente.painel.recarregar_tudo()
    resposta = cliente.get("/api/vinculos?rel=Pesquisa")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["resumo"]["valido"] == 1
    assert dados["resumo"]["futuro"] == 1
    assert dados["resumo"]["revisao"] == 1
    assert dados["total"] == 3
    grafo = cliente.get("/api/pastas/grafo?rel=Pesquisa").json()
    assert ["Pesquisa/Destino.md", "Pesquisa/Origem.md"] in grafo["ligacoes"]
    pagina = cliente.get("/vinculos?rel=Pesquisa")
    assert pagina.status_code == 200 and "Anexo ausente" in pagina.text
    assert "faltante.png" in pagina.text and "Futura" not in pagina.text
    futuras = cliente.get("/vinculos?rel=Pesquisa&filtro=futuro")
    assert futuras.status_code == 200 and "Futura" in futuras.text and "faltante.png" not in futuras.text
    assert cliente.get("/api/vinculos?rel=../fora").status_code == 404


def test_resumo_existente_e_backup_opcional(cliente):
    data = dt.date.today().isoformat()
    resumo = cliente.get(f"/dia/{data}")
    assert resumo.status_code == 200 and "Resumo do dia" in resumo.text
    assert f'href="/dia/{(dt.date.today() - dt.timedelta(days=1)).isoformat()}"' in resumo.text
    backup = cliente.get("/ajustes/backup")
    assert backup.status_code == 200 and "Sincronização opcional" in backup.text
    assert "orquestra-backup" in backup.text

