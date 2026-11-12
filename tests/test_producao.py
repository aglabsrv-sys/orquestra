"""Contratos de recuperação, primeiro uso, falhas e paginação do candidato de release."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orquestra import armazenamento, backup, preparo
from orquestra.config import ler_yaml
from orquestra.notas import ler_nota, nome_de_arquivo
from orquestra.servidor import criar_app


@pytest.fixture
def app_leve(tmp_path):
    vault = preparo.preparar(tmp_path / "vault", ["tarefas"], exemplos=False, com_backup=False).vault
    app = criar_app(vault, vigiar=False, agendar=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 41000)) as cliente:
        yield cliente, vault, app.state.painel


def criar(cliente, titulo="Teste"):
    resposta = cliente.post("/api/notas", json={"modulo": "tarefas", "titulo": titulo, "corpo": "Texto inicial."})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


@pytest.mark.parametrize("nome", ["CON", "aux", "COM1", "LPT9", "NUL.txt", "COM¹"])
def test_nomes_portaveis_evitem_dispositivos_reservados(nome, tmp_path):
    for titulo in (nome, "🎼" * 80):
        caminho = tmp_path / (nome_de_arquivo(titulo) + ".md")
        caminho.write_text(titulo, encoding="utf-8")
        assert caminho.read_text(encoding="utf-8") == titulo


def test_edicao_e_arquivamento_exigem_versao_e_preservam_origem(app_leve):
    cliente, vault, _ = app_leve
    nota = criar(cliente)
    original = (vault / nota["rel"]).read_bytes()
    assert cliente.put("/api/notas/" + nota["rel"], json={"corpo": "Novo."}).status_code == 400
    assert cliente.post("/api/arquivar/" + nota["rel"], json={}).status_code == 400
    assert (vault / nota["rel"]).read_bytes() == original
    (vault / nota["rel"]).write_bytes(original + b"Mudanca externa.\n")
    resposta = cliente.post("/api/arquivar/" + nota["rel"], json={"versao": nota["versao"]})
    assert resposta.status_code == 409
    assert (vault / nota["rel"]).read_bytes().endswith(b"Mudanca externa.\n")


def test_aba_de_outro_vault_nao_altera_mesmo_arquivo_com_versao_igual(app_leve):
    cliente, vault, _ = app_leve
    nota = criar(cliente)
    antes = (vault / nota["rel"]).read_bytes()
    resposta = cliente.put("/api/notas/" + nota["rel"], json={"versao": nota["versao"], "corpo": "Aba antiga."},
                           headers={"X-Orquestra-Vault": "outro-vault"})
    assert resposta.status_code == 409 and "outro vault" in resposta.json()["erro"]
    assert (vault / nota["rel"]).read_bytes() == antes
    atual = cliente.get("/api/resumo").json()["vault_id"]
    assert cliente.put("/api/notas/" + nota["rel"], json={"versao": nota["versao"], "corpo": "Correto."},
                       headers={"X-Orquestra-Vault": atual}).status_code == 200


def test_arquivos_internos_nao_sao_editaveis_nem_servidos_como_midia(app_leve):
    cliente, vault, _ = app_leve
    pasta = vault / ".obsidian"
    pasta.mkdir()
    nota = pasta / "interno.md"
    nota.write_text("Estado interno.", encoding="utf-8")
    (pasta / "interno.svg").write_text("<svg/>", encoding="utf-8")
    resposta = cliente.put("/api/notas/.obsidian/interno.md", json={"versao": "inexistente", "corpo": "Não alterar."})
    assert resposta.status_code == 404 and nota.read_text(encoding="utf-8") == "Estado interno."
    assert cliente.get("/arquivo/.obsidian/interno.svg").status_code == 404


def test_recuperacao_cria_copia_byte_a_byte_sem_reverter_atual(app_leve):
    cliente, vault, _ = app_leve
    nota = criar(cliente)
    original = (vault / nota["rel"]).read_bytes()
    editada = cliente.put("/api/notas/" + nota["rel"], json={"versao": nota["versao"], "corpo": "Versão nova."})
    assert editada.status_code == 200
    atual = (vault / nota["rel"]).read_bytes()
    versoes = cliente.get("/api/notas/recuperacao/" + nota["rel"]).json()["versoes"]
    assert versoes and versoes[0]["tem_anterior"]
    copia = cliente.post("/api/notas/recuperacao/copia/" + nota["rel"], json={
        "id": versoes[0]["id"], "tipo": "antes", "titulo": "Versão recuperada",
    })
    assert copia.status_code == 200, copia.text
    assert copia.json()["rel"] != nota["rel"]
    assert (vault / copia.json()["rel"]).read_bytes() == original
    assert (vault / nota["rel"]).read_bytes() == atual
    assert cliente.get("/api/notas/recuperacao/" + nota["rel"], params={"id": "../segredo"}).status_code == 404


def test_nota_removida_vira_conflito_e_rascunho_pode_virar_copia(app_leve):
    cliente, vault, painel = app_leve
    nota = criar(cliente)
    (vault / nota["rel"]).unlink()
    painel.indice.sincronizar()  # mesmo sem qualquer cópia antiga no índice
    resposta = cliente.put("/api/notas/" + nota["rel"], json={"versao": nota["versao"], "corpo": "Rascunho meu."})
    assert resposta.status_code == 409 and resposta.json()["conflito"]
    copia = cliente.post("/api/notas/copia/" + nota["rel"], json={
        "titulo": "Meu rascunho recuperado", "corpo": "Rascunho meu.",
        "campos": {"status": "a_fazer", "prioridade": "alta", "campo_livre": "Valor preservado"},
    })
    assert copia.status_code == 200, copia.text
    assert not (vault / nota["rel"]).exists()
    recuperada = ler_nota(vault / copia.json()["rel"], vault)
    assert recuperada.corpo == "Rascunho meu."
    assert recuperada.meta["campo_livre"] == "Valor preservado" and recuperada.meta["prioridade"] == "alta"


@pytest.mark.parametrize("pedido", [
    {"campos": 1}, {"remover": 1}, {"campos": [{"nome": "campo", "tipo": "escolha", "opcoes": 1}]},
])
def test_personalizacao_malformada_nao_modifica_yaml(app_leve, pedido):
    cliente, vault, _ = app_leve
    arquivo = vault / "tarefas/_modulo.yaml"
    antes = arquivo.read_bytes()
    resposta = cliente.put("/api/modulos/tarefas", json=pedido)
    assert resposta.status_code == 400 and "erro" in resposta.json()
    assert arquivo.read_bytes() == antes


def test_yaml_parcial_preserva_last_good_sem_permitir_regravacao(app_leve):
    cliente, vault, painel = app_leve
    criar(cliente)
    arquivo = vault / "tarefas/_modulo.yaml"
    parcial = b"nome: Tarefas\ncampos: [configuracao, em, edicao]\n"
    arquivo.write_bytes(parcial)
    painel.recarregar_config()
    assert cliente.get("/m/tarefas").status_code == 200
    assert cliente.put("/api/modulos/tarefas", json={"nome": "Outro nome"}).status_code == 400
    assert cliente.post("/api/notas", json={"modulo": "tarefas", "titulo": "Bloqueada"}).status_code == 400
    assert arquivo.read_bytes() == parcial


def test_lista_e_busca_paginam_antes_de_renderizar_cartoes(app_leve):
    cliente, vault, painel = app_leve
    for numero in range(181):
        (vault / "tarefas/itens" / f"Nota {numero:03}.md").write_text("Texto para encontrar.\n", encoding="utf-8")
    painel.recarregar_tudo()
    primeira = cliente.get("/m/tarefas?aba=v1")
    segunda = cliente.get("/m/tarefas?aba=v1&pagina=2")
    ultima = cliente.get("/m/tarefas?aba=v1&pagina=3")
    assert [len(r.context["linhas"]) for r in (primeira, segunda, ultima)] == [80, 80, 21]
    assert segunda.context["paginacao"]["total"] == 181
    assert "aba=v1" in segunda.context["paginacao"]["proxima"]
    busca = cliente.get("/buscar?q=encontrar&pagina=2")
    assert len(busca.context["resultados"]) == 80
    assert busca.context["paginacao"]["total"] == 181
    assert "q=encontrar" in busca.context["paginacao"]["anterior"]
    assert len(primeira.content) < 120_000


def test_preparar_e_autorizar_git_sao_etapas_locais_distintas(app_leve):
    if not backup.git_disponivel():
        pytest.skip("Git não instalado")
    cliente, vault, _ = app_leve
    assert cliente.post("/api/backup/iniciar", json={}).status_code == 403
    token = cliente.get("/api/local/capacidade").json()["token"]
    cabecalhos = {"X-Orquestra-Local": token}
    preparado = cliente.post("/api/backup/iniciar", json={}, headers=cabecalhos)
    assert preparado.status_code == 200, preparado.text
    assert preparado.json()["revisar"] is True
    assert not backup.resumo(vault)["confiavel"]
    assert not (vault / ".git/refs/orquestra/backups").exists()
    assinatura = preparado.json()["resumo"]["assinatura"]
    assert assinatura
    assert cliente.post("/api/backup/confiar", json={"assinatura": assinatura}).status_code == 403
    autorizado = cliente.post("/api/backup/confiar", json={"assinatura": assinatura}, headers=cabecalhos)
    assert autorizado.status_code == 200 and autorizado.json()["confiavel"]
    criado = cliente.post("/api/backup/iniciar", json={"assinatura": assinatura}, headers=cabecalhos)
    assert criado.status_code == 200 and criado.json()["commit"] == "feito"
    assert ler_yaml(vault / "orquestra.yaml")["backup"]["auto_commit"] is True
    assert (vault / ".git/refs/orquestra/backups").is_file()


def test_falha_de_backup_nao_atualiza_ultimo_sucesso(app_leve, monkeypatch):
    _, _, painel = app_leve
    monkeypatch.setattr(backup, "commit", lambda _vault: "erro: falha sintética")
    monkeypatch.setattr(backup, "push", lambda _vault: pytest.fail("Não enviar antes do snapshot local"))
    resultado = painel.fazer_backup(enviar=True)
    estado = painel.ler_estado()["backup"]
    assert resultado["commit"].startswith("erro")
    assert "ultimo_commit" not in estado and "ultimo_push" not in estado
    assert estado["tentativa_commit"] and estado["tentativa_push"]
    assert painel.mudou_desde_o_backup


def test_disco_cheio_vira_erro_recuperavel_sem_alterar_nota(app_leve, monkeypatch):
    cliente, vault, _ = app_leve
    nota = criar(cliente)
    original = (vault / nota["rel"]).read_bytes()
    def falhar(*_args, **_kwargs):
        raise OSError("Falha sintética de disco")
    monkeypatch.setattr(armazenamento, "_trocar_com_captura", falhar)
    resposta = cliente.put("/api/notas/" + nota["rel"], json={"versao": nota["versao"], "corpo": "Meu rascunho."})
    assert resposta.status_code == 503 and "erro" in resposta.json()
    assert (vault / nota["rel"]).read_bytes() == original
