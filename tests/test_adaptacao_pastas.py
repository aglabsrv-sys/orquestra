"""Pastas importadas mantêm sua estrutura e a visualização escolhida."""

from pathlib import Path
import base64

from fastapi.testclient import TestClient

from orquestra import apresentacao, cli
from orquestra.painel import Painel
from orquestra.servidor import criar_app


def adotar(painel, pasta="Biblioteca", *, aninhada=True):
    notas = {"Visão geral.md": "# Visão geral\n"}
    if aninhada:
        notas.update({"Clientes/Briefing.md": "# Briefing reservado\n", "Clientes/Projeto/Plano.md": "# Plano detalhado\n", "Estudos/Aula.md": "# Aula\n"})
    else:
        notas = {"Primeira.md": "---\nstatus: aberto\n---\n", "Segunda.md": "---\nstatus: feito\n---\n"}
    for rel, texto in notas.items():
        caminho = painel.vault / pasta / rel
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
    painel.adotar_pasta(pasta)


def test_pasta_adotada_navega_sem_achatar_subpastas(cliente):
    adotar(cliente.painel)
    raiz = cliente.get("/m/Biblioteca")
    assert raiz.status_code == 200
    assert [p["nome"] for p in raiz.context["subpastas"]] == ["Clientes", "Estudos"]
    assert [l["cartao"]["titulo"] for l in raiz.context["linhas"]] == ["Visão geral"]
    filha = cliente.get("/m/Biblioteca?pasta=Clientes")
    assert filha.status_code == 200
    assert [p["nome"] for p in filha.context["subpastas"]] == ["Projeto"]
    assert [l["cartao"]["titulo"] for l in filha.context["linhas"]] == ["Briefing"]
    assert 'data-subpasta="Clientes"' in filha.text
    assert cliente.get("/m/Biblioteca?pasta=../tarefas").status_code == 400


def test_explorador_mostra_subpastas_vazias_e_so_com_anexos(cliente, vault):
    for nome in ("Vazia", "Anexos"):
        (vault / "Arquivo" / nome).mkdir(parents=True)
    (vault / "Arquivo" / "Anexos" / "modelo.html").write_text("<p>Prévia</p>", encoding="utf-8")
    arvore = cliente.get("/api/pastas/arvore?rel=Arquivo").json()
    assert {p["nome"] for p in arvore["pastas"]} == {"Vazia", "Anexos"}
    pagina = cliente.get("/pastas/Arquivo")
    assert pagina.status_code == 200
    assert {p["nome"] for p in pagina.context["pastas"]} == {"Vazia", "Anexos"}
    assert cliente.get("/pastas/Arquivo/Vazia").status_code == 200
    assert "modelo.html" in cliente.get("/pastas/Arquivo/Anexos").text


def test_lista_e_sugerida_quando_kanban_so_teria_uma_coluna(cliente):
    adotar(cliente.painel, aninhada=False)
    for nota in cliente.painel.indice.itens("Biblioteca"):
        cliente.painel.editar_nota(nota.rel, nota.versao, campos={"status": "aberto"})
    pagina = cliente.get("/m/Biblioteca")
    assert pagina.context["visao"].tipo == "tabela"


def test_escolha_de_visao_e_memorizada_por_pasta_e_cofre(cliente, tmp_path: Path):
    adotar(cliente.painel, aninhada=False)
    assert cliente.get("/m/Biblioteca").context["visao"].tipo == "kanban"
    assert cliente.get("/m/Biblioteca?aba=v1").context["visao"].tipo == "tabela"
    assert cliente.get("/m/Biblioteca").context["visao"].tipo == "tabela"
    outro = cli.criar_vault(tmp_path / "outro")
    painel = Painel(outro)
    adotar(painel, aninhada=False)
    with TestClient(criar_app(outro, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as segundo:
        segundo.cookies.update(cliente.cookies)
        assert segundo.get("/m/Biblioteca").context["visao"].tipo == "kanban"


def test_criar_dentro_da_subpasta_preserva_local_e_schema(cliente):
    adotar(cliente.painel)
    r = cliente.post("/api/notas", json={"modulo": "Biblioteca", "titulo": "Nova referência", "subpasta": "Clientes", "campos": {}, "corpo": "Texto"})
    assert r.status_code == 200
    assert r.json()["rel"] == "Biblioteca/Clientes/Nova referência.md"
    ruim = cliente.post("/api/notas", json={"modulo": "Biblioteca", "titulo": "Escape", "subpasta": "../../fora"})
    assert ruim.status_code == 400


def test_capas_de_pastas_desconhecidas_nao_repetem_e_herdam_tema(cliente):
    for pasta in ("Arquivo pessoal", "Cliente Alfa", "Cliente Beta", "Referências", "Coleção"):
        adotar(cliente.painel, pasta, aninhada=False)
    cliente.painel.config.aparencia.cena = "mar"  # configuração antiga não uniformiza as capas
    capas = [apresentacao.capa_de(cliente.painel, pasta) for pasta in ("Arquivo pessoal", "Cliente Alfa", "Cliente Beta", "Referências", "Coleção")]
    assert len({(c["cena"], str(c["paleta"])) for c in capas}) == len(capas)


def test_personalizacao_de_pagina_salva_capa_oculta_e_restaura_tema(cliente):
    for alvo in ("diario", "decidir", "pastas"):
        pagina = cliente.get("/personalizar/" + alvo)
        assert pagina.status_code == 200
        versao = pagina.context["config_versao"]
        r = cliente.post(f"/api/paginas/{alvo}/personalizar", json={"versao": versao, "cena": "aurora"})
        assert r.status_code == 200
        assert cliente.painel.config.capas[alvo] == {"cena": "aurora"}
        assert cliente.post(f"/api/paginas/{alvo}/personalizar", json={"versao": versao, "ocultar": True}).status_code == 409
        versao = cliente.get("/personalizar/" + alvo).context["config_versao"]
        assert cliente.post(f"/api/paginas/{alvo}/personalizar", json={"versao": versao, "ocultar": True}).status_code == 200
        assert cliente.painel.config.capas[alvo] is False
        if alvo != "pastas":
            assert cliente.get("/" + alvo).context["capa"] is None
        versao = cliente.get("/personalizar/" + alvo).context["config_versao"]
        assert cliente.post(f"/api/paginas/{alvo}/personalizar", json={"versao": versao, "padrao": True}).status_code == 200
        assert alvo not in cliente.painel.config.capas


def test_upload_de_capa_da_pagina_usa_contrato_binario(cliente):
    token = cliente.get("/api/local/capacidade").json()["token"]
    imagem = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5QsAAAAASUVORK5CYII=")
    headers = {"Content-Type": "application/octet-stream", "X-Orquestra-Local": token}
    upload = cliente.post("/api/capas", content=imagem, headers=headers)
    assert upload.status_code == 200
    pagina = cliente.get("/personalizar/diario")
    r = cliente.post("/api/paginas/diario/personalizar", json={"versao": pagina.context["config_versao"], "capa": upload.json()["caminho"]})
    assert r.status_code == 200
    assert cliente.get("/diario").context["capa"]["url"].startswith("/arquivo/midia/capas/")
