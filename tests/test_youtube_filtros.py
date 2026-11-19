"""Filtro opcional do YouTube mantém a coleta e os IDs quando não é usado."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from xml.sax.saxutils import escape

import pytest


@pytest.fixture
def coletar(monkeypatch):
    def rodar(titulos, termos=None, maximo=2):
        itens = []
        helper = ModuleType("_comum")
        helper.CONFIG = {"canais": ["UC" + "a" * 22], "maximo_por_canal": maximo}
        if termos is not None:
            helper.CONFIG["titulos_contem"] = termos
        entradas = "".join(
            f"<entry><title>{escape(titulo)}</title><yt:videoId>video-{i}</yt:videoId>"
            "<published>2026-11-18T10:00:00Z</published>"
            "<media:group><media:description>Descrição sem efeito no filtro.</media:description>"
            "</media:group></entry>" for i, titulo in enumerate(titulos)
        )
        feed = ('<feed xmlns="http://www.w3.org/2005/Atom" '
                'xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
                'xmlns:media="http://search.yahoo.com/mrss/"><title>Canal de teste</title>'
                + entradas + '</feed>').encode()
        helper.baixar = lambda url: feed
        helper.emitir = lambda **item: itens.append(item)
        helper.avisar = lambda mensagem: pytest.fail(mensagem)
        monkeypatch.setitem(sys.modules, "_comum", helper)
        caminho = Path(__file__).parents[1] / "src/orquestra/catalogo/radar/maquina/coletores/youtube_rss.py"
        spec = importlib.util.spec_from_file_location("youtube_filtrado", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.main()
        return itens
    return rodar


@pytest.mark.parametrize("termos", [None, [], ["", "  "]])
def test_filtro_vazio_preserva_coleta_e_identidade(coletar, termos):
    itens = coletar(["Primeiro", "Segundo", "Terceiro"], termos)
    assert [i["titulo"] for i in itens] == ["Primeiro", "Segundo"]
    assert [i["id"] for i in itens] == ["youtube:video-0", "youtube:video-1"]


def test_filtra_antes_do_limite_ignorando_caixa_acentos_e_espacos(coletar):
    itens = coletar(["Notícias", "AUTOMAÇÃO com Python", "Outro assunto", "Inteligência   artificial"],
                    [" automacao ", "inteligencia artificial"])
    assert [i["id"] for i in itens] == ["youtube:video-1", "youtube:video-3"]
    assert all(i["canal"] == "Canal de teste" and i["fonte"] == "youtube" for i in itens)


def test_termos_sao_literais_e_descricao_nao_participa(coletar):
    assert [i["titulo"] for i in coletar(["C++ moderno", "Python", "Outros"], ["c++"])] == ["C++ moderno"]
    assert coletar(["Python"], ["descrição"]) == []
    assert coletar(["Python"], [".*"]) == []


@pytest.mark.parametrize("valor", ["python", [42], [None], {"termo": "python"}])
def test_api_recusa_formato_invalido_sem_gravar(cliente, valor):
    resposta = cliente.post("/api/automacoes/prever", json={
        "definicao": "radar/youtube_rss.py", "destino": "radar/itens",
        "config": {"titulos_contem": valor},
    })
    assert resposta.status_code == 400


def test_catalogo_expoe_filtro_opcional_sem_nova_automacao(cliente):
    catalogo = cliente.get("/api/automacoes/catalogo").json()["catalogo"]
    assert len(catalogo) == 9
    youtube = next(c for c in catalogo if c["id"] == "radar/youtube_rss.py")
    filtro = next(p for p in youtube["parametros"] if p["nome"] == "titulos_contem")
    assert filtro["tipo"] == "lista" and filtro["padrao"] == []
    assert youtube["requer"] == []
    previa = cliente.post("/api/automacoes/prever", json={
        "definicao": youtube["id"], "destino": "radar/itens",
        "config": {"titulos_contem": ["Python", "Inteligência artificial"]},
    })
    assert previa.status_code == 200
    assert previa.json()["config"]["titulos_contem"] == ["Python", "Inteligência artificial"]
