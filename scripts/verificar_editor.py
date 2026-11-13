"""Live preview em notas sintéticas: preserva Markdown e a moldura do explorador.

uv run --frozen --group browser python scripts/verificar_editor.py
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


FONTE = """# Documento de teste

Primeiro com **negrito** e [[Destino|apelido]].

Segundo parágrafo para editar.

- [ ] Tarefa aberta
- [x] Tarefa realizada

| Coluna | Valor |
| --- | --- |
| A | 42 |

```js
const literal = "[[não é link]]";
```

Fim da nota, com [link](https://example.invalid).
"""
CABECALHO = "---\n# comentário mantido\ncategoria: referência\n---\n"


def jornadas(browser, base: str, vault: Path, capturas: Path | None) -> dict:
    from orquestra.notas import ler_nota

    erros = []
    for largura in (1440, 390, 320):
        nome = f"Editor QA {largura}"
        arquivo = vault / "Notas" / f"{nome}.md"
        contexto = browser.new_context(viewport={"width": largura, "height": 960}, reduced_motion="reduce")
        try:
            page = contexto.new_page()
            page.on("pageerror", lambda erro: erros.append(str(erro)))
            page.goto(base + "/pastas/Notas", wait_until="domcontentloaded")
            page.locator("#arvore-pastas .arvore-nota").filter(has_text=nome).click()
            leitor = page.frame_locator("#leitor-frame")
            expect(leitor.locator("#ver table")).to_be_visible()
            antigo = leitor.locator("#ver > p").filter(has_text="Segundo parágrafo")
            dimensoes = antigo.bounding_box()
            fonte = antigo.evaluate("e=>getComputedStyle(e).fontSize")
            rota = page.url
            frame_src = page.locator("#leitor-frame").get_attribute("src")
            iframe = page.locator("#leitor-frame").bounding_box()
            antigo.dblclick()
            editor = leitor.locator("#editor[data-editor-bloco]")
            expect(editor).to_be_visible()
            expect(leitor.locator("#ver h1")).to_have_text("Documento de teste")
            expect(leitor.locator("#ver table")).to_be_visible()
            expect(leitor.locator("#ver pre")).to_be_visible()
            atual = editor.bounding_box()
            assert abs(atual["x"] - dimensoes["x"]) < 2
            assert abs(atual["width"] - dimensoes["width"]) < 2
            assert atual["height"] >= dimensoes["height"]
            assert editor.evaluate("e=>getComputedStyle(e).fontSize") == fonte
            assert page.locator("#leitor-frame").bounding_box() == iframe
            assert page.url == rota and page.locator("#leitor-frame").get_attribute("src") == frame_src
            if capturas:
                page.screenshot(path=str(capturas / f"editor-inline-{largura}.png"), full_page=True)

            novo = "Parágrafo revisado com *itálico* e [[Destino]]."
            editor.fill(novo)
            with page.expect_response(lambda r: "/api/notas/" in r.url and r.request.method == "PUT") as salvo:
                editor.press("Escape")
            assert salvo.value.status == 200
            expect(leitor.locator("#editor")).to_be_hidden()
            expect(leitor.locator("#ver em")).to_have_text("itálico")
            assert ler_nota(arquivo, vault).corpo == FONTE.replace("Segundo parágrafo para editar.", novo)
            assert page.url == rota and page.locator("#leitor-frame").get_attribute("src") == frame_src
            assert page.evaluate("document.documentElement.scrollHeight <= innerHeight + 1")

            # Entrar e sair sem digitar não grava nem normaliza o arquivo.
            antes = arquivo.read_bytes()
            puts = []
            page.on("request", lambda r: puts.append(r.url) if r.method == "PUT" else None)
            leitor.locator("#ver h1").dblclick()
            expect(editor).to_have_value("# Documento de teste")
            editor.press("Escape")
            expect(editor).to_be_hidden()
            assert arquivo.read_bytes() == antes and not puts

            # Sair por um wikilink salva o trecho e conserva a moldura do leitor.
            leitor.locator("#ver > p").filter(has_text="Parágrafo revisado").dblclick()
            editor.fill("Texto salvo antes de abrir outra nota.")
            leitor.locator("#ver a").filter(has_text="apelido").click()
            expect(leitor.locator("#nota-titulo")).to_have_value("Destino")
            expect(leitor.locator(".dock")).to_be_hidden()
            assert page.url == rota
            assert "Texto salvo antes de abrir outra nota." in ler_nota(arquivo, vault).corpo
        finally:
            contexto.close()
    assert not erros, erros
    return {"larguras": [1440, 390, 320], "erros_javascript": erros,
            "jornadas": ["edição no bloco renderizado", "fonte e largura preservadas", "iframe e rota estáveis",
                         "Markdown fora do trecho intacto", "Escape salva", "abrir sem editar não grava", "wikilink salva antes de navegar no leitor"]}


def conferir_linhas_iniciais(browser, base: str, vault: Path) -> dict:
    from orquestra.notas import ler_nota

    casos = 0
    for largura in (1440, 320):
        contexto = browser.new_context(viewport={"width": largura, "height": 960}, reduced_motion="reduce")
        try:
            page = contexto.new_page()
            for quebras in (0, 1, 2):
                for frontmatter in (False, True):
                    nome = f"Fonte {largura} {quebras} {'com' if frontmatter else 'sem'} frontmatter"
                    arquivo = vault / "Notas" / f"{nome}.md"
                    esperado = "\n" * quebras + FONTE
                    inicial = ler_nota(arquivo, vault)
                    assert inicial.corpo == esperado
                    cabecalho_bytes = CABECALHO.replace("\n", "\r\n" if inicial.crlf else "\n").encode("utf-8")
                    page.goto(base + "/n/" + quote(f"Notas/{nome}.md") + "?explorador=1", wait_until="domcontentloaded")
                    assert page.locator("#nota-fonte").input_value() == esperado

                    # O primeiro heading precisa abrir seu próprio texto, mesmo
                    # com linhas vazias no início do corpo após o frontmatter.
                    page.locator("#ver > h1").dblclick()
                    editor = page.locator("#editor[data-editor-bloco]")
                    expect(editor).to_have_value("# Documento de teste")
                    editor.fill("# Título revisado")
                    with page.expect_response(lambda r: "/api/notas/" in r.url and r.request.method == "PUT") as salvo:
                        editor.press("Escape")
                    assert salvo.value.status == 200
                    expect(editor).to_be_hidden()
                    esperado = esperado.replace("# Documento de teste", "# Título revisado", 1)
                    assert ler_nota(arquivo, vault).corpo == esperado
                    assert page.locator("#nota-fonte").input_value() == esperado

                    page.locator("#ver > p").filter(has_text="Primeiro com").dblclick()
                    expect(editor).to_have_value("Primeiro com **negrito** e [[Destino|apelido]].")
                    editor.fill("Primeiro parágrafo revisado.")
                    with page.expect_response(lambda r: "/api/notas/" in r.url and r.request.method == "PUT") as salvo:
                        editor.press("Escape")
                    assert salvo.value.status == 200
                    expect(editor).to_be_hidden()
                    esperado = esperado.replace("Primeiro com **negrito** e [[Destino|apelido]].", "Primeiro parágrafo revisado.", 1)
                    assert ler_nota(arquivo, vault).corpo == esperado
                    if frontmatter:
                        assert arquivo.read_bytes().startswith(cabecalho_bytes)

                    if quebras:
                        antes = arquivo.read_bytes()
                        page.locator("#ver > h1").evaluate("e=>{e.dataset.mdInicio='0';e.dataset.mdFim='1';}")
                        page.locator("#ver > h1").dblclick()
                        expect(editor).to_have_value(esperado)
                        editor.press("Escape")
                        expect(editor).to_be_hidden()
                        assert arquivo.read_bytes() == antes
                    casos += 1
        finally:
            contexto.close()
    return {"casos": casos, "linhas_iniciais": [0, 1, 2], "frontmatter": [False, True]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium")
    parser.add_argument("--capturas", type=Path)
    args = parser.parse_args()
    if args.capturas:
        args.capturas.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="orquestra-editor-") as pasta:
        raiz = Path(pasta)
        os.environ["ORQUESTRA_HOME"] = str(raiz / "home")
        os.environ.pop("ORQUESTRA_VAULT", None)
        from orquestra import preparo

        vault = raiz / "cofre"
        preparo.preparar(vault, [], exemplos=False, com_backup=False)
        notas = vault / "Notas"
        notas.mkdir()
        for largura in (1440, 390, 320):
            (notas / f"Editor QA {largura}.md").write_text(FONTE, encoding="utf-8")
        for largura in (1440, 320):
            for quebras in (0, 1, 2):
                for frontmatter in (False, True):
                    nome = f"Fonte {largura} {quebras} {'com' if frontmatter else 'sem'} frontmatter"
                    (notas / f"{nome}.md").write_text((CABECALHO if frontmatter else "") + "\n" * quebras + FONTE, encoding="utf-8")
        (notas / "Destino.md").write_text("# Destino\n\nOutra nota.", encoding="utf-8")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta = s.getsockname()[1]
        codigo = ("import uvicorn;from pathlib import Path;from orquestra.hospedeiro import Hospedeiro;"
                  f"uvicorn.run(Hospedeiro(Path({str(vault)!r}),agendar=False),host='127.0.0.1',port={porta},log_level='warning',proxy_headers=False)")
        with (raiz / "servidor.log").open("w", encoding="utf-8") as log:
            processo = subprocess.Popen([sys.executable, "-c", codigo], stdout=log, stderr=log)
            try:
                base = f"http://127.0.0.1:{porta}"
                aguardar_servidor(base, processo)
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path=args.chromium, headless=True)
                    try:
                        resultado = jornadas(browser, base, vault, args.capturas)
                        resultado["fonte_canonica"] = conferir_linhas_iniciais(browser, base, vault)
                        print(json.dumps(resultado, ensure_ascii=False, indent=2))
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
