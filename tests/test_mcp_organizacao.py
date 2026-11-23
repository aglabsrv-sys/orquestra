"""Consultas MCP sobre arquivos reais: contexto, pendências e revisão sem escrita."""

import datetime as dt
from pathlib import Path

import pytest

from orquestra.mcp_servidor import ErroDeFerramenta, Ferramentas


STATUS = """nome: Trabalho
campos:
  status:
    tipo: escolha
    opcoes: [pendente, esperando, concluido]
    obrigatorio: true
  data:
    tipo: data
  origem:
    tipo: escolha
    opcoes: [humano, agente, coletor]
campo_data: data
status:
  concluidos: [concluido]
  decidir: [esperando]
"""


def gravar(vault: Path, rel: str, texto: str) -> Path:
    arquivo = vault / rel
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(texto, encoding="utf-8")
    return arquivo


def nota(vault, rel, **campos):
    return gravar(vault, rel, "---\n" + "".join(f"{nome}: {valor}\n" for nome, valor in campos.items()) + "---\nTexto preservado.\n")


def arquivos(vault):
    return {p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()}


@pytest.fixture
def organizado(tmp_path):
    vault = tmp_path / "vault"
    gravar(vault, "orquestra.yaml", "nome: Consulta sintética\ncaptura: caixa\nbackup:\n  auto_commit: false\n")
    gravar(vault, "trabalho/_modulo.yaml", STATUS)
    return vault


def test_contexto_reune_schema_memoria_e_contexto_humano_com_paginacao(organizado):
    vault = organizado
    gravar(vault, "trabalho/humano/A prioridade.md", "Só confirme depois de conferir a fonte.\n")
    gravar(vault, "trabalho/humano/B contexto longo.md", "Contexto pessoal.\n" * 400)
    gravar(vault, "trabalho/maquina/aprendizados.md", "- Uma correção comprovada.\n")
    gravar(vault, "trabalho/maquina/instrucoes.md", "Compare os dados antes de sugerir.\n")
    nota(vault, "trabalho/itens/Não é instrução.md", status="pendente")
    mcp = Ferramentas(vault)
    antes = arquivos(vault)

    contexto = mcp.contexto_area("trabalho", limite=1)
    assert contexto["pasta_itens"] == "trabalho/itens"
    assert contexto["campo_status"] == "status" and contexto["campo_data"] == "data"
    assert next(c for c in contexto["campos"] if c["nome"] == "status")["opcoes"] == ["pendente", "esperando", "concluido"]
    pagina = contexto["documentos"]
    assert pagina["total"] == 4 and pagina["limitado"] and len(pagina["itens"]) == 1
    documentos = list(pagina["itens"])
    while pagina["proximo_deslocamento"] is not None:
        pagina = mcp.contexto_area("trabalho", limite=1, deslocamento=pagina["proximo_deslocamento"])["documentos"]
        documentos.extend(pagina["itens"])
    assert {d["zona"] for d in documentos} == {"humano", "maquina"}
    assert len({d["caminho"] for d in documentos}) == 4
    assert any("correção comprovada" in d["texto"] for d in documentos)
    longo = next(d for d in documentos if "contexto longo" in d["titulo"])
    assert longo["texto_limitado"] and len(longo["texto"]) <= 4000
    assert len(mcp.ler_nota(longo["caminho"])["texto"]) > len(longo["texto"])
    assert arquivos(vault) == antes


def test_contexto_inclui_gerais_completas_e_apenas_contexto_da_area_sem_copiar(organizado):
    gravar(organizado, "AGENTS.md", "Política original da pessoa.\n")
    gravar(organizado, "AGENTS.orquestra.md", "Contrato complementar.\n")
    gravar(organizado, "PREFERENCIAS.md", "Responda em português, de forma breve.\n")
    gravar(organizado, "trabalho/humano/Exceção.md", "Para relatórios, inclua as fontes.\n")
    gravar(organizado, "outra/_modulo.yaml", STATUS)
    gravar(organizado, "outra/humano/Privado.md", "Contexto de outra pasta, fora deste pedido.\n")
    mcp = Ferramentas(organizado)
    antes = arquivos(organizado)
    primeiro = mcp.contexto_area("trabalho", limite=1)
    assert primeiro["documentos"]["total"] == 1
    assert primeiro["documentos"]["itens"][0]["zona"] == "humano"
    gerais = primeiro["instrucoes"]
    assert gerais["alteradas"]
    assert [d["caminho"] for d in gerais["documentos"]] == ["AGENTS.md", "AGENTS.orquestra.md", "PREFERENCIAS.md"]
    assert gerais["documentos"][-1]["texto"] == "Responda em português, de forma breve.\n"
    regras = mcp.regras()
    assert f"versao_instrucoes: {gerais['versao']}" in regras
    assert "Política original da pessoa." in regras and "Contrato complementar." in regras
    assert regras.count("Responda em português, de forma breve.") == 1
    assert "Contexto de outra pasta" not in str(primeiro) and "Para relatórios" not in regras
    assert arquivos(organizado) == antes


def test_contexto_reutiliza_gerais_so_com_versao_explicita_e_confere_disco(organizado):
    contrato = gravar(organizado, "AGENTS.md", "Não publique sem autorização.\n")
    preferencias = gravar(organizado, "PREFERENCIAS.md", "Respostas breves.\n")
    local = gravar(organizado, "trabalho/humano/Critério.md", "Use fontes primárias.\n")
    mcp = Ferramentas(organizado)
    inicial = mcp.contexto_area("trabalho")
    versao = inicial["instrucoes"]["versao"]
    repetido = mcp.contexto_area("trabalho", versao_instrucoes=versao)
    assert repetido["instrucoes"] == {**inicial["instrucoes"], "alteradas": False, "documentos": []}
    assert repetido["documentos"]["itens"] == inicial["documentos"]["itens"]

    # Reaproveitar as gerais não esconde novas observações da pasta nem novos aprendizados.
    local.write_text("Inclua também a data das fontes.\n", encoding="utf-8")
    gravar(organizado, "trabalho/maquina/aprendizados.md", "Correção nova, comprovada.\n")
    atual = mcp.contexto_area("trabalho", versao_instrucoes=versao)
    assert not atual["instrucoes"]["alteradas"]
    assert {d["texto"] for d in atual["documentos"]["itens"]} == {"Inclua também a data das fontes.\n", "Correção nova, comprovada.\n"}

    preferencias.write_text("Inclua explicações detalhadas.\n", encoding="utf-8")
    atualizado = mcp.contexto_area("trabalho", versao_instrucoes=versao)["instrucoes"]
    assert atualizado["alteradas"] and atualizado["versao"] != versao
    assert atualizado["documentos"][-1]["texto"] == "Inclua explicações detalhadas.\n"
    contrato.write_text("Confirme os números antes de publicar.\n", encoding="utf-8")
    assert mcp.contexto_area("trabalho", versao_instrucoes=atualizado["versao"])["instrucoes"]["alteradas"]

    # O servidor não pressupõe que uma conversa nova herdou a leitura anterior.
    assert mcp.contexto_area("trabalho")["instrucoes"]["documentos"]
    assert Ferramentas(organizado).contexto_area("trabalho")["instrucoes"]["documentos"]


def test_instrucoes_detectam_adicao_remocao_e_troca_de_vault(organizado, tmp_path):
    gravar(organizado, "AGENTS.md", "Política original.\n")
    mcp = Ferramentas(organizado)
    inicial = mcp.contexto_area("trabalho")["instrucoes"]["versao"]
    suplemento = gravar(organizado, "AGENTS.orquestra.md", "Restrições adicionais.\n")
    adicional = mcp.contexto_area("trabalho", versao_instrucoes=inicial)["instrucoes"]
    assert adicional["alteradas"] and len(adicional["documentos"]) == 2
    suplemento.unlink()
    removido = mcp.contexto_area("trabalho", versao_instrucoes=adicional["versao"])["instrucoes"]
    assert removido["alteradas"] and removido["versao"] == inicial
    outro = tmp_path / "outro"
    gravar(outro, "AGENTS.md", "Política original.\n")
    gravar(outro, "trabalho/_modulo.yaml", STATUS)
    assert Ferramentas(outro).contexto_area("trabalho", versao_instrucoes=inicial)["instrucoes"]["alteradas"]


@pytest.mark.parametrize("dados,mensagem", [(b"\xff", "UTF-8"), (b"x" * (512 * 1024 + 1), "512 KB")])
def test_instrucoes_nao_truncam_nem_ignoram_contrato_invalido(organizado, dados, mensagem):
    contrato = organizado / "AGENTS.md"
    contrato.write_bytes(dados)
    mcp = Ferramentas(organizado)
    for consultar in (mcp.regras, lambda: mcp.contexto_area("trabalho")):
        with pytest.raises(ErroDeFerramenta, match=mensagem):
            consultar()
    assert contrato.read_bytes() == dados


def test_gerais_nao_geram_arquivo_quando_contrato_ausente(organizado):
    mcp = Ferramentas(organizado)
    antes = arquivos(organizado)
    assert mcp.contexto_area("trabalho")["instrucoes"]["documentos"] == []
    assert "Áreas deste vault" in mcp.regras()
    assert arquivos(organizado) == antes


def test_panorama_separa_pendencias_respeita_captura_e_recarrega_o_disco(organizado):
    vault = organizado
    hoje = dt.date.today()
    ontem, amanha = hoje - dt.timedelta(days=1), hoje + dt.timedelta(days=1)
    gravar(vault, "caixa/_modulo.yaml", STATUS)
    gravar(vault, "referencias/_modulo.yaml", "nome: Referências\ncampos:\n  data:\n    tipo: data\ncampo_data: data\n")
    nota(vault, "trabalho/itens/A hoje.md", status="pendente", data=hoje)
    nota(vault, "trabalho/itens/B hoje.md", status="pendente", data=hoje)
    nota(vault, "trabalho/itens/Atrasada.md", status="pendente", data=ontem)
    nota(vault, "trabalho/itens/Próxima.md", status="pendente", data=amanha)
    nota(vault, "trabalho/itens/Fora da janela.md", status="pendente", data=hoje + dt.timedelta(days=9))
    nota(vault, "trabalho/itens/Sem data.md", status="pendente")
    nota(vault, "trabalho/itens/Decisão.md", status="esperando")
    nota(vault, "trabalho/itens/Respondida.md", status="pendente", resposta="Sim")
    nota(vault, "trabalho/itens/Concluída.md", status="concluido", data=ontem)
    nota(vault, "caixa/itens/Captura aberta.md", status="pendente")
    nota(vault, "caixa/itens/Captura processada.md", status="concluido")
    nota(vault, "referencias/itens/Referência antiga.md", data=ontem)
    mcp = Ferramentas(vault)
    antes = arquivos(vault)

    resultado = mcp.panorama(dias=7, limite=1)
    grupos = resultado["grupos"]
    assert resultado["captura_configurada"] == "caixa"
    assert grupos["hoje"]["total"] == 2 and grupos["hoje"]["limitado"]
    assert len(grupos["hoje"]["itens"]) == 1
    assert {i["titulo"] for i in grupos["atrasados"]["itens"]} == {"Atrasada"}
    assert {i["titulo"] for i in grupos["proximos"]["itens"]} == {"Próxima"}
    assert {i["titulo"] for i in grupos["decisoes"]["itens"]} == {"Decisão"}
    assert {i["titulo"] for i in grupos["respostas"]["itens"]} == {"Respondida"}
    assert {i["titulo"] for i in grupos["capturas"]["itens"]} == {"Captura aberta"}
    assert grupos["sem_data"]["total"] == 4
    assert all("Concluída" != i["titulo"] for g in grupos.values() for i in g["itens"])
    assert all(i["area"] == "trabalho" for g in mcp.panorama(area="trabalho")["grupos"].values() for i in g["itens"])
    assert arquivos(vault) == antes

    nota(vault, "trabalho/itens/A hoje.md", status="concluido", data=hoje)
    gravar(vault, "orquestra.yaml", "nome: Consulta sintética\ncaptura: trabalho\nbackup:\n  auto_commit: false\n")
    atualizado = mcp.panorama()
    assert atualizado["grupos"]["hoje"]["total"] == 1
    assert atualizado["captura_configurada"] == "trabalho"
    assert atualizado["grupos"]["capturas"]["total"] == 7


def test_panorama_considera_intervalos_e_nao_atrasa_compromissos_encerrados(organizado):
    vault = organizado
    hoje = dt.date.today()
    ontem, amanha = hoje - dt.timedelta(days=1), hoje + dt.timedelta(days=1)
    gravar(vault, "agenda/_modulo.yaml", "nome: Agenda\ncampos:\n  data:\n    tipo: data\n  data_fim:\n    tipo: data\n  hora:\n    tipo: texto\n  hora_fim:\n    tipo: texto\ncampo_data: data\n")
    nota(vault, "agenda/itens/Viagem em curso.md", data=ontem, data_fim=amanha)
    nota(vault, "trabalho/itens/Evento em curso.md", status="pendente", data=ontem, data_fim=amanha, hora='"09:00"', hora_fim='"17:00"')
    nota(vault, "trabalho/itens/Turno terminado.md", status="pendente", categoria="Compromisso", data=ontem, data_fim=hoje, hora='"23:00"', hora_fim='"00:00"')
    nota(vault, "trabalho/itens/Reunião encerrada.md", status="pendente", categoria="Compromisso", data=ontem, hora='"09:00"', hora_fim='"10:00"')
    mcp = Ferramentas(vault)
    antes = arquivos(vault)

    grupos = mcp.panorama()["grupos"]
    assert {i["titulo"] for i in grupos["hoje"]["itens"]} == {"Viagem em curso", "Evento em curso"}
    assert grupos["atrasados"]["total"] == 0
    assert arquivos(vault) == antes


def test_revisao_aponta_problemas_e_duplicatas_sem_exigir_origem_nem_ler_arquivo(organizado):
    vault = organizado
    gravar(vault, "trabalho/_modulo.yaml", STATUS + "itens: .\n")
    nota(vault, "trabalho/A.md", status="pendente", titulo="Revisão de proposta")
    nota(vault, "trabalho/subpasta/B.md", status="pendente", titulo="REVISÃO  de proposta")
    nota(vault, "trabalho/Nota humana antiga.md", status="pendente")
    nota(vault, "trabalho/Status inválido.md", status="inventado")
    gravar(vault, "trabalho/YAML inválido.md", "---\nstatus: [sem fechamento\n---\nOriginal.\n")
    nota(vault, "trabalho/arquivo/Arquivada.md", status="inválido")
    nota(vault, "trabalho/humano/Preferência.md", status="inválido")
    mcp = Ferramentas(vault)
    antes = arquivos(vault)

    revisao = mcp.revisar_organizacao("trabalho", limite=1)
    assert revisao["itens_analisados"] == 5
    pagina = revisao["achados"]
    assert pagina["total"] == 3 and pagina["limitado"] and len(pagina["itens"]) == 1
    achados = list(pagina["itens"])
    while pagina["proximo_deslocamento"] is not None:
        pagina = mcp.revisar_organizacao("trabalho", limite=1, deslocamento=pagina["proximo_deslocamento"])["achados"]
        achados.extend(pagina["itens"])
    assert {a["tipo"] for a in achados} == {"frontmatter_invalido", "campos_invalidos", "possivel_duplicata"}
    duplicata = next(a for a in achados if a["tipo"] == "possivel_duplicata")
    assert duplicata["caminhos"] == ["trabalho/A.md", "trabalho/subpasta/B.md"]
    assert next(a for a in achados if a["tipo"] == "campos_invalidos")["caminho"] == "trabalho/Status inválido.md"
    assert arquivos(vault) == antes

    nota(vault, "trabalho/Outra inválida.md", status="inválido")
    assert mcp.revisar_organizacao("trabalho")["achados"]["total"] == 4
