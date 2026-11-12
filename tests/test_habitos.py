import datetime as dt
from types import SimpleNamespace

import pytest

from orquestra import habitos, backup, temas, confianca
from orquestra.notas import ler_nota
from orquestra.painel import Recusado


def test_home_limpa_e_foco_proprio(cliente):
    pagina=cliente.get('/').text
    assert 'data-pomodoro' not in pagina and 'data-pomo-duracao' not in pagina
    assert 'href="/habitos"' not in pagina
    assert 'id="abrir-foco"' in pagina and 'href="/foco"' in pagina
    foco=cliente.get('/foco')
    assert foco.status_code == 200 and 'foco-mostrador' in foco.text and 'id="foco-tempo"' in foco.text
    assert '<select' not in foco.text


def test_habitos_e_modulo_com_pasta_e_marcacoes_vazias(cliente,vault):
    assert cliente.get('/habitos',follow_redirects=False).headers['location']=='/m/habitos'
    assert cliente.get('/m/habitos').status_code==200
    assert not (vault/'habitos').exists()
    r=cliente.post('/api/habitos',json={'titulo':'Academia','meta_semanal':3,'tags':['saude']})
    assert r.status_code==200 and r.json()['ativado']
    dados=r.json(); nota=ler_nota(vault/dados['rel'],vault)
    assert not nota.campo('registros') and nota.campo('meta_semanal')==3
    for aba in ('','?aba=lista','?aba=humano','?aba=maquina'):
        assert cliente.get('/m/habitos'+aba).status_code==200
    assert 'href="/m/habitos"' in cliente.get('/').text


def test_marcar_atualiza_semana_total_e_versao_sem_perder_metadados(cliente,vault):
    novo=cliente.post('/api/habitos',json={'titulo':'Leitura','meta_semanal':5}).json()
    hoje=dt.date(2026,11,12)
    dados=habitos.marcar(cliente.painel,{'rel':novo['rel'],'versao':novo['versao']},hoje)
    assert dados['item']['semana']==1 and dados['resumo']['hoje']==1 and dados['item']['percentual']==20
    assert dados['item']['registros']==['2026-11-12']
    with pytest.raises(Exception,match='mudou'):
        habitos.marcar(cliente.painel,{'rel':novo['rel'],'versao':novo['versao']},hoje)
    atualizado=habitos.salvar(cliente.painel,{'rel':novo['rel'],'versao':dados['versao'],'titulo':'Ler','meta_semanal':3,'tags':['livros']},hoje)
    assert atualizado['item']['registros']==['2026-11-12']
    assert atualizado['item']['meta']==3


@pytest.mark.parametrize('meta',[0,8,1.5,True,'3'])
def test_metas_invalidas_recusadas_sem_criar_modulo(cliente,vault,meta):
    assert cliente.post('/api/habitos',json={'titulo':'Teste','meta_semanal':meta}).status_code==400
    assert not (vault/'habitos').exists()


def test_resumo_semana_nao_conta_futuro_e_marcacao_recusa_registros_invalidos(cliente,vault):
    novo=cliente.post('/api/habitos',json={'titulo':'Caminhada','meta_semanal':4}).json()
    nota=cliente.painel.editar_nota(novo['rel'],novo['versao'],campos={'registros':['2026-11-09','2026-11-10','2026-11-15']})
    item=habitos.apresentar(nota,dt.date(2026,11,12))
    assert item['semana']==2 and item['total_registros']==2
    nota=cliente.painel.editar_nota(novo['rel'],nota.versao,campos={'registros':['invalida']})
    antes=(vault/novo['rel']).read_bytes()
    with pytest.raises(Exception,match='registro'):
        habitos.marcar(cliente.painel,{'rel':novo['rel'],'versao':nota.versao})
    assert (vault/novo['rel']).read_bytes()==antes


def test_ajustes_leem_somente_contexto_da_pagina(cliente,monkeypatch):
    def nao_chamar(*a,**kw): pytest.fail('Contexto de outra seção não deve ser consultado')
    monkeypatch.setattr(backup,'resumo',nao_chamar); monkeypatch.setattr(backup,'e_repositorio',nao_chamar)
    monkeypatch.setattr(confianca,'resumo',nao_chamar); monkeypatch.setattr(temas,'listar',nao_chamar)
    for secao in ('painel','areas','coletores','acesso','vault','variaveis'):
        assert cliente.get('/ajustes/'+secao).status_code==200


@pytest.mark.parametrize('valor', [False, 0, ''])
def test_registros_escalares_nao_sao_descartados_silenciosamente(valor):
    nota = SimpleNamespace(campo=lambda _: valor)
    with pytest.raises(Recusado, match='lista de datas'):
        habitos._datas(nota)


@pytest.mark.parametrize('campo', ['registros', 'meta_semanal', 'tags'])
def test_schema_incompativel_nao_converte_nem_sobrescreve_historico(cliente, vault, campo):
    from orquestra.config import ler_yaml, gravar_yaml

    novo = cliente.post('/api/habitos', json={'titulo': 'Preservar histórico', 'meta_semanal': 3}).json()
    nota = cliente.painel.editar_nota(novo['rel'], novo['versao'], campos={'registros': ['2026-11-12']})
    caminho = vault / 'habitos/_modulo.yaml'
    schema = ler_yaml(caminho)
    schema['campos'][campo]['tipo'] = 'texto'
    gravar_yaml(caminho, schema)
    # O índice ainda tem o contrato anterior: a escrita precisa conferir o disco.
    antes = (vault / novo['rel']).read_bytes()
    for url, dados in [
        ('/api/habitos/marcar', {'rel': novo['rel'], 'versao': nota.versao}),
        ('/api/habitos', {'rel': novo['rel'], 'versao': nota.versao, 'titulo': 'Alterar', 'meta_semanal': 4}),
        ('/api/habitos', {'titulo': 'Outro hábito', 'meta_semanal': 2}),
    ]:
        resposta = cliente.post(url, json=dados)
        assert resposta.status_code == 400 and 'Personalizar' in resposta.json()['erro']
    assert (vault / novo['rel']).read_bytes() == antes
    assert len(list((vault / 'habitos/itens').glob('*.md'))) == 1
