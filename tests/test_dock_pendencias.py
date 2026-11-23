"""O dock chama atenção para pendências, sem contar o estoque de arquivos."""

import datetime as dt
from html.parser import HTMLParser

from orquestra.apresentacao import montar_dock
from orquestra.indice import espera_decisao


def atalho_entrada(html):
    class Atalho(HTMLParser):
        destino = None

        def handle_starttag(self, tag, attrs):
            atributos = dict(attrs)
            if tag == "a" and "dock-entrada" in atributos.get("class", "").split():
                self.destino = atributos["href"]
    leitor = Atalho()
    leitor.feed(html)
    return leitor.destino


def test_entrada_abre_decisoes_e_dock_alterna_com_capturas(cliente):
    inicio = cliente.get("/")
    assert next(s for s in inicio.context["slides"] if s["id"] == "entrada")["url"] == "/entrada?aba=decisoes"
    for origem in ("/", "/m/tarefas", "/m/entrada"):
        assert atalho_entrada(cliente.get(origem).text) == "/entrada?aba=decisoes"
    decisoes = cliente.get("/entrada", follow_redirects=False)
    assert decisoes.status_code == 200
    assert decisoes.template.name == "decidir.html"
    assert atalho_entrada(decisoes.text) == "/m/entrada"
    capturas = cliente.get("/entrada?aba=capturas", follow_redirects=False)
    assert capturas.status_code == 303 and capturas.headers["location"] == "/m/entrada"


def test_entrada_sem_capturas_nao_alterna_para_area_desligada(cliente):
    cliente.painel.desligar_modulo("entrada")
    for url in ("/entrada", "/entrada?aba=decisoes", "/entrada?aba=capturas"):
        pagina = cliente.get(url)
        assert pagina.status_code == 200
        assert atalho_entrada(pagina.text) == "/entrada?aba=decisoes"


def test_radar_sugere_lista_e_preserva_escolha_de_triagem(cliente):
    painel = cliente.painel
    painel.criar_nota("radar", "Notícia nova", {"status": "novo"})
    painel.criar_nota("radar", "Referência útil", {"status": "util"})
    pagina = cliente.get("/m/radar")
    assert pagina.context["visao"].tipo == "tabela"
    assert cliente.get("/m/radar?aba=v0").context["visao"].tipo == "kanban"
    assert cliente.get("/m/radar").context["visao"].tipo == "kanban"


def test_preview_compacto_nas_decisoes_e_no_radar(cliente):
    painel = cliente.painel
    com_imagem = painel.criar_nota("radar", "Vídeo demonstrativo", {"miniatura": "https://example.test/video.jpg", "status": "novo"})
    sem_imagem = painel.criar_nota("radar", "Notícia somente em texto", {"status": "novo"})
    pagina = cliente.get("/entrada")
    assert 'cartao-compacto' in pagina.text
    assert 'data-previa-compacta' in pagina.text
    assert com_imagem.titulo in pagina.text and sem_imagem.titulo in pagina.text
    lista = cliente.get("/m/radar?aba=v1")
    assert 'radar-lista' in lista.text and 'radar-item-texto' in lista.text
    assert com_imagem.titulo in lista.text and sem_imagem.titulo in lista.text


def test_itens_abertos_sem_prazo_nem_decisao_nao_viram_notificacao(painel):
    modulo = painel.criar_modulo("Referências", "nota", com_quadro=True)
    painel.criar_nota(modulo.id, "Uma referência para consultar", campos={"status": "a_fazer"})
    assert painel.indice.resumo(modulo).abertos == 1
    item = next(m for m in montar_dock(painel, "inicio", dt.date.today())["modulos"] if m["id"] == modulo.id)
    assert item["selo"] == 0


def test_concluir_uma_nota_com_pergunta_remove_a_pendencia(cliente):
    painel = cliente.painel
    modulo = painel.modulo("tarefas")
    nota = painel.criar_nota(modulo.id, "Aprovação encerrada", campos={"status": "aguardando", "pergunta": "Podemos concluir?"})
    antes = cliente.get("/api/resumo").json()["decidir"]
    assert espera_decisao(nota, modulo)
    nota = painel.editar_nota(nota.rel, nota.versao, campos={"status": "feito"})
    assert not espera_decisao(nota, modulo)
    assert cliente.get("/api/resumo").json()["decidir"] == antes - 1
    assert "Aprovação encerrada" not in cliente.get("/decidir").text


def test_entrada_mantem_decisoes_quando_capturas_sao_desligadas(cliente):
    cliente.painel.desligar_modulo("entrada")
    legado = cliente.get("/decidir?modulo=conteudo", follow_redirects=False)
    assert legado.status_code == 303
    assert legado.headers["location"] == "/entrada?modulo=conteudo&aba=decisoes"
    pagina = cliente.get("/m/entrada")
    assert pagina.status_code == 200 and "Para decidir" in pagina.text
    assert not pagina.context["tem_capturas"]
    assert pagina.context["dock"]["entrada"]["selo"] == cliente.get("/api/resumo").json()["decidir"]
    assert pagina.context["dock"]["entrada"]["ativo"]


def test_responder_pergunta_mantem_item_cujo_status_ainda_exige_decisao(cliente):
    painel = cliente.painel
    nota = painel.criar_nota("tarefas", "Revisão de pauta", {"status": "aguardando"})
    nota = painel.editar_nota(nota.rel, nota.versao, campos={"pergunta": "Pode revisar?"})
    resposta = cliente.put("/api/notas/" + nota.rel, json={
        "versao": nota.versao, "campos": {"resposta": "Sim.", "pergunta": ""},
    })
    assert resposta.status_code == 200
    assert resposta.json()["decisao_pendente"]
    fila = cliente.get("/entrada", params={"aba": "decisoes", "nota": nota.rel})
    assert "Revisão de pauta" in fila.text and "Pode revisar?" not in fila.text

