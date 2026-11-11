"""Leitura e escrita de notas: o que não pode quebrar é o arquivo do usuário."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from orquestra.notas import (
    Conflito,
    FrontmatterInvalido,
    caminho_livre,
    gravar_nota,
    ler_nota,
    nome_de_arquivo,
    separar,
)

EXEMPLO = """---
# comentário que o usuário escreveu
status: a_fazer   # outro comentário
titulo: "Com aspas"
data: 2026-01-15
tags:
  - um
  - dois
campo_meu: qualquer coisa
---

# Corpo

Texto com **negrito** e um [[link]].
"""


def escrever(tmp_path: Path, texto: str, nome: str = "nota.md") -> Path:
    caminho = tmp_path / nome
    caminho.write_bytes(texto.encode("utf-8"))
    return caminho


def test_separar_frontmatter_e_corpo():
    fm, corpo = separar("---\na: 1\n---\ncorpo\n")
    assert fm == "a: 1"
    assert corpo == "corpo\n"
    assert separar("sem frontmatter") == (None, "sem frontmatter")
    assert separar("---\nnunca fecha") == (None, "---\nnunca fecha")


def test_le_tipos_do_yaml(tmp_path):
    nota = ler_nota(escrever(tmp_path, EXEMPLO), tmp_path)
    assert nota.titulo == "Com aspas"
    assert nota.campo("status") == "a_fazer"
    assert nota.campo("data") == "2026-01-15"
    assert isinstance(nota.meta["data"], dt.date)
    assert nota.campo("tags") == ["um", "dois"]
    assert nota.corpo.startswith("\n# Corpo")


def test_editar_um_campo_preserva_todo_o_resto(tmp_path):
    caminho = escrever(tmp_path, EXEMPLO)
    nota = ler_nota(caminho, tmp_path)
    nota.meta["status"] = "feito"
    gravar_nota(nota, versao_esperada=nota.versao)

    depois = caminho.read_text(encoding="utf-8")
    # O comentário da linha continua na mesma coluna; todo o resto fica idêntico.
    assert depois == EXEMPLO.replace("status: a_fazer   #", "status: feito     #")


def test_gravar_sem_mudar_nada_nao_altera_o_arquivo(tmp_path):
    caminho = escrever(tmp_path, EXEMPLO)
    nota = ler_nota(caminho, tmp_path)
    gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_text(encoding="utf-8") == EXEMPLO


def test_titulo_vem_do_nome_do_arquivo_quando_nao_ha_campo(tmp_path):
    nota = ler_nota(escrever(tmp_path, "---\nstatus: x\n---\n", "Minha tarefa.md"), tmp_path)
    assert nota.titulo == "Minha tarefa"


def test_nota_sem_frontmatter_continua_sem(tmp_path):
    caminho = escrever(tmp_path, "Só texto.\n")
    nota = ler_nota(caminho, tmp_path)
    nota.corpo = "Só texto, editado.\n"
    gravar_nota(nota, versao_esperada=nota.versao)
    assert caminho.read_text(encoding="utf-8") == "Só texto, editado.\n"


def test_preserva_quebras_de_linha_do_windows(tmp_path):
    caminho = escrever(tmp_path, EXEMPLO.replace("\n", "\r\n"))
    nota = ler_nota(caminho, tmp_path)
    nota.meta["status"] = "feito"
    gravar_nota(nota, versao_esperada=nota.versao)
    bruto = caminho.read_bytes()
    assert b"\r\n" in bruto
    assert b"\n" not in bruto.replace(b"\r\n", b"")


def test_conflito_quando_o_arquivo_mudou_no_disco(tmp_path):
    caminho = escrever(tmp_path, EXEMPLO)
    nota = ler_nota(caminho, tmp_path)
    # Outra pessoa (Obsidian, um agente) grava enquanto a nota está aberta no painel.
    caminho.write_text(EXEMPLO + "\nlinha nova\n", encoding="utf-8")
    nota.meta["status"] = "feito"
    with pytest.raises(Conflito):
        gravar_nota(nota, versao_esperada=nota.versao)
    assert "linha nova" in caminho.read_text(encoding="utf-8")  # nada foi sobrescrito


def test_criar_nunca_sobrescreve(tmp_path):
    caminho = escrever(tmp_path, EXEMPLO)
    nota = ler_nota(caminho, tmp_path)
    with pytest.raises(FileExistsError):
        gravar_nota(nota, criar=True)


def test_frontmatter_invalido_nao_e_reescrito(tmp_path):
    quebrado = "---\nstatus: [sem fechar\n---\ncorpo\n"
    caminho = escrever(tmp_path, quebrado)
    nota = ler_nota(caminho, tmp_path)
    assert nota.erro
    with pytest.raises(FrontmatterInvalido):
        gravar_nota(nota)
    assert caminho.read_text(encoding="utf-8") == quebrado


def test_nao_deixa_arquivo_temporario(tmp_path):
    caminho = escrever(tmp_path, EXEMPLO)
    nota = ler_nota(caminho, tmp_path)
    nota.meta["status"] = "feito"
    gravar_nota(nota, versao_esperada=nota.versao)
    assert [p.name for p in tmp_path.iterdir()] == ["nota.md"]


def test_nome_de_arquivo_mantem_acentos_e_tira_o_proibido():
    assert nome_de_arquivo("Gravação: parte 1/2?") == "Gravação parte 1 2"
    assert nome_de_arquivo("  ...  ") == "Sem título"
    assert nome_de_arquivo("[[link]] #tag") == "link tag"
    assert len(nome_de_arquivo("x" * 300)) == 80


def test_caminho_livre_numera_os_repetidos(tmp_path):
    primeiro = caminho_livre(tmp_path, "Ideia")
    primeiro.write_text("a", encoding="utf-8")
    segundo = caminho_livre(tmp_path, "Ideia")
    assert primeiro.name == "Ideia.md"
    assert segundo.name == "Ideia 2.md"
