"""Aparência (claro/escuro, destaque, cantos, letra), capas por tema, backup e coletores sem rede."""

from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

from orquestra import agenda, aparencia, backup, preparo, temas
from orquestra.aparencia import Aparencia
from orquestra.config import ler_config_painel
from orquestra.modulos import carregar_modulo
from orquestra.painel import Recusado

TEMAS = temas.listar(preparo.MODELO)


# ---------------------------------------------------------------- aparência


def test_aparencia_tolera_valores_estranhos():
    assert aparencia.ler(None) == Aparencia()
    assert aparencia.ler({"modo": "neon", "cantos": 7, "fonte": "comic", "destaque": "vermelho"}) == Aparencia()
    lida = aparencia.ler({"modo": "claro", "cantos": "redondo", "fonte": "serifada", "destaque": "#7CC4FF"})
    assert lida == Aparencia("claro", "#7cc4ff", "redondo", "serifada")


def test_validar_recusa_o_que_viraria_css_estranho():
    assert aparencia.validar({"modo": "auto", "destaque": ""}) == {"modo": "auto", "destaque": ""}
    for ruim in [{"modo": "x"}, {"cantos": "pill"}, {"fonte": "Arial; }"}, {"destaque": "red"}, {"destaque": "#fff;}body{display:none"}]:
        with pytest.raises(ValueError):
            aparencia.validar(ruim)


@pytest.mark.parametrize("tema", TEMAS, ids=lambda t: t["id"])
def test_todo_tema_e_legivel_nos_dois_modos(tema):
    assert tema["cores_claras"], "o tema precisa trazer a paleta clara"
    for claro in (False, True):
        cores = aparencia.cores(tema, Aparencia(), claro)
        assert aparencia.contraste(cores["texto"], cores["fundo"]) >= 7
        assert aparencia.contraste(cores["texto_suave"], cores["fundo"]) >= 4
        assert aparencia.contraste(cores["destaque"], cores["fundo"]) >= 3
        assert aparencia.contraste(cores["sobre_destaque"], cores["destaque"]) >= 4


def test_destaque_escolhido_continua_legivel_no_claro_e_no_escuro():
    tema = TEMAS[0]
    for cor in ["#fff7c2", "#101010", "#7cc4ff", "#ff0000"]:  # pastel, quase preto, médio, saturado
        for claro in (False, True):
            cores = aparencia.cores(tema, Aparencia(destaque=cor), claro)
            assert aparencia.contraste(cores["destaque"], cores["fundo"]) >= 3, (cor, claro)
            assert aparencia.contraste(cores["sobre_destaque"], cores["destaque"]) >= 4, (cor, claro)
    # Uma cor que já funciona não é mexida.
    assert aparencia.cores(tema, Aparencia(destaque="#7cc4ff"), False)["destaque"] == "#7cc4ff"


def test_tema_sem_paleta_clara_ganha_uma_derivada():
    tema = {**TEMAS[0], "cores_claras": None}
    cores = aparencia.cores(tema, Aparencia(), True)
    assert aparencia.luminancia(cores["fundo"]) > 0.8
    assert aparencia.contraste(cores["texto"], cores["fundo"]) >= 7


def test_estilo_por_modo():
    tema = TEMAS[0]
    escuro = aparencia.estilo(tema, Aparencia())
    assert "color-scheme:dark" in escuro and "prefers-color-scheme" not in escuro and "--cantos:0.45" in escuro
    claro = aparencia.estilo(tema, Aparencia(modo="claro", cantos="reto", fonte="mono"))
    assert "color-scheme:light" in claro and "--cantos:0.0" in claro and "ui-monospace" in claro
    auto = aparencia.estilo(tema, Aparencia(modo="auto"))
    assert "color-scheme:dark" in auto and "color-scheme:light" in auto and "@media (prefers-color-scheme: light)" in auto


def test_aparencia_pela_api(cliente, vault):
    r = cliente.post("/api/config", json={"aparencia": {"modo": "claro", "destaque": "#7cc4ff", "cantos": "redondo", "fonte": "arredondada"}})
    assert r.status_code == 200
    assert ler_config_painel(vault).aparencia == Aparencia("claro", "#7cc4ff", "redondo", "arredondada")
    pagina = cliente.get("/").text
    assert 'class="cantos-redondo"' in pagina and "color-scheme:light" in pagina and "ui-rounded" in pagina
    assert "# Configuração do painel." in (vault / "orquestra.yaml").read_text(encoding="utf-8")  # comentários preservados
    assert cliente.post("/api/config", json={"aparencia": {"destaque": "azul"}}).status_code == 400
    assert cliente.post("/api/config", json={"aparencia": {"destaque": ""}}).status_code == 200
    assert ler_config_painel(vault).aparencia.destaque == ""
    assert cliente.get("/ajustes").status_code == 200


def test_definir_config_recusa_visual_invalido(painel):
    with pytest.raises(Recusado):
        painel.definir_config(visual={"cantos": "pill"})


@pytest.mark.parametrize("tamanho,pixels", [("xl", "20px"), ("xxl", "22px")])
def test_fontes_ampliadas_persistem_e_renderizam(cliente, vault, tamanho, pixels):
    resposta = cliente.post("/api/config", json={"aparencia": {"tamanho": tamanho}})
    assert resposta.status_code == 200
    assert ler_config_painel(vault).aparencia.tamanho == tamanho
    pagina = cliente.get("/ajustes/aparencia")
    assert f"--tamanho-fonte:{pixels}" in pagina.text
    assert f'data-valor="{tamanho}"' in pagina.text
    assert aparencia.ler({"tamanho": tamanho}).tamanho == tamanho


# ---------------------------------------------------------------- capas


@pytest.mark.parametrize("tema", TEMAS, ids=lambda t: t["id"])
def test_cada_area_tem_uma_capa_diferente(tema):
    alvos = [*preparo.catalogo(), "decidir", "diario", "pastas"]
    capas = [temas.resolver_capa(tema, alvo) for alvo in alvos]
    assert all(c["tipo"] == "cena" and c["cena"] in temas.CENAS and c["paleta"] for c in capas)
    pares = [(c["cena"], str(c["paleta"])) for c in capas]
    assert len(set(pares)) == len(pares), "duas áreas ficaram com a mesma capa"
    assert set(tema["cenas"]) <= set(temas.CENAS)


@pytest.mark.parametrize("tema", TEMAS, ids=lambda t: t["id"])
def test_cada_tema_tem_assinatura_e_previas_fieis(tema):
    # A capa que representa o tema é uma escolha do tema, não um sorteio, e é de uma cena do seu estilo.
    assinatura = tema["capas"]["boas-vindas"]
    assert assinatura["cena"] == tema["cenas"][0] and assinatura["paleta"] in tema["paletas"]
    assert temas.previa(tema) == temas.resolver_capa(tema, "boas-vindas")
    # Uma prévia por cena, as do estilo do tema primeiro, iguais ao que a área recebe ao salvar a cena.
    previas = temas.previas_das_cenas(tema, "tarefas")
    assert [p["cena"] for p in previas[: len(tema["cenas"])]] == tema["cenas"]
    assert sorted(p["cena"] for p in previas) == sorted(temas.CENAS)
    assert all(p == temas.resolver_capa(tema, "tarefas", {"cena": p["cena"]}) for p in previas)
    # As paletas de um tema são de fato diferentes entre si (nada de quatro cópias do mesmo céu).
    assert len({tuple(p["ceu"]) for p in tema["paletas"].values()}) == len(tema["paletas"]) >= 4


def test_temas_sao_distintos_entre_si():
    assinaturas = [(t["capas"]["boas-vindas"]["cena"], t["cores"]["fundo"], t["cores"]["destaque"]) for t in TEMAS]
    assert len({a[0] for a in assinaturas}) == len(TEMAS), "dois temas com a mesma cena de assinatura"
    assert len({a[1] for a in assinaturas}) == len(TEMAS) == len({a[2] for a in assinaturas})


def test_colecao_tem_uma_peca_por_tema_e_os_arquivos_existem():
    arte = Path(temas.__file__).parent / "static" / "arte"
    assert {p["tema"] for p in temas.COLECAO} == {t["id"] for t in TEMAS}
    assert all((arte / p["arquivo"]).is_file() and p["alt"] and p["nome"] for p in temas.COLECAO)
    assert {p.name for p in arte.iterdir()} == {p["arquivo"] for p in temas.COLECAO} | {"README.md"}
    assert [p["tema"] for p in temas.colecao("luz")][0] == "luz"
    assert temas.nome_cena("espaco") == "Espaço" and temas.nome_cena("mar") == "Mar"


def test_area_que_o_tema_nao_conhece_recebe_capa_livre_e_estavel():
    tema = TEMAS[0]
    usados = {(c["cena"], c["paleta"]) for c in tema["capas"].values()}
    nomes = {nome for nome, p in tema["paletas"].items()}
    for alvo in ["viagens", "treinos", "receitas", "qualquer-coisa"]:
        capa = temas.resolver_capa(tema, alvo)
        par = (capa["cena"], next(n for n in nomes if tema["paletas"][n] == capa["paleta"]))
        assert par not in usados and capa["cena"] in tema["cenas"]
        assert temas.resolver_capa(tema, alvo) == capa
    # Pasta da pessoa com nome conhecido usa a capa que o tema reservou para aquela área.
    visual = lambda alvo: {k: v for k, v in temas.resolver_capa(tema, alvo).items() if k != "semente"}  # noqa: E731
    assert visual("1. Projetos") == visual("projetos") and visual("Áreas") == visual("areas")
    # A escolha da própria área continua valendo, inclusive só a cena.
    assert temas.resolver_capa(tema, "x", {"cena": "aurora"})["cena"] == "aurora"
    assert temas.resolver_capa(tema, "x", "minha/capa.webp") == {"tipo": "imagem", "url": "/arquivo/minha/capa.webp"}


def test_as_cenas_do_python_existem_no_javascript():
    js = (Path(temas.__file__).parent / "static" / "js" / "cenas.js").read_text(encoding="utf-8")
    for cena in temas.CENAS:
        assert f"CENAS.{cena} = function" in js, cena


# ---------------------------------------------------------------- backup: só quando algo muda


def test_versao_local_so_quando_algo_mudou(painel, monkeypatch):
    feitos = []
    monkeypatch.setattr(backup, "e_repositorio", lambda vault: True)
    monkeypatch.setattr(backup, "resumo", lambda vault: {"confiavel": True})
    monkeypatch.setattr(backup, "commit", lambda vault, mensagem=None: feitos.append("commit") or "feito")
    agora = dt.datetime.now()

    asyncio.run(agenda.verificar(painel, agora))
    assert feitos == ["commit"]  # ao abrir, confere uma vez

    asyncio.run(agenda.verificar(painel, agora + dt.timedelta(hours=5)))
    assert feitos == ["commit"]  # nada mudou: o git nem é chamado, por mais tempo que passe

    painel.criar_nota("tarefas", "Mudou algo")
    asyncio.run(agenda.verificar(painel, agora + dt.timedelta(minutes=5)))
    assert feitos == ["commit"]  # mudou, mas ainda dentro do intervalo
    asyncio.run(agenda.verificar(painel, agora + dt.timedelta(minutes=45)))
    assert feitos == ["commit", "commit"]


# ---------------------------------------------------------------- coletores que não precisam de rede


def carregar_coletor(modulo: str, nome: str):
    """Importa um script de coletor do catálogo como se fosse um módulo."""
    pasta = preparo.CATALOGO / modulo / "maquina" / "coletores"
    sys.path.insert(0, str(pasta))
    sys.modules.pop("_comum", None)
    try:
        spec = importlib.util.spec_from_file_location(f"coletor_{nome}", pasta / f"{nome}.py")
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        return script
    finally:
        sys.path.remove(str(pasta))
        sys.modules.pop("_comum", None)


def test_regras_de_tarefas_recorrentes():
    cai = carregar_coletor("tarefas", "recorrentes").cai_hoje
    sexta, sabado, fim_de_fev = dt.date(2026, 11, 13), dt.date(2026, 11, 14), dt.date(2026, 2, 28)
    assert cai("todo dia", sabado) and cai("Sexta", sexta) and cai("sexta-feira", sexta) and not cai("sexta", sabado)
    assert cai("dia útil", sexta) and not cai("dia util", sabado) and cai("fim de semana", sabado)
    assert cai("segunda, sexta", sexta) and cai("terça e sábado", sabado) and not cai("segunda, quinta", sexta)
    assert cai("dia 13", sexta) and not cai("dia 5", sexta)
    assert cai("dia 31", fim_de_fev)  # mês curto: cai no último dia
    assert cai("quando der", sexta) is None and cai("dia x", sexta) is None


def test_leitura_de_agenda_ical():
    script = carregar_coletor("tarefas", "agenda_ics")
    texto = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:a1\r\nSUMMARY:Reunião\\, com a equipe que tem um nome mui\r\n to comprido\r\n"
        "DTSTART;TZID=America/Sao_Paulo:20260115T143000\r\nLOCATION:Sala 2\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:a2\r\nSUMMARY:Feriado\r\nDTSTART;VALUE=DATE:20260120\r\nSTATUS:CANCELLED\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    reuniao, feriado = script.eventos(texto)
    assert reuniao["summary"] == "Reunião, com a equipe que tem um nome muito comprido"
    assert reuniao["inicio"] == (dt.date(2026, 1, 15), "14:30") and reuniao["location"] == "Sala 2"
    assert feriado["inicio"] == (dt.date(2026, 1, 20), "") and feriado["status"] == "CANCELLED"
    assert script.quando("lixo", "") is None


def test_todo_coletor_do_catalogo_tem_o_script():
    for modulo_id in preparo.catalogo():
        modulo = carregar_modulo(preparo.CATALOGO / modulo_id)
        for coletor in modulo.coletores:
            script = preparo.CATALOGO / modulo_id / "maquina" / "coletores" / coletor.script
            assert script.is_file(), f"{modulo_id}/{coletor.script}"
            assert not coletor.ativo, "coletor do catálogo nasce desligado: quem liga é a pessoa"
            if "_comum" in script.read_text(encoding="utf-8"):
                assert (script.parent / "_comum.py").is_file()


# ---------------------------------------------------------------- dock compacto


def test_dock_mostra_tudo_quando_ha_poucas_areas(cliente):
    cliente.painel.desligar_modulo("numeros")
    resposta = cliente.get("/")
    pagina = resposta.text
    assert not resposta.context["dock"]["gaveta_desktop"]
    assert 'dock-so-mobile' in pagina and 'id="abrir-gaveta"' in pagina
    assert 'data-dica="Pastas"' in pagina and 'data-dica="Ajustes"' in pagina


def test_dock_compacta_quando_ha_muitas_areas(cliente, vault):
    from orquestra import apresentacao as ap
    from orquestra.config import definir_chave

    painel = cliente.painel
    for area in ["notas", "projetos", "clientes", "financas", "estudos"]:
        painel.adicionar_modulo(area)
    dock = ap.montar_dock(painel, "m:financas", dt.date.today())
    assert len(dock["modulos"]) == 10
    barra = [m["id"] for m in dock["barra"]]
    assert len(barra) == 6 and barra[-1] == "financas"  # as cinco primeiras, mais a área aberta
    assert [s["id"] for s in dock["sistema_barra"]] == ["calendario", "decidir"]
    assert {i["id"] for i in dock["gaveta"]} >= {"pastas", "diario", "ajustes", "estudos"}
    assert not dock["gaveta_ativa"]  # a área aberta está visível na barra

    definir_chave(vault / "orquestra.yaml", "dock", ["estudos", "tarefas", "nao-existe"])
    painel.recarregar_config()
    dock = ap.montar_dock(painel, "ajustes", dt.date.today())
    assert [m["id"] for m in dock["barra"]] == ["estudos", "tarefas"] and dock["gaveta_ativa"]

    pagina = cliente.get("/ajustes").text
    assert 'id="abrir-gaveta"' in pagina and 'class="gaveta"' in pagina and "Finanças" in pagina
    assert "_gaveta" in cliente.get("/api/resumo").json()["selos"]
