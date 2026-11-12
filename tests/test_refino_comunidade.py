"""Fronteiras de segurança e regressões dos novos fluxos."""
import os
import subprocess

import pytest

from orquestra import aparencia, confianca, preparo, segredos
from orquestra.config import carregar_env, pasta_app
from orquestra.modulos import carregar_modulo


def local(cliente):
    return {"X-Orquestra-Local": cliente.get('/api/local/capacidade').json()['token']}


def test_variaveis_nao_vazam_e_exigem_capacidade(cliente, vault):
    valor = 'segredo-ficticio-789'
    assert cliente.post('/api/variaveis', json={'nome':'YOUTUBE_API_KEY','valor':valor}).status_code == 403
    headers = local(cliente)
    assert cliente.post('/api/variaveis', headers=headers, json={'nome':'YOUTUBE_API_KEY','valor':valor}).status_code == 200
    r = cliente.get('/api/variaveis', headers=headers)
    assert r.json() == {'nomes':['YOUTUBE_API_KEY']}
    assert valor not in r.text and valor not in cliente.get('/ajustes/variaveis').text
    assert carregar_env()['YOUTUBE_API_KEY'] == valor
    assert not any(valor.encode() in p.read_bytes() for p in vault.rglob('*') if p.is_file())
    assert cliente.post('/api/variaveis', headers=headers, json={'nome':'YOUTUBE_API_KEY','valor':None}).status_code == 200
    assert carregar_env() == {}


@pytest.mark.parametrize('nome,valor', [('PATH','x'), ('GIT_CONFIG_COUNT','1'), ('OK_KEY','x\nEVIL=y'), ('OK_KEY','\x00'), ('../BAD','x')])
def test_variaveis_recusam_injecao(vault, nome, valor):
    antes = (pasta_app() / '.env').read_bytes()
    with pytest.raises(ValueError):
        segredos.salvar(vault, nome, valor)
    assert (pasta_app() / '.env').read_bytes() == antes


def test_original_liberado_alterado_bloqueado_e_revogacao_respeitada(tmp_path):
    vault = preparo.preparar(tmp_path / 'vault', ['tarefas'], com_backup=False).vault
    modulo = carregar_modulo(vault / 'tarefas')
    c = modulo.coletores[0]
    assert confianca.resumo(vault, modulo, c)['confiavel']
    c.config = {'tarefas':[{'titulo':'Alterada','quando':'todo dia'}]}
    assert not confianca.resumo(vault, modulo, c)['confiavel']
    modulo = carregar_modulo(vault / 'tarefas'); c = modulo.coletores[0]
    confianca.revogar(vault, modulo, c)
    assert not confianca.resumo(vault, modulo, c)['confiavel']
    confianca.autorizar(vault, modulo, c, confianca.resumo(vault, modulo, c)['assinatura'])
    assert confianca.resumo(vault, modulo, c)['confiavel']
    (modulo.pasta / 'maquina/coletores/recorrentes.py').write_text('print("alterado")', encoding='utf-8')
    assert not confianca.resumo(vault, modulo, c)['confiavel']


def test_capas_confinadas_e_conteudo_recusado(cliente, vault):
    headers = local(cliente)
    headers['Content-Type'] = 'application/octet-stream'
    assert cliente.post('/api/capas', headers=headers, content=b'<script>bad</script>').status_code == 400
    r = cliente.post('/api/capas', headers=headers, content=b'\x89PNG\r\n\x1a\n' + b'x'*20)
    assert r.status_code == 200
    assert (vault / r.json()['caminho']).read_bytes().startswith(b'\x89PNG')
    assert cliente.post('/api/capas', headers={'Content-Type':'application/octet-stream'}, content=b'x').status_code == 403


def test_capa_recusa_aba_de_outro_vault(cliente, vault):
    headers = {**local(cliente), 'Content-Type': 'application/octet-stream', 'X-Orquestra-Vault': 'outro-vault'}
    resposta = cliente.post('/api/capas', headers=headers, content=b'\x89PNG\r\n\x1a\n' + b'x' * 20)
    assert resposta.status_code == 409
    assert not (vault / 'midia/capas').exists()


def test_capa_revalida_confinamento_antes_da_gravacao(cliente, vault, tmp_path, monkeypatch):
    from orquestra import armazenamento

    externo = tmp_path / 'destino-externo'
    externo.mkdir()
    (vault / 'midia').mkdir(exist_ok=True)
    atualizar = armazenamento.atualizar_bytes

    def concorrer(caminho, transformar, **kwargs):
        if caminho.suffix == '.png':
            pasta = vault / 'midia/capas'
            if os.name == 'nt':
                resultado = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(pasta), str(externo)], capture_output=True)
                assert resultado.returncode == 0, 'Não foi possível preparar junction sintética'
            else:
                pasta.symlink_to(externo, target_is_directory=True)
        return atualizar(caminho, transformar, **kwargs)

    headers = {**local(cliente), 'Content-Type': 'application/octet-stream'}
    monkeypatch.setattr(armazenamento, 'atualizar_bytes', concorrer)
    resposta = cliente.post('/api/capas', headers=headers, content=b'\x89PNG\r\n\x1a\n' + b'x' * 20)
    assert resposta.status_code == 404
    assert not list(externo.iterdir())


def test_habitos_salvam_e_recusam_versao_antiga(cliente):
    cliente.painel.adicionar_modulo('habitos', exemplos=True)
    nota = next(iter(cliente.painel.indice.itens('habitos')))
    pedido = {'rel':nota.rel, 'versao':nota.versao}
    r = cliente.post('/api/habitos/marcar', json=pedido)
    assert r.status_code == 200 and r.json()['marcado']
    assert cliente.post('/api/habitos/marcar', json=pedido).status_code == 409
    assert cliente.get('/habitos').status_code == 200


def test_fonte_validada_e_persistente(cliente):
    assert cliente.post('/api/config', json={'aparencia':{'tamanho':'grande'}}).status_code == 200
    assert '--tamanho-fonte:18px' in cliente.get('/').text
    with pytest.raises(ValueError):
        aparencia.validar({'tamanho':'18px; color:red'})


def test_agenda_guarda_link_fora_do_vault_e_pede_revisao(cliente, vault):
    assert cliente.post('/api/modulos', json={'pronto':'tarefas'}).status_code in (200, 400)
    url = 'https://calendar.example.test/privado/basic.ics'
    r = cliente.post('/api/agenda/conectar', headers=local(cliente), json={'url':url})
    assert r.status_code == 200 and r.json()['revisar']
    assert carregar_env()['AGENDA_ICAL_URL'] == url
    assert url not in (vault / 'tarefas/_modulo.yaml').read_text(encoding='utf-8')
    modulo, c = cliente.painel.coletor('tarefas','agenda_ics.py')
    assert not c.ativo and c.requer == ['AGENDA_ICAL_URL']
    assert not confianca.resumo(vault, modulo, c)['confiavel']


def test_github_nao_inicia_login_sem_capacidade(cliente, monkeypatch):
    from orquestra.github_local import LoginGitHub
    monkeypatch.setattr(LoginGitHub, 'iniciar', lambda _: pytest.fail('login sem capacidade'))
    assert cliente.post('/api/github/login', json={}).status_code == 403


def test_github_vinculo_define_destino_de_leitura_e_envio(cliente, monkeypatch):
    from orquestra import backup, github_local, servidor
    monkeypatch.setattr(backup, 'e_repositorio', lambda _: True)
    monkeypatch.setattr(backup, 'resumo', lambda _: {})
    monkeypatch.setattr(github_local.LoginGitHub, 'comando', lambda *a: '{"isPrivate":true}')
    comandos = []
    monkeypatch.setattr(servidor.subprocess, 'run', lambda args, **kw: comandos.append(args))
    monkeypatch.setattr('shutil.which', lambda _: 'git')
    r = cliente.post('/api/github/vincular', headers=local(cliente), json={'repositorio':'exemplo/vault'})
    assert r.status_code == 200
    assert len(comandos) == 2
    assert {c[-2] for c in comandos} == {'remote.origin.url','remote.origin.pushurl'}
    assert all(c[-1] == 'https://github.com/exemplo/vault.git' for c in comandos)
    assert all('push' not in c for c in comandos)


def test_aprovacao_aditiva_preserva_pipeline(cliente):
    if 'conteudo' not in cliente.painel.indice.modulos:
        cliente.painel.adicionar_modulo('conteudo')
    assert cliente.post('/api/conteudo/aprovacao', json={}).status_code == 200
    m = cliente.painel.modulo('conteudo')
    assert 'ideia' in m.campos['status'].opcoes and 'em_aprovacao' in m.decidir
    assert any(a.definir == {'status':'aprovado'} for a in m.acoes)


def test_tailscale_permite_host_exato_e_mantem_limite_local(cliente):
    headers = local(cliente)
    for url in ('https://example.com', 'https://[', 'https://pc.rede.ts.net/arquivo', 'https://pc.rede.ts.net:80'):
        assert cliente.post('/api/tailscale/host', headers=headers, json={'url':url}).status_code == 400
    assert cliente.post('/api/tailscale/host', headers=headers, json={'url':'https://pc.rede.ts.net'}).status_code == 200
    origem = {'Host':'pc.rede.ts.net', 'Origin':'https://pc.rede.ts.net'}
    assert cliente.post('/api/config', headers=origem, json={'nome':'Via Serve'}).status_code == 200
    assert cliente.post('/api/config', headers={**origem,'Origin':'https://evil.test'}, json={'nome':'Ruim'}).status_code == 403
    assert cliente.get('/api/local/capacidade', headers={'Host':'pc.rede.ts.net'}).status_code == 403
    assert cliente.get('/', headers={'Host':'outro.rede.ts.net'}).status_code == 403


def test_agenda_nao_sobrescreve_script_modificado_durante_upgrade(cliente, monkeypatch):
    from orquestra import armazenamento
    modulo, _ = cliente.painel.coletor('tarefas','agenda_ics.py')
    script = modulo.pasta / 'maquina/coletores/agenda_ics.py'
    novo = script.read_bytes().replace(b'\r\n', b'\n')
    antigo = novo.replace(b'import os\n', b'').replace(b'        if isinstance(agenda, dict) and agenda.get("variavel"):\n            endereco = os.environ.get(str(agenda["variavel"]), "")\n', b'')
    script.write_bytes(antigo)
    atualizar = armazenamento.atualizar_bytes
    personalizado = b'print("Personalizado durante a operacao")\n'

    def concorrer(caminho, transformar, **kwargs):
        if caminho == script:
            script.write_bytes(personalizado)
        return atualizar(caminho, transformar, **kwargs)

    monkeypatch.setattr(armazenamento, 'atualizar_bytes', concorrer)
    r = cliente.post('/api/agenda/conectar', headers=local(cliente), json={'url':'https://calendar.example.test/basic.ics'})
    assert r.status_code == 409
    assert script.read_bytes() == personalizado
    assert 'AGENDA_ICAL_URL' not in carregar_env()
