"""Caches de cálculos sem perder isolamento, comentários ou alterações externas."""

import os
from copy import deepcopy

import pytest

from orquestra import aparencia, armazenamento, temas
from orquestra.config import gravar_yaml, ler_yaml


def test_yaml_reutilizado_isola_mutacoes_e_conserva_comentarios_e_conflitos(tmp_path):
    caminho = tmp_path / "config.yaml"
    original = b"# Configura\xc3\xa7\xc3\xa3o fict\xc3\xadcia\r\nlista: [um, dois] # preservar\r\n"
    caminho.write_bytes(original)
    primeiro, segundo = ler_yaml(caminho), ler_yaml(caminho)
    primeiro["lista"].append("tres")
    assert segundo["lista"] == ["um", "dois"]
    gravar_yaml(caminho, segundo)
    assert caminho.read_bytes() == original
    gravar_yaml(caminho, primeiro)
    assert b"# preservar\r\n" in caminho.read_bytes()
    with pytest.raises(armazenamento.ConflitoDeEscrita):
        gravar_yaml(caminho, segundo)


def test_yaml_detecta_bytes_novos_com_mesmo_tamanho_e_horario(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text("valor: um\n", encoding="utf-8")
    b.write_bytes(a.read_bytes())
    primeiro, segundo = ler_yaml(a), ler_yaml(b)
    gravar_yaml(b, segundo)  # origem de cada cópia continua independente
    info = a.stat()
    a.write_text("valor: oi\n", encoding="utf-8")
    os.utime(a, ns=(info.st_atime_ns, info.st_mtime_ns))
    assert ler_yaml(a)["valor"] == "oi"
    with pytest.raises(armazenamento.ConflitoDeEscrita):
        gravar_yaml(a, primeiro)


def test_cache_de_cores_isola_resultado_e_acompanha_tema_editado(tmp_path):
    tema = temas.listar(tmp_path)[0]
    ap = aparencia.Aparencia()
    original = aparencia.cores(tema, ap, False)
    outra = aparencia.cores(tema, ap, False)
    outra["destaque"] = "#000000"
    assert aparencia.cores(tema, ap, False) == original
    editado = deepcopy(tema)
    editado["cores"]["destaque"] = "#ffffff"
    assert aparencia.cores(editado, ap, False) != original
    assert aparencia.cores(tema, ap, False) == original
