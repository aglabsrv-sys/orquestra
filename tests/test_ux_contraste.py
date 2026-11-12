"""Contraste dos controles e textos nos temas e cores escolhidas pela pessoa."""

import pytest

from orquestra import aparencia, preparo, temas


@pytest.mark.parametrize("tema", temas.listar(preparo.MODELO), ids=lambda tema: tema["id"])
@pytest.mark.parametrize("claro", [False, True], ids=["escuro", "claro"])
def test_textos_e_estados_legiveis_nas_superficies_e_etiquetas(tema, claro):
    for destaque in ("", *aparencia.SUGESTOES, "#ffffff", "#000000", "#ff0000"):
        paleta = aparencia.cores(tema, aparencia.Aparencia(destaque=destaque), claro)
        superficies = [paleta[chave] for chave in ("fundo", "superficie", "superficie_alta")]
        for chave in ("texto", "texto_suave", "destaque", "alerta", "ok"):
            fundos = superficies
            if chave in ("destaque", "alerta", "ok"):
                fundos = [*fundos, *(aparencia.misturar(fundo, paleta[chave], 0.20) for fundo in superficies)]
            for fundo in fundos:
                assert aparencia.contraste(paleta[chave], fundo) >= 4.5, (destaque, chave, fundo)
        assert aparencia.contraste(paleta["sobre_destaque"], paleta["destaque"]) >= 4.5
        borda = aparencia.legivel_sobre(paleta["borda"], paleta["fundo"], 3.0)
        assert aparencia.contraste(borda, paleta["fundo"]) >= 3.0
