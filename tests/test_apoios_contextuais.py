"""Notas relacionadas pertencem ao contexto, preservando status e arquivos originais."""
import datetime as dt
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import pytest

from orquestra import habitos
from orquestra.config import gravar_yaml, ler_yaml
from orquestra.mcp_servidor import Ferramentas


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


def test_anotar_realizacao_no_dia_do_mapa_ou_hoje_preserva_o_habito(cliente):
    painel = cliente.painel
    item = cliente.post("/api/habitos", json={"titulo": "Academia", "descricao": "Treinar com regularidade."}).json()["item"]
    outro = cliente.post("/api/habitos", json={"titulo": "Caminhada"}).json()["item"]
    habito = painel.nota(item["rel"])
    antes = habito.caminho.read_bytes()
    agora = dt.date.today()
    ontem = (agora - dt.timedelta(days=1)).isoformat()
    painel_habitos = cliente.get("/m/habitos").text
    assert f'href="{item["url"]}?dia={ontem}" tabindex="-1"' in painel_habitos
    assert f'data-dia="{ontem}"' in cliente.get(item["url"], params={"dia": ontem}).text

    rota = "/api/habitos/realizacoes/notas"
    dados = {"rel": habito.rel, "texto": "Treino de perna\n\nTambém conversei sobre [[Caminhada]]."}
    primeira = cliente.post(rota, json={**dados, "data": ontem})
    assert primeira.status_code == 200
    registro = primeira.json()
    nota = painel.nota(registro["rel"])
    assert nota.rel.startswith("habitos/execucoes/Academia/")
    assert registro["data"] == nota.campo("data") == ontem
    assert nota.campo("habito") == f"[[{habito.rel.removesuffix('.md')}]]"
    assert nota.corpo.strip() == dados["texto"]
    assert cliente.get(outro["url"], params={"dia": ontem}).context["relacionadas"] == []
    hoje = cliente.post(rota, json={**dados, "texto": "Treino de braço"}).json()
    assert hoje["data"] == agora.isoformat()
    assert [n["rel"] for n in cliente.get(item["url"], params={"dia": ontem}).context["relacionadas"]] == [nota.rel]
    assert cliente.post(rota, json={**dados, "data": (agora + dt.timedelta(days=1)).isoformat()}).status_code == 400
    assert habito.caminho.read_bytes() == antes


def test_notas_de_realizacao_paginam_com_datas_recentes_primeiro(cliente):
    item = cliente.post("/api/habitos", json={"titulo": "Leitura"}).json()["item"]
    hoje = dt.date.today()
    for dias in (5, 1, 7, 0, 4, 8, 2, 6, 3):
        data = hoje - dt.timedelta(days=dias)
        apoio(cliente.painel, f"habitos/execucoes/Leitura/Leitura {data}.md", "Registro de exemplo.")
    primeira = cliente.get(item["url"]).context
    assert [n["data"] for n in primeira["relacionadas"]] == [(hoje - dt.timedelta(days=d)).isoformat() for d in range(6)]
    seguinte = cliente.get(primeira["paginacao_relacionadas"]["proxima"]).context
    assert [n["data"] for n in seguinte["relacionadas"]] == [(hoje - dt.timedelta(days=d)).isoformat() for d in range(6, 9)]
    assert seguinte["paginacao_relacionadas"]["anterior"]


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


def test_projeto_reune_tarefas_vinculadas_nos_dois_sentidos_sem_duplicar(cliente):
    painel = cliente.painel
    painel.adicionar_modulo("projetos")
    projeto = painel.criar_nota("projetos", "Triagem da semana", corpo=(
        "## Mapa inicial\n\n"
        "[Rever prazos](../../tarefas/itens/Rever%20prazos.md)\n"
        "[[tarefas/itens/Conferir retornos]]"
    ))
    antes = projeto.caminho.read_bytes()
    ferramentas = Ferramentas(painel.vault)
    criada = ferramentas.criar_item("tarefas", "Rever prazos", texto="[[projetos/itens/Triagem da semana]]")
    apoio(painel, "tarefas/itens/Conferir retornos.md", "---\nstatus: feito\n---\n")
    apoio(painel, "tarefas/itens/Reunir pendências.md", "---\nprojeto: '[[Triagem da semana]]'\n---\n")
    apoio(painel, "tarefas/itens/Outras compras.md", "Sem vínculo")
    apoio(painel, "tarefas/arquivo/Passo antigo.md", "[[Triagem da semana]]")
    painel.indice.sincronizar()
    for url, parametros in (
        ("/m/projetos", {"abrir": projeto.rel, "aba": "v0"}),
        ("/m/projetos", {"abrir": projeto.rel, "aba": "v1"}),
        ("/n/" + projeto.rel, {}),
    ):
        resposta = cliente.get(url, params=parametros)
        assert resposta.status_code == 200
        assert "Tarefas do projeto" in resposta.text
        tarefas = resposta.context["tarefas_vinculadas"]
        assert [t["titulo"] for t in tarefas] == ["Conferir retornos", "Reunir pendências", "Rever prazos"]
        assert tarefas[0]["status"] == "feito"

    for rel in (criada["caminho"], "tarefas/itens/Conferir retornos.md", "tarefas/itens/Reunir pendências.md"):
        assert [n.rel for n in cliente.get("/n/" + rel).context["projetos_vinculados"]] == [projeto.rel]
    conexoes = ferramentas.conexoes_nota(projeto.rel)
    assert criada["caminho"] in {n["caminho"] for n in conexoes["entradas"]["itens"]}
    assert criada["caminho"] in {n["caminho"] for n in conexoes["saidas"]["itens"]}
    assert projeto.caminho.read_bytes() == antes


def test_pergunta_aparece_no_contexto_e_em_decidir_sem_criar_outra_nota(cliente):
    painel = cliente.painel
    painel.adicionar_modulo("projetos")
    projeto = painel.criar_nota("projetos", "Organização semanal")
    tarefa = painel.criar_nota("tarefas", "Reservar horário", corpo="[[Organização semanal]]")
    ferramentas = Ferramentas(painel.vault)
    assert "ordem de triagem" in ferramentas.regras()
    assert "próximo passo executável" in ferramentas.contexto_area("projetos")["orientacao"]

    pergunta_projeto = "Qual entrega pode esperar até a próxima semana?"
    pergunta_tarefa = "Reservo terça ou quinta?"
    ferramentas.perguntar(projeto.rel, pergunta_projeto)
    ferramentas.perguntar(tarefa.rel, pergunta_tarefa)
    painel.indice.sincronizar()
    caminhos_antes = set(painel.indice.notas)

    pasta = cliente.get("/m/projetos", params={"abrir": projeto.rel})
    assert pergunta_projeto in pasta.text and pergunta_tarefa in pasta.text
    link_tarefa = pasta.context["tarefas_vinculadas"][0]["decisao_pendente"]
    resposta = cliente.get(link_tarefa)
    assert resposta.context["total"] == 1
    cartao = resposta.context["grupos"][0]["cartoes"][0]
    assert cartao["rel"] == tarefa.rel and pergunta_tarefa in resposta.text
    assert pergunta_projeto not in resposta.text and projeto.titulo in resposta.text
    fila = ferramentas.fila_de_decisoes()
    assert {item["caminho"] for item in fila} >= {projeto.rel, tarefa.rel}

    resposta = cliente.put("/api/notas/" + tarefa.rel, json={
        "versao": cartao["versao"], "campos": {"resposta": "Terça.", "pergunta": ""},
    })
    assert resposta.status_code == 200
    assert cliente.get(link_tarefa).context["total"] == 0
    assert pergunta_tarefa not in cliente.get("/m/projetos", params={"abrir": projeto.rel}).text
    assert ferramentas.ler_nota(tarefa.rel)["campos"]["resposta"] == "Terça."
    assert set(painel.indice.notas) == caminhos_antes
