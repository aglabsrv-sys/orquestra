import pytest

from orquestra import habitos
from orquestra.painel import Painel


def local(cliente):
    return {"X-Orquestra-Local": cliente.get("/api/local/capacidade").json()["token"]}


def escrever(cliente, rel, dados=b"Texto pessoal.\n"):
    caminho = cliente.painel.vault / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(dados)
    cliente.painel.apos_escrita(caminho, "painel")
    return caminho


def consultar(cliente, rel):
    resposta = cliente.get("/api/contexto", params={"rel": rel})
    assert resposta.status_code == 200
    return resposta.json()


def agir(cliente, item, acao, headers=None):
    return cliente.post("/api/contexto/acao", headers=headers or local(cliente), json={
        **{chave: item[chave] for chave in ("rel", "modulo", "chave", "versao")}, "acao": acao,
    })


def test_menu_respeita_versao_capacidade_e_arquivos_protegidos(cliente):
    caminho = escrever(cliente, "Pessoal/Nota.md")
    item = consultar(cliente, "Pessoal/Nota.md")
    assert item["arquivar"] and item["excluir"]
    assert agir(cliente, item, "excluir", {"X-Orquestra-Local": "invalida"}).status_code == 403
    caminho.write_bytes(b"Edicao externa.\n")
    assert agir(cliente, item, "arquivar").status_code == 409
    assert caminho.read_bytes() == b"Edicao externa.\n"
    protegido = consultar(cliente, "AGENTS.md")
    assert not protegido["arquivar"] and not protegido["excluir"]
    assert agir(cliente, protegido, "arquivar").status_code == 400
    pasta = consultar(cliente, "tarefas")
    assert not pasta["arquivar"] and not pasta["excluir"]


def test_arquivar_nota_pessoal_preserva_bytes_e_evitar_sobrescrita(cliente):
    original = escrever(cliente, "Pessoal/Nota.md", b"Texto humano sem frontmatter.\n")
    existente = escrever(cliente, "Pessoal/arquivo/Nota.md", b"Versao anterior.\n")
    resposta = agir(cliente, consultar(cliente, "Pessoal/Nota.md"), "arquivar")
    assert resposta.status_code == 200 and not original.exists()
    assert (cliente.painel.vault / resposta.json()["rel"]).read_bytes() == b"Texto humano sem frontmatter.\n"
    assert existente.read_bytes() == b"Versao anterior.\n"
    assert not consultar(cliente, resposta.json()["rel"])["arquivar"]


def test_pasta_da_raiz_pode_ir_para_lixeira_e_voltar(cliente):
    original = escrever(cliente, "Pessoal/Subpasta/Nota.md")
    anexo = escrever(cliente, "Pessoal/Manual.pdf", b"%PDF-sintetico")
    resposta = agir(cliente, consultar(cliente, "Pessoal"), "excluir")
    assert resposta.status_code == 200 and not original.exists()
    from orquestra import lixeira
    item = next(i for i in lixeira.listar(cliente.painel.vault) if i["id"] == resposta.json()["id"])
    assert cliente.post(f"/api/lixeira/{item['id']}/restaurar", headers=local(cliente), json={"versao": item["versao"]}).status_code == 200
    assert original.read_bytes() == b"Texto pessoal.\n" and anexo.read_bytes() == b"%PDF-sintetico"


def test_pasta_com_contrato_ou_links_nao_pode_ser_movida(cliente):
    escrever(cliente, "Pessoal/Contrato/AGENTS.md")
    item = consultar(cliente, "Pessoal")
    assert not item["excluir"] and not item["arquivar"]
    assert agir(cliente, item, "excluir").status_code == 400


def test_pasta_recusa_acao_apos_edicao_de_uma_nota_interna(cliente):
    nota = escrever(cliente, "Pessoal/Subpasta/Nota.md")
    item = consultar(cliente, "Pessoal")
    nota.write_bytes(b"Texto alterado antes da confirmacao.\n")
    assert agir(cliente, item, "excluir").status_code == 409
    assert nota.is_file()


def importar(cliente, destino, nome, dados, **extra):
    return cliente.post("/api/pastas/importar", params={"destino": destino, "nome": nome, **extra},
                        headers={**local(cliente), "Content-Type": "application/octet-stream"}, content=dados)


def test_importar_preserva_conteudo_e_duplica_nome_sem_sobrescrever(cliente):
    original = escrever(cliente, "Pessoal/Nota.md")
    resposta = importar(cliente, "Pessoal", "Nota.md", b"Texto importado.\n")
    assert resposta.status_code == 200 and resposta.json()["renomeado"]
    assert original.read_bytes() == b"Texto pessoal.\n"
    assert (cliente.painel.vault / resposta.json()["rel"]).read_bytes() == b"Texto importado.\n"
    assert importar(cliente, "Pessoal", "Manual.pdf", b"%PDF-demo").status_code == 200
    assert "Manual.pdf" in cliente.get("/pastas/Pessoal").text
    download = cliente.get("/download/Pessoal/Manual.pdf")
    assert download.status_code == 200 and download.content == b"%PDF-demo"
    assert download.headers["content-disposition"].startswith("attachment;")


@pytest.mark.parametrize("destino,nome", [
    ("../fora", "Nota.md"), ("tarefas/maquina", "Nota.md"), ("_orquestra", "Nota.md"),
    ("tarefas/itens", "AGENTS.md"), ("tarefas/itens", "../Nota.md"), ("tarefas/itens", "executar.py"),
    ("tarefas/itens", "CON.txt"), ("tarefas/itens", "_modulo.yaml"),
])
def test_importar_recusa_destino_e_nome_protegidos(cliente, destino, nome):
    assert importar(cliente, destino, nome, b"nao gravar").status_code in (400, 404)


def test_importar_exige_capacidade_e_identidade_do_cofre(cliente):
    consulta = {"destino": "tarefas/itens", "nome": "Importada.md"}
    assert cliente.post("/api/pastas/importar", params=consulta, headers={"Content-Type": "application/octet-stream"}, content=b"texto").status_code == 403
    assert cliente.post("/api/pastas/importar", params=consulta, headers={**local(cliente), "Content-Type": "application/octet-stream", "X-Orquestra-Vault": "outro"}, content=b"texto").status_code == 409
    assert not (cliente.painel.vault / "tarefas/itens/Importada.md").exists()


def test_importacao_tem_limite_proprio_sem_aumentar_o_limite_json(cliente):
    assert importar(cliente, "tarefas/itens", "Grande.txt", b"x" * (20 * 1024 * 1024 + 1)).status_code == 413
    assert not (cliente.painel.vault / "tarefas/itens/Grande.txt").exists()
    resposta = cliente.post("/api/pastas/nota", json={"pasta": "", "titulo": "Grande", "corpo": "x" * (2 * 1024 * 1024)})
    assert resposta.status_code == 413


def test_importar_em_estudo_cria_referencia_na_pasta_correta(cliente):
    painel = cliente.painel
    painel.adicionar_modulo("estudos")
    estudo = painel.criar_nota("estudos", "Curso demonstrativo", {})
    destino = "estudos/referencias/Curso demonstrativo"
    resposta = importar(cliente, destino, "Resumo.md", b"Notas da aula.\n", vinculo=estudo.rel)
    assert resposta.status_code == 200
    pagina = cliente.get("/m/estudos", params={"abrir": estudo.rel})
    assert "Resumo" in pagina.text
    assert importar(cliente, "tarefas/itens", "Outra.md", b"texto", vinculo=estudo.rel).status_code == 400


def test_ordem_de_habitos_persiste_sem_reescrever_notas(cliente):
    painel = cliente.painel
    criados = [habitos.salvar(painel, {"titulo": nome, "meta_semanal": 3}) for nome in ("Caminhar", "Ler", "Estudar")]
    antes = {r["rel"]: (painel.vault / r["rel"]).read_bytes() for r in criados}
    contexto = habitos.montar(painel)
    ordem = [r["rel"] for r in reversed(criados)]
    resposta = cliente.post("/api/habitos/ordem", json={"ordem": ordem, "versao": contexto["versao_ordem"]})
    assert resposta.status_code == 200
    assert [i["rel"] for i in habitos.montar(Painel(painel.vault))["itens"]] == ordem
    assert all((painel.vault / rel).read_bytes() == bruto for rel, bruto in antes.items())
    assert cliente.post("/api/habitos/ordem", json={"ordem": list(reversed(ordem)), "versao": contexto["versao_ordem"]}).status_code == 409
    assert cliente.post("/api/habitos/ordem", json={"ordem": [ordem[0]] * 3, "versao": resposta.json()["versao"]}).status_code == 409
