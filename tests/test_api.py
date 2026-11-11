"""O painel de ponta a ponta: páginas, API e as proteções do servidor."""

from __future__ import annotations

import datetime as dt
from urllib.parse import quote

from orquestra.notas import ler_nota

TAREFA = "tarefas/itens/Responder comentários do último vídeo.md"


def versao_de(cliente, rel):
    return cliente.painel.nota(rel).versao


def url(rel):
    return "/api/notas/" + quote(rel)


# ---------------------------------------------------------------- páginas


def test_todas_as_paginas_abrem(cliente):
    paginas = ["/", "/decidir", "/diario", "/ajustes", "/buscar?q=roteiro", f"/dia/{dt.date.today()}"]
    for modulo in cliente.painel.indice.modulos.values():
        paginas += [f"/m/{modulo.id}?aba=v{i}" for i in range(len(modulo.visoes))]
        paginas += [f"/m/{modulo.id}?aba=humano", f"/m/{modulo.id}?aba=maquina"]
    paginas += ["/n/" + quote(rel) for rel in cliente.painel.indice.notas]
    for pagina in paginas:
        resposta = cliente.get(pagina)
        assert resposta.status_code == 200, pagina
        assert "Orquestra" in resposta.text


def test_o_exemplo_ja_nasce_com_itens_para_hoje(cliente):
    resumo = cliente.get("/api/resumo").json()
    assert resumo["hoje"] == 2
    assert resumo["selos"]["tarefas"] == 2
    assert resumo["decidir"] == 5  # 3 do radar + 2 perguntas de agente


def test_pagina_que_nao_existe(cliente):
    assert cliente.get("/m/nao-existe").status_code == 404
    assert cliente.get("/n/tarefas/itens/fantasma.md").status_code == 404


def test_wikilink_vira_link_para_a_nota(cliente):
    html = cliente.get("/n/" + quote("tarefas/itens/Gravar vídeo sobre organização com IA.md")).text
    assert "/n/conteudo/itens/5%20erros%20de%20quem%20come%C3%A7a%20a%20usar%20IA.md" in html


def test_html_cru_na_nota_nao_e_executado(cliente, vault):
    (vault / "tarefas/itens/Perigosa.md").write_text("---\nstatus: a_fazer\n---\n<script>alert(1)</script>\n", encoding="utf-8")
    cliente.painel.indice.carregar()
    html = cliente.get("/n/tarefas/itens/Perigosa.md").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_link_perigoso_vindo_de_um_feed_nao_vira_clicavel(cliente, vault):
    (vault / "radar/itens/Isca.md").write_text("---\nstatus: novo\nlink: 'javascript:alert(1)'\n---\n", encoding="utf-8")
    cliente.painel.indice.carregar()
    for pagina in ("/m/radar?aba=v0", "/m/radar?aba=v1", "/decidir"):
        assert 'href="javascript:' not in cliente.get(pagina).text, pagina


# ---------------------------------------------------------------- criar e editar


def test_criar_nota_grava_arquivo_com_o_schema(cliente, vault):
    r = cliente.post("/api/notas", json={"modulo": "tarefas", "titulo": "Testar: o painel?", "campos": {"prioridade": "alta", "data": "2026-12-01", "tags": "a, b"}, "corpo": "Detalhes."})
    assert r.status_code == 200, r.text
    nota = ler_nota(vault / r.json()["rel"], vault)
    assert nota.caminho.name == "Testar o painel.md"
    assert nota.titulo == "Testar: o painel?"  # o título original fica no frontmatter
    assert nota.campos() | {"criado_em": None} == {
        "titulo": "Testar: o painel?", "status": "a_fazer", "prioridade": "alta",
        "origem": "humano", "data": "2026-12-01", "tags": ["a", "b"], "criado_em": None,
    }
    assert nota.corpo == "\nDetalhes.\n"


def test_criar_sem_titulo_e_recusado(cliente):
    r = cliente.post("/api/notas", json={"modulo": "tarefas", "titulo": "  "})
    assert r.status_code == 400
    assert "título" in r.json()["erro"]


def test_editar_um_campo_nao_mexe_no_resto_do_arquivo(cliente, vault):
    antes = (vault / TAREFA).read_text(encoding="utf-8")
    r = cliente.put(url(TAREFA), json={"versao": versao_de(cliente, TAREFA), "campos": {"status": "feito"}})
    assert r.status_code == 200, r.text
    assert (vault / TAREFA).read_text(encoding="utf-8") == antes.replace("status: a_fazer", "status: feito")


def test_editar_com_versao_antiga_da_conflito(cliente, vault):
    velha = versao_de(cliente, TAREFA)
    # O arquivo muda por fora (Obsidian ou um agente) depois que a página foi aberta.
    (vault / TAREFA).write_text((vault / TAREFA).read_text(encoding="utf-8") + "\nEditado no Obsidian.\n", encoding="utf-8")
    r = cliente.put(url(TAREFA), json={"versao": velha, "campos": {"status": "feito"}})
    assert r.status_code == 409
    assert r.json()["conflito"] is True
    texto = (vault / TAREFA).read_text(encoding="utf-8")
    assert "Editado no Obsidian." in texto and "status: a_fazer" in texto


def test_valor_fora_do_schema_e_recusado(cliente):
    r = cliente.put(url(TAREFA), json={"versao": versao_de(cliente, TAREFA), "campos": {"status": "talvez"}})
    assert r.status_code == 400
    assert "não é uma opção" in r.json()["erro"]


def test_editar_texto_e_titulo(cliente, vault):
    r = cliente.put(url(TAREFA), json={"versao": versao_de(cliente, TAREFA), "titulo": "Novo título", "corpo": "\nNovo **texto**.\n"})
    assert "<strong>texto</strong>" in r.json()["html"]
    nota = ler_nota(vault / TAREFA, vault)
    assert nota.titulo == "Novo título"
    assert nota.corpo == "\nNovo **texto**.\n"
    assert (vault / TAREFA).exists()  # mudar o título não renomeia o arquivo (não quebra links)


def test_arquivar_move_e_nao_apaga(cliente, vault):
    r = cliente.post("/api/arquivar/" + quote(TAREFA), json={})
    assert r.status_code == 200
    assert not (vault / TAREFA).exists()
    assert (vault / r.json()["rel"]).exists()
    assert r.json()["rel"].startswith("tarefas/arquivo/")
    assert TAREFA not in cliente.painel.indice.notas


def test_captura_rapida_vai_para_a_entrada_como_fala_do_usuario(cliente, vault):
    r = cliente.post("/api/captura", json={"texto": "Ideia: vídeo sobre backup\ncom mais detalhes aqui"})
    nota = ler_nota(vault / r.json()["rel"], vault)
    assert nota.rel.startswith("entrada/itens/")
    assert nota.campo("origem") == "humano"
    assert nota.campo("status") == "novo"
    assert "com mais detalhes aqui" in nota.corpo


def test_responder_pergunta_de_agente(cliente, vault):
    rel = "tarefas/itens/Revisar o roteiro que o agente escreveu.md"
    assert "O roteiro ficou com 9 minutos" in cliente.get("/decidir").text
    cliente.put(url(rel), json={"versao": versao_de(cliente, rel), "campos": {"resposta": "Corta o bloco 3.", "pergunta": ""}})
    nota = ler_nota(vault / rel, vault)
    assert nota.campo("resposta") == "Corta o bloco 3."
    assert "pergunta" not in nota.meta


def test_trocar_tema(cliente, vault):
    assert cliente.post("/api/tema", json={"tema": "mare"}).status_code == 200
    assert "tema: mare" in (vault / "orquestra.yaml").read_text(encoding="utf-8")
    assert "# Configuração do painel" in (vault / "orquestra.yaml").read_text(encoding="utf-8")  # comentários preservados
    assert "#07141a" in cliente.get("/").text
    assert cliente.post("/api/tema", json={"tema": "inexistente"}).status_code == 404


def test_ligar_coletor_altera_so_aquela_chave(cliente, vault):
    r = cliente.post("/api/coletores/ativo", json={"modulo": "radar", "script": "rss.py", "ativo": True})
    assert r.status_code == 200
    ativos = {c.script: c.ativo for c in cliente.painel.modulo("radar").coletores}
    assert ativos == {"youtube_rss.py": False, "rss.py": True, "google_trends.py": False, "youtube_api.py": False}
    assert "# Coletores: scripts em radar/maquina/coletores/." in (vault / "radar/_modulo.yaml").read_text(encoding="utf-8")


# ---------------------------------------------------------------- segurança


def test_post_vindo_de_outro_site_e_bloqueado(cliente):
    r = cliente.post("/api/captura", json={"texto": "x"}, headers={"Origin": "https://site-malicioso.com"})
    assert r.status_code == 403


def test_post_do_proprio_painel_passa(cliente):
    r = cliente.post("/api/captura", json={"texto": "x"}, headers={"Origin": "http://localhost"})
    assert r.status_code == 200


def test_host_desconhecido_e_bloqueado(cliente):
    assert cliente.get("/", headers={"Host": "atacante.com"}).status_code == 403
    assert cliente.get("/", headers={"Host": "minha-maquina.tail1234.ts.net"}).status_code == 200


def test_formulario_comum_nao_altera_nada(cliente):
    r = cliente.post("/api/captura", data={"texto": "x"})  # é o que um <form> de outro site conseguiria mandar
    assert r.status_code == 415


def test_so_serve_midia_e_so_de_dentro_do_vault(cliente):
    imagem = cliente.get("/arquivo/conteudo/midia/5-erros.svg")
    assert imagem.status_code == 200
    assert "sandbox" in imagem.headers["content-security-policy"]
    assert cliente.get("/arquivo/AGENTS.md").status_code == 404
    assert cliente.get("/arquivo/..%2F..%2Fsegredo.png").status_code == 404
    assert cliente.put("/api/notas/..%2Ffora.md", json={"campos": {}}).status_code == 404
