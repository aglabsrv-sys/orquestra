"""Central única: preservação de autoria, referências e gravação concorrente."""

import pytest
from html.parser import HTMLParser

from orquestra import armazenamento, instrucoes
from orquestra.mcp_servidor import Ferramentas


def local(cliente):
    return {"X-Orquestra-Local": cliente.get("/api/local/capacidade").json()["token"]}


def estado(cliente):
    return cliente.get("/ajustes/instrucoes").context["central_instrucoes"]


def test_leitura_da_central_nao_cria_nem_migra_arquivos(cliente, vault):
    antes = {p: p.read_bytes() for p in vault.rglob("*.md")}
    pagina = cliente.get("/ajustes/instrucoes")
    assert pagina.status_code == 200 and pagina.context["secao"] == "instrucoes"
    assert pagina.context["central_instrucoes"]["fontes"]
    assert {p: p.read_bytes() for p in antes} == antes
    assert not (vault / "PREFERENCIAS.md").exists()
    assert 'Preferências da IA' not in pagina.text
    class Campos(HTMLParser):
        entradas = 0

        def handle_starttag(self, tag, attrs):
            if tag in {"textarea", "input"}:
                self.entradas += 1
    central_html = pagina.text.split('class="central-instrucoes"', 1)[1].split('</section>', 1)[0]
    campos = Campos()
    campos.feed(central_html)
    assert campos.entradas == 1
    assert cliente.get("/ajustes/humano", follow_redirects=False).headers["location"] == "/ajustes/instrucoes"


def test_salvar_acrescenta_bloco_e_vinculos_sem_reescrever_fontes(cliente, vault):
    contrato = vault / "AGENTS.md"
    anterior = b"# Minhas regras\r\n\r\nTexto proprio intacto.\r\n"
    contrato.write_bytes(anterior)
    preferencias = vault / "PREFERENCIAS.md"
    preferencias.write_text("Preferências anteriores da pessoa.\n", encoding="utf-8")
    cliente.painel.recarregar_tudo()
    fontes = instrucoes.fontes(cliente.painel)
    originais = {nota.caminho: nota.caminho.read_bytes() for _, nota in fontes}
    claude = (vault / "CLAUDE.md").read_bytes()
    texto = "## Como trabalhar comigo\nSeja breve.\n\n## Radar\nPriorize ferramentas locais."
    pedido = {"texto": texto, "versao": estado(cliente)["versao"]}
    resposta = cliente.put("/api/instrucoes", json=pedido, headers=local(cliente))
    assert resposta.status_code == 200, resposta.text
    novo = contrato.read_bytes()
    assert novo.startswith(anterior)
    assert novo.count(texto.encode()) == 1
    assert b"PREFERENCIAS.md" in novo
    assert b"radar/humano/" in novo
    assert b"Preferencias anteriores" not in novo
    assert {p: p.read_bytes() for p in originais} == originais
    assert (vault / "CLAUDE.md").read_bytes() == claude
    assert estado(cliente)["texto"] == texto
    segunda = cliente.put("/api/instrucoes", json={"texto": texto, "versao": resposta.json()["versao"]}, headers=local(cliente))
    assert segunda.status_code == 200 and contrato.read_bytes() == novo
    mcp = Ferramentas(vault)
    assert texto in mcp.regras()
    contexto = mcp.contexto_area("radar", limite=20)
    caminhos = [d["caminho"] for d in contexto["documentos"]["itens"]]
    assert len(caminhos) == len(set(caminhos))
    assert "PREFERENCIAS.md" in caminhos
    assert contexto["central_instrucoes"] == "AGENTS.md"


def test_edicao_em_outra_janela_nao_e_sobrescrita(cliente, vault):
    dados = estado(cliente)
    contrato = vault / "AGENTS.md"
    contrato.write_bytes(contrato.read_bytes() + b"\nRegra externa.\n")
    antes = contrato.read_bytes()
    resposta = cliente.put("/api/instrucoes", json={"texto": "Minha proposta", "versao": dados["versao"]}, headers=local(cliente))
    assert resposta.status_code == 409
    assert contrato.read_bytes() == antes


def test_editar_fonte_na_central_preserva_frontmatter_e_detecta_conflito(cliente, vault):
    fonte = next(f for f in estado(cliente)["fontes"] if f["area"] == "radar")
    caminho = vault / fonte["rel"]
    anterior = caminho.read_text(encoding="utf-8").split("---", 2)[1]
    pedido = {"rel": fonte["rel"], "texto": "Meu critério de seleção.\n", "versao": fonte["versao"]}
    resposta = cliente.put("/api/instrucoes/nota", json=pedido, headers=local(cliente))
    assert resposta.status_code == 200, resposta.text
    assert caminho.read_text(encoding="utf-8").split("---", 2)[1] == anterior
    assert "Meu critério de seleção." in caminho.read_text(encoding="utf-8")
    antes = caminho.read_bytes()
    assert cliente.put("/api/instrucoes/nota", json=pedido, headers=local(cliente)).status_code == 409
    assert caminho.read_bytes() == antes


def test_escrita_de_instrucoes_exige_capacidade_local_e_nao_aceita_outros_arquivos(cliente, vault):
    pedido = {"texto": "Instruções", "versao": estado(cliente)["versao"]}
    assert cliente.put("/api/instrucoes", json=pedido).status_code == 403
    for rel in ("AGENTS.md", "CLAUDE.md", "../fora.md", "radar/maquina/instrucoes.md"):
        resposta = cliente.put("/api/instrucoes/nota", json={**pedido, "rel": rel}, headers=local(cliente))
        assert resposta.status_code == 400


@pytest.mark.parametrize("bloco", [instrucoes.INICIO, instrucoes.FIM, instrucoes.INICIO * 2 + instrucoes.FIM,
                                  instrucoes.FIM + instrucoes.INICIO])
def test_delimitadores_invalidos_nao_modificam_contrato(painel, bloco):
    arquivo = painel.vault / "AGENTS.md"
    arquivo.write_bytes(b"Texto da pessoa.\n" + bloco)
    antes = arquivo.read_bytes()
    with pytest.raises(ValueError, match="delimitadores"):
        instrucoes.salvar(painel, "Nova orientação", armazenamento.versao(antes))
    assert arquivo.read_bytes() == antes


def test_contrato_ausente_e_criado_so_ao_salvar(painel):
    arquivo = painel.vault / "AGENTS.md"
    arquivo.unlink()
    assert instrucoes.contexto(painel)["versao"] == "ausente"
    assert not arquivo.exists()
    resultado = instrucoes.salvar(painel, "Use português.", "ausente")
    assert resultado["versao"] == armazenamento.versao(arquivo.read_bytes())


def test_texto_da_pessoa_preserva_espacos_e_quebras_e_nao_vira_html(cliente):
    texto = '\n\nMinha instrução.  \n</textarea><input name="nao-criar">\n\n'
    anterior = estado(cliente)
    resposta = cliente.put("/api/instrucoes", json={"texto": texto, "versao": anterior["versao"]}, headers=local(cliente))
    assert resposta.status_code == 200
    pagina = cliente.get("/ajustes/instrucoes")
    assert pagina.context["central_instrucoes"]["texto"] == texto
    assert '&lt;/textarea&gt;&lt;input name=&#34;nao-criar&#34;&gt;' in pagina.text
    assert '<input name="nao-criar">' not in pagina.text


def test_texto_novo_nao_pode_injetar_delimitadores(painel):
    estado_atual = instrucoes.contexto(painel)
    arquivo = painel.vault / "AGENTS.md"
    antes = arquivo.read_bytes()
    with pytest.raises(ValueError):
        instrucoes.salvar(painel, instrucoes.FIM.decode(), estado_atual["versao"])
    assert arquivo.read_bytes() == antes


def test_blocos_sobrepostos_e_utf8_invalido_nao_sao_reescritos(painel):
    arquivo = painel.vault / "AGENTS.md"
    for dados in (instrucoes.INICIO + instrucoes.LINKS_INICIO + instrucoes.FIM + instrucoes.LINKS_FIM, b"\xff\xfe"):
        arquivo.write_bytes(dados)
        with pytest.raises(ValueError):
            instrucoes.salvar(painel, "Minha proposta", armazenamento.versao(dados))
        assert arquivo.read_bytes() == dados


def test_modulos_sem_aba_humano_e_links_antigos_na_central(cliente):
    pagina = cliente.get("/m/radar")
    assert '?aba=humano' not in pagina.text
    assert cliente.get("/m/radar?aba=humano", follow_redirects=False).headers["location"] == "/ajustes/instrucoes#area-radar"
    # Um cookie gravado por uma versão anterior não aprisiona a pessoa na central.
    resposta = cliente.get("/m/radar?aba=v1")
    chave = next(k for k in resposta.cookies if k.startswith("orq-visao-"))
    cliente.cookies.set(chave, "humano")
    assert cliente.get("/m/radar").template.name == "modulo.html"


def test_modulo_novo_nao_exige_pasta_humano(painel):
    modulo = painel.criar_modulo("Pasta sem duplicação", "nota")
    assert not (modulo.pasta / "humano").exists()
    painel.adicionar_modulo("financas", exemplos=False)
    assert not (painel.modulo("financas").pasta / "humano").exists()


def test_preferencias_existentes_sao_o_editor_geral_sem_segunda_copia(cliente, vault):
    preferencias = vault / "PREFERENCIAS.md"
    preferencias.write_text("Meu único texto geral.\n", encoding="utf-8")
    cliente.painel.recarregar_tudo()
    pagina = cliente.get("/ajustes/instrucoes")
    central = pagina.context["central_instrucoes"]
    assert central["geral_rel"] == "PREFERENCIAS.md"
    assert central["texto"] == "Meu único texto geral.\n"
    assert not any(f["rel"] == "PREFERENCIAS.md" for f in central["fontes"])
    assert pagina.text.count("Meu único texto geral.") == 1
    assert instrucoes.INICIO not in (vault / "AGENTS.md").read_bytes()


def test_contrato_muito_grande_e_recusado_sem_escrita(painel, monkeypatch):
    arquivo = painel.vault / "AGENTS.md"
    antes = arquivo.read_bytes()
    monkeypatch.setattr(instrucoes, "LIMITE", 10)
    with pytest.raises(ValueError, match="excede"):
        instrucoes.contexto(painel)
    assert arquivo.read_bytes() == antes
