"""Criação do vault pela linha de comando, temas e a checagem de endereços."""

from __future__ import annotations

import datetime as dt

from orquestra import temas
from orquestra.cli import _datas_relativas, criar_vault
from orquestra.config import ler_config_painel, localizar_vault
from orquestra.doctor import verificar_vault
from orquestra.seguranca import host_permitido, nome_do_host


def test_datas_do_exemplo_sao_relativas_a_hoje():
    hoje = dt.date(2026, 3, 10)
    assert _datas_relativas("a {{hoje}} b {{hoje+2}} c {{hoje-10}}", hoje) == "a 2026-03-10 b 2026-03-12 c 2026-02-28"


def test_vault_criado_fica_pronto_para_usar(vault):
    hoje = dt.date.today().isoformat()
    assert (vault / "AGENTS.md").is_file()
    assert (vault / "CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"
    assert (vault / "diario/sessoes" / f"{hoje}.md").is_file()
    assert not list(vault.rglob("_HOJE_.md"))
    # Nenhum marcador de data sobrou em nenhuma nota.
    assert not [p for p in vault.rglob("*.md") if "{{hoje" in p.read_text(encoding="utf-8")]
    assert localizar_vault() == vault.resolve()
    assert ler_config_painel(vault).tema == "brasa"


def test_criar_de_novo_no_mesmo_lugar_nao_sobrescreve(vault):
    nota = vault / "tarefas/itens/Minha.md"
    nota.write_text("minha nota", encoding="utf-8")
    criar_vault(vault)
    assert nota.read_text(encoding="utf-8") == "minha nota"


def test_doctor_nao_acha_erro_no_vault_modelo(vault):
    itens = verificar_vault(vault)
    assert [i.titulo for i in itens if i.estado == "erro"] == []
    assert any("4 módulo(s)" in i.titulo for i in itens)
    assert any("YOUTUBE_API_KEY" in i.detalhe for i in itens)  # avisa da chave que falta


def test_temas_do_modelo(vault):
    lista = temas.listar(vault)
    assert [t["id"] for t in lista] == ["brasa", "mare", "noturno"]
    for tema in lista:
        assert set(tema["cores"]) == set(temas.CORES_PADRAO)
        for alvo in ("tarefas", "conteudo", "radar", "entrada", "decidir", "diario"):
            capa = temas.resolver_capa(tema, alvo)
            assert capa["tipo"] == "cena" and capa["cena"] in temas.CENAS
            assert len(capa["paleta"]["ceu"]) == 4


def test_capa_do_modulo_vale_mais_que_a_do_tema(vault):
    tema = temas.carregar(vault, "brasa")
    assert temas.resolver_capa(tema, "tarefas", "_orquestra/capas/minha foto.webp") == {
        "tipo": "imagem", "url": "/arquivo/_orquestra/capas/minha%20foto.webp"
    }
    assert temas.resolver_capa(tema, "tarefas", "capas/loop.mp4")["tipo"] == "video"
    assert temas.resolver_capa(tema, "tarefas", {"cena": "mar", "paleta": "areia"})["cena"] == "mar"
    # Módulo que o tema não conhece ganha sempre a mesma cena.
    assert temas.resolver_capa(tema, "financas") == temas.resolver_capa(tema, "financas")


def test_tema_so_aceita_cores_em_hexadecimal(vault):
    arquivo = vault / "_orquestra/temas/brasa/tema.yaml"
    arquivo.write_text(
        arquivo.read_text(encoding="utf-8").replace('fundo: "#130c09"', 'fundo: "red;} body{display:none"'), encoding="utf-8"
    )
    assert temas.carregar(vault, "brasa")["cores"]["fundo"] == temas.CORES_PADRAO["fundo"]


def test_tema_inexistente_cai_no_primeiro(vault):
    assert temas.carregar(vault, "nao-existe")["id"] == "brasa"


def test_nome_do_host():
    assert nome_do_host("Localhost:8420") == "localhost"
    assert nome_do_host("[::1]:8420") == "::1"
    assert nome_do_host("pc.tail1234.ts.net") == "pc.tail1234.ts.net"


def test_hosts_permitidos():
    assert host_permitido("localhost:8420")
    assert host_permitido("127.0.0.1:8420")
    assert host_permitido("meu-pc.tail1234.ts.net")
    assert host_permitido("painel.casa", ["painel.casa"])
    assert not host_permitido("painel.casa")
    assert not host_permitido("localhost.atacante.com")
    assert not host_permitido("ts.net.atacante.com")
    assert not host_permitido("")
