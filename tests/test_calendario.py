"""Agenda: persistência no vault, intervalos civis e fronteiras de edição."""
import datetime as dt
import json
from html.parser import HTMLParser

import pytest

from orquestra import calendario
from orquestra.notas import ler_nota


def criar(cliente, **campos):
    dados = {"titulo":"Reunião de planejamento", "data":"2026-11-12", "data_fim":"2026-11-12", "hora":"09:00", "hora_fim":"10:00", "categoria":"Trabalho", "cor":"azul", "tags":["equipe"], "corpo":"Contexto preservado.", **campos}
    resposta = cliente.post('/api/agenda/eventos', json=dados)
    assert resposta.status_code == 200, resposta.text
    return resposta.json(), dados


def test_evento_e_nota_real_sem_alterar_esquema_das_tarefas(cliente, vault):
    antes = (vault / 'tarefas/_modulo.yaml').read_bytes()
    resultado, _ = criar(cliente)
    nota = ler_nota(vault / resultado['rel'], vault)
    assert resultado['rel'].startswith('agenda/itens/')
    assert nota.campo('hora') == '09:00' and nota.campo('cor') == 'azul'
    assert nota.campo('tags') == ['equipe'] and 'Contexto preservado.' in nota.corpo
    assert (vault / 'tarefas/_modulo.yaml').read_bytes() == antes
    assert cliente.get('/api/agenda/evento/' + resultado['rel']).json()['hora_fim'] == '10:00'


@pytest.mark.parametrize('visao', calendario.VISOES)
def test_visoes_usam_os_mesmos_eventos_e_urls_preservam_filtros(cliente, visao):
    criar(cliente)
    r = cliente.get('/agenda/2026-11-12', params={'visao':visao,'q':'planejamento','categoria':'Trabalho'})
    assert r.status_code == 200 and 'Reunião de planejamento' in r.text
    assert all(('>' + nome + '</a>') in r.text for nome in ('Mês','Semana','Dia','Lista'))
    assert 'categoria=Trabalho' in r.text and 'q=planejamento' in r.text


def test_mes_preenche_semanas_e_nao_pula_mes_em_31_de_janeiro(painel):
    cal = calendario.montar(painel, dt.date(2026,1,31))
    assert len(cal['dias']) == 42 and cal['dias'][0]['nome'] == 'Seg'
    assert '/agenda/2026-02-28?' in cal['proximo']
    assert calendario.deslocar(dt.date(2024,1,31),'mes',1) == dt.date(2024,2,29)
    assert 'dez 2025' in calendario.montar(painel,dt.date(2026,1,1),'semana')['titulo']
    assert calendario.hora('0٣:00') == ''


def test_busca_ignora_acentos_e_inclui_descricao(cliente):
    criar(cliente,titulo='Revisão',corpo='Conversar sobre divulgação')
    assert calendario.montar(cliente.painel,dt.date(2026,11,12),q='revisao',pasta='agenda')['total'] == 1
    assert calendario.montar(cliente.painel,dt.date(2026,11,12),q='divulgacao',pasta='agenda')['total'] == 1


def test_data_extrema_em_nota_externa_nao_derruba_agenda(cliente):
    nota = cliente.painel.criar_nota('tarefas', 'Data externa', {'data': '9999-12-31', 'hora': '23:30'})
    resposta = cliente.get('/agenda/2026-11-12')
    assert resposta.status_code == 200
    assert not any(e['rel'] == nota.rel for e in calendario.montar(cliente.painel, dt.date(2026, 11, 12))['eventos'])


def test_intervalos_e_sobreposicoes_separam_faixas(cliente):
    criar(cliente)
    criar(cliente,titulo='Outra reunião',hora='09:30',hora_fim='10:30')
    criar(cliente,titulo='Depois',hora='10:30',hora_fim='11:00')
    cal = calendario.montar(cliente.painel, dt.date(2026,11,12),'dia')
    blocos = cal['dias'][0]['blocos']
    assert blocos[0]['largura'] == blocos[1]['largura'] == 50
    assert blocos[0]['esquerda'] != blocos[1]['esquerda']
    assert next(e for e in blocos if e['titulo'] == 'Depois')['largura'] == 100


def test_meia_noite_nao_ocupa_o_dia_seguinte(cliente):
    criar(cliente, titulo='Turno', hora='23:00',data_fim='2026-11-13',hora_fim='00:00')
    cal = calendario.montar(cliente.painel,dt.date(2026,11,12),'semana')
    dia12 = next(d for d in cal['dias'] if d['iso'] == '2026-11-12')
    dia13 = next(d for d in cal['dias'] if d['iso'] == '2026-11-13')
    assert any(e['titulo'] == 'Turno' for e in dia12['eventos'])
    assert not any(e['titulo'] == 'Turno' for e in dia13['eventos'])


def test_mover_preserva_duracao_e_recusa_versao_antiga(cliente):
    resultado, _ = criar(cliente,hora='23:00',data_fim='2026-11-13',hora_fim='01:30')
    pedido = {**{k:resultado[k] for k in ('rel','versao')},'data':'2026-11-15','hora':'08:00'}
    r = cliente.post('/api/agenda/mover',json=pedido)
    assert r.status_code == 200
    evento = cliente.get('/api/agenda/evento/' + resultado['rel']).json()
    assert evento['data'] == '2026-11-15' and evento['hora_fim'] == '10:30'
    assert cliente.post('/api/agenda/mover',json=pedido).status_code == 409


def test_edicao_concorrente_preserva_nota_e_nao_cria_copia(cliente,vault):
    resultado,dados = criar(cliente)
    caminho = vault / resultado['rel']
    caminho.write_bytes(caminho.read_bytes()+b'\nMudou no Obsidian.\n')
    resposta = cliente.post('/api/agenda/eventos',json={**dados,'rel':resultado['rel'],'versao':resultado['versao'],'titulo':'Alterar'})
    assert resposta.status_code == 409
    assert b'Mudou no Obsidian.' in caminho.read_bytes()
    assert len(list((vault / 'agenda/itens').glob('*.md'))) == 1


@pytest.mark.parametrize('mudanca', [dict(hora='24:00'),dict(hora_fim='08:00'),dict(data_fim='2026-11-11'),dict(data='2026-02-30'),dict(cor='red;display:none'),dict(data_fim='2028-01-01')])
def test_intervalos_invalidos_nao_criam_pastas(cliente,vault,mudanca):
    dados = {'titulo':'Inválido','data':'2026-11-12','hora':'09:00','hora_fim':'10:00',**mudanca}
    assert cliente.post('/api/agenda/eventos',json=dados).status_code == 400
    assert not (vault / 'agenda').exists()


def test_nao_transforma_instrucoes_em_eventos(cliente):
    nota = cliente.painel.criar_nota('tarefas','Preferência de agenda',{},'Só instruções',zona='humano')
    assert cliente.get('/api/agenda/evento/'+nota.rel).status_code == 400


def test_mover_item_com_outro_campo_de_data_preserva_contrato(cliente):
    modulo = cliente.painel.modulo('tarefas')
    nota = cliente.painel.criar_nota(modulo.id,'Tarefa sem horário',{'data':'2026-11-12'})
    r = cliente.post('/api/agenda/mover',json={'rel':nota.rel,'versao':nota.versao,'data':'2026-11-13'})
    assert r.status_code == 200
    atual = cliente.painel.nota(nota.rel)
    assert str(atual.campo('data')) == '2026-11-13' and atual.campo('status') == 'a_fazer'


def test_dados_do_vault_nao_viram_html_executavel(cliente):
    criar(cliente,titulo='</script><script>alert(1)</script>',categoria='<img src=x onerror=alert(1)>')
    pagina = cliente.get('/agenda/2026-11-12').text
    assert '<script>alert(1)</script>' not in pagina and '<img src=x' not in pagina
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(); self.capturar=False; self.json=''
        def handle_starttag(self,tag,attrs):
            if dict(attrs).get('id') == 'cal-eventos': self.capturar=True
        def handle_endtag(self,tag):
            if tag == 'script': self.capturar=False
        def handle_data(self,texto):
            if self.capturar: self.json += texto
    parser=Parser(); parser.feed(pagina)
    assert any(e['titulo'] == '</script><script>alert(1)</script>' for e in json.loads(parser.json))
