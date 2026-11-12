"""Persistência e isolamento das novas interações do explorador."""
from orquestra.config import ler_config_painel
from orquestra.painel import Painel


def test_reordenacao_persistente_sem_alterar_modulos(cliente, vault):
    ordem = list(reversed(cliente.painel.indice.modulos))
    antes = {p: p.read_bytes() for p in vault.glob('*/_modulo.yaml')}
    assert cliente.post('/api/config', json={'ordem_pastas': ordem}).status_code == 200
    assert list(cliente.painel.indice.modulos) == ordem
    assert list(Painel(vault).indice.modulos) == ordem
    assert ler_config_painel(vault).ordem_pastas == ordem
    assert all(p.read_bytes() == dados for p, dados in antes.items())


def test_reordenacao_recusa_lista_obsoleta_sem_gravar(cliente, vault):
    antes = (vault / 'orquestra.yaml').read_bytes()
    ordem = list(cliente.painel.indice.modulos)
    for invalida in [ordem[:-1], ordem + [ordem[0]], ordem + ['inexistente']]:
        assert cliente.post('/api/config', json={'ordem_pastas': invalida}).status_code == 400
        assert (vault / 'orquestra.yaml').read_bytes() == antes


def test_ordem_sobrevive_a_novo_modulo(cliente):
    ordem = list(reversed(cliente.painel.indice.modulos))
    cliente.post('/api/config', json={'ordem_pastas': ordem})
    cliente.painel.criar_modulo('Viagens')
    assert list(cliente.painel.indice.modulos) == ordem + ['viagens']


def test_arvore_inclui_pastas_vazias_e_oculta_diretorios_internos(cliente, vault):
    (vault / 'Vazia').mkdir()
    (vault / '.oculta').mkdir()
    (vault / '.oculta/Privada.md').write_text('invisível', encoding='utf-8')
    dados = cliente.get('/api/pastas/arvore').json()
    nomes = [p['nome'] for p in dados['pastas']]
    assert 'Vazia' in nomes and '.oculta' not in nomes and '.git' not in nomes
    assert cliente.get('/api/pastas/arvore', params={'rel': '../'}).status_code == 404
    assert cliente.get('/api/pastas/arvore', params={'rel': '.oculta'}).status_code == 404


def test_arvore_nao_segue_link_para_pasta_externa(cliente, vault, tmp_path):
    externo = tmp_path / 'fora'; externo.mkdir()
    (externo / 'Segredo.md').write_text('privado', encoding='utf-8')
    import os
    import pytest
    if os.name == 'nt':
        pytest.skip('Symlink precisa de permissão específica no Windows')
    (vault / 'Atalho').symlink_to(externo, target_is_directory=True)
    assert 'Atalho' not in [p['nome'] for p in cliente.get('/api/pastas/arvore').json()['pastas']]
    assert cliente.get('/api/pastas/arvore', params={'rel': 'Atalho'}).status_code == 404


def test_grafo_contem_ligacoes_reais_filtradas(cliente, vault):
    (vault / 'Mundo').mkdir()
    (vault / 'Mundo/A.md').write_text('# A\n[[B]] e [[B|nome]] e [[Fora]]', encoding='utf-8')
    (vault / 'Mundo/B.md').write_text('# B\n[[A]]', encoding='utf-8')
    (vault / 'Fora.md').write_text('# Fora', encoding='utf-8')
    cliente.painel.recarregar_tudo()
    dados = cliente.get('/api/pastas/grafo', params={'rel': 'Mundo'}).json()
    assert {n['id'] for n in dados['notas']} == {'Mundo/A.md', 'Mundo/B.md'}
    assert dados['ligacoes'] == [['Mundo/A.md', 'Mundo/B.md']]
    assert cliente.get('/api/pastas/grafo', params={'rel': '../'}).status_code == 404


def test_aprovacao_filtra_conteudo_e_tem_estado_vazio(cliente):
    r = cliente.get('/decidir?modulo=conteudo')
    assert r.status_code == 200
    assert 'Aprovação de criativos' in r.text
    assert 'data-rel="radar/' not in r.text
    assert 'Envie o criativo em Miniatura' not in cliente.get('/m/conteudo').text


def test_nota_compacta_preserva_metadados_discretos(cliente):
    nota = next(iter(cliente.painel.indice.itens('conteudo')))
    r = cliente.get('/n/' + nota.rel)
    assert r.status_code == 200
    assert 'name="origem"' not in r.text
    assert 'type="url"' not in r.text
    assert 'id="nota-propriedades"' in r.text
    assert 'id="nota-imagem-campo"' in r.text
    assert 'data-miniatura-para' not in r.text
