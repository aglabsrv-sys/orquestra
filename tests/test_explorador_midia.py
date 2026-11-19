"""Leitura de anexos e templates sem escapar do vault ou executar HTML no painel."""
from urllib.parse import quote

from orquestra import apresentacao as ap, temas


def test_grafo_completo_nao_trunca_notas_apos_seiscentas(cliente, vault):
    pasta = vault / "Acervo sintético"
    pasta.mkdir()
    for i in range(650):
        (pasta / f"Nota {i:04}.md").write_text(f"[[Nota {(i + 1) % 650:04}]]\n", encoding="utf-8")
    cliente.painel.indice.carregar()
    resultado = cliente.get("/api/pastas/grafo").json()
    assert not resultado["limitado"]
    assert len([n for n in resultado["notas"] if n["id"].startswith("Acervo sintético/")]) == 650
    assert len(resultado["ligacoes"]) >= 650
    assert resultado["total"] == len(resultado["notas"])


def test_imagens_relativas_e_obsidian_com_nomes_repetidos(cliente, vault):
    for pasta in ('A', 'B'):
        (vault / pasta).mkdir()
        (vault / pasta / 'foto com espaço.png').write_bytes(b'png')
    nota = vault / 'A' / 'Leitura.md'
    nota.write_text('![Foto](<foto com espaço.png>)\n\n![[foto com espaço.png|300]]', encoding='utf-8')
    cliente.painel.indice.carregar()
    html = str(ap.render_markdown(nota.read_text(encoding='utf-8'), cliente.painel.indice, 'A/Leitura.md'))
    assert html.count('/arquivo/' + quote('A/foto com espaço.png')) == 2
    assert '/arquivo/B/' not in html


def test_anexos_html_isolados_e_arquivos_privados_bloqueados(cliente, vault):
    (vault / 'Email.html').write_text('<html><style>h1{color:blue}</style><h1>Email</h1><script>parent.hacked=true</script></html>', encoding='utf-8')
    arquivos = cliente.get('/api/pastas/arvore').json()['arquivos']
    assert any(a['nome'] == 'Email.html' for a in arquivos)
    resposta = cliente.get('/documento/Email.html')
    assert resposta.status_code == 200
    csp = resposta.headers['content-security-policy']
    assert "default-src 'none'" in csp and 'sandbox' in csp and "frame-ancestors 'self'" in csp
    assert 'allow-scripts' not in csp
    assert cliente.get('/arquivo/Email.html').status_code == 404
    assert cliente.get('/documento/orquestra.yaml').status_code == 404
    assert cliente.get('/documento/.env').status_code == 404


def test_catalogo_salva_e_resolve_imagem_e_video(cliente):
    for capa in temas.CAPAS_CATALOGO:
        r = cliente.put('/api/modulos/tarefas', json={'capa': capa})
        assert r.status_code == 200
        resultado = ap.capa_de(cliente.painel, 'tarefas', cliente.painel.modulo('tarefas').capa)
        assert resultado['url'] == capa
        assert resultado['tipo'] == ('video' if capa.endswith('.webm') else 'imagem')
        assert cliente.get(capa).status_code == 200


def test_nota_embutida_so_permite_frame_do_proprio_painel(cliente):
    rel = next(iter(cliente.painel.indice.notas))
    normal = cliente.get('/n/' + quote(rel))
    embutida = cliente.get('/n/' + quote(rel) + '?explorador=1')
    assert "frame-ancestors 'none'" in normal.headers['content-security-policy']
    assert "frame-ancestors 'self'" in embutida.headers['content-security-policy']
