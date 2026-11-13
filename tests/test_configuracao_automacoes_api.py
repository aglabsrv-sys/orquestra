"""Configuração pública de rotinas existentes e estado da inicialização local."""
from __future__ import annotations

import copy
from pathlib import Path

from orquestra import autostart, segredos


def local(cliente):
    return {"X-Orquestra-Local": cliente.get("/api/local/capacidade").json()["token"]}


def test_rotina_existente_edita_fontes_sem_mover_notas(cliente, vault):
    dados = cliente.get("/api/automacoes/catalogo").json()
    existente = next(a for a in dados["legadas"] if a["definicao"] == "radar/rss.py")
    antes = {p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*.md")}
    config = copy.deepcopy(existente["config"])
    config["feeds"] = ["https://example.test/pesquisa.xml"]
    pedido = {**existente["legado"], "versao": existente["versao"], "config": config,
              "nome": "Pesquisa da equipe", "a_cada": "12h", "diario_as": ""}
    previa = cliente.post("/api/automacoes/legado/prever", json=pedido)
    assert previa.status_code == 200
    editada = cliente.post("/api/automacoes/legado/editar", json=pedido)
    assert editada.status_code == 200
    resultado = editada.json()
    assert resultado["config"]["feeds"] == config["feeds"]
    assert resultado["nome"] == "Pesquisa da equipe"
    assert not resultado["ativo"]
    assert antes == {p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*.md")}
    # O mesmo formulário aberto em outra aba não substitui uma configuração nova.
    assert cliente.post("/api/automacoes/legado/editar", json=pedido).status_code in {400, 409}
    pagina = cliente.get("/ajustes/automacoes")
    assert pagina.status_code == 200 and "Pesquisa da equipe" in pagina.text


def test_previa_existente_aceita_opcionais_sem_erro_interno(cliente):
    resposta = cliente.post("/api/automacoes/legado/prever", json={"modulo": "radar", "script": "rss.py"})
    assert resposta.status_code == 200
    assert cliente.post("/api/automacoes/legado/editar", json={"modulo": "radar", "script": "rss.py"}).status_code in {400, 409}
    assert cliente.post("/api/automacoes/legado/prever", json={"modulo": "radar", "script": "../../fora.py"}).status_code in {400, 404}


def test_inicializacao_api_tem_estado_real_e_retorno_conciso(cliente, monkeypatch):
    estado = {"presente": False, "ativo": False, "neste_cofre": False, "estado": "desligado", "descricao": "Desativado."}
    chamadas = []

    def executar(acao, vault=None):
        chamadas.append(acao)
        ativo = acao == "ativar"
        estado.update(presente=ativo, ativo=ativo, neste_cofre=ativo,
                      estado="ativo" if ativo else "desligado", descricao="Ativado." if ativo else "Desativado.")
        return "Pronto: Arquivo criado: um/caminho/interno"

    monkeypatch.setattr(autostart, "resumo", lambda vault: dict(estado))
    monkeypatch.setattr(autostart, "executar", executar)
    assert cliente.get("/api/autostart").status_code == 403
    headers = local(cliente)
    assert cliente.get("/api/autostart", headers=headers).json()["estado"] == "desligado"
    ativado = cliente.post("/api/autostart", json={"acao": "ativar"}, headers=headers)
    assert ativado.status_code == 200
    assert ativado.json()["mensagem"] == "Pronto" and ativado.json()["ativo"]
    assert "caminho/interno" not in ativado.text
    assert cliente.get("/api/autostart", headers=headers).json()["ativo"]
    assert chamadas == ["ativar"]
    desativado = cliente.post("/api/autostart", json={"acao": "desativar"}, headers=headers)
    assert desativado.status_code == 200 and not desativado.json()["ativo"]


def test_inicializacao_falha_sem_anunciar_sucesso(cliente, monkeypatch):
    def falhar(*args):
        raise RuntimeError("Não foi possível ativar a inicialização.")

    monkeypatch.setattr(autostart, "executar", falhar)
    resposta = cliente.post("/api/autostart", json={"acao": "ativar"}, headers=local(cliente))
    assert resposta.status_code == 400 and "mensagem" not in resposta.json()


def test_segredo_omitido_nao_apaga_valor_e_api_nunca_o_expoe(cliente, vault):
    headers = local(cliente)
    exemplo = "valor-ficticio-do-teste"
    assert cliente.post("/api/variaveis", json={"nome": "YOUTUBE_API_KEY", "valor": exemplo}, headers=headers).status_code == 200
    antes = segredos.arquivo(vault).read_bytes()
    assert cliente.post("/api/variaveis", json={"nome": "YOUTUBE_API_KEY"}, headers=headers).status_code == 400
    assert segredos.arquivo(vault).read_bytes() == antes
    listagem = cliente.get("/api/variaveis", headers=headers)
    assert listagem.json() == {"nomes": ["YOUTUBE_API_KEY"]}
    assert exemplo not in listagem.text
    assert exemplo not in cliente.get("/ajustes/variaveis").text
    assert cliente.post("/api/variaveis", json={"nome": "YOUTUBE_API_KEY", "valor": None}, headers=headers).status_code == 200
    assert cliente.get("/api/variaveis", headers=headers).json()["nomes"] == []


def test_atualizacao_nativa_exige_acesso_local_e_preserva_notas(cliente, vault):
    helper = vault / "radar/maquina/coletores/_comum.py"
    antigo = (Path(__file__).parent / "fixtures/coletor-comum-040.txt").read_bytes()
    helper.write_bytes(antigo)
    yaml = (vault / "radar/_modulo.yaml").read_bytes()
    notas = {p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*.md")}
    catalogo = cliente.get("/api/automacoes/catalogo").json()
    atual = next(a for a in catalogo["legadas"] if a["legado"] == {"modulo": "radar", "script": "rss.py"})
    assert atual["atualizacao_disponivel"] and atual["codigo_nativo"]
    pedido = {**atual["legado"], "versao": atual["versao"], "assinatura": atual["confianca"]["assinatura"]}
    assert cliente.post("/api/automacoes/legado/atualizar", json=pedido).status_code == 403
    assert helper.read_bytes() == antigo
    resposta = cliente.post("/api/automacoes/legado/atualizar", json=pedido, headers=local(cliente))
    assert resposta.status_code == 200
    assert resposta.json()["codigo_nativo"] and not resposta.json()["atualizacao_disponivel"]
    assert resposta.json()["confianca"]["confiavel"]
    assert helper.read_bytes() != antigo
    assert (vault / "radar/_modulo.yaml").read_bytes() == yaml
    assert notas == {p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*.md")}
