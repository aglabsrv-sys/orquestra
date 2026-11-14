"""Jornada de contatos, clientes, lixeira e reativação em um cofre fictício."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from orquestra import preparo
from verificar_interface import aguardar_servidor


def confirmar(page, nome):
    page.locator("dialog.confirmacao").get_by_role("button", name=nome, exact=True).click()


def conferir(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.url


def jornada(page, base, largura, capturas):
    page.set_viewport_size({"width": largura, "height": 900})
    page.goto(base + "/m/contatos")
    page.locator("#abrir-novo").click()
    page.locator("#novo-titulo").fill(f"Maria de exemplo {largura}")
    expect(page.locator('#novo-corpo')).not_to_be_visible()
    expect(page.locator('[data-novo][name="telefone"]')).not_to_be_visible()
    for campo in ("telefone", "email", "grupos", "favorito"):
        page.locator("#novo-adicionar-campo").select_option(campo)
    page.locator('[data-novo][name="telefone"]').fill("(00) 00000-0000")
    page.locator('[data-novo][name="email"]').fill(f"maria{largura}@example.com")
    page.locator('[data-novo][name="grupos"]').fill("amigos, trabalho")
    if capturas:
        page.screenshot(path=str(capturas / f"novo-contato-{largura}.png"), full_page=True)
    page.locator('[data-novo][name="favorito"]').check()
    page.locator("#novo-salvar").click()
    page.get_by_role("link", name=f"Maria de exemplo {largura}", exact=True).click()
    page.wait_for_url("**/n/**")
    contato_url = page.url
    conferir(page)
    if capturas:
        page.screenshot(path=str(capturas / f"contato-{largura}.png"), full_page=True)
    page.locator("#vincular-cliente").click()
    confirmar(page, "Acompanhar em Clientes")
    page.wait_for_url("**/n/clientes/**")
    expect(page.locator('[data-campo][name="contato_id"]')).not_to_have_value("")
    expect(page.locator("p.campo-ajuda").filter(has_text=f"maria{largura}@example.com")).to_be_visible()
    conferir(page)
    if capturas:
        page.screenshot(path=str(capturas / f"cliente-{largura}.png"), full_page=True)
    page.goto(base + "/m/contatos")
    page.get_by_role("searchbox", name="Buscar contato").fill(str(largura))
    page.get_by_role("combobox", name="Grupo", exact=True).select_option("amigos")
    page.get_by_role("button", name="Filtrar", exact=True).click()
    expect(page.locator(".tabela tbody tr")).to_have_count(1)
    conferir(page)
    page.goto(contato_url)
    page.locator("#excluir-nota").click()
    confirmar(page, "Mover para a lixeira")
    page.wait_for_url("**/lixeira")
    conferir(page)
    if capturas:
        page.screenshot(path=str(capturas / f"lixeira-{largura}.png"), full_page=True)
    page.get_by_role("button", name="Restaurar", exact=True).click()
    page.wait_for_url(contato_url)
    expect(page.get_by_role("link", name=f"Abrir em Clientes: Maria de exemplo {largura}")).to_be_visible()
    page.locator("#excluir-nota").click()
    confirmar(page, "Mover para a lixeira")
    page.wait_for_url("**/lixeira")
    page.get_by_role("button", name="Excluir definitivamente", exact=True).click()
    confirmar(page, "Excluir definitivamente")
    expect(page.get_by_text("A lixeira está vazia.")).to_be_visible()
    page.goto(base + "/ajustes/areas")
    pronto = page.locator('[data-pronto="estudos"]')
    if pronto.count():
        pronto.click()
    elif page.locator('[data-religar="estudos"]').count():
        page.locator('[data-religar="estudos"]').click()
    linha = page.locator('.area-linha[data-modulo="estudos"]')
    expect(linha).to_be_visible()
    linha.locator("[data-desligar]").click()
    confirmar(page, "Retirar do painel")
    expect(page.locator('[data-religar="estudos"]')).to_be_visible()
    page.locator('[data-religar="estudos"]').click()
    expect(linha).to_be_visible()
    conferir(page)
    # Deixa a próxima jornada no mesmo ponto inicial.
    linha.locator("[data-desligar]").click()
    confirmar(page, "Retirar do painel")
    expect(page.locator('[data-religar="estudos"]')).to_be_visible()
    page.goto(base + "/")
    expect(page.locator('.dock a[href="/m/agenda"]')).to_have_count(0)
    expect(page.locator('.dock a[href="/agenda"]')).to_have_count(1)
    assert page.locator('.dock .dock-entrada').count() == 0  # este cofre fictício não instalou Entrada

    # Seleção de vários itens e conferência da operação real nos arquivos.
    for nome in ('A', 'B'):
        resposta = page.request.post(base + '/api/notas', data={'modulo':'contatos', 'titulo':f'Lote {nome} {largura}'})
        assert resposta.ok
    page.goto(base + '/m/contatos')
    page.get_by_role('button', name='Ordenar esta página por Título', exact=True).click()
    page.get_by_role('button', name='Ordenar esta página por Título', exact=True).click()
    expect(page.locator('[data-lote-item]').first).to_have_attribute('aria-label', f'Selecionar Lote B {largura}')
    page.locator('[data-lote-item]').first.check()
    assert page.locator('[data-lote-todos]').evaluate('e=>e.indeterminate')
    page.locator('[data-lote-todos]').check()
    expect(page.locator('[data-lote-contagem]')).to_have_text('2 selecionados')
    page.locator('[data-lote-acao]').select_option('arquivar')
    page.locator('[data-lote-executar]').click()
    confirmar(page, 'Arquivar')
    expect(page.locator('[data-lote-resultado]')).to_have_text('2 notas atualizadas.')
    expect(page.locator('[data-lote-item]')).to_have_count(0)

    page.goto(base + '/m/clientes/personalizar')
    expect(page.locator('[role=tabpanel]:visible')).to_have_count(1)
    descricao = page.locator('#p-descricao').input_value()
    page.locator('#p-descricao').fill('Rascunho preservado')
    page.get_by_role('tab', name='Propriedades', exact=True).click()
    expect(page.locator('#p-identidade')).not_to_be_visible()
    expect(page.locator('#p-propriedades')).to_be_visible()
    page.get_by_role('tab', name='Visualizações', exact=True).click()
    expect(page.locator('#p-propriedades')).not_to_be_visible()
    expect(page.locator('#p-visoes')).to_be_visible()
    page.get_by_role('tab', name='Aparência', exact=True).click()
    expect(page.locator('#p-descricao')).to_have_value('Rascunho preservado')
    page.locator('#p-descricao').fill(descricao)
    assert page.locator('#personalizar > header').evaluate("e=>getComputedStyle(e).position") == 'static'
    conferir(page)
    if capturas:
        page.screenshot(path=str(capturas / f'personalizar-{largura}.png'), full_page=True)

    page.goto(base + '/ajustes/acesso')
    endereco = 'https://pc.exemplo.ts.net'
    page.evaluate("url=>window.Orquestra.api('POST','/api/tailscale/host',{url})", endereco)
    page.reload()
    expect(page.locator('#tailscale-links a')).to_have_text(endereco)
    page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async texto=>{window.__linkCopiado=texto}}})")
    page.get_by_role('button', name='Copiar endereço', exact=True).click()
    expect(page.locator('#tailscale-estado')).to_have_text('Endereço copiado.')
    assert page.evaluate('window.__linkCopiado') == endereco
    if capturas:
        page.screenshot(path=str(capturas / f'acesso-{largura}.png'), full_page=True)
    page.get_by_role('button', name='Revogar endereço', exact=True).click()
    confirmar(page, 'Revogar')
    expect(page.locator('#tailscale-links a')).to_have_count(0)

    if largura == 1440:
        page.goto(base + '/')
        page.evaluate("sessionStorage.setItem('orq-slide','0')")
        page.reload()
        inicial = page.locator('.slide.ativo').get_attribute('data-id')
        trilho = page.locator('.trilho').bounding_box()
        x, y = trilho['x'] + trilho['width'] * .8, trilho['y'] + trilho['height'] * .5
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x - trilho['width'] * .6, y, steps=15)
        page.mouse.up()
        page.wait_for_function("id=>document.querySelector('.slide.ativo').dataset.id!==id", arg=inicial)
        assert page.url.rstrip('/') == base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capturas", type=Path)
    args = parser.parse_args()
    if args.capturas:
        args.capturas.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="orquestra-contatos-") as temporario:
        raiz = Path(temporario)
        os.environ["ORQUESTRA_HOME"] = str(raiz / "home")
        vault = preparo.preparar(raiz / "vault", ["contatos", "clientes", "agenda"], exemplos=False, com_backup=False).vault
        ambiente = {**os.environ, "APPDATA": str(raiz / "appdata"), "HOME": str(raiz / "perfil")}
        ambiente.pop("ORQUESTRA_EM_SEGUNDO_PLANO", None)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta = s.getsockname()[1]
        base = f"http://127.0.0.1:{porta}"
        with (raiz / "servidor.log").open("wb") as log:
            servidor = subprocess.Popen([sys.executable, "-m", "orquestra", "iniciar", "--vault", str(vault), "--porta", str(porta)],
                                        env=ambiente, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            try:
                aguardar_servidor(base, servidor)
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.emulate_media(reduced_motion="reduce")
                    erros = []
                    page.on("pageerror", lambda erro: erros.append(str(erro)))
                    for largura in (1440, 390):
                        jornada(page, base, largura, args.capturas)
                    assert not erros, erros
                    browser.close()
                print("Contatos, clientes, filtros, lixeira e reativação: OK em 1440 e 390 px.")
            finally:
                try:
                    with urllib.request.urlopen(base + "/api/local/capacidade", timeout=2) as r:
                        token = json.load(r)["token"]
                    pedido = urllib.request.Request(base + "/api/local/encerrar", data=b"{}", headers={"Content-Type": "application/json", "X-Orquestra-Local": token})
                    urllib.request.urlopen(pedido, timeout=3).close()
                    servidor.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(servidor.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        servidor.terminate()
                    servidor.wait(timeout=10)


if __name__ == "__main__":
    main()
