"""Projetos em pastas e Estudos em cartões: organização sem quadro de status."""
import html
import re
from urllib.parse import parse_qs, urljoin, urlsplit

import pytest


def garantir(painel, modulo_id):
    if modulo_id not in painel.indice.modulos:
        painel.adicionar_modulo(modulo_id)
    return painel.modulo(modulo_id)


def escrever(painel, rel, texto):
    p = painel.vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8")
    painel.apos_escrita(p, "externo")
    return p


def test_catalogo_traz_pastas_em_projetos_e_cartoes_em_estudos(cliente):
    painel = cliente.painel
    assert garantir(painel, "projetos").visoes[0].tipo == "pastas"
    assert garantir(painel, "estudos").visoes[0].tipo == "cartoes"
    assert not any(v.tipo == "kanban" for v in painel.modulo("projetos").visoes)


def test_projeto_vira_pasta_com_notas_vinculadas_e_referencias_soltas_agrupadas(cliente):
    painel = cliente.painel
    garantir(painel, "projetos")
    projeto = painel.criar_nota("projetos", "Projeto sintético", {"status": "ativo"})
    escrever(painel, "projetos/referencias/Projeto sintético/Briefing.md", "Ideias fictícias.\n")
    escrever(painel, "projetos/referencias/Projeto sintético/Capa.md", "![capa](https://exemplo.invalid/capa.png)\n")
    solta = escrever(painel, "projetos/referencias/Arquivo antigo/Nota solta.md", "---\nstatus: publicado\n---\nTexto.\n")
    antes = solta.read_bytes()
    resposta = cliente.get("/m/projetos?aba=v0")
    pastas = resposta.context["pastas"]
    item = next(p for p in pastas if p["rel"] == projeto.rel)
    # A nota do projeto mora dentro da pasta, junto das vinculadas.
    assert item["total"] == 3 and item["estado"] == "Ativo"
    assert item["arquivos"][-1]["rel"] == projeto.rel
    assert item["imagem"] == "https://exemplo.invalid/capa.png"
    grupo = next(p for p in pastas if not p["item"])
    assert grupo["titulo"] == "Arquivo antigo" and grupo["arquivos"][0]["titulo"] == "Nota solta"
    assert 'class="gf-root' in resposta.text and 'class="quadro"' not in resposta.text
    # Entrada rápida é opcional: sem ajuste, todas as pastas têm a mesma face.
    assert 'class="gf-key gf-key--add"' not in resposta.text
    assert item["arte"] == "" and grupo["arte"] == ""  # imagem achada nas notas vale como capa
    assert solta.read_bytes() == antes
    dentro = cliente.get("/m/projetos", params={"aba": "v0", "abrir": projeto.rel})
    notas = dentro.context["pasta_aberta"]["notas"]
    assert notas[0]["rel"] == projeto.rel and notas[0]["principal"]
    assert {n["titulo"] for n in notas[1:]} == {"Briefing", "Capa"}
    assert 'class="pasta-dentro"' in dentro.text and "data-pasta-nova" in dentro.text
    grupo_aberto = cliente.get("/m/projetos", params={"aba": "v0", "abrir": "grupo:Arquivo antigo"})
    assert [n["titulo"] for n in grupo_aberto.context["pasta_aberta"]["notas"]] == ["Nota solta"]
    assert cliente.get("/m/projetos", params={"aba": "v0", "abrir": "tarefas/itens/x.md"}).status_code == 404


def test_mais_da_pasta_cria_nota_vinculada_ao_projeto(cliente):
    painel = cliente.painel
    garantir(painel, "projetos")
    projeto = painel.criar_nota("projetos", "Lançamento fictício", {})
    r = cliente.post("/api/captura", json={"texto": "Ideia para a capa\nUsar tons quentes.", "vinculo": projeto.rel})
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["rel"] == "projetos/referencias/Lançamento fictício/Ideia para a capa.md" and dados["versao"]
    nota = painel.indice.notas[dados["rel"]]
    assert nota.campo("projeto") == "[[Lançamento fictício]]"
    assert "Usar tons quentes." in nota.corpo
    pasta = next(p for p in cliente.get("/m/projetos?aba=v0").context["pastas"] if p["rel"] == projeto.rel)
    assert pasta["total"] == 2 and pasta["arquivos"][0]["titulo"] == "Ideia para a capa"
    assert len(painel.indice.itens("projetos")) == 1


def test_ajustes_da_pasta_ficam_no_modulo(cliente):
    painel = cliente.painel
    garantir(painel, "projetos")
    projeto = painel.criar_nota("projetos", "Pasta ajustável", {})
    sem_ajuste = next(p for p in cliente.get("/m/projetos?aba=v0").context["pastas"] if p["rel"] == projeto.rel)
    assert sem_ajuste["arte"] in {"aurora", "brasa", "ametista", "oceano"} and not sem_ajuste["entrada_rapida"]
    r = cliente.post("/api/modulos/projetos/pastas", json={"chave": projeto.rel, "arte": "oceano", "entrada_rapida": True})
    assert r.status_code == 200, r.text
    pagina = cliente.get("/m/projetos?aba=v0")
    pasta = next(p for p in pagina.context["pastas"] if p["rel"] == projeto.rel)
    assert pasta["arte"] == "oceano" and pasta["entrada_rapida"]
    assert 'data-arte="oceano"' in pagina.text and 'class="gf-key gf-key--add"' in pagina.text
    assert "oceano" in (painel.vault / "projetos/_modulo.yaml").read_text(encoding="utf-8")
    midia = painel.vault / "midia/capas/capa.png"
    midia.parent.mkdir(parents=True, exist_ok=True)
    midia.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    assert cliente.post("/api/modulos/projetos/pastas", json={"chave": projeto.rel, "imagem": "midia/capas/capa.png"}).status_code == 200
    pasta = next(p for p in cliente.get("/m/projetos?aba=v0").context["pastas"] if p["rel"] == projeto.rel)
    assert pasta["imagem"] == "/arquivo/midia/capas/capa.png" and pasta["arte"] == "" and not pasta["entrada_rapida"]
    dentro = cliente.get("/m/projetos", params={"aba": "v0", "abrir": projeto.rel})
    assert 'id="pasta-ajustes"' in dentro.text and dentro.context["pasta_aberta"]["ajuste"]["imagem"] == "midia/capas/capa.png"
    assert cliente.post("/api/modulos/projetos/pastas", json={"chave": projeto.rel, "arte": "inexistente"}).status_code == 400
    assert cliente.post("/api/modulos/projetos/pastas", json={"chave": "projetos/itens/Outra.md", "arte": "brasa"}).status_code == 404
    assert cliente.post("/api/modulos/projetos/pastas", json={"chave": projeto.rel, "imagem": "../fora.png"}).status_code in (400, 404)
    assert cliente.post("/api/modulos/projetos/pastas", json={"chave": projeto.rel}).status_code == 200
    assert "pastas:" not in (painel.vault / "projetos/_modulo.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("vinculo", ["tarefas/itens/Não existe.md", "../fora.md"])
def test_captura_vinculada_recusa_destino_invalido(cliente, vinculo):
    garantir(cliente.painel, "projetos")
    r = cliente.post("/api/captura", json={"texto": "Algo", "vinculo": vinculo})
    assert 400 <= r.status_code < 500


def test_estudos_em_cartoes_que_sao_pastas(cliente):
    painel = cliente.painel
    garantir(painel, "estudos")
    oratoria = painel.criar_nota("estudos", "Oratória sintética", {"materia": "Comunicação"})
    painel.criar_nota("estudos", "Inglês sintético", {"status": "dominado"})
    escrever(painel, "estudos/referencias/Base solta.md", "Texto.\n")
    resposta = cliente.get("/m/estudos?aba=v0")
    cartoes = resposta.context["pastas"]
    titulos = [c["titulo"] for c in cartoes]
    assert titulos.index("Inglês sintético") > titulos.index("Oratória sintética")  # concluídos no fim
    assert next(c for c in cartoes if c["titulo"] == "Oratória sintética")["apoio"] == "Comunicação"
    assert "Referências" in titulos  # referências soltas também viram pasta
    assert 'class="cartao-simples' in resposta.text and "abrir=" in resposta.text and 'class="quadro"' not in resposta.text
    dentro = cliente.get("/m/estudos", params={"aba": "v0", "abrir": oratoria.rel})
    assert dentro.context["pasta_aberta"]["notas"][0]["rel"] == oratoria.rel
    assert "data-pasta-nova" in dentro.text and "data-pasta-ajustes" in dentro.text
    assert "pasta-ajustes-nome" in dentro.text and "pasta-capas" not in dentro.text  # título sem opções de capa sem efeito


def test_lista_mostra_pastas_e_dentro_as_notas(cliente):
    painel = cliente.painel
    garantir(painel, "projetos")
    projeto = painel.criar_nota("projetos", "Projeto em lista", {})
    escrever(painel, "projetos/referencias/Projeto em lista/Ata.md", "Texto.\n")
    lista = cliente.get("/m/projetos?aba=v1")
    assert any(p["rel"] == projeto.rel for p in lista.context["pastas"])
    assert 'class="lista-pasta lista-pastas"' in lista.text and 'class="tabela"' not in lista.text
    dentro = cliente.get("/m/projetos", params={"aba": "v1", "abrir": projeto.rel})
    assert [n["titulo"] for n in dentro.context["pasta_aberta"]["notas"]] == ["Projeto em lista", "Ata"]
    assert 'class="lista-pasta"' in dentro.text
    # Dentro da pasta, ajustes e Novo são da pasta, não da área.
    assert "data-pasta-ajustes" in dentro.text and "data-pasta-nova" in dentro.text
    assert "/m/projetos/personalizar" not in dentro.text and 'id="abrir-novo"' not in dentro.text


def test_novo_em_area_de_pastas_cria_pasta_e_primeira_nota(cliente):
    painel = cliente.painel
    garantir(painel, "projetos")
    pagina = cliente.get("/m/projetos?aba=v0")
    assert "Nova pasta em Projetos" in pagina.text and "Criar pasta" in pagina.text
    r = cliente.post("/api/notas", json={"modulo": "projetos", "titulo": "Loja nova", "campos": {}, "corpo": "Briefing inicial\nPúblico e prazo.", "zona": "itens"})
    assert r.status_code == 200, r.text
    item = painel.indice.notas[r.json()["rel"]]
    assert item.titulo == "Loja nova" and not item.corpo.strip()
    nota = painel.indice.notas["projetos/referencias/Loja nova/Briefing inicial.md"]
    assert nota.campo("projeto") == "[[Loja nova]]" and nota.corpo.strip() == "Público e prazo."
    sem_texto = cliente.post("/api/notas", json={"modulo": "projetos", "titulo": "Vazio", "campos": {}, "corpo": "", "zona": "itens"})
    assert sem_texto.status_code == 200 and not (painel.vault / "projetos/referencias/Vazio").exists()


def test_capa_padrao_e_estavel_pelo_nome(cliente):
    painel = cliente.painel
    garantir(painel, "projetos")
    a = painel.criar_nota("projetos", "Alfa estável", {})
    primeira = {p["rel"]: p["arte"] for p in cliente.get("/m/projetos?aba=v0").context["pastas"]}
    painel.criar_nota("projetos", "Beta que muda a ordem", {})
    segunda = {p["rel"]: p["arte"] for p in cliente.get("/m/projetos?aba=v0").context["pastas"]}
    assert primeira[a.rel] == segunda[a.rel]


@pytest.mark.parametrize("modulo_id", ["projetos", "estudos"])
@pytest.mark.parametrize("grupo", [False, True])
def test_trocar_visao_preserva_pasta_e_voltar_sai_dela(cliente, modulo_id, grupo):
    painel = cliente.painel
    garantir(painel, modulo_id)
    nome = "Pasta ação & revisão #1"
    if grupo:
        escrever(painel, f"{modulo_id}/referencias/{nome}/Nota.md", "Texto fictício.\n")
        chave = "grupo:" + nome
    else:
        chave = painel.criar_nota(modulo_id, nome, {}).rel
    pagina = cliente.get(f"/m/{modulo_id}", params={"aba": "v0", "abrir": chave})
    for aba in ("v1", "v0", "v1"):
        nav = pagina.text.split('class="abas-visoes"', 1)[1].split('</div>', 1)[0]
        link = next(html.unescape(h) for h in re.findall(r'href="([^"]+)"', nav)
                    if parse_qs(urlsplit(html.unescape(h)).query).get("aba") == [aba])
        assert parse_qs(urlsplit(link).query)["abrir"] == [chave]
        pagina = cliente.get(f"/m/{modulo_id}{link}")
        assert pagina.status_code == 200
        assert pagina.context["pasta_aberta"]["chave"] == chave
        assert pagina.context["pasta_aberta"]["titulo"] == nome
        assert pagina.context["aba"] == aba
        assert 'aria-current="page"' in pagina.text
        if not grupo:
            assert "data-pasta-nova" in pagina.text
            assert 'id="abrir-novo"' not in pagina.text
        # Atualizar a página conserva o contexto; Voltar é a saída explícita.
        assert cliente.get(pagina.url).context["pasta_aberta"]["chave"] == chave
    cab = pagina.text.split('class="pasta-dentro-cab"', 1)[1].split('</header>', 1)[0]
    voltar = html.unescape(re.search(r'href="([^"]+)"', cab).group(1))
    raiz = cliente.get(f"/m/{modulo_id}{voltar}")
    assert "pasta_aberta" not in raiz.context and "pastas" in raiz.context
    assert raiz.context["aba"] == "v0"


@pytest.mark.parametrize("modulo_id", ["projetos", "estudos"])
def test_memoria_de_visao_separa_area_e_interior(cliente, modulo_id):
    garantir(cliente.painel, modulo_id)
    item = cliente.painel.criar_nota(modulo_id, "Pasta lembrada", {})
    outra = cliente.painel.criar_nota(modulo_id, "Outra pasta", {})
    url = f"/m/{modulo_id}"
    cliente.get(url, params={"aba": "v0"})
    cliente.get(url, params={"aba": "v1", "abrir": item.rel})
    assert cliente.get(url).context["aba"] == "v0"
    assert cliente.get(url, params={"abrir": item.rel}).context["aba"] == "v1"
    assert cliente.get(url, params={"abrir": outra.rel}).context["aba"] == "v1"
    cliente.get(url, params={"aba": "v1"})
    cliente.get(url, params={"aba": "v0", "abrir": item.rel})
    assert cliente.get(url).context["aba"] == "v1"
    assert cliente.get(url, params={"abrir": item.rel}).context["aba"] == "v0"


@pytest.mark.parametrize("grupo", [False, True])
def test_cor_lisa_persiste_substitui_arte_e_recusa_cor_invalida(cliente, grupo):
    painel = cliente.painel
    garantir(painel, "projetos")
    if grupo:
        escrever(painel, "projetos/referencias/Soltas/Nota.md", "Texto.\n")
        chave = "grupo:Soltas"
    else:
        chave = painel.criar_nota("projetos", "Colorida", {}).rel
    endpoint = "/api/modulos/projetos/pastas"
    r = cliente.post(endpoint, json={"chave": chave, "cor": "#Aa77Cc", "entrada_rapida": True})
    assert r.status_code == 200 and r.json()["cor"] == "#aa77cc"
    pasta = next(p for p in cliente.get("/m/projetos?aba=v0").context["pastas"] if p["chave"] == chave)
    assert pasta["cor"] == "#aa77cc" and not pasta["arte"] and not pasta["imagem"]
    assert pasta["entrada_rapida"] is (not grupo)
    assert 'style="background:#aa77cc"' in cliente.get("/m/projetos?aba=v0").text
    for invalida in ("red", "#123", "#000000;display:none", "url(https://exemplo.invalid)"):
        assert cliente.post(endpoint, json={"chave": chave, "cor": invalida}).status_code == 400
    assert painel.modulo("projetos").pastas[chave]["cor"] == "#aa77cc"
    assert cliente.post(endpoint, json={"chave": chave, "arte": "oceano"}).status_code == 200
    assert "cor" not in painel.modulo("projetos").pastas[chave]


@pytest.mark.parametrize("area", ["projetos", "estudos"])
def test_titulo_da_pasta_nao_move_nem_reescreve_suas_notas(cliente, area):
    painel = cliente.painel
    garantir(painel, area)
    item = painel.criar_nota(area, "Nome original", {}, "Texto humano.")
    antes = item.caminho.read_bytes()
    r = cliente.post(f"/api/modulos/{area}/pastas", json={"chave": item.rel, "titulo": "Nome da pasta"})
    assert r.status_code == 200
    pasta = next(p for p in cliente.get(f"/m/{area}?aba=v0").context["pastas"] if p["chave"] == item.rel)
    assert pasta["titulo"] == "Nome da pasta"
    dentro = cliente.get(f"/m/{area}", params={"abrir": item.rel})
    assert dentro.context["pasta_aberta"]["titulo"] == "Nome da pasta"
    assert dentro.context["pasta_aberta"]["notas"][0]["titulo"] == "Nome original"
    assert item.caminho.read_bytes() == antes
    assert cliente.post(f"/api/modulos/{area}/pastas", json={"chave": item.rel, "titulo": "   "}).status_code == 400


def test_grupo_aberto_mostra_apenas_as_notas_contadas(cliente):
    painel = cliente.painel
    garantir(painel, "projetos")
    projeto = painel.criar_nota("projetos", "Projeto ligado", {})
    escrever(painel, "projetos/referencias/Arquivo/Apoio.md", "---\nprojeto: '[[Projeto ligado]]'\n---\nTexto.\n")
    escrever(painel, "projetos/referencias/Arquivo/Solta.md", "Texto.\n")
    raiz = cliente.get("/m/projetos?aba=v0")
    grupo = next(p for p in raiz.context["pastas"] if p["chave"] == "grupo:Arquivo")
    dentro = cliente.get("/m/projetos", params={"abrir": grupo["chave"], "aba": "v1"})
    notas = dentro.context["pasta_aberta"]["notas"]
    assert grupo["total"] == len(notas) == 1
    assert notas[0]["titulo"] == "Solta"
    ligado = cliente.get("/m/projetos", params={"abrir": projeto.rel, "aba": "v0"})
    assert [n["titulo"] for n in ligado.context["pasta_aberta"]["notas"]] == ["Projeto ligado", "Apoio"]


@pytest.mark.parametrize(("area", "padrao"), [("projetos", "pastas"), ("estudos", "cartoes")])
def test_subpastas_mistas_abrem_no_contexto_e_herdam_visualizacao(cliente, area, padrao):
    painel = cliente.painel
    garantir(painel, area)
    item = painel.criar_nota(area, "Pasta mista", {})
    filha = "Revisão & mídia #1"
    raiz = f"{area}/referencias/Pasta mista/{filha}"
    escrever(painel, raiz + "/Pauta.md", "Texto\n")
    escrever(painel, raiz + "/Complemento.html", "<p>Anexo</p>")
    (painel.vault / raiz / "Vazia").mkdir()
    aberta = cliente.get(f"/m/{area}", params={"abrir": item.rel})
    assert aberta.context["modo_subpastas"] == padrao
    assert [n["titulo"] for n in aberta.context["pasta_aberta"]["notas"]] == ["Pasta mista"]
    link = aberta.context["pasta_aberta"]["subpastas"][0]["url"]
    assert html.escape(link) in aberta.text
    assert parse_qs(urlsplit(link).query) == {"abrir": [item.rel], "pasta": [filha]}
    destino = cliente.get(urljoin(str(aberta.url), link))
    assert destino.status_code == 200
    assert destino.context["pasta_aberta"]["titulo"] == filha
    assert [n["titulo"] for n in destino.context["pasta_aberta"]["notas"]] == ["Pauta"]
    assert "Complemento.html" in destino.text and "Vazia" in destino.text
    assert cliente.get(f"/m/{area}", params={"abrir": item.rel, "pasta": "../outra"}).status_code == 404
    seletor = destino.text.split('id="pasta-ajustes-subpastas"', 1)[1].split('</select>', 1)[0]
    assert 'value="lista"' not in seletor and "Herdar" not in seletor
    escolha = "pastas" if padrao == "cartoes" else "cartoes"
    r = cliente.post(f"/api/modulos/{area}/pastas", json={"chave": "diretorio:" + raiz, "subpastas": escolha})
    assert r.status_code == 200, r.text
    assert cliente.get(destino.url).context["modo_subpastas"] == escolha
    lista = cliente.get(destino.url.copy_add_param("aba", "v1"))
    assert lista.context["modo_subpastas"] == "lista" and lista.context["estilo_subpastas"] == escolha
    assert 'class="lista-pasta lista-pastas"' in lista.text
    assert cliente.get(destino.url.copy_add_param("aba", "v0")).context["modo_subpastas"] == escolha
    assert cliente.get(aberta.url).context["modo_subpastas"] == padrao
    nota = painel.nota(raiz + "/Pauta.md")
    painel.excluir(nota.rel, nota.versao)
    atualizada = cliente.get(destino.url)
    assert atualizada.status_code == 200
    assert not atualizada.context["pasta_aberta"]["notas"] and "Complemento.html" in atualizada.text


def test_acoes_da_pasta_preservam_notas_compartilhadas_e_anexos(cliente):
    painel = cliente.painel
    garantir(painel, "projetos")
    item = painel.criar_nota("projetos", "Primeiro", {})
    painel.criar_nota("projetos", "Segundo", {})
    propria = escrever(painel, "projetos/referencias/Primeiro/Exclusiva.md", "[[Primeiro]]\n")
    comum = escrever(painel, "projetos/referencias/Primeiro/Comum.md", "[[Primeiro]] e [[Segundo]]\n")
    anexo = escrever(painel, "projetos/referencias/Primeiro/Manual.html", "<p>Exemplo</p>")
    url = "/m/projetos"
    pasta = cliente.get(url, params={"abrir": item.rel}).context["pasta_aberta"]
    endpoint = "/api/modulos/projetos/pastas/acao"
    assert cliente.post(endpoint, json={"chave": item.rel, "acao": "arquivar", "versao": "antiga"}).status_code == 409
    r = cliente.post(endpoint, json={"chave": item.rel, "acao": "arquivar", "versao": pasta["versao"]})
    assert r.status_code == 200 and r.json() == {"movidas": 2, "parcial": False}
    assert not propria.exists() and not item.caminho.exists()
    assert comum.is_file() and anexo.is_file()
    assert cliente.get(url, params={"aba": "maquina"}).context["tem_arquivo"]
