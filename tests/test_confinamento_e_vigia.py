"""Vaults sintéticos: fronteiras de arquivos, observação real e eventos entre threads."""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orquestra import adocao, diario, preparo, temas
from orquestra.caminhos import CaminhoInseguro, arquivos_do_vault, caminho_no_vault
from orquestra.eventos import Eventos
from orquestra.indice import Indice
from orquestra.mcp_servidor import ErroDeFerramenta, Ferramentas
from orquestra.notas import FrontmatterInvalido, gravar_nota, ler_nota
from orquestra.painel import NaoEncontrado, Painel, Recusado
from orquestra.servidor import criar_app
from orquestra.vigia import Vigia
import orquestra.vigia as modulo_vigia
import orquestra.indice as modulo_indice


MARCADOR = "CONTEUDO_PRIVADO_SINTETICO_FORA_DO_VAULT"


@pytest.fixture
def pequeno(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "orquestra.yaml").write_text("nome: Teste\ntema: brasa\ncaptura: tarefas\nbackup:\n  auto_commit: false\n", encoding="utf-8")
    for zona in ("itens", "humano", "maquina"):
        (vault / "tarefas" / zona).mkdir(parents=True)
    (vault / "tarefas/_modulo.yaml").write_text(
        "nome: Tarefas\ncampos:\n  status: {tipo: texto}\n  valor: {tipo: numero}\n  origem: {tipo: texto}\n", encoding="utf-8"
    )
    (vault / "tarefas/itens/A.md").write_text("---\nstatus: aberto\norigem: humano\n---\nTexto inicial.\n", encoding="utf-8")
    (vault / "AGENTS.md").write_text("Regras sintéticas.", encoding="utf-8")
    tema = vault / "_orquestra/temas/brasa/tema.yaml"
    tema.parent.mkdir(parents=True)
    tema.write_text("nome: Tema inicial\n", encoding="utf-8")
    for pasta in ("diario/registro", "diario/sessoes"):
        (vault / pasta).mkdir(parents=True)
    fora = tmp_path / "fora"
    fora.mkdir()
    (fora / "segredo.md").write_text("---\nstatus: privado\n---\n" + MARCADOR, encoding="utf-8")
    (fora / "imagem.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>' + MARCADOR + "</text></svg>", encoding="utf-8")
    (fora / "_modulo.yaml").write_text("nome: Externo\n", encoding="utf-8")
    (fora / "tema.yaml").write_text("nome: Tema externo secreto\n", encoding="utf-8")
    (fora / "estado.json").write_text('{"privado":true}', encoding="utf-8")
    return vault, fora


@pytest.fixture
def vincular(tmp_path):
    """Junction Windows real dispensa privilégio; symlink de diretório nos Unix."""
    criados = []

    def criar(destino: Path, alvo: Path):
        assert destino.absolute().is_relative_to(tmp_path.absolute())
        assert alvo.absolute().is_relative_to(tmp_path.absolute())
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            guardado = tmp_path / f"guardado-{len(criados)}"
            assert guardado.absolute().is_relative_to(tmp_path.absolute())
            destino.rename(guardado)
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(alvo.resolve()), str(destino))
        else:
            destino.symlink_to(alvo, target_is_directory=True)
        criados.append(destino)
        return destino

    yield criar
    for caminho in reversed(criados):
        if caminho.is_symlink():
            caminho.unlink()
        elif os.name == "nt" and caminho.exists():
            os.rmdir(caminho)  # remove somente a junction, nunca o conteúdo do alvo


def bytes_da_pasta(pasta: Path):
    return {p.relative_to(pasta).as_posix(): p.read_bytes() for p in pasta.rglob("*") if p.is_file()}


@pytest.mark.parametrize("rel", ["../fora/segredo.md", "tarefas/../../fora/segredo.md", "tarefas\\..\\..\\fora", "C:\\fora\\segredo.md", "C:segredo.md", "//servidor/compartilhamento/segredo.md", "tarefas/itens/A.md:fluxo", "tarefas/\x00.md"])
def test_caminhos_recusam_traversal_absoluto_externo_ads_e_controles(pequeno, rel):
    vault, _ = pequeno
    with pytest.raises(CaminhoInseguro):
        caminho_no_vault(vault, rel)


def test_indice_http_mcp_nao_expoem_junction_externa_load_ou_sync(pequeno, vincular):
    vault, fora = pequeno
    vincular(vault / "externo", fora)
    indice = Indice(vault)
    indice.carregar()
    indice.sincronizar()
    assert not any(rel.startswith("externo/") for rel in indice.notas)
    assert "externo" not in indice.modulos
    assert not any(rel.startswith("externo/") for rel in indice.midias.values())
    mcp = Ferramentas(vault)
    assert mcp.buscar(MARCADOR) == []
    with pytest.raises(ErroDeFerramenta):
        mcp.ler_nota("externo/segredo.md")
    with TestClient(criar_app(vault, False, False), base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        for url in ("/n/externo/segredo.md", "/arquivo/externo/imagem.svg", "/pastas/externo"):
            resposta = cliente.get(url)
            assert resposta.status_code == 404 and MARCADOR not in resposta.text
        busca = cliente.get("/buscar", params={"q": MARCADOR}).text
        assert "0 resultado(s)" in busca and "/n/externo/" not in busca
        assert cliente.get("/api/pastas/resumo", params={"pasta": "externo"}).status_code in (400, 404)


def test_analisar_vault_nao_conta_nem_infere_notas_de_junction(pequeno, vincular):
    vault, fora = pequeno
    vincular(vault / "externo", fora)
    analise = preparo.analisar(vault)
    assert "externo" not in [p["pasta"] for p in analise["pastas"]]
    assert analise["notas"] == 2  # A.md e AGENTS.md, ambos dentro do vault
    assert MARCADOR not in str(analise)


def test_link_trocado_depois_de_indexar_nao_usa_nota_ou_modulo_em_cache(pequeno, vincular):
    vault, fora = pequeno
    (fora / "itens").mkdir()
    (fora / "itens/A.md").write_text(MARCADOR, encoding="utf-8")
    app = criar_app(vault, False, False)
    painel = app.state.painel
    mcp = Ferramentas(vault)
    antes = bytes_da_pasta(fora)
    versao = painel.nota("tarefas/itens/A.md").versao
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        vincular(vault / "tarefas", fora)
        resposta = cliente.get("/n/tarefas/itens/A.md")
        assert resposta.status_code == 404 and MARCADOR not in resposta.text
        for operacao in (
            lambda: painel.criar_nota("tarefas", "Nova"),
            lambda: painel.editar_nota("tarefas/itens/A.md", versao, corpo="alterado"),
            lambda: painel.arquivar("tarefas/itens/A.md", versao=versao),
        ):
            with pytest.raises((CaminhoInseguro, NaoEncontrado, Recusado)):
                operacao()
        with pytest.raises(ErroDeFerramenta):
            mcp.ler_nota("tarefas/itens/A.md")
    painel.indice.sincronizar()
    assert not any(rel.startswith("tarefas/") for rel in painel.indice.notas)
    assert bytes_da_pasta(fora) == antes


def test_raiz_substituida_por_junction_nao_redefine_limite_do_vault(pequeno, vincular):
    vault, fora = pequeno
    (fora / "tarefas/itens").mkdir(parents=True)
    (fora / "tarefas/itens/A.md").write_text(MARCADOR, encoding="utf-8")
    (fora / "tarefas/_modulo.yaml").write_text("nome: Área externa\n", encoding="utf-8")
    (fora / "AGENTS.md").write_text(MARCADOR, encoding="utf-8")
    (fora / "orquestra.yaml").write_text("nome: Painel externo\n", encoding="utf-8")
    app = criar_app(vault, False, False)
    painel = app.state.painel
    mcp = Ferramentas(vault)
    nota = ler_nota(vault / "tarefas/itens/A.md", vault)
    antes = bytes_da_pasta(fora)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        vincular(vault, fora)
        assert list(arquivos_do_vault(vault)) == []
        with pytest.raises(CaminhoInseguro):
            ler_nota(vault / "tarefas/itens/A.md", vault)
        with pytest.raises((CaminhoInseguro, NaoEncontrado, Recusado)):
            painel.criar_nota("tarefas", "Nao pode sair")
        nota.corpo = "Rascunho que não deve ser gravado fora"
        with pytest.raises(CaminhoInseguro):
            gravar_nota(nota, versao_esperada=nota.versao)
        for url in ("/n/tarefas/itens/A.md", "/arquivo/imagem.svg"):
            resposta = cliente.get(url)
            assert resposta.status_code in (400, 404) and MARCADOR not in resposta.text
        resposta = cliente.post("/api/notas", json={"modulo": "tarefas", "titulo": "Nao pode sair"})
        assert resposta.status_code in (400, 404)
        with pytest.raises(ErroDeFerramenta):
            mcp.ler_nota("tarefas/itens/A.md")
        with pytest.raises(ErroDeFerramenta):
            mcp.regras()
        assert mcp.buscar(MARCADOR) == []
        painel.indice.sincronizar()
        assert painel.indice.notas == {} and painel.indice.modulos == {}
        painel.recarregar_config()
        assert painel.config.nome == "Teste"
    assert bytes_da_pasta(fora) == antes


def test_indice_repete_leitura_quando_arquivo_muda_entre_read_e_stat(pequeno, monkeypatch):
    vault, _ = pequeno
    indice = Indice(vault)
    indice.carregar()
    caminho = vault / "tarefas/itens/A.md"
    caminho.write_text("Primeira versão\n", encoding="utf-8")
    ler_original = modulo_indice.ler_nota
    leituras = []

    def ler_e_mudar(caminho_lido, vault_lido, **kwargs):
        nota = ler_original(caminho_lido, vault_lido, **kwargs)
        if caminho_lido == caminho:
            leituras.append(nota.corpo)
            if len(leituras) == 1:
                caminho.write_text("Segunda versão, com tamanho diferente\n", encoding="utf-8")
        return nota

    monkeypatch.setattr(modulo_indice, "ler_nota", ler_e_mudar)
    indice.atualizar(caminho)
    assert len(leituras) >= 2
    assert indice.notas["tarefas/itens/A.md"].corpo == "Segunda versão, com tamanho diferente\n"
    indice.sincronizar()
    assert indice.notas["tarefas/itens/A.md"].corpo == caminho.read_text(encoding="utf-8")


def test_indice_nao_carimba_assinatura_de_versao_que_nao_conseguiu_ler(pequeno, monkeypatch):
    vault, _ = pequeno
    indice = Indice(vault)
    indice.carregar()
    caminho = vault / "tarefas/itens/A.md"
    caminho.write_text("Versão em movimento 0\n", encoding="utf-8")
    ler_original = modulo_indice.ler_nota
    leituras = 0

    def escritor_continuo(caminho_lido, vault_lido, **kwargs):
        nonlocal leituras
        nota = ler_original(caminho_lido, vault_lido, **kwargs)
        if caminho_lido == caminho:
            leituras += 1
            caminho.write_text("Versão em movimento " + "x" * leituras + "\n", encoding="utf-8")
        return nota

    monkeypatch.setattr(modulo_indice, "ler_nota", escritor_continuo)
    indice.atualizar(caminho)
    assert leituras == 3
    assert "tarefas/itens/A.md" not in indice._assinaturas
    monkeypatch.setattr(modulo_indice, "ler_nota", ler_original)
    indice.sincronizar()
    assert indice.notas["tarefas/itens/A.md"].corpo == caminho.read_text(encoding="utf-8")


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_json_http_recusa_numero_nao_finito_ate_em_campo_livre(pequeno, literal):
    vault, _ = pequeno
    caminho = vault / "tarefas/itens/A.md"
    antes = caminho.read_bytes()
    app = criar_app(vault, False, False)
    versao = app.state.painel.nota("tarefas/itens/A.md").versao
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        payload = '{"versao":"' + versao + '","campos":{"livre":{"aninhado":[' + literal + ']}}}'
        resposta = cliente.put("/api/notas/tarefas/itens/A.md", content=payload, headers={"Content-Type": "application/json"})
        assert resposta.status_code == 400
        payload = '{"modulo":"tarefas","valores":{"valor":' + literal + '}}'
        resposta = cliente.post("/api/numeros", content=payload, headers={"Content-Type": "application/json"})
        assert resposta.status_code == 400
    assert caminho.read_bytes() == antes
    assert list((vault / "tarefas/itens").glob("*.md")) == [caminho]


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), float("-inf")])
def test_escrita_backend_recusa_metadata_nao_finita_antes_de_alterar_bytes(pequeno, valor):
    vault, _ = pequeno
    caminho = vault / "tarefas/itens/A.md"
    antes = caminho.read_bytes()
    nota = ler_nota(caminho, vault)
    nota.meta["livre"] = {"aninhado": [valor]}
    with pytest.raises((ValueError, FrontmatterInvalido)):
        gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_bytes() == antes


@pytest.mark.parametrize("literal", [".nan", ".inf", "-.inf"])
def test_nota_externa_com_nao_finito_fica_protegida_sem_regravar(pequeno, literal):
    vault, _ = pequeno
    caminho = vault / "tarefas/itens/Externa.md"
    caminho.write_text("---\nvalor: " + literal + "\n---\nTexto da pessoa.\n", encoding="utf-8")
    antes = caminho.read_bytes()
    nota = ler_nota(caminho, vault)
    assert nota.erro
    with pytest.raises(FrontmatterInvalido):
        gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_bytes() == antes


@pytest.mark.parametrize("url,payload", [
    ("/api/modulos", {"nome": "Nome", "quadro": "false"}),
    ("/api/coletores/ativo", {"modulo": "tarefas", "script": "x.py", "ativo": "false"}),
    ("/api/config", {"nome": "Nome", "campo_desconhecido": "NAO_REPETIR_VALOR_PRIVADO"}),
    ("/api/notas", {"modulo": "tarefas", "titulo": "Nome", "campos": [1, 2]}),
])
def test_contrato_http_recusa_coercao_e_campos_estranhos_sem_ecoar_valor(pequeno, url, payload):
    vault, _ = pequeno
    antes = bytes_da_pasta(vault)
    with TestClient(criar_app(vault, False, False), base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        resposta = cliente.post(url, json=payload)
        assert resposta.status_code == 400
        assert "NAO_REPETIR_VALOR_PRIVADO" not in resposta.text
    assert bytes_da_pasta(vault) == antes


@pytest.mark.parametrize("zona", ["itens", "humano", "arquivo", "maquina", "diario", "_orquestra"])
def test_escritas_auxiliares_nao_atravessam_junctions(pequeno, vincular, zona):
    vault, fora = pequeno
    painel = Painel(vault)
    rel = "tarefas/itens/A.md"
    original = (vault / rel).read_bytes()
    versao = painel.nota(rel).versao
    destino = vault / zona if zona in ("diario", "_orquestra") else vault / "tarefas" / zona
    vincular(destino, fora)
    antes = bytes_da_pasta(fora)
    if zona == "_orquestra":
        assert painel.ler_estado() == {}
        painel.gravar_estado("teste", "x", "nao pode sair")  # falha recuperável, sem escrever no alvo
    else:
        operacoes = {
            "itens": lambda: painel.criar_nota("tarefas", "Fora"),
            "humano": lambda: painel.criar_nota("tarefas", "Fora", zona="humano"),
            "arquivo": lambda: painel.arquivar(rel, versao=versao),
            "maquina": lambda: painel.registrar_aprendizado("tarefas", "Nao pode sair"),
            "diario": lambda: painel.registrar_sessao("teste", "pedido", "feito"),
        }
        with pytest.raises((CaminhoInseguro, NaoEncontrado, Recusado)):
            operacoes[zona]()
        if zona == "itens":
            with pytest.raises((CaminhoInseguro, NaoEncontrado)):
                painel.registrar_numeros("tarefas", {"valor": 2})
        if zona == "diario":
            with pytest.raises(CaminhoInseguro):
                diario.registrar(vault, "teste", "x.md")
            assert diario.ler_sessoes(vault, dt.date.today()) == ""
            assert diario.ler_registro(vault, dt.date.today()) == []
            assert diario.dias_com_registro(vault) == []
    assert bytes_da_pasta(fora) == antes
    if zona != "itens":
        assert (vault / rel).read_bytes() == original


def test_adotar_desligar_criar_e_copiar_modelo_nao_escrevem_em_junction(pequeno, vincular):
    vault, fora = pequeno
    vincular(vault / "externo", fora)
    painel = Painel(vault)
    antes = bytes_da_pasta(fora)
    with pytest.raises(adocao.NaoPodeAdotar):
        adocao.adotar(vault, "externo")
    with pytest.raises(adocao.NaoPodeAdotar):
        adocao.desligar(vault, "externo")
    with pytest.raises((CaminhoInseguro, Recusado)):
        painel.criar_modulo("Externo")
    with pytest.raises((CaminhoInseguro, NaoEncontrado)):
        painel.criar_nota_em_pasta("externo", "Nao criar")
    # Mesmo quando o catálogo encontra a pasta já existente e apenas a preserva.
    vincular(vault / "radar", fora)
    assert preparo.adicionar_modulo(vault, "radar", exemplos=True) is False
    assert bytes_da_pasta(fora) == antes


def test_tema_vinculado_nao_e_lido_nem_recebe_copia_do_preparo(pequeno, vincular):
    vault, fora = pequeno
    vincular(vault / "_orquestra/temas/brasa", fora)
    antes = bytes_da_pasta(fora)
    assert all(tema["nome"] != "Tema externo secreto" for tema in temas.listar(vault))
    with pytest.raises(CaminhoInseguro):
        preparo.preparar(vault, [], exemplos=False, com_backup=False)
    assert bytes_da_pasta(fora) == antes


def test_diario_vinculado_nao_faz_arquivamento_concluido_parecer_falha(pequeno, vincular):
    vault, fora = pequeno
    painel = Painel(vault)
    rel = "tarefas/itens/A.md"
    original = (vault / rel).read_bytes()
    versao = painel.nota(rel).versao
    vincular(vault / "diario", fora)
    antes = bytes_da_pasta(fora)
    novo = painel.arquivar(rel, versao=versao)
    assert not (vault / rel).exists() and (vault / novo).read_bytes() == original
    assert bytes_da_pasta(fora) == antes


def test_link_interno_tambem_e_recusado_mas_raiz_escolhida_pode_ser_alias(pequeno, vincular, tmp_path):
    vault, _ = pequeno
    vincular(vault / "atalho", vault / "tarefas")
    with pytest.raises(CaminhoInseguro):
        caminho_no_vault(vault, "atalho/itens/A.md")
    indice = Indice(vault)
    indice.carregar()
    assert not any(rel.startswith("atalho/") for rel in indice.notas)
    alias = vincular(tmp_path / "vault-escolhido", vault)
    escolhido = Indice(alias)
    escolhido.carregar()
    assert "tarefas/itens/A.md" in escolhido.notas


@pytest.mark.skipif(os.name == "nt", reason="Junctions reais cobertas acima; symlink de arquivo Unix não exige privilégio")
def test_symlink_de_arquivo_unix_nao_entra_no_indice_ou_leitura(pequeno):
    vault, fora = pequeno
    (vault / "isca.md").symlink_to(fora / "segredo.md")
    indice = Indice(vault)
    indice.carregar()
    assert "isca.md" not in indice.notas
    with pytest.raises(CaminhoInseguro):
        caminho_no_vault(vault, "isca.md")


async def esperar(condicao, *, prazo=5):
    limite = time.monotonic() + prazo
    while time.monotonic() < limite:
        if condicao():
            return
        await asyncio.sleep(0.02)
    assert condicao(), "A alteração esperada não chegou ao índice/canal dentro do prazo"


def test_vigia_real_edicao_rename_pasta_nova_e_tema(pequeno, monkeypatch):
    vault, _ = pequeno
    monkeypatch.setattr(modulo_vigia, "ATRASO", 0.08)
    monkeypatch.setattr(modulo_vigia, "ESPERA_MAXIMA", 0.25)

    async def cenario():
        painel = Painel(vault)
        fila = painel.eventos.assinar()
        vigia = Vigia(vault, asyncio.get_running_loop(), painel.ao_mudar_arquivos, painel.recarregar_tudo)
        vigia.iniciar()
        try:
            nota = vault / "tarefas/itens/A.md"
            nota.write_text("Editada externamente.\n", encoding="utf-8")
            await esperar(lambda: painel.indice.notas["tarefas/itens/A.md"].corpo == "Editada externamente.\n")
            assert not fila.empty()  # o worker também conseguiu publicar para a fila do loop
            renomeada = nota.with_name("Renomeada.md")
            nota.rename(renomeada)
            await esperar(lambda: "tarefas/itens/Renomeada.md" in painel.indice.notas and "tarefas/itens/A.md" not in painel.indice.notas)
            pasta = vault / "Nova pasta"
            pasta.mkdir()
            nova = pasta / "Criada junto.md"
            nova.write_text("Primeira versão", encoding="utf-8")
            await esperar(lambda: "Nova pasta/Criada junto.md" in painel.indice.notas)
            assert len(vigia._observador.emitters) == 1  # a pasta nova não custa uma thread extra
            nova.write_text("Segunda versão", encoding="utf-8")
            await esperar(lambda: painel.indice.notas["Nova pasta/Criada junto.md"].corpo == "Segunda versão")
            (vault / "_orquestra/temas/brasa/tema.yaml").write_text("nome: Tema atualizado\n", encoding="utf-8")
            await esperar(lambda: painel.tema["nome"] == "Tema atualizado")
        finally:
            painel.eventos.cancelar(fila)
            await asyncio.to_thread(vigia.parar)

    asyncio.run(cenario())


def test_vigia_real_nao_observa_dependencias_ou_junction_externa(pequeno, vincular, monkeypatch):
    vault, fora = pequeno
    for nome in (".venv", "node_modules"):
        (vault / nome / "profunda").mkdir(parents=True)
        (vault / nome / "profunda/isca.md").write_text("ignorada", encoding="utf-8")
    vincular(vault / "externo", fora)
    monkeypatch.setattr(modulo_vigia, "ATRASO", 0.05)
    monkeypatch.setattr(modulo_vigia, "INTERVALO_POLL", 0.05)

    async def cenario():
        lotes = []
        vigia = Vigia(vault, asyncio.get_running_loop(), lambda caminhos: lotes.append(caminhos), lambda: lotes.append("reorganizar"))
        vigia.iniciar()
        try:
            assert not any(any(parte in (".venv", "node_modules", "externo") for parte in p.relative_to(vault).parts) for p in vigia._vigiados)
            for nome in (".venv", "node_modules"):
                (vault / nome / "profunda/isca.md").write_text("mudou", encoding="utf-8")
            (fora / "segredo.md").write_text("Mudou fora", encoding="utf-8")
            await asyncio.sleep(0.3)
            assert lotes == []
        finally:
            await asyncio.to_thread(vigia.parar)

    asyncio.run(cenario())


def test_vigia_remove_notas_em_cache_quando_pasta_vira_junction(pequeno, vincular, monkeypatch):
    vault, fora = pequeno
    monkeypatch.setattr(modulo_vigia, "ATRASO", 0.05)

    async def cenario():
        painel = Painel(vault)
        vigia = Vigia(vault, asyncio.get_running_loop(), painel.ao_mudar_arquivos, painel.recarregar_tudo)
        await asyncio.to_thread(vigia.iniciar)
        try:
            assert "tarefas/itens/A.md" in painel.indice.notas
            vincular(vault / "tarefas", fora)
            await esperar(lambda: not any(rel.startswith("tarefas/") for rel in painel.indice.notas))
            assert "tarefas" not in painel.indice.modulos
            assert all(MARCADOR not in nota.corpo for nota in painel.indice.notas.values())
        finally:
            await asyncio.to_thread(vigia.parar)

    asyncio.run(cenario())


def test_mil_pastas_usam_um_emitter_e_dependencias_sao_podadas(pequeno, monkeypatch):
    vault, _ = pequeno
    for i in range(1000):
        (vault / "Pastas" / f"p{i:04}").mkdir(parents=True, exist_ok=True)
        (vault / "node_modules" / f"ignorada{i:04}").mkdir(parents=True, exist_ok=True)
    listadas = set()
    listar_original = Vigia._listar

    def listar(self, pasta):
        listadas.add(Path(pasta))
        yield from listar_original(self, pasta)

    monkeypatch.setattr(Vigia, "_listar", listar)
    monkeypatch.setattr(modulo_vigia, "ATRASO", 0.05)

    async def cenario():
        mudancas = set()
        vigia = Vigia(vault, asyncio.get_running_loop(), lambda caminhos: mudancas.update(caminhos), lambda: mudancas.add("reorganizar"))
        await asyncio.to_thread(vigia.iniciar)
        try:
            assert len(vigia._vigiados) == 1
            assert len(vigia._observador.emitters) == 1
            assert len(listadas) >= 1000
            assert not any("node_modules" in p.relative_to(vault).parts for p in listadas)
            nova = vault / "Pastas/p0999/Nova.md"
            nova.write_text("Encontrada sem criar outro emitter", encoding="utf-8")
            await esperar(lambda: nova in mudancas, prazo=5)
            assert len(vigia._observador.emitters) == 1
        finally:
            await asyncio.to_thread(vigia.parar)

    asyncio.run(cenario())


def test_debounce_continuo_entrega_antes_de_parar_edicoes_e_limita_lote(pequeno, monkeypatch):
    vault, _ = pequeno
    monkeypatch.setattr(modulo_vigia, "ATRASO", 0.12)
    monkeypatch.setattr(modulo_vigia, "ESPERA_MAXIMA", 0.2)
    monkeypatch.setattr(modulo_vigia, "LIMITE_LOTE", 3)

    async def cenario():
        entregas = []
        reorganizacoes = []
        vigia = Vigia(vault, asyncio.get_running_loop(), lambda caminhos: entregas.append(time.monotonic()), lambda: reorganizacoes.append(time.monotonic()))
        vigia.iniciar()
        try:
            fim = time.monotonic() + 0.6
            nota = vault / "tarefas/itens/A.md"
            while time.monotonic() < fim:
                # Rajada determinística na entrada do debounce. A entrega nativa
                # do sistema operacional é coberta no teste de vigia real acima.
                vigia._anotar([str(nota)], False)
                await asyncio.sleep(0.025)
            processadas = entregas + reorganizacoes
            assert processadas and min(processadas) < fim - 0.1
            anteriores = len(reorganizacoes)
            vigia._anotar([str(vault / f"sintetica-{i}.md") for i in range(20)], False)
            assert len(vigia._pendentes) <= 3
            await esperar(lambda: len(reorganizacoes) > anteriores)
        finally:
            await asyncio.to_thread(vigia.parar)

    asyncio.run(cenario())


def test_eventos_publicados_de_thread_tem_overflow_e_cancelamento():
    async def cenario():
        eventos = Eventos()
        fila = eventos.assinar()

        def publicar():
            for numero in range(450):
                eventos.publicar({"tipo": "nota", "numero": numero})

        thread = threading.Thread(target=publicar)
        thread.start()
        await asyncio.to_thread(thread.join)
        await asyncio.sleep(0)
        assert 0 < fila.qsize() <= 200
        recebidos = []
        while not fila.empty():
            recebidos.append(fila.get_nowait())
        assert any(e.get("ressincronizar") is True for e in recebidos)
        assert recebidos[-1]["numero"] == 449
        eventos.cancelar(fila)
        await asyncio.to_thread(eventos.publicar, {"tipo": "nota", "numero": 451})
        await asyncio.sleep(0)
        assert fila.empty()

    asyncio.run(cenario())
