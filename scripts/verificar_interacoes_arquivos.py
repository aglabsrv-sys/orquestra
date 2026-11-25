"""Menu contextual, importação e ordem de hábitos num cofre demonstrativo descartável."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from urllib.parse import quote

from playwright.sync_api import expect, sync_playwright

from orquestra import habitos, preparo
from orquestra.painel import Painel
from verificar_interface import aguardar_servidor


def jornadas(browser, base, vault, capturas):
    pagina = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    pagina.set_default_timeout(10000)
    erros = []
    pagina.on("pageerror", lambda erro: erros.append(str(erro)))

    def captura(nome):
        if capturas:
            pagina.screenshot(path=str(capturas / nome), full_page=True)

    def centralizado(seletor):
        alvo = pagina.locator(seletor)
        expect(alvo).to_be_visible()
        assert alvo.evaluate("e=>{const r=e.getBoundingClientRect(),p=e.parentElement.getBoundingClientRect();return Math.abs((r.left+r.right-p.left-p.right)/2)<2;}")
        assert pagina.evaluate("document.documentElement.scrollWidth<=innerWidth")

    for largura in (1440, 390):
        pagina.set_viewport_size({"width": largura, "height": 960})
        for area, classe in (("estudos", ".cartoes-simples"), ("projetos", ".pastas-vidro")):
            pagina.goto(base + "/m/" + area)
            centralizado(classe + " > .vazio")
        captura(f"projetos-vazio-{largura}.png")
    pagina.set_viewport_size({"width": 1440, "height": 960})
    resposta = pagina.request.post(base + "/api/notas", data={"modulo": "estudos", "titulo": "Estudo demonstrativo"})
    assert resposta.status == 200, resposta.text()
    estudo = resposta.json()["rel"]
    pagina.goto(base + "/m/estudos")
    pagina.locator('.cartao-pasta[data-contexto-pasta]').click(button="right")
    pagina.locator('#menu-contexto').get_by_role('menuitem', name='Propriedades', exact=True).click()
    expect(pagina.locator('#pasta-ajustes')).to_be_visible()
    pagina.goto(base + "/m/estudos?abrir=" + quote(estudo))
    # Uma subpasta física vazia exercita o mesmo estado dentro do estudo.
    filha = vault / "estudos/referencias/Estudo demonstrativo/Subpasta vazia"
    filha.mkdir(parents=True)
    pagina.goto(base + "/m/estudos?abrir=" + quote(estudo) + "&pasta=Subpasta%20vazia")
    centralizado(".pasta-conteudo > .vazio")

    pagina.goto(base + "/pastas/Pessoal?visao=notas")
    nota = pagina.locator(".lista-notas a.linha-nota").filter(has_text="Nota demonstrativa")
    nota.click(button="right")
    menu = pagina.locator("#menu-contexto")
    expect(menu).to_be_visible()
    expect(menu.get_by_role("menuitem")).to_have_text(["Abrir", "Propriedades", "Arquivar", "Excluir"])
    captura("menu-nota.png")
    pagina.keyboard.press("End")
    expect(menu.get_by_role("menuitem", name="Excluir", exact=True)).to_be_focused()
    pagina.keyboard.press("Escape")
    expect(menu).to_be_hidden()
    nota.focus()
    pagina.keyboard.press("Shift+F10")
    expect(menu.get_by_role("menuitem", name="Abrir", exact=True)).to_be_focused()
    menu.get_by_role("menuitem", name="Propriedades", exact=True).click()
    expect(pagina.locator("#nota-propriedades")).to_be_visible()
    pagina.goto(base + "/pastas/Pessoal?visao=notas")
    nota.click(button="right")
    menu.get_by_role("menuitem", name="Arquivar", exact=True).click()
    pagina.get_by_role("button", name="Cancelar", exact=True).last.click()
    assert (vault / "Pessoal/Nota demonstrativa.md").is_file()
    nota.click(button="right")
    menu.get_by_role("menuitem", name="Arquivar", exact=True).click()
    pagina.get_by_role("button", name="Arquivar", exact=True).click()
    expect(pagina.locator(".lista-notas a.linha-nota").filter(has_text="Nota demonstrativa")).to_have_count(0)
    assert (vault / "Pessoal/arquivo/Nota demonstrativa.md").read_bytes() == b"Conteudo demonstrativo.\n"
    pagina.locator('a[data-pasta="Pessoal"]').click(button='right')
    menu.get_by_role('menuitem',name='Excluir',exact=True).click()
    pagina.get_by_role('button',name='Mover para a lixeira',exact=True).click()
    pagina.wait_for_url(base + '/pastas/')
    assert not (vault / 'Pessoal').exists()
    pagina.goto(base + '/pastas?visao=grafo')
    expect(pagina.locator('#grafo-estado')).to_contain_text(re.compile(r'\d+ de \d+ notas'))
    pagina.locator('#grafo-canvas').focus()
    pagina.keyboard.press('ArrowRight')
    pagina.keyboard.press('Shift+F10')
    expect(menu.get_by_role('menuitem', name='Abrir', exact=True)).to_be_focused()
    assert menu.evaluate('e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;}')
    pagina.keyboard.press('Escape')

    pagina.goto(base + "/m/estudos?abrir=" + quote(estudo))
    transferir = pagina.evaluate_handle("""() => {
      const dados = new DataTransfer();
      dados.items.add(new File(['Resumo de demonstracao.\\n'], 'Resumo.md', {type:'text/markdown'}));
      dados.items.add(new File(['%PDF-demonstracao'], 'Manual.pdf', {type:'application/pdf'}));
      return dados;
    }""")
    pagina.dispatch_event("body", "dragenter", {"dataTransfer": transferir})
    expect(pagina.locator("#soltar-arquivos")).to_be_visible()
    captura("soltar-arquivos.png")
    pagina.dispatch_event("#soltar-arquivos", "drop", {"dataTransfer": transferir})
    expect(pagina.locator("#importar-arquivos-estado")).to_contain_text("2 de 2 arquivos adicionados")
    pagina.get_by_role("button", name="Concluir", exact=True).click()
    expect(pagina.locator(".folhas")).to_contain_text("Resumo")
    expect(pagina.locator(".arquivo-item").filter(has_text="Manual.pdf")).to_be_visible()
    assert (filha.parent / "Resumo.md").read_bytes() == b"Resumo de demonstracao.\n"
    transferir.dispose()

    # Soltar imagem na própria nota conserva o fluxo de anexo já existente.
    criativo = pagina.request.post(base + "/api/notas", data={"modulo": "conteudo", "titulo": "Criativo demonstrativo"}).json()["rel"]
    pagina.goto(base + "/n/" + quote(criativo))
    imagem = pagina.evaluate_handle("""() => {
      const dados = new DataTransfer();
      const bytes = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1kAAAAASUVORK5CYII='), c=>c.charCodeAt(0));
      dados.items.add(new File([bytes], 'Imagem.png', {type:'image/png'}));
      return dados;
    }""")
    # O DataTransfer sintético do Chromium não conserva dropEffect fora do evento.
    assert pagina.evaluate("""() => {
      const dados = {types:['Files'], dropEffect:'none'};
      const evento = new Event('dragover', {bubbles:true, cancelable:true});
      Object.defineProperty(evento, 'dataTransfer', {value:dados});
      document.querySelector('.nota').dispatchEvent(evento);
      return dados.dropEffect;
    }""") == "copy"
    pagina.dispatch_event(".nota", "drop", {"dataTransfer": imagem})
    expect(pagina.locator("#nota-imagem-campo")).to_have_value(re.compile(r"midia/capas/.+\.png"))
    expect(pagina.locator("#importar-arquivos")).to_be_hidden()
    imagem.dispose()

    pagina.goto(base + "/m/habitos")
    grade = pagina.locator("#habitos-grade")
    ordem = grade.locator("[data-habito]").evaluate_all("els=>els.map(e=>e.dataset.habito)")
    alcas = grade.locator("[data-habito-arrastar]")
    alcas.first.focus()
    pagina.keyboard.press("ArrowDown")
    expect(pagina.locator("#habitos-ordem-estado")).to_have_text("Ordem salva.")
    pagina.reload()
    atual = grade.locator("[data-habito]").evaluate_all("els=>els.map(e=>e.dataset.habito)")
    assert atual == [ordem[1], ordem[0], *ordem[2:]]
    # O arraste pertence somente à alça, preservando os cliques do histórico.
    inicio = alcas.first.bounding_box()
    fim = alcas.nth(2).bounding_box()
    pagina.mouse.move(inicio["x"] + inicio["width"] / 2, inicio["y"] + inicio["height"] / 2)
    pagina.mouse.down()
    pagina.mouse.move(fim["x"] + fim["width"] / 2, fim["y"] + fim["height"] / 2, steps=10)
    pagina.mouse.up()
    expect(pagina.locator("#habitos-ordem-estado")).to_have_text("Ordem salva.")
    depois = grade.locator("[data-habito]").evaluate_all("els=>els.map(e=>e.dataset.habito)")
    assert depois != atual
    pagina.reload()
    assert grade.locator("[data-habito]").evaluate_all("els=>els.map(e=>e.dataset.habito)") == depois
    captura("habitos-ordenaveis.png")
    pagina.route('**/api/habitos/ordem', lambda rota: rota.fulfill(status=503, content_type='application/json', body='{"erro":"Falha demonstrativa. Tente novamente."}'))
    alcas.first.focus()
    pagina.keyboard.press('ArrowDown')
    expect(pagina.locator('#habitos-ordem-estado')).to_have_text('Falha demonstrativa. Tente novamente.')
    assert grade.locator("[data-habito]").evaluate_all("els=>els.map(e=>e.dataset.habito)") == depois
    pagina.unroute('**/api/habitos/ordem')
    pagina.reload()
    pagina.set_viewport_size({'width':390,'height':844})
    assert pagina.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert grade.locator('[data-habito]').evaluate_all('els=>els.every(e=>e.querySelector("[data-habito-arrastar]").getBoundingClientRect().bottom<=e.querySelector(".habito-nome").getBoundingClientRect().top)')
    captura('habitos-ordenaveis-mobile.png')

    # A jornada intercepta somente a atualização: nunca muda o checkout do teste.
    pedidos_atualizacao = []
    def responder_atualizacao(rota):
        if rota.request.method == "POST":
            pedidos_atualizacao.append(rota.request.post_data_json)
            rota.fulfill(status=400, json={"erro": "Falha demonstrativa. Tente novamente."})
        else:
            rota.fulfill(json={"disponivel": True, "local": True, "pid": 1, "revisao": "nova"})
    pagina.route("**/api/atualizacao", responder_atualizacao)
    for largura in (1440, 390):
        pagina.set_viewport_size({"width": largura, "height": 844})
        pagina.goto(base + "/m/habitos")
        antes = len(pedidos_atualizacao)
        pagina.locator("#atualizar-app").click()
        expect(pagina.locator("#avisos")).to_contain_text("Falha demonstrativa. Tente novamente.")
        expect(pagina.locator("dialog[open]")).to_have_count(0)
        assert len(pedidos_atualizacao) == antes + 1
        assert pedidos_atualizacao[-1] == {}
        assert pagina.evaluate("document.documentElement.scrollWidth<=innerWidth")
    pagina.unroute("**/api/atualizacao")
    assert not erros, erros
    pagina.close()
    return {"jornadas": ["vazios centralizados desktop/mobile", "menu, teclado e propriedades", "cancelar e arquivar", "soltar Markdown e PDF", "ordem de hábitos por teclado e arraste", "atualização direta desktop/mobile"], "erros_js": erros}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capturas", type=Path)
    args = parser.parse_args()
    if args.capturas:
        args.capturas.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="orquestra-interacoes-") as temporario:
        raiz = Path(temporario)
        os.environ["ORQUESTRA_HOME"] = str(raiz / "home")
        os.environ.pop("ORQUESTRA_VAULT", None)
        vault = preparo.preparar(raiz / "Cofre demonstrativo", ["estudos", "projetos", "habitos", "tarefas", "conteudo"], exemplos=False, com_backup=False).vault
        pessoal = vault / "Pessoal"
        pessoal.mkdir()
        (pessoal / "Nota demonstrativa.md").write_bytes(b"Conteudo demonstrativo.\n")
        painel = Painel(vault)
        for nome in ("Caminhar", "Ler", "Estudar"):
            habitos.salvar(painel, {"titulo": nome, "meta_semanal": 3})
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta = s.getsockname()[1]
        codigo = ("import uvicorn; from pathlib import Path; from orquestra.hospedeiro import Hospedeiro; "
                  f"uvicorn.run(Hospedeiro(Path({str(vault)!r}),vigiar=False,agendar=False),host='127.0.0.1',port={porta},log_level='warning',proxy_headers=False)")
        with (raiz / "servidor.log").open("w", encoding="utf-8") as log:
            processo = subprocess.Popen([sys.executable, "-c", codigo], stdout=log, stderr=log)
            try:
                base = f"http://127.0.0.1:{porta}"
                aguardar_servidor(base, processo)
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        print(json.dumps(jornadas(browser, base, vault, args.capturas), ensure_ascii=False, indent=2))
                    finally:
                        browser.close()
            except Exception:
                print((raiz / "servidor.log").read_text(encoding="utf-8"), file=sys.stderr)
                raise
            finally:
                processo.terminate()
                processo.wait(timeout=10)


if __name__ == "__main__":
    main()
