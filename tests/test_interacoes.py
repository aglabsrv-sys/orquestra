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
    assert 'data-tarefa-conclusao' in lista and 'data-lote-item' not in lista
    assert 'id="novo-adicionar-campo"' in lista
    assert 'data-extra-campo="tags" hidden' in lista
    pagina = cliente.get("/m/tarefas/personalizar").text
    assert pagina.count('role="tab"') == 2
    assert pagina.count('role="tabpanel"') == 2
    assert 'id="p-aba-propriedades"' not in pagina
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


def test_catalogo_reutiliza_metadados_sem_compartilhar_mutacoes(tmp_path, monkeypatch):
    from orquestra import preparo
    pasta = tmp_path / "catalogo" / "exemplo"
    pasta.mkdir(parents=True)
    arquivo = pasta / "_modulo.yaml"
    arquivo.write_text("nome: Exemplo\nicone: pasta\n", encoding="utf-8")
    monkeypatch.setattr(preparo, "CATALOGO", pasta.parent)
    chamadas = []
    ler = preparo.ler_yaml
    def contar(caminho):
        chamadas.append(caminho)
        return ler(caminho)
    monkeypatch.setattr(preparo, "ler_yaml", contar)
    primeiro = preparo.catalogo()
    primeiro["exemplo"].nome = "Mudança do chamador"
    primeiro.clear()
    assert preparo.catalogo()["exemplo"].nome == "Exemplo"
    assert len(chamadas) == 1
    arquivo.write_text("nome: Outro exemplo\nicone: pessoas\n", encoding="utf-8")
    assert preparo.catalogo()["exemplo"].nome == "Outro exemplo"
    assert len(chamadas) == 2
    arquivo.unlink()
    assert not preparo.catalogo()


def test_tailscale_exclui_sem_conceder_capacidade_local(cliente):
    host = "computador.exemplo.ts.net"
    assert cliente.post("/api/tailscale/host", headers=local(cliente), json={"url": "https://" + host}).status_code == 200
    remoto = {"Host": host, "Origin": "https://" + host}
    nota = cliente.painel.criar_nota("tarefas", "Excluir pelo celular")
    rota = "/api/excluir/" + nota.rel
    assert cliente.post(rota, headers={**remoto, "Origin": "https://outro.example"}, json={"versao": nota.versao}).status_code == 403
    assert cliente.post(rota, headers={**remoto, "X-Orquestra-Vault": "outro"}, json={"versao": nota.versao}).status_code == 409
    resposta = cliente.post(rota, headers=remoto, json={"versao": nota.versao})
    assert resposta.status_code == 200
    assert not nota.caminho.exists()
    identificador = resposta.json()["id"]
    assert cliente.post(f"/api/lixeira/{identificador}/apagar", headers=remoto, json={"versao": nota.versao}).status_code == 403
    assert cliente.get("/api/local/capacidade", headers=remoto).status_code == 403
    nota = cliente.painel.criar_nota("tarefas", "Lote pelo celular")
    itens = [{"rel": nota.rel, "versao": nota.versao}]
    resposta = cliente.post("/api/lote", headers=remoto, json={"acao": "excluir", "itens": itens})
    assert resposta.status_code == 200 and resposta.json()["resultados"][0]["ok"]
    assert cliente.post("/api/tailscale/host/revogar", headers=local(cliente), json={"url": "https://" + host}).status_code == 200
    assert cliente.post("/api/lote", headers=remoto, json={"acao": "excluir", "itens": itens}).status_code == 403
