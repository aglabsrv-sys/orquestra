"""Interações reais do grafo no Chromium, em um cofre sintético descartável.

uv run --frozen --group browser python scripts/verificar_grafo.py
Use --chromium CAMINHO para escolher o navegador ou --capturas PASTA para
guardar as telas verificadas em desktop e celular.
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
from urllib.parse import quote

from playwright.sync_api import expect, sync_playwright

from verificar_interface import aguardar_servidor


# O canvas não expõe elementos DOM para as notas. Observamos os círculos que o
# navegador efetivamente desenha, incluindo a transformação de zoom, para clicar
# nos nós sem criar pontos de teste no código de produção.
OBSERVAR_NOS = """(() => {
  const clear = CanvasRenderingContext2D.prototype.clearRect;
  const arc = CanvasRenderingContext2D.prototype.arc;
  const fill = CanvasRenderingContext2D.prototype.fill;
  const fillText = CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.clearRect = function(...args) {
    if (this.canvas.id === 'grafo-canvas') { this.canvas.__nosDesenhados = []; this.canvas.__rotulosDesenhados = []; }
    return clear.apply(this, args);
  };
  CanvasRenderingContext2D.prototype.arc = function(x, y, r, ...args) {
    if (this.canvas.id === 'grafo-canvas') {
      const m = this.getTransform(), b = this.canvas.getBoundingClientRect();
      const escala = this.canvas.width / b.width;
      this.__ultimoNo = {
        x: (m.a * x + m.c * y + m.e) / escala,
        y: (m.b * x + m.d * y + m.f) / escala,
        raio: r * m.a / escala
      };
    }
    return arc.call(this, x, y, r, ...args);
  };
  CanvasRenderingContext2D.prototype.fillText = function(text, x, y, ...args) {
    if (this.canvas.id === 'grafo-canvas') {
      const m=this.getTransform(), b=this.canvas.getBoundingClientRect(), escala=this.canvas.width/b.width;
      const w=this.measureText(text).width*m.a/escala;
      let px=(m.a*x+m.c*y+m.e)/escala;
      if(this.textAlign==='center') px-=w/2;
      this.canvas.__rotulosDesenhados.push({x:px,y:(m.b*x+m.d*y+m.f)/escala,w});
    }
    return fillText.call(this,text,x,y,...args);
  };
  CanvasRenderingContext2D.prototype.fill = function(...args) {
    if (this.canvas.id === 'grafo-canvas' && this.__ultimoNo) {
      (this.canvas.__nosDesenhados ||= []).push(this.__ultimoNo);
    }
    return fill.apply(this, args);
  };
})()"""


def aguardar_grafo(page) -> None:
    expect(page.locator("#pasta-grafo")).to_be_visible()
    expect(page.locator("#grafo-estado")).to_contain_text("notas")
    page.wait_for_function(
        "(document.querySelector('#grafo-canvas').__nosDesenhados || []).length > 0"
    )


def no_visivel(page) -> dict:
    ponto = page.locator("#grafo-canvas").evaluate("""e => {
      const b=e.getBoundingClientRect();
      return e.__nosDesenhados.map(p=>({...p,x:p.x+b.left,y:p.y+b.top})).find(p =>
        p.x > 0 && p.x < innerWidth && p.y > 0 && p.y < innerHeight - 80);
    }""")
    assert ponto, "Nenhuma nota do grafo está acessível na janela"
    return ponto


def abrir_no(page) -> None:
    ponto = no_visivel(page)
    page.mouse.click(ponto["x"], ponto["y"])
    expect(page.locator("#pasta-leitor")).to_be_visible()
    expect(page.frame_locator("#leitor-frame").locator(".nota")).to_be_visible()


def conferir_viewport(page) -> None:
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), "Explorador excede a largura"
    assert page.evaluate("document.documentElement.scrollHeight<=innerHeight+1"), "Explorador cria rolagem fora da janela"
    assert page.locator(".explorador").evaluate("e=>e.getBoundingClientRect().bottom<=innerHeight"), "Painel fora da janela"
    if page.locator("#pasta-grafo").is_visible():
        assert page.locator("#grafo-canvas").evaluate("e=>{const b=e.getBoundingClientRect();return b.height>100&&b.bottom<=innerHeight-65;}"), "Canvas fora da área útil"


def jornadas(browser, base: str, capturas: Path | None) -> dict:
    erros: list[str] = []
    for largura, altura in ((1440, 960), (390, 844), (320, 740), (320, 568)):
        contexto = browser.new_context(
            viewport={"width": largura, "height": altura}, reduced_motion="reduce"
        )
        try:
            contexto.add_init_script(OBSERVAR_NOS)
            page = contexto.new_page()
            page.set_default_timeout(10000)
            page.on("pageerror", lambda erro: erros.append(str(erro)))
            url = base + "/pastas/" + quote("Grafo QA", safe="")
            page.goto(url, wait_until="domcontentloaded")
            aguardar_grafo(page)
            expect(page.locator("#grafo-estado")).to_contain_text(
                "4 de 4 notas · 3 ligações"
            )
            if capturas:
                page.wait_for_timeout(160)
                page.screenshot(path=str(capturas / f"grafo-{largura}{'-curto' if altura<700 else ''}.png"), full_page=True)

            # A árvore só expande: mantém o mesmo grafo, URL, posições e escopo.
            ramo = page.locator('details[data-rel="Segunda"]')
            original = page.url
            page.evaluate("window.__canvasPasta=document.querySelector('#grafo-canvas')")
            antes = page.locator("#grafo-canvas").evaluate("e=>e.__nosDesenhados")
            ramo.locator(":scope > summary > a").click()
            expect(ramo).to_have_attribute("open", "")
            expect(ramo.locator('.arvore-ramo[data-rel="Segunda/Interna"]')).to_be_visible()
            assert page.url == original
            assert page.evaluate("window.__canvasPasta===document.querySelector('#grafo-canvas')")
            assert page.locator("#grafo-canvas").evaluate("e=>e.__nosDesenhados") == antes
            expect(page.locator("#pasta-painel")).to_have_attribute("data-rel", "Grafo QA")
            ramo.locator(":scope > summary > a").click()
            expect(ramo).not_to_have_attribute("open", "")
            conferir_viewport(page)
            assert page.locator("#grafo-canvas").evaluate("""e=>e.__rotulosDesenhados.every(r=>
              r.x>=0 && r.x+r.w<=e.getBoundingClientRect().width && r.y>=0 && r.y<=e.getBoundingClientRect().height)"""), "Rótulos fora do canvas"

            # Filtros permanecem acessíveis mesmo em uma janela baixa.
            page.locator(".grafo-opcoes summary").click()
            assert page.locator(".grafo-opcoes > div").evaluate("""e=>{
              const r=e.getBoundingClientRect(),p=document.querySelector('#pasta-grafo').getBoundingClientRect();
              return r.bottom<=p.bottom+1 && r.top>=p.top;
            }"""), "Filtros cortados pelo painel"
            page.locator("#grafo-rotulos").uncheck()
            page.locator("#grafo-rotulos").check()
            # Busca e notas isoladas filtram o desenho e sua lista acessível.
            page.locator("#grafo-busca").fill("Alpha")
            expect(page.locator("#grafo-estado")).to_contain_text(
                "1 de 4 notas · 0 ligações"
            )
            assert page.locator("#grafo-notas li:not([hidden])").count() == 1
            page.locator("#grafo-busca").fill("")
            page.locator("#grafo-isoladas").uncheck()
            expect(page.locator("#grafo-estado")).to_contain_text(
                "3 de 4 notas · 3 ligações"
            )
            assert page.locator("#grafo-notas li:not([hidden])").count() == 3
            page.locator(".grafo-opcoes summary").click()

            # Zoom pelo teclado muda a escala; zero volta a enquadrar as notas.
            page.locator("#grafo-canvas").focus()
            raio_inicial = no_visivel(page)["raio"]
            page.keyboard.press("+")
            assert no_visivel(page)["raio"] > raio_inicial
            page.keyboard.press("0")
            assert abs(no_visivel(page)["raio"] - raio_inicial) < .1

            # Arrastar reposiciona a nota; apenas o clique abre o leitor.
            ponto = no_visivel(page)
            page.mouse.move(ponto["x"], ponto["y"])
            page.mouse.down()
            page.mouse.move(ponto["x"] + 45, ponto["y"] + 20, steps=5)
            page.mouse.up()
            expect(page.locator("#pasta-leitor")).to_be_hidden()
            page.locator("#grafo-centralizar").click()
            abrir_no(page)
            page.locator("#leitor-fechar").click()
            aguardar_grafo(page)
            expect(page.locator("#grafo-isoladas")).not_to_be_checked()
            expect(page.locator("#grafo-estado")).to_contain_text(
                "3 de 4 notas · 3 ligações"
            )

            # A busca também continua aplicada ao reconstruir o canvas.
            page.locator(".grafo-opcoes summary").click()
            page.locator("#grafo-busca").fill("Alpha")
            page.locator(".grafo-opcoes summary").click()
            abrir_no(page)
            page.locator("#leitor-fechar").click()
            aguardar_grafo(page)
            expect(page.locator("#grafo-busca")).to_have_value("Alpha")
            expect(page.locator("#grafo-estado")).to_contain_text(
                "1 de 4 notas · 0 ligações"
            )

            # Cada pasta memoriza sua visualização, inclusive após recarregar.
            page.locator("[data-pasta-visao=notas]").click()
            expect(page.locator("#pasta-notas")).to_be_visible()
            page.reload(wait_until="domcontentloaded")
            expect(page.locator("#pasta-notas")).to_be_visible()
            expect(page.locator("[data-pasta-visao=notas]")).to_have_attribute(
                "aria-pressed", "true"
            )
            # Navegar explicitamente para outra pasta usa o grafo como padrão.
            page.goto(base + "/pastas/Segunda", wait_until="domcontentloaded")
            aguardar_grafo(page)
            expect(page.locator("#pasta-painel")).to_have_attribute("data-rel", "Segunda")
            assert page.locator(".explorador-trilha").count() == 0
            page.locator(".explorador-voltar").click()
            expect(page.locator("#pasta-painel")).to_have_attribute("data-rel", "")
            aguardar_grafo(page)
            page.goto(url, wait_until="domcontentloaded")
            expect(page.locator("#pasta-notas")).to_be_visible()
            page.locator("[data-pasta-visao=grafo]").click()
            aguardar_grafo(page)
            page.reload(wait_until="domcontentloaded")
            aguardar_grafo(page)
            expect(page.locator("[data-pasta-visao=grafo]")).to_have_attribute(
                "aria-pressed", "true"
            )
            # Muitos arquivos avulsos não afastam o grupo conectado nem deixam pontos fora da tela.
            page.goto(base + "/pastas/Conjunto", wait_until="domcontentloaded")
            page.locator("[data-pasta-visao=grafo]").click()
            aguardar_grafo(page)
            expect(page.locator("#grafo-estado")).to_contain_text("104 de 104 notas")
            enquadramento = page.locator("#grafo-canvas").evaluate("""e => {
              const b=e.getBoundingClientRect(), nos=e.__nosDesenhados, miolo=nos.slice(0,8);
              const xs=miolo.map(n=>n.x), ys=miolo.map(n=>n.y);
              return { largura:b.width, altura:b.height,
                tamanho:Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys)),
                visiveis:nos.every(n=>n.x>10 && n.x<b.width-10 && n.y>30 && n.y<b.height-10) };
            }""")
            assert enquadramento["visiveis"], "Centralização deixa notas fora da tela"
            assert enquadramento["tamanho"] > enquadramento["largura"] * .09, "Avulsos reduziram demais o miolo"
            # A acomodação animada também termina sem dispersar o conjunto.
            page.emulate_media(reduced_motion="no-preference")
            page.wait_for_timeout(1500)
            page.locator("#grafo-centralizar").click()
            assert page.locator("#grafo-canvas").evaluate("""e => {
              const b=e.getBoundingClientRect();
              return e.__nosDesenhados.length===104 && e.__nosDesenhados.every(n=>
                Number.isFinite(n.x) && Number.isFinite(n.y) &&
                n.x>10 && n.x<b.width-10 && n.y>30 && n.y<b.height-10);
            }"""), "A simulação dispersou notas para fora da área"
            if capturas:
                page.wait_for_timeout(160)
                page.screenshot(path=str(capturas / f"grafo-avulsos-{largura}{'-curto' if altura<700 else ''}.png"), full_page=True)
            conferir_viewport(page)
        finally:
            contexto.close()
    assert not erros, erros
    return {
        "larguras": [1440, 390, 320], "janela_curta": "320x568", "erros_javascript": erros,
        "jornadas": ["busca", "notas isoladas", "filtros ao voltar do leitor",
                     "zoom pelo teclado e centralização", "arrastar e abrir notas",
                     "visualização memorizada por pasta e após recarregar",
                     "nome da pasta só expande sem alterar grafo", "centralização com muitos avulsos", "painéis dentro do viewport"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium")
    parser.add_argument("--capturas", type=Path)
    args = parser.parse_args()
    if args.capturas:
        args.capturas.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="orquestra-grafo-") as pasta:
        raiz = Path(pasta)
        # Preparação e servidor só enxergam a configuração temporária.
        os.environ["ORQUESTRA_HOME"] = str(raiz / "home")
        os.environ.pop("ORQUESTRA_VAULT", None)
        from orquestra import preparo

        vault = raiz / "cofre"
        preparo.preparar(vault, [], exemplos=False, com_backup=False)
        notas = vault / "Grafo QA"
        notas.mkdir()
        for nome, texto in (("Alpha", "[[Beta]]"), ("Beta", "[[Gamma]]"),
                            ("Gamma", "[[Alpha]]"), ("Isolada", "Sem ligações.")):
            (notas / (nome + ".md")).write_text("# " + nome + "\n\n" + texto, encoding="utf-8")
        segunda = vault / "Segunda"
        segunda.mkdir()
        (segunda / "Outra.md").write_text("# Outra\n\nOutra pasta.", encoding="utf-8")
        interna=segunda / "Interna" / "Neta"
        interna.mkdir(parents=True)
        (interna / "Referência.md").write_text("# Referência\n\nNota aninhada.", encoding="utf-8")
        conjunto = vault / "Conjunto"
        conjunto.mkdir()
        for i in range(8):
            (conjunto / f"Centro {i:02}.md").write_text(f"# Centro {i:02}\n\n[[Centro {(i+1)%8:02}]]", encoding="utf-8")
        for i in range(96):
            (conjunto / f"Solta {i:02}.md").write_text(f"# Solta {i:02}\n\nArquivo sem ligações.", encoding="utf-8")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta = s.getsockname()[1]
        codigo = (
            "import uvicorn; from pathlib import Path; from orquestra.hospedeiro import Hospedeiro; "
            f"uvicorn.run(Hospedeiro(Path({str(vault)!r}),vigiar=False,agendar=False), "
            f"host='127.0.0.1', port={porta}, log_level='warning', proxy_headers=False)"
        )
        with (raiz / "servidor.log").open("w", encoding="utf-8") as log:
            processo = subprocess.Popen([sys.executable, "-c", codigo], stdout=log, stderr=log)
            try:
                base = f"http://127.0.0.1:{porta}"
                aguardar_servidor(base, processo)
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path=args.chromium, headless=True)
                    try:
                        print(json.dumps(jornadas(browser, base, args.capturas), ensure_ascii=False, indent=2))
                    finally:
                        browser.close()
            except Exception:
                print((raiz / "servidor.log").read_text(encoding="utf-8"), file=sys.stderr)
                raise
            finally:
                processo.terminate()
                try:
                    processo.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    processo.kill()
                    processo.wait(timeout=5)


if __name__ == "__main__":
    main()
