"""Vaults de vários formatos: perfis, vault que já existia, pastas adotadas, boas-vindas e MCP."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from orquestra import adocao, backup, diario, graficos, preparo
from orquestra.coletores import importar
from orquestra.config import ler_config_painel, localizar_vault
from orquestra.hospedeiro import Hospedeiro
from orquestra.indice import deve_ignorar
from orquestra.mcp_servidor import ErroDeFerramenta, Ferramentas
from orquestra.modulos import ColetorDef, descobrir
from orquestra.notas import gravar_nota, ler_nota
from orquestra.painel import Painel, Recusado
from orquestra.servidor import criar_app

NOTAS_DA_PESSOA = {
    "1. Projetos/Reforma da cozinha.md": "---\nstatus: em andamento\nprazo: 2026-12-20\ntags: [casa]\n---\nOrçamentos e medidas.\n",
    "1. Projetos/Curso de fotografia.md": "---\nstatus: ideia\nprazo: 2027-02-01\n---\nVer turmas de sábado.\n",
    "1. Projetos/Site novo/Briefing.md": "---\nstatus: em andamento\n---\nPáginas: início, sobre, contato.\n",
    "1. Projetos/Viagem.md": "---\nstatus: concluido\n---\nPassagens compradas.\n",
    "2. Áreas/Saúde.md": "Treino 3x por semana.\n",
    "3. Recursos/Livro.md": "---\nautor: Fulano\nnota: 9\nlido: true\n---\nResumo meu.\n",
    "3. Recursos/Artigo.md": "---\nautor: Beltrano\nnota: 7\nlido: false\n---\n",
    "4. Arquivo/Mudança.md": "Checklist antiga.\n",
    "Solta.md": "Uma nota na raiz.\n",
}


@pytest.fixture
def isolado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Nada dos testes toca a configuração real da máquina, nem o git."""
    monkeypatch.setenv("ORQUESTRA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ORQUESTRA_VAULT", raising=False)
    monkeypatch.setattr(backup, "iniciar", lambda vault: False)
    monkeypatch.setattr(preparo, "cofres_obsidian", lambda: [])
    return tmp_path


@pytest.fixture
def cofre(isolado: Path) -> Path:
    """Um vault "do Obsidian" que a pessoa já usava, no estilo PARA."""
    pasta = isolado / "MeuCofre"
    for rel, texto in NOTAS_DA_PESSOA.items():
        arquivo = pasta / rel
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(texto.encode("utf-8"))
    (pasta / ".obsidian").mkdir()
    return pasta


def intacto(pasta: Path) -> bool:
    return all((pasta / rel).read_bytes() == texto.encode("utf-8") for rel, texto in NOTAS_DA_PESSOA.items())


def autorizar_canal_local(cliente: TestClient) -> None:
    """Obtém a capacidade do peer local real, sem fabricar tokens nos testes."""
    resposta = cliente.get("/api/local/capacidade")
    assert resposta.status_code == 200
    cliente.headers["X-Orquestra-Local"] = resposta.json()["token"]


# ---------------------------------------------------------------- perfis e catálogo


def test_todo_perfil_so_usa_modulos_que_existem():
    disponiveis = preparo.catalogo()
    assert {"tarefas", "notas", "projetos", "numeros", "entrada"} <= set(disponiveis)
    for perfil in preparo.perfis().values():
        assert set(perfil.modulos) <= set(disponiveis), perfil.id
    assert preparo.perfis()["vazio"].modulos == []


def test_todo_modulo_do_catalogo_carrega_sem_avisos(isolado):
    relatorio = preparo.preparar(isolado / "tudo", list(preparo.catalogo()), exemplos=True, com_backup=False)
    modulos = descobrir(relatorio.vault)
    assert set(modulos) == set(preparo.catalogo())
    for modulo in modulos.values():
        assert modulo.avisos == [], modulo.id
        assert (modulo.pasta / "maquina" / "aprendizados.md").is_file(), modulo.id
        assert (modulo.pasta / "maquina" / "instrucoes.md").is_file(), modulo.id


def test_perfil_essencial_sem_exemplos_nasce_vazio(isolado):
    relatorio = preparo.preparar(isolado / "v", preparo.modulos_do_perfil("essencial"), exemplos=False, nome="Casa", tema="mare")
    vault = relatorio.vault
    assert relatorio.novo
    assert list(descobrir(vault)) == ["tarefas", "notas", "entrada"]
    assert not list((vault / "tarefas" / "itens").glob("*.md"))
    assert (vault / "tarefas" / "humano" / "Como eu priorizo.md").is_file()  # o que orienta os agentes fica
    cfg = ler_config_painel(vault)
    assert (cfg.nome, cfg.tema, cfg.captura) == ("Casa", "mare", "entrada")
    assert "`notas/`" in (vault / "Comece aqui.md").read_text(encoding="utf-8")


def test_exemplos_de_numeros_nascem_com_datas_de_hoje(isolado):
    vault = preparo.preparar(isolado / "v", ["numeros"]).vault
    hoje = dt.date.today()
    assert (vault / "numeros" / "itens" / f"{hoje.isoformat()}.md").is_file()
    assert (vault / "numeros" / "itens" / f"{(hoje - dt.timedelta(days=7)).isoformat()}.md").is_file()


# ---------------------------------------------------------------- vault que já existia


def test_analisar_reconhece_o_estilo_e_nao_altera_nada(cofre):
    info = preparo.analisar(cofre)
    assert info["notas"] == 9 and info["soltas"] == 1 and info["obsidian"] and not info["ja_e_vault"]
    assert info["estilo"]["id"] == "para"
    projetos = next(p for p in info["pastas"] if p["pasta"] == "1. Projetos")
    assert projetos["notas"] == 4 and projetos["tem_status"] and projetos["nome"] == "Projetos"
    assert intacto(cofre)
    assert sorted(p.name for p in cofre.iterdir()) == [".obsidian", "1. Projetos", "2. Áreas", "3. Recursos", "4. Arquivo", "Solta.md"]


def test_preparar_vault_existente_so_acrescenta(cofre):
    relatorio = preparo.preparar(
        cofre, ["tarefas", "entrada"], exemplos=False, com_backup=False, pastas=[{"pasta": "1. Projetos"}, {"pasta": "3. Recursos"}]
    )
    assert not relatorio.novo
    assert intacto(cofre)
    assert (cofre / "AGENTS.md").is_file() and (cofre / "orquestra.yaml").is_file()
    assert list(descobrir(cofre)) == ["tarefas", "entrada", "1. Projetos", "3. Recursos"]
    # Num vault que a pessoa já usa, o painel não liga commit automático por conta própria.
    assert ler_config_painel(cofre).backup.auto_commit is False


def test_agents_da_pessoa_e_respeitado(cofre):
    (cofre / "AGENTS.md").write_text("Minhas regras.\n", encoding="utf-8")
    relatorio = preparo.preparar(cofre, [], com_backup=False)
    assert (cofre / "AGENTS.md").read_text(encoding="utf-8") == "Minhas regras.\n"
    assert (cofre / "AGENTS.orquestra.md").is_file()
    assert any("AGENTS.orquestra.md" in a for a in relatorio.avisos)


def test_modulo_pronto_nao_passa_por_cima_de_pasta_existente(cofre):
    (cofre / "Tarefas").mkdir()
    (cofre / "Tarefas" / "Comprar pão.md").write_text("hoje\n", encoding="utf-8")
    relatorio = preparo.preparar(cofre, ["tarefas"], com_backup=False)
    assert not (cofre / "Tarefas" / "_modulo.yaml").exists()
    assert any("Tarefas" in a for a in relatorio.avisos)


def test_pasta_recusada():
    for ruim in ["", "relativa/pasta", str(Path.home()), str(Path(Path.home().anchor))]:
        with pytest.raises(preparo.PastaRecusada):
            preparo.conferir_pasta(ruim)


def test_pasta_sem_preparo_nao_faz_commit_automatico(cofre):
    assert ler_config_painel(cofre).backup.auto_commit is False


# ---------------------------------------------------------------- pasta adotada como módulo


def test_inferir_descobre_campos_status_e_data(cofre):
    d = adocao.inferir(cofre / "1. Projetos")
    assert d["itens"] == "." and d["nome"] == "Projetos" and d["icone"] == "raio"
    assert d["campos"]["status"] == {"tipo": "escolha", "opcoes": ["ideia", "em andamento", "concluido"]}
    assert d["campos"]["prazo"]["tipo"] == "data" and d["campo_data"] == "prazo"
    assert d["status"]["concluidos"] == ["concluido"]
    assert [v["tipo"] for v in d["visoes"]] == ["kanban", "tabela"]

    recursos = adocao.inferir(cofre / "3. Recursos")
    assert {n: c["tipo"] for n, c in recursos["campos"].items()} == {
        "autor": "texto", "nota": "numero", "lido": "booleano", "origem": "escolha",
    }
    assert "status" not in recursos
    assert "status" in adocao.inferir(cofre / "3. Recursos", com_quadro=True)["campos"]


def test_estilos_de_organizacao():
    assert adocao.detectar_estilo(["10-19 Vida", "20-29 Trabalho", "30-39 Estudos"], ["a"]) == "johnny"
    assert adocao.detectar_estilo(["Atlas", "Calendar", "Efforts"], ["a"]) == "ace"
    assert adocao.detectar_estilo(["notas"], ["202401011200 ideia", "202401021200 outra", "x"]) == "zettel"
    assert adocao.detectar_estilo(["Diário"], ["2026-01-01", "2026-01-02", "2026-01-03"]) == "diario"
    assert adocao.detectar_estilo(["Coisas", "Mais coisas"], ["a", "b"]) == "livre"
    assert adocao.detectar_estilo([], []) == "vazio"


def test_modulo_sobre_pasta_existente(cofre):
    painel = Painel(cofre)
    modulo = painel.adotar_pasta("1. Projetos")
    assert modulo.itens_na_raiz and modulo.tem_status
    titulos = {n.titulo for n in painel.indice.itens(modulo.id)}
    assert titulos == {"Reforma da cozinha", "Curso de fotografia", "Briefing", "Viagem"}  # inclui a subpasta
    assert painel.indice.zona_de("1. Projetos/Site novo/Briefing.md") == "itens"
    resumo = painel.indice.resumo(modulo)
    assert (resumo.total, resumo.abertos) == (4, 3)

    nova = painel.criar_nota(modulo.id, "Pintar a sala", {"status": "ideia"})
    assert nova.rel == "1. Projetos/Pintar a sala.md"  # direto na pasta, sem itens/
    assert nova.meta["origem"] == "humano"
    assert intacto(cofre)

    arquivada = painel.arquivar(nova.rel)
    assert arquivada == "1. Projetos/arquivo/Pintar a sala.md"
    assert painel.indice.zona_de(arquivada) == "arquivo"


def test_desligar_e_religar_guarda_a_personalizacao(cofre):
    painel = Painel(cofre)
    painel.adotar_pasta("1. Projetos")
    painel.personalizar_modulo("1. Projetos", {"nome": "Meus projetos"})
    painel.desligar_modulo("1. Projetos")
    assert "1. Projetos" not in painel.indice.modulos
    assert intacto(cofre)
    assert painel.adotar_pasta("1. Projetos").nome == "Meus projetos"


def test_so_pasta_da_raiz_vira_area(cofre):
    painel = Painel(cofre)
    for ruim in ["", "nao-existe", "1. Projetos/Site novo", "_orquestra", ".obsidian", "diario"]:
        with pytest.raises(Recusado):
            painel.adotar_pasta(ruim)


def test_nota_em_pasta_que_nao_e_modulo(cofre):
    painel = Painel(cofre)
    nota = painel.criar_nota_em_pasta("2. Áreas", "Finanças", "Conferir o cartão.")
    assert nota.rel == "2. Áreas/Finanças.md"
    assert nota.caminho.read_text(encoding="utf-8") == "Conferir o cartão.\n"  # sem frontmatter imposto
    with pytest.raises(Exception):
        painel.criar_nota_em_pasta("../fora", "x")


def test_registro_nunca_e_tratado_como_mudanca():
    assert deve_ignorar("diario/registro/2026-01-01.md")
    assert deve_ignorar("Diario/Registro/2026-01-01.md")  # mesma pasta no Windows e no macOS
    assert deve_ignorar("_orquestra/estado.json") and deve_ignorar(".obsidian/app.json")
    assert not deve_ignorar("diario/sessoes/2026-01-01.md")


# ---------------------------------------------------------------- personalizar sem IA


def test_personalizar_preserva_comentarios_e_valida(painel, vault):
    painel.personalizar_modulo(
        "tarefas",
        {
            "nome": "Afazeres",
            "icone": "estrela",
            "cena": "mar",
            "campos": [{"nome": "status", "tipo": "escolha", "opcoes": "a_fazer, feito"}, {"nome": "esforco", "tipo": "numero"}],
            "remover": ["prioridade"],
            "concluidos": "feito, inexistente",
            "grafico": True,
        },
    )
    m = painel.modulo("tarefas")
    assert (m.nome, m.icone, m.capa["cena"]) == ("Afazeres", "estrela", "mar")
    assert m.campos["status"].opcoes == ["a_fazer", "feito"] and m.campos["status"].padrao == "a_fazer"
    assert "prioridade" not in m.campos and m.campos["esforco"].tipo == "numero"
    assert m.concluidos == ["feito"]
    assert [v.tipo for v in m.visoes] == ["kanban", "tabela", "grafico"]
    assert "# Módulo Tarefas." in (vault / "tarefas" / "_modulo.yaml").read_text(encoding="utf-8")

    for ruim in [{"campos": [{"nome": "x", "tipo": "dinheiro"}]}, {"campos": [{"nome": "y", "tipo": "escolha"}]}, {"cena": "lua"}]:
        with pytest.raises(Recusado):
            painel.personalizar_modulo("tarefas", ruim)


def test_criar_area_em_branco_e_acrescentar_pronta(painel):
    area = painel.criar_modulo("Viagens e Passeios", "estrela", com_quadro=True)
    assert area.id == "viagens-e-passeios" and area.tem_status and not area.avisos
    assert (area.pasta / "maquina" / "aprendizados.md").is_file()
    with pytest.raises(Recusado):
        painel.criar_modulo("Viagens e Passeios")

    assert painel.adicionar_modulo("financas", exemplos=True).nome == "Finanças"
    assert len(painel.indice.itens("financas")) == 3
    with pytest.raises(Recusado):
        painel.adicionar_modulo("financas")

    painel.definir_config(nome="Meu painel", captura="tarefas", auto_commit=False)
    assert (painel.config.nome, painel.config.captura, painel.config.backup.auto_commit) == ("Meu painel", "tarefas", False)


# ---------------------------------------------------------------- números e gráfico


def test_numeros_uma_nota_por_dia(painel):
    hoje = dt.date.today()
    antes = len(painel.indice.itens("numeros"))
    nota = painel.registrar_numeros("numeros", {"seguidores": "2100", "fora_do_schema": 1})
    assert nota.rel == f"numeros/itens/{hoje.isoformat()}.md" and nota.meta["seguidores"] == 2100
    assert "fora_do_schema" not in nota.meta
    assert len(painel.indice.itens("numeros")) == antes  # o dia de hoje já existia no exemplo: atualizou

    ontem = hoje - dt.timedelta(days=30)
    painel.registrar_numeros("numeros", {"receita": 12.5}, ontem)
    assert len(painel.indice.itens("numeros")) == antes + 1
    with pytest.raises(Recusado):
        painel.registrar_numeros("numeros", {})
    with pytest.raises(Recusado):
        painel.registrar_numeros("entrada", {"x": 1})


def test_grafico_um_quadro_por_numero(painel):
    modulo = painel.modulo("numeros")
    visao = next(v for v in modulo.visoes if v.tipo == "grafico")
    quadros = graficos.montar(painel.indice, modulo, visao, dt.date.today())
    assert [q["campo"] for q in quadros] == ["seguidores", "inscritos", "receita"]
    seguidores = quadros[0]
    assert len(seguidores["pontos"]) == 8 and seguidores["quando"] == "hoje"
    assert seguidores["variacao"]["direcao"] == "sobe" and seguidores["variacao"]["texto"].startswith("+")
    assert seguidores["linha"].startswith("M") and seguidores["pontos"][-1]["x"] == seguidores["fim"]["x"]
    # O eixo vai do primeiro registro até hoje, ocupando a largura toda.
    assert seguidores["pontos"][0]["x"] == graficos.MARGEM_ESQ
    assert seguidores["pontos"][-1]["x"] == graficos.LARGURA - graficos.MARGEM_DIR


def test_formato_brasileiro_de_numero():
    assert graficos.numero(1284) == "1.284"
    assert graficos.numero(119.9) == "119,90"
    assert graficos.numero(12900, compacto=True) == "12,9 mil"
    assert graficos.numero(4_200_000, compacto=True) == "4,2 mi"
    assert graficos.numero(2000, compacto=True) == "2.000"


def test_coletor_com_atualizar_completa_a_nota_do_dia(painel):
    modulo = painel.modulo("numeros")
    coletor = ColetorDef(script="youtube_canal.py", nome="teste")
    hoje = dt.date.today().isoformat()
    item = {"id": f"numeros:{hoje}", "titulo": hoje, "atualizar": True, "campos": {"dia": hoje, "inscritos": 5000}}
    antes = len(painel.indice.itens("numeros"))
    # Campos humanos preenchidos são protegidos. Este fluxo completa um vazio.
    atual = ler_nota(painel.vault / f"numeros/itens/{hoje}.md", painel.vault)
    atual.meta.pop("inscritos", None)
    gravar_nota(atual, versao_esperada=atual.versao)
    painel.apos_escrita(atual.caminho, "painel")

    criadas, repetidos = importar(painel.indice, modulo, coletor, [item])
    assert (len(criadas), repetidos) == (1, 0)
    for nota in criadas:
        painel.apos_escrita(nota.caminho, "coletor:teste")
    assert len(painel.indice.itens("numeros")) == antes  # completou a nota de hoje, não criou outra
    nota = painel.nota(f"numeros/itens/{hoje}.md")
    assert nota.meta["inscritos"] == 5000 and nota.meta["seguidores"] > 0 and nota.meta["origem"] == "humano"

    assert importar(painel.indice, modulo, coletor, [item]) == ([], 1)  # nada mudou: conta como repetido


# ---------------------------------------------------------------- páginas e API


def test_paginas_de_um_vault_adotado(cofre):
    preparo.preparar(cofre, ["entrada"], com_backup=False, pastas=[{"pasta": "1. Projetos"}])
    with TestClient(criar_app(cofre, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        inicio = c.get("/").text
        assert "Suas pastas" in inicio and "Projetos" in inicio
        assert "Reforma da cozinha" in c.get("/m/" + quote("1. Projetos")).text
        pastas = c.get("/pastas").text
        assert "Mostrar no painel" in pastas and "2. Áreas" in pastas and "Solta" in pastas
        assert "Saúde" in c.get("/pastas/" + quote("2. Áreas")).text
        assert "Briefing" in c.get("/pastas/" + quote("1. Projetos/Site novo")).text
        assert c.get("/pastas/nao-existe").status_code == 404
        assert c.get("/pastas/_orquestra").status_code == 404
        assert c.get("/n/" + quote("2. Áreas/Saúde.md")).status_code == 200
        assert c.get("/m/" + quote("1. Projetos") + "/personalizar").status_code == 200
        assert c.get("/ajustes").status_code == 200

        resumo = c.get("/api/pastas/resumo", params={"pasta": "3. Recursos"}).json()
        assert [x["nome"] for x in resumo["campos"]] == ["autor", "nota", "lido"] and not resumo["tem_status"]
        r = c.post("/api/pastas/adotar", json={"pasta": "3. Recursos", "quadro": True})
        assert r.status_code == 200 and c.get(r.json()["url"]).status_code == 200
        r = c.post("/api/pastas/nota", json={"pasta": "2. Áreas", "titulo": "Casa"})
        assert r.json()["rel"] == "2. Áreas/Casa.md"
    assert intacto(cofre)


def test_vault_sem_areas_convida_a_escolher(cofre):
    with TestClient(criar_app(cofre, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        assert "ainda não tem áreas" in c.get("/").text
        assert c.post("/api/captura", json={"texto": "x"}).status_code == 400


def test_api_de_areas_e_numeros(cliente):
    r = cliente.post("/api/modulos", json={"pronto": "notas", "exemplos": True})
    assert r.status_code == 200 and cliente.get(r.json()["url"]).status_code == 200
    r = cliente.post("/api/modulos", json={"nome": "Treinos", "icone": "coracao", "quadro": False})
    assert r.json()["id"] == "treinos"
    assert cliente.put("/api/modulos/treinos", json={"campos": [{"nome": "carga", "tipo": "numero"}], "grafico": True}).status_code == 200
    assert cliente.post("/api/numeros", json={"modulo": "treinos", "valores": {"carga": "80"}}).status_code == 200
    pagina = cliente.get("/m/treinos?aba=v1").text
    assert "numero-quadro" in pagina and "Primeiro registro" in pagina
    assert cliente.post("/api/modulos/treinos/desligar", json={}).status_code == 200
    assert cliente.get("/m/treinos").status_code == 404
    assert "Religar no painel" in cliente.get("/pastas").text
    assert cliente.post("/api/config", json={"nome": "Estúdio"}).status_code == 200
    assert "Estúdio" in cliente.get("/").text
    assert cliente.put("/api/modulos/tarefas", json={"campos": [{"nome": "a:b", "tipo": "texto"}]}).status_code == 400


# ---------------------------------------------------------------- boas-vindas e troca de vault


def test_sem_vault_tudo_leva_para_as_boas_vindas(isolado):
    with TestClient(Hospedeiro(None, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "/boas-vindas"
        pagina = c.get("/boas-vindas").text
        assert "Já tenho um vault do Obsidian" in pagina and "Criar um vault novo" in pagina
        assert c.get("/static/js/boasvindas.js").status_code == 200


def test_criar_vault_pela_tela_abre_o_painel(isolado):
    destino = isolado / "Novo"
    with TestClient(Hospedeiro(None, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        autorizar_canal_local(c)
        r = c.post(
            "/api/boas-vindas/concluir",
            json={"modo": "novo", "caminho": str(destino), "nome": "Meu canto", "tema": "noturno", "modulos": ["tarefas", "notas"], "exemplos": True},
        )
        assert r.status_code == 200 and r.json()["ok"]
        inicio = c.get("/")
        assert inicio.status_code == 200 and "Meu canto" in inicio.text and "Tarefas" in inicio.text
        assert "Trocar de vault" in c.get("/ajustes").text
        assert c.get("/boas-vindas").status_code == 200  # continua acessível, para trocar de vault
    assert localizar_vault() == destino.resolve()
    assert ler_config_painel(destino).tema == "noturno"


def test_adotar_vault_pela_tela(cofre):
    with TestClient(Hospedeiro(None, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        autorizar_canal_local(c)
        analise = c.post("/api/boas-vindas/analisar", json={"caminho": str(cofre)}).json()
        assert analise["estilo"]["id"] == "para" and analise["notas"] == 9
        r = c.post(
            "/api/boas-vindas/concluir",
            json={"modo": "existente", "caminho": str(cofre), "modulos": ["entrada"], "pastas": [{"pasta": "1. Projetos", "quadro": False}]},
        )
        assert r.status_code == 200
        assert "Reforma da cozinha" in c.get("/m/" + quote("1. Projetos")).text
    assert intacto(cofre)


def test_boas_vindas_recusa_o_que_nao_deve(isolado, cofre):
    with TestClient(Hospedeiro(None, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        autorizar_canal_local(c)
        # "novo" numa pasta que já tem arquivos: não pode passar por cima
        r = c.post("/api/boas-vindas/concluir", json={"modo": "novo", "caminho": str(cofre)})
        assert r.status_code == 400 and intacto(cofre) and not (cofre / "orquestra.yaml").exists()
        assert c.post("/api/boas-vindas/concluir", json={"modo": "existente", "caminho": str(isolado / "nao-existe")}).status_code == 400
        assert c.post("/api/boas-vindas/concluir", json={"modo": "novo", "caminho": str(Path.home())}).status_code == 400
        # Sem vault configurado, nenhum nome Tailscale foi permitido explicitamente.
        remoto = {"host": "maquina.rede.ts.net", "origin": "http://maquina.rede.ts.net"}
        assert c.get("/boas-vindas", headers=remoto).status_code == 403
        assert c.post("/api/boas-vindas/analisar", json={"caminho": str(cofre)}, headers=remoto).status_code == 403
        assert c.post("/api/boas-vindas/concluir", json={"modo": "existente", "caminho": str(cofre)}, headers=remoto).status_code == 403


def test_boas_vindas_remota_configurada_nao_recebe_capacidade(vault, cofre):
    config = vault / "orquestra.yaml"
    config.write_text(config.read_text(encoding="utf-8").replace("hosts_permitidos: []", "hosts_permitidos: [maquina.rede.ts.net]"), encoding="utf-8")
    with TestClient(Hospedeiro(vault, vigiar=False, agendar=False), base_url="http://maquina.rede.ts.net", client=("100.64.0.2", 50000)) as c:
        assert c.get("/boas-vindas").status_code == 200
        assert c.get("/api/local/capacidade").status_code == 403
        assert c.post("/api/boas-vindas/analisar", json={"caminho": str(cofre)}).status_code == 403
        assert c.post("/api/boas-vindas/concluir", json={"modo": "existente", "caminho": str(cofre)}).status_code == 403
    assert intacto(cofre) and not (cofre / "orquestra.yaml").exists()


def test_trocar_de_vault_sem_reiniciar(vault, cofre):
    with TestClient(Hospedeiro(vault, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        autorizar_canal_local(c)
        assert "Tarefas" in c.get("/").text
        c.post("/api/boas-vindas/concluir", json={"modo": "existente", "caminho": str(cofre), "pastas": [{"pasta": "3. Recursos"}]})
        assert c.get("/m/tarefas").status_code == 404
        assert c.get("/m/" + quote("3. Recursos")).status_code == 200


# ---------------------------------------------------------------- MCP: as regras aplicadas pelo código


@pytest.fixture
def mcp(vault: Path) -> Ferramentas:
    return Ferramentas(vault)


def test_mcp_cria_como_agente_e_respeita_o_schema(mcp):
    criado = mcp.criar_item("tarefas", "Revisar proposta", {"prioridade": "alta", "origem": "humano", "inventado": 1})
    assert criado["campos"]["origem"] == "agente" and criado["campos"]["status"] == "a_fazer"
    assert "inventado" in criado["ignorados"]
    with pytest.raises(ErroDeFerramenta, match="não é uma opção"):
        mcp.criar_item("tarefas", "Outra", {"status": "inexistente"})
    with pytest.raises(ErroDeFerramenta, match="Áreas deste vault"):
        mcp.criar_item("nao-existe", "x")
    assert "AGENTS.md" in mcp.regras() and "**tarefas**" in mcp.regras()


def test_mcp_nao_reescreve_o_que_e_da_pessoa(mcp, vault):
    dela = "tarefas/itens/Renovar o domínio do site.md"
    original = mcp.ler_nota(dela)["texto"]
    with pytest.raises(ErroDeFerramenta, match="não pode ser substituído"):
        mcp.atualizar_item(dela, novo_texto="Reescrito pelo agente.")
    with pytest.raises(ErroDeFerramenta, match="origem"):
        mcp.atualizar_item(dela, campos={"origem": "agente"})

    mcp.atualizar_item(dela, campos={"status": "fazendo"}, acrescentar="Vence dia 20.")
    depois = mcp.ler_nota(dela)
    assert depois["campos"]["status"] == "fazendo"
    assert depois["texto"].startswith(original.rstrip("\n")) and depois["texto"].rstrip().endswith("## Notas do agente\n\nVence dia 20.")

    humano = "tarefas/humano/Como eu priorizo.md"
    with pytest.raises(ErroDeFerramenta, match="só acrescentar"):
        mcp.atualizar_item(humano, campos={"status": "feito"})
    mcp.atualizar_item(humano, acrescentar="Ela disse que sexta é dia de revisão.")
    assert f"> Acrescentado por agente em {dt.date.today().isoformat()}:" in (vault / humano).read_text(encoding="utf-8")
    with pytest.raises(ErroDeFerramenta):
        mcp.atualizar_item("tarefas/maquina/instrucoes.md", acrescentar="x")

    # O que o próprio agente escreveu, ele pode reescrever.
    rascunho = mcp.criar_item("conteudo", "Roteiro teste", texto="v1")["caminho"]
    assert mcp.atualizar_item(rascunho, novo_texto="v2") and mcp.ler_nota(rascunho)["texto"].strip() == "v2"


def test_mcp_perguntas_captura_e_memoria(mcp, vault):
    antes = len(mcp.fila_de_decisoes())
    item = mcp.criar_item("tarefas", "Publicar o post")["caminho"]
    mcp.perguntar(item, "Publico hoje ou\namanhã?")
    assert len(mcp.fila_de_decisoes()) == antes + 1
    assert mcp.ler_nota(item)["campos"]["pergunta"] == "Publico hoje ou amanhã?"
    with pytest.raises(ErroDeFerramenta, match="escrita pela pessoa"):
        mcp.atualizar_item(item, campos={"resposta": "sim"})

    assert mcp.capturar("Ligar para a Marina")["campos"]["origem"] == "agente"
    assert mcp.capturar("comprar café", palavras_da_pessoa=True)["campos"]["origem"] == "humano"

    assert "numeros/itens" in mcp.registrar_numeros({"inscritos": 1000})["caminho"]
    with pytest.raises(ErroDeFerramenta, match="Campos de número disponíveis"):
        mcp.registrar_numeros({"curtidas": 3})

    mcp.registrar_aprendizado("conteudo", "Títulos com pergunta\n tiveram mais resposta.")
    assert f"- {dt.date.today().isoformat()}: Títulos com pergunta tiveram mais resposta." in mcp.aprendizados("conteudo")
    mcp.registrar_sessao("teste", "organizar o dia", "criei [[Publicar o post]]", "uma pergunta na fila")
    sessoes = mcp.sessoes_recentes(1)
    assert "· teste" in sessoes and "**Pendente:** uma pergunta na fila" in sessoes
    assert any(i["titulo"] == "Publicar o post" for i in mcp.listar_itens("tarefas", status="a_fazer"))


def test_mcp_enxerga_o_que_mudou_no_disco(mcp, vault):
    (vault / "tarefas/itens/Feita no Obsidian.md").write_text("---\nstatus: a_fazer\n---\n", encoding="utf-8")
    assert any(i["titulo"] == "Feita no Obsidian" for i in mcp.listar_itens("tarefas"))
    (vault / "tarefas/itens/Feita no Obsidian.md").unlink()
    assert not any(i["titulo"] == "Feita no Obsidian" for i in mcp.listar_itens("tarefas"))


def test_mudanca_do_mcp_nao_aparece_duas_vezes_no_diario(vault):
    diario.registrar(vault, "criado", "tarefas/itens/X.md", "", "agente:mcp")
    diario.registrar(vault, "criado", "tarefas/itens/X.md", "", "externo")  # o vigia do painel vendo a mesma mudança
    diario.registrar(vault, "editado", "tarefas/itens/X.md", "", "externo")  # outra mudança: esta entra
    entradas = [e for e in diario.ler_registro(vault, dt.date.today()) if e.rel == "tarefas/itens/X.md"]
    assert [(e.tipo, e.autor) for e in entradas] == [("editado", "externo"), ("criado", "agente:mcp")]
