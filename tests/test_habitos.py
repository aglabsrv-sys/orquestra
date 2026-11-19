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


def test_progresso_substitui_preferencia_lista_e_funciona_apos_humano(cliente):
    cliente.post('/api/habitos', json={'titulo': 'Hábito fictício', 'meta_semanal': 3})
    lista = cliente.get('/m/habitos?aba=lista')
    assert lista.context['aba'] == 'lista'
    assert cliente.get('/m/habitos').context['aba'] == 'lista'
    assert 'href="/m/habitos?aba=progresso"' in lista.text
    assert 'href="/m/habitos?aba=progresso"' in cliente.get('/m/habitos?aba=humano').text
    assert cliente.get('/m/habitos?aba=progresso').context['aba'] == 'progresso'
    assert cliente.get('/m/habitos').context['aba'] == 'progresso'


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
    repetido = habitos.marcar(cliente.painel, {'rel': novo['rel'], 'versao': dados['versao']}, hoje)
    assert repetido['item']['contagem_hoje'] == 2
    assert repetido['item']['contagens'] == {'2026-11-12': 2}
    assert repetido['item']['tem_repeticoes']
    assert repetido['item']['semana'] == repetido['item']['total_registros'] == 1
    with pytest.raises(Exception,match='mudou'):
        habitos.marcar(cliente.painel,{'rel':novo['rel'],'versao':novo['versao']},hoje)
    atualizado=habitos.salvar(cliente.painel,{'rel':novo['rel'],'versao':repetido['versao'],'titulo':'Ler','meta_semanal':3,'tags':['livros']},hoje)
    assert atualizado['item']['registros']==['2026-11-12']
    assert atualizado['item']['contagem_hoje'] == 2
    assert cliente.painel.indice.notas[novo['rel']].campo('registros') == ['2026-11-12'] * 2
    assert atualizado['item']['meta']==3


@pytest.mark.parametrize('meta',[0,8,1.5,True,'3'])
def test_metas_invalidas_recusadas_sem_criar_modulo(cliente,vault,meta):
    assert cliente.post('/api/habitos',json={'titulo':'Teste','meta_semanal':meta}).status_code==400
    assert not (vault/'habitos').exists()


def test_descricao_opcional_e_texto_da_nota_e_omitir_preserva(cliente, vault):
    criado = cliente.post('/api/habitos', json={'titulo': 'Caminhar', 'descricao': 'Uma volta na praça.'}).json()
    assert criado['item']['descricao'].strip() == 'Uma volta na praça.'
    assert 'Uma volta na praça.' in (vault / criado['rel']).read_text(encoding='utf-8')
    alterado = cliente.post('/api/habitos', json={'rel': criado['rel'], 'versao': criado['versao'], 'titulo': 'Caminhar mais'}).json()
    assert alterado['item']['descricao'] == criado['item']['descricao']
    falha = cliente.post('/api/habitos', json={'rel': criado['rel'], 'versao': criado['versao'], 'titulo': 'Antigo', 'descricao': 'Não deve salvar'})
    assert falha.status_code == 409
    assert 'Não deve salvar' not in (vault / criado['rel']).read_text(encoding='utf-8')
    limpo = cliente.post('/api/habitos', json={'rel': alterado['rel'], 'versao': alterado['versao'], 'titulo': 'Caminhar mais', 'descricao': ''}).json()
    assert not limpo['item']['descricao']


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
        assert resposta.status_code == 400 and '_modulo.yaml' in resposta.json()['erro']
    assert (vault / novo['rel']).read_bytes() == antes
    assert len(list((vault / 'habitos/itens').glob('*.md'))) == 1


def test_mapa_completo_fica_visivel_nas_duas_visoes_e_apos_editar(cliente):
    novo = cliente.post('/api/habitos', json={'titulo': 'Mapa sempre visível', 'meta_semanal': 3}).json()
    for aba in ('progresso', 'lista'):
        pagina = cliente.get('/m/habitos?aba=' + aba).text
        assert pagina.count('data-mapa-dia=') == 91
        assert 'class="habito-historico"' not in pagina
        assert 'class="habito-semana"' not in pagina
        assert 'class="habito-acoes"' in pagina
    resposta = cliente.post('/api/habitos', json={'rel': novo['rel'], 'versao': novo['versao'], 'titulo': 'Mapa editado', 'meta_semanal': 4}).json()
    assert resposta['html'].count('data-mapa-dia=') == 91
    assert 'class="habito-historico"' not in resposta['html']
