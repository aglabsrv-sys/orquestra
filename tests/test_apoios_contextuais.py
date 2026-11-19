"""Notas relacionadas pertencem ao contexto, preservando status e arquivos originais."""
import datetime as dt
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import pytest

from orquestra import habitos
from orquestra.config import gravar_yaml, ler_yaml


@pytest.fixture(autouse=True)
def area_notas(cliente):
    if "notas" not in cliente.painel.indice.modulos:
        cliente.painel.adicionar_modulo("notas")


def apoio(painel, rel, texto):
    p = painel.vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8")
    painel.apos_escrita(p, "externo")
    return p


def test_execucao_aparece_no_habito_e_na_data_sem_marcar_automaticamente(cliente):
    painel = cliente.painel
    criado = cliente.post("/api/habitos", json={"titulo": "Academia", "meta_semanal": 3}).json()
    rel = criado["item"]["rel"]
    hoje = dt.date.today().isoformat()
    nota = apoio(painel, f"habitos/execucoes/Academia/Sessão sintética - {hoje}.md",
                 f"---\nstatus: publicado\ndata: {hoje}\n---\n[[Academia]]\n\nExercício fictício, ação e evolução.\n")
    ontem = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    apoio(painel, f"habitos/execucoes/Academia/Sessão anterior - {ontem}.md", "Outra nota.")
    antes = nota.read_bytes()
    contexto = habitos.montar(painel)
    item = next(i for i in contexto["itens"] if i["rel"] == rel)
    assert item["dias_com_notas"] == [ontem, hoje] and item["semana"] == 0
    assert len(painel.indice.itens("habitos")) == 1
    card = cliente.get("/m/habitos").text
    assert "Sessão sintética" not in card and "Notas das realizações" not in card
    assert f'href="{item["url"]}?dia={hoje}"' in card
    todas = cliente.get("/n/" + rel)
    assert 'class="nota nota-habito"' in todas.text and "Sessão anterior" in todas.text and "Sessão sintética" in todas.text
    resposta = cliente.get("/n/" + rel, params={"dia": hoje})
    assert resposta.status_code == 200
    assert "Exercício fictício" not in resposta.text  # a nota de execução é ligada, não copiada.
    assert "Sessão sintética" in resposta.text
    assert "Sessão anterior" not in resposta.text and "Todas as notas" in resposta.text
    assert "Nenhuma nota nesta data" in cliente.get("/n/" + rel, params={"dia": "2020-01-01"}).text
    assert "Sessão sintética" not in cliente.get("/m/notas").text
    assert nota.read_bytes() == antes


def test_referencia_e_apoio_de_projeto_nao_recebem_schema_de_cartao(cliente):
    painel = cliente.painel
    if "projetos" not in painel.indice.modulos:
        painel.adicionar_modulo("projetos")
    projeto = painel.criar_nota("projetos", "Projeto fictício", {"status": "ativo"})
    ref = apoio(painel, "projetos/referencias/Projetos pessoais/Projeto fictício/Apoio.md",
                "---\nstatus: publicado\n---\n[[Projeto fictício]]\nConteúdo de referência, sem conversão.\n")
    antes = ref.read_bytes()
    assert ref.relative_to(painel.vault).as_posix() not in {n.rel for n in painel.indice.itens("projetos")}
    # Em Pastas, a nota de apoio aparece dentro da pasta do projeto, sem aba própria.
    resposta = cliente.get("/m/projetos?aba=v0")
    assert resposta.status_code == 200 and "Apoio" in resposta.text and "?aba=referencias" not in resposta.text
    assert "Notas de apoio" in cliente.get("/n/" + projeto.rel).text
    ref_rel = ref.relative_to(painel.vault).as_posix()
    assert "Revise estas propriedades" not in cliente.get("/n/" + ref_rel).text
    assert ref.read_bytes() == antes


def test_referencias_permanecem_fora_dos_itens_em_area_adotada(cliente):
    painel = cliente.painel
    arquivo = painel.modulo("notas").pasta / "_modulo.yaml"
    dados = ler_yaml(arquivo)
    dados["itens"] = "."
    gravar_yaml(arquivo, dados)
    painel.recarregar_tudo()
    p = apoio(painel, "notas/referencias/Base/Apoio.md", "Conteúdo sintético.")
    assert painel.indice.zona_de(p.relative_to(painel.vault).as_posix()) == "referencias"
    assert cliente.get("/m/notas?aba=referencias").status_code == 200


def test_link_para_pastas_transporta_unicode_sem_obsidian(cliente):
    nota = cliente.painel.criar_nota("notas", "Ação, saúde e café", corpo="Descrição com ç, ã, é e 🚀.")
    resposta = cliente.get("/n/" + nota.rel)
    class Links(HTMLParser):
        href = ""

        def handle_starttag(self, tag, attrs):
            atributos = dict(attrs)
            if tag == "a" and atributos.get("aria-label") == "Mostrar esta nota na pasta":
                self.href = atributos["href"]

    links = Links()
    links.feed(resposta.text)
    assert parse_qs(urlsplit(links.href).query)["nota"] == [nota.rel]
    assert "Descrição com ç, ã, é e 🚀." in resposta.text
    assert "obsidian://" not in resposta.text
    assert urlsplit(links.href).path == "/pastas"
    assert '<dialog class="nota-propriedades"' in resposta.text


def test_estudos_exibem_notas_no_contexto_sem_aba_referencias(cliente):
    painel = cliente.painel
    if "estudos" not in painel.indice.modulos:
        painel.adicionar_modulo("estudos")
    estudo = painel.criar_nota("estudos", "Curso sintético", {})
    arquivo = apoio(painel, "estudos/referencias/Curso sintético/Aula.md", "[[Curso sintético]]\nAnotações da aula.")
    antes = arquivo.read_bytes()
    pagina = cliente.get("/m/estudos")
    # A referência pertence ao estudo: só aparece dentro dele.
    assert "Notas de estudo" not in pagina.text and "Aula" not in pagina.text
    assert "?aba=referencias" not in pagina.text
    assert "Aula" in cliente.get("/n/" + estudo.rel).text
    assert arquivo.read_bytes() == antes
