"""Cadastro único, agenda sem duplicação e exclusão explícita com recuperação."""
from __future__ import annotations

import json
import datetime as dt
from urllib.parse import quote

import pytest

from orquestra import armazenamento, lixeira
from orquestra.notas import Conflito
from orquestra.painel import Recusado


def local(cliente):
    return {"X-Orquestra-Local": cliente.get("/api/local/capacidade").json()["token"]}


def contato(painel):
    painel.adicionar_modulo("contatos")
    return painel.criar_nota("contatos", "Maria de exemplo", {"telefone": "(00) 00000-0000", "email": "maria@example.com", "grupos": ["amigos", "trabalho"]}, "Texto humano.")


def test_contato_pessoal_independente_e_cliente_sem_duplicar_dados(painel):
    nota = contato(painel)
    assert "clientes" not in painel.indice.modulos
    original = nota.caminho.read_bytes()
    cliente = painel.vincular_cliente(nota.rel, nota.versao)
    assert cliente.campo("contato_id") == nota.campo("contato_id")
    assert cliente.campo("telefone") is None and cliente.campo("email") is None
    assert nota.caminho.read_bytes() == original
    assert painel.vincular_cliente(nota.rel, nota.versao).rel == cliente.rel
    assert len(painel.indice.itens("clientes")) == 1


def test_vinculo_sobrevive_a_renomear_e_copias_nao_duplicam_identidade(painel):
    nota = contato(painel)
    cliente = painel.vincular_cliente(nota.rel, nota.versao)
    destino = nota.caminho.with_name("Outro nome.md")
    nota.caminho.rename(destino)
    painel.recarregar_tudo()
    from orquestra.contatos import contexto
    assert contexto(painel, cliente)["contato_vinculado"]["rel"].endswith("Outro nome.md")
    copia = painel.copiar_nota(destino.relative_to(painel.vault).as_posix(), "Outra pessoa", "Rascunho")
    assert copia.campo("contato_id") != cliente.campo("contato_id")


def test_recusa_id_inventado_duplicado_e_arquivo_desatualizado(painel):
    nota = contato(painel)
    painel.adicionar_modulo("clientes")
    with pytest.raises(Recusado):
        painel.criar_nota("clientes", "Inválido", {"contato_id": "abc"})
    with pytest.raises(Recusado, match="permanente"):
        painel.editar_nota(nota.rel, nota.versao, campos={"contato_id": "outro"})
    copia = nota.caminho.with_name("Duplicado.md")
    copia.write_bytes(nota.caminho.read_bytes())
    painel.recarregar_tudo()
    with pytest.raises(Recusado, match="duplicado"):
        painel.vincular_cliente(nota.rel, nota.versao)
    copia.unlink()
    painel.recarregar_tudo()
    nota.caminho.write_text("Texto alterado externamente", encoding="utf-8")
    with pytest.raises(Conflito):
        painel.vincular_cliente(nota.rel, nota.versao)


def test_vincula_contato_feito_no_obsidian_e_preserva_historico(painel):
    nota = contato(painel)
    externo = nota.caminho.with_name("Contato externo.md")
    externo.write_text("Histórico escrito no Obsidian.\n", encoding="utf-8")
    painel.recarregar_tudo()
    atual = painel.nota(externo.relative_to(painel.vault).as_posix())
    cliente = painel.vincular_cliente(atual.rel, atual.versao)
    assert cliente.campo("contato_id")
    assert painel.nota(atual.rel).corpo.strip() == "Histórico escrito no Obsidian."


def test_telas_cadastro_vinculo_e_agenda_unica(cliente):
    nota = contato(cliente.painel)
    assert cliente.get("/m/contatos").status_code == 200
    pagina = cliente.get("/n/" + quote(nota.rel))
    assert 'id="vincular-cliente"' in pagina.text
    resposta = cliente.post("/api/contatos/cliente/" + quote(nota.rel), json={"versao": nota.versao})
    assert resposta.status_code == 200
    pagina = cliente.get(resposta.json()["url"])
    assert 'name="contato_id"' in pagina.text
    assert "maria@example.com" in pagina.text
    assert 'data-novo' in cliente.get("/m/clientes").text
    cliente.painel.adicionar_modulo("agenda")
    inicio = cliente.get("/").text
    assert 'href="/m/agenda"' not in inicio and 'href="/agenda"' in inicio
    assert cliente.get("/m/agenda", follow_redirects=False).headers["location"] == "/agenda"
    assert cliente.get("/m/agenda?aba=maquina").status_code == 200
    assert 'data-pronto="agenda"' not in cliente.get("/ajustes/areas").text


def test_excluir_restaurar_e_apagar_nao_afetam_anexos_ou_outros_arquivos(painel):
    nota = contato(painel)
    original = nota.caminho.read_bytes()
    anexo = painel.vault / "imagem.png"
    anexo.write_bytes(b"exemplo")
    identificador = painel.excluir(nota.rel, nota.versao)
    assert nota.rel not in painel.indice.notas and not nota.caminho.exists()
    assert all(n.rel != nota.rel for n in painel.indice.buscar("Maria"))
    item = lixeira.listar(painel.vault)[0]
    assert item["id"] == identificador
    assert painel.restaurar_excluida(identificador, item["versao"]) == nota.rel
    assert nota.caminho.read_bytes() == original
    assert not lixeira.listar(painel.vault)
    identificador = painel.excluir(nota.rel, nota.versao)
    item = lixeira.listar(painel.vault)[0]
    lixeira.apagar(painel.vault, identificador, item["versao"])
    assert not lixeira.listar(painel.vault)
    assert anexo.read_bytes() == b"exemplo"


def test_lixeira_recusa_conflitos_e_nao_sobrescreve_restauracao(painel):
    nota = contato(painel)
    with pytest.raises(armazenamento.ConflitoDeEscrita):
        painel.excluir(nota.rel, "antiga")
    assert nota.caminho.exists()
    identificador = painel.excluir(nota.rel, nota.versao)
    item = lixeira.listar(painel.vault)[0]
    nota.caminho.write_text("Outra nota", encoding="utf-8")
    with pytest.raises(Conflito):
        painel.restaurar_excluida(identificador, item["versao"])
    assert nota.caminho.read_text(encoding="utf-8") == "Outra nota"
    with pytest.raises(Conflito):
        lixeira.apagar(painel.vault, identificador, "antiga")
    assert lixeira.listar(painel.vault)


@pytest.mark.parametrize("rel", ["AGENTS.md", "CLAUDE.md", "tarefas/maquina/instrucoes.md", "contatos/_modulo.yaml"])
def test_protege_instrucoes_e_configuracoes(painel, rel):
    assert not lixeira.pode_excluir(painel, rel)


def test_lixeira_api_exige_capacidade_e_versao(cliente):
    nota = contato(cliente.painel)
    rota = "/api/excluir/" + quote(nota.rel)
    assert cliente.post(rota, json={"versao": nota.versao}).status_code == 403
    headers = local(cliente)
    assert cliente.post(rota, headers=headers, json={}).status_code == 400
    resposta = cliente.post(rota, headers=headers, json={"versao": nota.versao})
    assert resposta.status_code == 200
    assert "Maria de exemplo" in cliente.get("/lixeira").text
    item = lixeira.listar(cliente.painel.vault)[0]
    rota = f'/api/lixeira/{item["id"]}/restaurar'
    assert cliente.post(rota, json={"versao": item["versao"]}).status_code == 403
    assert cliente.post(rota, headers=headers, json={"versao": item["versao"]}).status_code == 200


def test_lixeira_metadados_fora_do_vault_nao_restauram(painel):
    nota = contato(painel)
    identificador = painel.excluir(nota.rel, nota.versao)
    registro = painel.vault / ".trash/orquestra" / identificador / "registro.json"
    registro.write_text(json.dumps({"rel": "../fora.md"}), encoding="utf-8")
    with pytest.raises(ValueError):
        painel.restaurar_excluida(identificador, nota.versao)


def test_excluir_contato_preserva_cliente_e_restaurar_recupera_vinculo(painel):
    from orquestra.contatos import contexto
    nota = contato(painel)
    cliente = painel.vincular_cliente(nota.rel, nota.versao)
    identificador = painel.excluir(nota.rel, nota.versao)
    assert contexto(painel, cliente)["contato_vinculado"] is None
    assert painel.nota(cliente.rel)
    painel.restaurar_excluida(identificador, nota.versao)
    assert contexto(painel, cliente)["contato_vinculado"]["id"] == cliente.campo("contato_id")


def test_filtros_de_contatos_buscam_sem_acento_e_combinam_grupos(cliente):
    nota = contato(cliente.painel)
    cliente.painel.editar_nota(nota.rel, nota.versao, titulo="Márcia", campos={"favorito": True})
    cliente.painel.criar_nota("contatos", "Outra pessoa", {"grupos": ["familia"]})
    html = cliente.get("/m/contatos?q=marcia&grupo=amigos&favoritos=1").text
    assert "Márcia" in html and "Outra pessoa" not in html
    html = cliente.get("/m/contatos?grupo=familia&favoritos=1").text
    assert "Outra pessoa" not in html and 'Nenhum item' in html


@pytest.mark.parametrize("pronto", [True, False])
def test_retirar_e_adicionar_novamente_preserva_notas_e_schema(cliente, pronto):
    painel = cliente.painel
    modulo = painel.adicionar_modulo("contatos") if pronto else painel.criar_modulo("Minha coleção", com_quadro=False)
    nota = painel.criar_nota(modulo.id, "Uma nota minha", corpo="Não modificar este texto.")
    arquivo = modulo.pasta / "_modulo.yaml"
    original, conteudo = arquivo.read_bytes(), nota.caminho.read_bytes()
    resposta = cliente.post(f"/api/modulos/{modulo.id}/desligar", json={})
    assert resposta.status_code == 200
    html = cliente.get("/ajustes/areas").text
    assert f'data-religar="{modulo.id}"' in html
    assert f'data-pronto="{modulo.id}"' not in html
    resposta = cliente.post("/api/pastas/adotar", json={"pasta": modulo.id})
    assert resposta.status_code == 200
    assert arquivo.read_bytes() == original and nota.caminho.read_bytes() == conteudo
    assert f'data-religar="{modulo.id}"' not in cliente.get("/ajustes/areas").text
    assert cliente.get(resposta.json()["url"]).status_code == 200


def test_resumos_reutilizados_invalidam_com_edicao_dia_e_schema(painel, monkeypatch):
    modulo = painel.modulo("tarefas")
    hoje = dt.date.today()
    chamadas = []
    calcular = painel.indice._calcular_resumo
    def contar(*args):
        chamadas.append(args)
        return calcular(*args)
    monkeypatch.setattr(painel.indice, "_calcular_resumo", contar)
    primeiro = painel.indice.resumo(modulo, hoje)
    assert painel.indice.resumo(modulo, hoje) == primeiro
    primeiro.total = -1
    assert painel.indice.resumo(modulo, hoje).total != -1
    assert len(chamadas) == 1
    nota = painel.criar_nota("tarefas", "Item novo", {"data": hoje})
    depois = painel.indice.resumo(modulo, hoje)
    assert len(chamadas) == 2
    assert depois.total > 0
    painel.editar_nota(nota.rel, nota.versao, campos={"status": "feito"})
    assert painel.indice.resumo(modulo, hoje).abertos == depois.abertos - 1
    painel.indice.resumo(modulo, hoje + dt.timedelta(days=1))
    assert len(chamadas) == 4
    painel.recarregar_config()
    painel.indice.resumo(painel.modulo("tarefas"), hoje + dt.timedelta(days=1))
    assert len(chamadas) == 5
