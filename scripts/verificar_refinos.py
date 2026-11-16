"""Jornadas de navegação, recorrências e formulários em um vault fictício.

uv run --frozen --group browser python scripts/verificar_refinos.py
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from playwright.sync_api import expect, sync_playwright

from verificar_interface import aguardar_servidor


def jornadas(browser, base, vault, capturas):
    erros = []
    for largura in (1440, 390):
        contexto = browser.new_context(viewport={"width": largura, "height": 960 if largura == 1440 else 844}, reduced_motion="reduce")
        page = contexto.new_page()
        page.on('pageerror', lambda e: erros.append(str(e)))
        page.goto(base)
        ids = page.locator('.slide').evaluate_all('els=>els.map(e=>e.dataset.id)')
        page.keyboard.press('2')
        expect(page.locator('.slide.ativo')).to_have_attribute('data-id', ids[1])
        page.keyboard.press('0')
        expect(page.locator('#gaveta')).to_be_visible()
        page.keyboard.press('Escape')
        page.goto(base + '/m/projetos')
        page.locator('.dock a[href="/"]').click()
        expect(page.locator('.slide.ativo')).to_have_attribute('data-id', 'projetos')
        page.locator('.dock a[href="/"]').click()
        expect(page.locator('.slide.ativo')).to_have_attribute('data-id', ids[0])
        for modulo in ('tarefas', 'projetos'):
            page.goto(base + '/m/' + modulo)
            page.locator('#abrir-novo').click()
            expect(page.locator('#novo-corpo')).to_be_visible()
            page.locator('#novo-titulo').fill('Teste ' + modulo + ' ' + str(largura))
            page.locator('#novo-corpo').fill('Descrição opcional preservada no texto.')
            url_antes = page.url
            page.keyboard.press('2')
            assert page.url == url_antes
            page.locator('#novo-salvar').click()
            expect(page.locator('#dialogo-novo')).not_to_be_visible()

        page.goto(base + '/ajustes/automacoes')
        page.locator('[data-auto-ver-catalogo]').first.click() if page.locator('[data-auto-ver-catalogo]').count() else page.locator('[data-auto-aba=catalogo]').click()
        page.locator('[data-auto-adicionar="tarefas/recorrentes.py"]').click()
        expect(page.locator('.auto-config-item')).to_have_count(1)
        page.locator('.auto-config-item input').first.fill('Revisar clientes ' + str(largura))
        page.locator('.auto-recorrencia select').select_option('semana')
        page.locator('.auto-semana input[value=sexta]').uncheck()
        page.locator('.auto-semana input[value=segunda]').check()
        expect(page.locator('#automacao-frequencia')).to_have_value('diaria')
        if capturas:
            page.screenshot(path=str(capturas / f'automacao-semanal-{largura}.png'))
        page.locator('#automacao-salvar').click()
        expect(page.locator('#automacao-previa')).to_be_visible()
        page.locator('#automacao-salvar').click()
        expect(page.locator('#automacao-dialogo')).not_to_be_visible()

        page.goto(base + '/m/habitos')
        page.locator('[data-habito-novo]').first.click()
        page.locator('#habito-titulo').fill('Caminhar ' + str(largura))
        page.locator('#habito-descricao').fill('Uma volta na praça, sem pressa.')
        if capturas:
            page.screenshot(path=str(capturas / f'habito-editor-{largura}.png'))
        page.locator('#habito-salvar').click()
        expect(page.locator('#habito-editor')).not_to_be_visible()
        expect(page.locator('.habito-descricao').last).not_to_be_visible()
        page.goto(base + '/m/habitos?aba=lista')
        expect(page.locator('.habito-descricao').last).to_be_visible()

        page.goto(base + '/m/tarefas/personalizar')
        page.locator('#p-nome').fill('Tarefas pessoais ' + str(largura))
        page.locator('.icone-seletor summary').click()
        page.locator('[data-icone=estrela]').click()
        page.locator('#escolher-cena').click()
        page.locator('[data-escolher-cena=mar]').click()
        expect(page.locator('#p-capa-estado')).to_have_text('Capa salva.')
        expect(page.locator('#p-nome')).to_have_value('Tarefas pessoais ' + str(largura))
        expect(page.locator('#p-estado')).to_have_text('Há alterações para salvar.')
        # Salvar capa não pode salvar o nome/ícone ainda em edição.
        from orquestra.config import ler_yaml
        salvo = ler_yaml(vault / 'tarefas/_modulo.yaml')
        assert salvo['capa']['cena'] == 'mar'
        if largura == 1440:
            assert salvo['icone'] != 'estrela'
        page.locator('#p-salvar').click()
        expect(page.locator('.cab-modulo h1')).to_have_text('Tarefas pessoais ' + str(largura))

        page.goto(base + '/lixeira')
        if page.locator('#lixeira-todos').count():
            page.locator('#lixeira-todos').check()
            page.locator('#lixeira-acao').select_option('restaurar')
            page.locator('#lixeira-executar').click()
            expect(page.locator('[data-lixeira-id]')).to_have_count(0)
            expect(page.locator('#lixeira-resultado')).to_contain_text('restauradas')

        page.goto(base + '/agenda/2026-11-16?visao=semana')
        page.locator('[data-guia=agenda]').click()
        page.get_by_role('button', name='Continuar', exact=True).click()
        expect(page.locator('.guia-passos h3')).to_have_count(2)
        if capturas:
            page.screenshot(path=str(capturas / f'agenda-guia-{largura}.png'))
        page.get_by_role('button', name='Continuar', exact=True).click()
        page.locator('.guia-endereco').fill('https://calendario.example.test/ficticio.ics')
        page.get_by_role('dialog', name='Conecte sua agenda').get_by_role('button', name='Conectar agenda', exact=True).click()
        expect(page.get_by_role('button', name='Abrir Agenda', exact=True)).to_be_visible()
        page.get_by_role('button', name='Abrir Agenda', exact=True).click()
        page.goto(base + '/agenda/2026-11-16?visao=semana')
        expect(page.locator('[data-cal-externo]')).to_have_count(1)
        page.locator('[data-cal-externo]').click()
        expect(page.get_by_role('dialog', name='Compromisso da agenda externa')).to_contain_text('somente leitura')
        page.get_by_role('dialog', name='Compromisso da agenda externa').get_by_role('button', name='Fechar').click()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        contexto.close()
    assert not erros, erros
    return {"larguras": [1440, 390], "erros_javascript": erros, "jornadas": ["atalhos e dock", "descrições", "recorrência semanal", "capa imediata e rascunhos", "ícones", "lixeira em lote", "assinatura iCal sem tarefas"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capturas', type=Path)
    args = parser.parse_args()
    if args.capturas:
        args.capturas.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='orquestra-refinos-') as temporario:
        raiz = Path(temporario)
        os.environ['ORQUESTRA_HOME'] = str(raiz / 'home')
        os.environ.pop('ORQUESTRA_VAULT', None)
        from orquestra import preparo
        from orquestra.painel import Painel
        vault = raiz / 'vault'
        preparo.preparar(vault, ['tarefas', 'projetos', 'habitos'], exemplos=False, com_backup=False)
        painel = Painel(vault)
        for i in range(2):
            nota = painel.criar_nota('tarefas', 'Lixeira fictícia ' + str(i))
            painel.excluir(nota.rel, nota.versao)
        ical = b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:ficticio\r\nDTSTART:20261116T130000Z\r\nDTEND:20261116T140000Z\r\nSUMMARY:Compromisso ficticio\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            porta = sock.getsockname()[1]
        codigo = ('import uvicorn; from pathlib import Path; from orquestra import agenda_externa; '
                  f'agenda_externa.baixar=lambda _: {ical!r}; '
                  'from orquestra.hospedeiro import Hospedeiro; '
                  f'uvicorn.run(Hospedeiro(Path({str(vault)!r}),vigiar=False,agendar=False),host="127.0.0.1",port={porta},log_level="warning",proxy_headers=False)')
        with (raiz / 'servidor.log').open('w', encoding='utf-8') as log:
            processo = subprocess.Popen([sys.executable, '-c', codigo], stdout=log, stderr=log, **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            try:
                base = f'http://127.0.0.1:{porta}'
                aguardar_servidor(base, processo)
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        print(json.dumps(jornadas(browser, base, vault, args.capturas), ensure_ascii=False, indent=2))
                    finally:
                        browser.close()
            finally:
                processo.terminate()
                processo.wait(timeout=10)


if __name__ == '__main__':
    main()
