"""Seleção em lote, formulários progressivos e permissões persistentes do Serve."""
from fastapi.testclient import TestClient

from orquestra.hospedeiro import Hospedeiro


def local(cliente):
    return {"X-Orquestra-Local": cliente.get("/api/local/capacidade").json()["token"]}


def test_lote_preserva_alteracao_concorrente_e_relata_resultados(cliente):
    painel = cliente.painel
    a = painel.criar_nota("tarefas", "Primeira do lote")
    b = painel.criar_nota("tarefas", "Segunda do lote")
    painel.editar_nota(b.rel, b.versao, corpo="Texto novo em outra aba.")
    resposta = cliente.post("/api/lote", json={"acao": "arquivar", "itens": [
        {"rel": a.rel, "versao": a.versao}, {"rel": b.rel, "versao": b.versao}]})
    assert resposta.status_code == 200
    resultados = resposta.json()["resultados"]
    assert resultados[0]["ok"] and not resultados[1]["ok"]
    assert not a.caminho.exists()
    assert "Texto novo" in b.caminho.read_text(encoding="utf-8")


def test_lote_status_e_exclusao_exigem_contratos_e_capacidade(cliente):
    nota = cliente.painel.criar_nota("tarefas", "Item de lote")
    itens = [{"rel": nota.rel, "versao": nota.versao}]
    assert cliente.post("/api/lote", json={"acao":"excluir", "itens":itens}).status_code == 403
    assert cliente.post("/api/lote", json={"acao":"arquivar", "itens":[]}).status_code == 400
    assert cliente.post("/api/lote", json={"acao":"status", "status":"inexistente", "itens":itens}).json()["resultados"][0]["ok"] is False
    resposta = cliente.post("/api/lote", json={"acao":"status", "status":"feito", "itens":itens})
    atual = resposta.json()["resultados"][0]
    assert atual["ok"] and cliente.painel.nota(nota.rel).campo("status") == "feito"
    itens[0]["versao"] = atual["versao"]
    assert cliente.post("/api/lote", headers=local(cliente), json={"acao":"excluir", "itens":itens}).json()["resultados"][0]["ok"]


def test_telas_compactas_e_entrada_persistente(cliente):
    lista = cliente.get("/m/tarefas?aba=v1").text
    assert 'data-lote-todos' in lista and 'data-lote-item' in lista
    assert 'id="novo-adicionar-campo"' in lista
    assert 'data-extra-campo="tags" hidden' in lista
    pagina = cliente.get("/m/tarefas/personalizar").text
    assert pagina.count('role="tab"') == 3
    assert pagina.count('role="tabpanel"') == 3
    assert 'href="#p-identidade"' not in pagina
    for rota in ("/", "/m/tarefas", "/ajustes"):
        html = cliente.get(rota).text
        assert 'dock-entrada' in html
        assert html.count('href="/m/entrada"') >= 1
        dock = html.split('<nav class="dock"')[1].split('</nav>')[0]
        assert dock.count('href="/m/entrada"') == 1


def test_tailscale_sincroniza_painel_bootstrap_releitura_e_reinicio(vault):
    endereco = "https://computador.exemplo.ts.net"
    headers_remotos = {"Host":"computador.exemplo.ts.net"}
    hospedeiro = Hospedeiro(vault, vigiar=False, agendar=False)
    with TestClient(hospedeiro, base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        assert cliente.get("/", headers=headers_remotos).status_code == 403
        assert cliente.post("/api/tailscale/host", json={"url":endereco}).status_code == 403
        assert cliente.post("/api/tailscale/host", headers=local(cliente), json={"url":endereco}).status_code == 200
        assert cliente.get("/", headers=headers_remotos).status_code == 200
        assert cliente.get("/boas-vindas", headers=headers_remotos).status_code == 200
        # As duas proteções precisam consultar a mesma configuração nova.
        hospedeiro.painel.recarregar_config()
        assert cliente.get("/boas-vindas", headers=headers_remotos).status_code == 200
        assert cliente.get("/api/local/capacidade", headers=headers_remotos).status_code == 403
    hospedeiro = Hospedeiro(vault, vigiar=False, agendar=False)
    with TestClient(hospedeiro, base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        headers = local(cliente)
        assert cliente.get("/", headers=headers_remotos).status_code == 200
        assert cliente.get("/api/tailscale/hosts", headers=headers).json()["urls"] == [endereco]
        pagina = cliente.get("/ajustes/acesso").text
        assert endereco in pagina and 'data-ts-acao="copiar"' in pagina and 'data-ts-acao="revogar"' in pagina
        assert cliente.post("/api/tailscale/host/revogar", headers=headers, json={"url":endereco}).status_code == 200
        assert cliente.get("/", headers=headers_remotos).status_code == 403
        assert cliente.get("/boas-vindas", headers=headers_remotos).status_code == 403
        assert cliente.get("/api/tailscale/hosts", headers=headers).json()["urls"] == []
        assert cliente.get("/").status_code == 200
