"""Jornadas reais no Chromium, sempre em vault e configuração descartáveis.

uv run --frozen --group browser python scripts/verificar_interface.py
Acrescente --chromium /usr/bin/chromium para usar um navegador já instalado;
--capturas PASTA salva imagens demonstrativas das telas verificadas.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def aguardar_servidor(url: str, processo: subprocess.Popen) -> None:
    prazo = time.monotonic() + 20
    while time.monotonic() < prazo:
        if processo.poll() is not None:
            raise RuntimeError("O servidor de teste encerrou antes de abrir a interface.")
        try:
            with urllib.request.urlopen(url, timeout=1) as resposta:
                if resposta.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("O servidor de teste não respondeu em 20 segundos.")


def conferir_layout(page) -> None:
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Página com rolagem horizontal"
    dock = page.locator(".dock")
    if dock.count():
        assert dock.locator(".dock-item").evaluate_all("els => els.every(e => { const r=e.getBoundingClientRect(); return !r.width || (r.left>=0 && r.right<=innerWidth && r.bottom<=innerHeight); })"), "Navegação esconde destinos"
        caminho = urlsplit(page.url).path
        opcional = caminho == "/m/habitos" and not dock.locator('a[href="/m/habitos"]').count()
        assert page.locator('.dock [aria-current="page"], #abrir-gaveta.ativo-mobile, #abrir-foco[aria-current="page"]').count() or caminho == "/buscar" or opcional, page.url
    novo = page.locator("#abrir-novo")
    if novo.count():
        assert novo.evaluate("e => { const r=e.getBoundingClientRect(); return r.left>=0 && r.right<=innerWidth; }")


def aguardar_vigia(page, vault: Path) -> None:
    """Confirma um ciclo real do polling, além de abrir a conexão SSE.

    O Linux pode criar/editar a nota pela API e apagá-la antes de o primeiro
    snapshot vê-la. O marcador na raiz não afeta a página do módulo em teste.
    """
    page.wait_for_function("window.__fonteAoVivo && window.__fonteAoVivo.readyState===1")
    marcador = vault / f"Sonda do monitor {time.monotonic_ns()}.md"
    marcador.write_text("Arquivo sintético para sincronizar a observação.\n", encoding="utf-8")
    for acao in ("criado", "removido"):
        page.wait_for_function(
            "([rel, acao]) => window.__eventos.some(e => e.rel===rel && e.acao===acao)",
            arg=[marcador.name, acao], timeout=8000,
        )
        if acao == "criado":
            marcador.unlink()


def jornadas(browser, base: str, raiz: Path, capturas: Path | None) -> dict:
    contexto = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    contexto.set_default_timeout(8000)
    # Contar chamadas reais de RAF permite detectar animação ociosa no modo reduzido.
    contexto.add_init_script("""window.__quadros=0; window.__eventos=[];
      const raf=window.requestAnimationFrame.bind(window);
      window.requestAnimationFrame=cb=>{window.__quadros++;return raf(cb);};
      const Fonte=window.EventSource;
      window.EventSource=class extends Fonte {
        constructor(...args) {
          super(...args); window.__fonteAoVivo=this;
          this.addEventListener('message', e => window.__eventos.push(JSON.parse(e.data)));
        }
      };""")
    page = contexto.new_page()
    erros = []
    page.on("pageerror", lambda erro: erros.append(str(erro)))
    page.goto(base, wait_until="domcontentloaded")
    expect(page.locator("#boas-vindas")).to_be_visible()
    page.locator('[data-modo="novo"]').click()
    vault = raiz / "Vault de demonstração"
    page.locator("#caminho-novo").fill(str(vault))
    page.locator("#bv-proximo").click()
    page.locator('.bv-perfil:has(input[value="criador"])').click()
    page.locator("#exemplos").check()
    assert page.locator(".bv-perfil").count() == 3
    page.locator("#bv-proximo").click()
    capa_inicial = page.locator('.bv-capa canvas').get_attribute('data-paleta')
    page.locator('.bv-tema:has(input[value="mare"])').click()
    assert page.locator('.bv-capa canvas').get_attribute('data-paleta') != capa_inicial
    for _ in range(8):
        if page.locator("#concluir").is_visible():
            break
        page.locator("#bv-proximo").click()
    if page.locator("#backup").is_checked():
        page.locator("label:has(#backup)").click()
    page.locator("#concluir").click()
    page.locator('#passo-pronto a[href="/"]').click(timeout=20000)
    page.wait_for_url(base + "/", timeout=20000)
    expect(page.locator(".carrossel")).to_be_visible()

    # A capa é a mesma instância ao alternar visões; o histórico continua navegável.
    page.goto(base + "/m/tarefas", wait_until="domcontentloaded")
    page.evaluate("window.__capaPersistente=document.querySelector('.cab-modulo canvas')")
    page.locator('.abas a[href="?aba=v1"]').click()
    expect(page.locator('.tabela-envolta')).to_be_visible()
    assert page.evaluate("window.__capaPersistente===document.querySelector('.cab-modulo canvas')")
    page.go_back()
    expect(page.locator('.quadro')).to_be_visible()
    assert page.evaluate("window.__capaPersistente===document.querySelector('.cab-modulo canvas')")

    page.goto(base + "/pastas", wait_until="domcontentloaded")
    page.locator('#arvore-pastas a[data-pasta="tarefas"]').click()
    expect(page.locator('#pasta-painel')).to_have_attribute('data-rel', 'tarefas')
    page.locator('[data-pasta-visao="grafo"]').click()
    expect(page.locator('#grafo-estado')).to_contain_text('notas')

    page.goto(base + "/ajustes/variaveis", wait_until="domcontentloaded")
    page.locator('#variavel-adicionar').click()
    page.locator('#variavel-nome').fill('DEMONSTRACAO_API_KEY')
    page.locator('#variavel-valor').fill('valor-ficticio-sem-acesso-externo')
    page.locator('#variaveis-form button[type="submit"]').click()
    expect(page.locator('#variaveis-lista')).to_contain_text('DEMONSTRACAO_API_KEY')
    assert 'valor-ficticio-sem-acesso-externo' not in page.content()

    page.goto(base + "/ajustes/areas", wait_until="domcontentloaded")
    primeira = page.locator('.area-linha').first.get_attribute('data-modulo')
    with page.expect_response(lambda r: r.url.endswith('/api/config') and r.request.method == 'POST') as reordenacao:
        page.locator('.area-linha').first.locator('[data-mover="1"]').click()
    assert reordenacao.value.status == 200
    page.reload(wait_until="domcontentloaded")
    assert page.locator('.area-linha').nth(1).get_attribute('data-modulo') == primeira

    rotas = ("/", "/m/tarefas", "/m/tarefas?aba=v1", "/m/tarefas?aba=humano", "/m/tarefas?aba=maquina",
             "/m/conteudo", "/m/numeros", "/m/radar", "/m/entrada", "/ajustes", "/m/tarefas/personalizar",
             "/buscar?q=vídeo", "/pastas", "/decidir", "/diario", "/agenda", "/agenda?visao=semana",
             "/agenda?visao=dia", "/agenda?visao=lista", "/foco", "/m/habitos",
             *["/ajustes/" + s for s in ("painel", "areas", "aparencia", "backup", "coletores", "acesso", "vault", "variaveis")])
    for largura in (1440, 390, 320):
        page.set_viewport_size({"width": largura, "height": 900})
        for rota in rotas:
            resposta = page.goto(base + rota, wait_until="domcontentloaded")
            assert resposta.status == 200, rota
            conferir_layout(page)
            if capturas and largura != 320 and rota in ("/", "/m/tarefas", "/m/conteudo", "/ajustes"):
                page.wait_for_timeout(220)
                nome = {"/": "inicio", "/m/tarefas": "tarefas", "/m/conteudo": "conteudo", "/ajustes": "ajustes"}[rota]
                page.screenshot(path=str(capturas / f"{nome}{'-mobile' if largura == 390 else ''}.png"), full_page=True)
        page.goto(base + "/m/tarefas", wait_until="domcontentloaded")
        if largura < 700:
            page.locator("#abrir-gaveta").click()
            expect(page.locator('#gaveta a[href="/ajustes"]')).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.locator("#abrir-gaveta")).to_be_focused()
        page.locator("#abrir-novo").click()
        titulo = f"Teste de jornada {largura}"
        page.locator("#novo-titulo").fill(titulo)
        page.locator("#novo-corpo").fill("Texto original da demonstração.")
        with page.expect_response(lambda r: r.url.endswith("/api/notas") and r.request.method == "POST") as envio:
            page.locator("#novo-salvar").click()
        assert envio.value.status == 200
        link = page.get_by_role("link", name=titulo, exact=True)
        expect(link).to_be_visible()
        url = link.get_attribute("href")
        page.goto(base + url, wait_until="domcontentloaded")
        nota = {"url": url, "rel": page.locator(".nota").get_attribute("data-rel")}
        page.locator("#ver").dblclick()
        page.locator("#editor").fill("Texto revisado pelo navegador.")
        with page.expect_response(lambda r: "/api/notas/" in r.url and r.request.method == "PUT") as envio:
            page.locator("#editor").press("Escape")
        assert envio.value.status == 200
        expect(page.locator("#editor")).to_be_hidden()
        expect(page.locator("#ver")).to_contain_text("Texto revisado pelo navegador.")
        assert "Texto revisado" in (vault / nota["rel"]).read_text(encoding="utf-8")
        page.locator("#nota-propriedades > summary").click()
        page.locator("#consultar-versoes").click()
        expect(page.locator("#versoes-conteudo")).to_be_visible()
        expect(page.locator("#versao-texto")).to_have_value(re.compile("Texto original"))
        if largura != 320:
            # Prints da próxima largura usam apenas as demonstrações do catálogo.
            page.goto(base + "/m/tarefas?aba=v1", wait_until="domcontentloaded")
            aguardar_vigia(page, vault)
            (vault / nota["rel"]).unlink()
            expect(page.get_by_role("button", name="Atualizar", exact=True)).to_be_visible(timeout=8000)
            page.get_by_role("button", name="Atualizar", exact=True).click()
            expect(page.get_by_role("link", name=titulo, exact=True)).not_to_be_visible(timeout=8000)

    # Conflito real com edição externa: conservar rascunho e recuperar como cópia.
    page.locator("#editar").click()
    page.locator("#editor").fill("Meu rascunho ainda não salvo.")
    arquivo = vault / nota["rel"]
    aguardar_vigia(page, vault)
    arquivo.write_text(arquivo.read_text(encoding="utf-8") + "\nAlteração externa.\n", encoding="utf-8")
    expect(page.locator("#faixa-conflito")).to_be_visible(timeout=8000)
    with page.expect_response(lambda r: "/api/notas/" in r.url and r.request.method == "PUT") as conflito:
        page.locator("#salvar").click()
    assert conflito.value.status == 409
    expect(page.locator("#editor")).to_have_value("Meu rascunho ainda não salvo.")
    url_original = page.url
    with page.expect_response(lambda r: "/api/notas/copia/" in r.url) as copia:
        page.locator("#salvar-copia").click()
    assert copia.value.status == 200
    expect(page).not_to_have_url(url_original)
    expect(page.locator(".nota")).to_be_visible()
    rel_copia = page.locator(".nota").get_attribute("data-rel")
    assert "Meu rascunho" in (vault / rel_copia).read_text(encoding="utf-8")
    assert "Alteração externa." in arquivo.read_text(encoding="utf-8")

    # Formulário deixa de ter foco, mas continua protegido contra eventos do watcher.
    page.goto(base + "/m/tarefas/personalizar", wait_until="domcontentloaded")
    page.locator("#p-descricao").fill("Descrição pendente")
    page.locator("h1").click()
    schema = vault / "tarefas/_modulo.yaml"
    aguardar_vigia(page, vault)
    schema.write_text(schema.read_text(encoding="utf-8") + "\n# Alteração externa para testar atualização ao vivo.\n", encoding="utf-8")
    expect(page.locator("#p-novidades")).to_be_visible(timeout=8000)
    expect(page.locator("#p-descricao")).to_have_value("Descrição pendente")
    expect(page.locator("#p-estado")).to_contain_text("Há alterações")
    with page.expect_response(lambda r: r.url.endswith("/api/modulos/tarefas") and r.request.method == "PUT") as personalizacao:
        page.locator("#p-salvar").click()
    assert personalizacao.value.status == 409
    expect(page.locator("#p-descricao")).to_have_value("Descrição pendente")
    assert "Descrição pendente" not in schema.read_text(encoding="utf-8")

    # Número e decisão usam as mesmas regras do domínio, com controles reais.
    page.once("dialog", lambda dialogo: dialogo.accept())  # descarte explícito do formulário de teste
    page.goto(base + "/m/numeros", wait_until="domcontentloaded")
    page.locator("#abrir-numeros").click()
    page.locator("[data-numero]").first.fill("123")
    with page.expect_response(lambda r: r.url.endswith("/api/numeros")) as numeros:
        page.locator("#numeros-salvar").click()
    assert numeros.value.status == 200
    expect(page.locator("#dialogo-numeros")).to_be_hidden()
    page.goto(base + "/decidir", wait_until="domcontentloaded")
    with page.expect_response(lambda r: "/api/notas/" in r.url and r.request.method == "PUT") as decisao:
        page.locator("[data-acao]").first.click()
    assert decisao.value.status == 200
    page.goto(base + "/m/tarefas", wait_until="domcontentloaded")

    # Captura pelo teclado e modal com falha de rede: entrada permanece disponível.
    page.locator("h1").click()
    page.keyboard.press("c")
    expect(page.locator("#captura")).to_be_visible()
    page.locator("#captura-texto").fill("Ideia preservada sem conexão")
    page.route("**/api/captura", lambda route: route.abort())
    page.locator("#captura-salvar").click()
    expect(page.locator("#captura")).to_contain_text("Sem conexão")
    expect(page.locator("#captura-texto")).to_have_value("Ideia preservada sem conexão")
    page.unroute("**/api/captura")
    with page.expect_response(lambda r: r.url.endswith("/api/captura")) as captura:
        page.locator("#captura-salvar").click()
    assert captura.value.status == 200
    expect(page.locator("#captura")).to_be_hidden()

    # O limite de cartões não pode virar o total da coluna após mover um item.
    for numero in range(100):
        (vault / "tarefas/itens" / f"Volume {numero:03}.md").write_text("---\nstatus: a_fazer\n---\n", encoding="utf-8")
    page.wait_for_timeout(1700)
    page.goto(base + "/m/tarefas", wait_until="domcontentloaded")
    coluna = page.locator('.coluna[data-valor="a_fazer"]')
    total = int(coluna.locator(".conta").inner_text())
    assert total > 80
    cartao = coluna.locator(".cartao").first
    rel = cartao.get_attribute("data-rel")
    with page.expect_response(lambda r: "/api/notas/" in r.url and r.request.method == "PUT") as movimento:
        cartao.locator(".mudar-status").select_option("fazendo")
    assert movimento.value.status == 200
    expect(page.locator(f'.cartao[data-rel="{rel}"] .mudar-status')).to_be_enabled()
    assert int(coluna.locator(".conta").inner_text()) == total - 1

    # Agenda: validação, falha recuperável, escrita Markdown e edição no mesmo fluxo.
    page.goto(base + "/agenda?visao=lista", wait_until="domcontentloaded")
    page.locator(".cal-acoes [data-cal-novo]").click()
    if page.locator("#cal-dia-inteiro").is_checked():
        page.locator("label:has(#cal-dia-inteiro)").click()
    dia = page.locator("#cal-inicio").input_value()[:10]
    page.locator("#cal-titulo").fill("Encontro da comunidade")
    page.locator("#cal-inicio").fill(dia + "T14:00")
    page.locator("#cal-fim").fill(dia + "T13:00")
    page.locator("#cal-salvar").click()
    expect(page.locator("#cal-editor-estado")).to_contain_text("posterior")
    page.locator("#cal-fim").fill(dia + "T15:00")
    page.route("**/api/agenda/eventos", lambda route: route.abort())
    page.locator("#cal-salvar").click()
    expect(page.locator("#cal-editor-estado")).to_contain_text("Sem conexão")
    expect(page.locator("#cal-titulo")).to_have_value("Encontro da comunidade")
    page.unroute("**/api/agenda/eventos")
    with page.expect_response(lambda r: r.url.endswith("/api/agenda/eventos")) as evento:
        page.locator("#cal-salvar").click()
    assert evento.value.status == 200
    rel_evento = evento.value.json()["rel"]
    assert "Encontro da comunidade" in (vault / rel_evento).name
    assert "14:00" in (vault / rel_evento).read_text(encoding="utf-8")
    expect(page.locator("#cal-evento-dialogo")).to_be_hidden()
    evento_ui = page.locator("[data-evento]").filter(has_text="Encontro da comunidade")
    evento_ui.click()
    page.locator("#cal-titulo").fill("Encontro revisado")
    with page.expect_response(lambda r: r.url.endswith("/api/agenda/eventos")) as edicao:
        page.locator("#cal-salvar").click()
    assert edicao.value.status == 200
    expect(page.locator("[data-evento]").filter(has_text="Encontro revisado")).to_be_visible()
    assert "Encontro revisado" in (vault / edicao.value.json()["rel"]).read_text(encoding="utf-8")

    # Hábitos: ativação opcional, meta, marcação de hoje e edição preservam registros.
    page.goto(base + "/m/habitos", wait_until="domcontentloaded")
    page.locator(".habitos-cabecalho [data-habito-novo]").click()
    page.locator("#habito-titulo").fill("Ler com a comunidade")
    page.route("**/api/habitos", lambda route: route.abort())
    page.locator("#habito-salvar").click()
    expect(page.locator("#habito-editor-estado")).to_contain_text("Sem conexão")
    expect(page.locator("#habito-titulo")).to_have_value("Ler com a comunidade")
    page.unroute("**/api/habitos")
    with page.expect_response(lambda r: r.url.endswith("/api/habitos")) as habito:
        page.locator("#habito-salvar").click()
    assert habito.value.status == 200
    card = page.locator("[data-habito]").filter(has_text="Ler com a comunidade")
    expect(card).to_be_visible()
    with page.expect_response(lambda r: r.url.endswith("/api/habitos/marcar")) as marcado:
        card.locator("[data-habito-marcar]").click()
    assert marcado.value.status == 200
    expect(card.locator("[data-habito-marcar]")).to_have_attribute("aria-pressed", "true")
    registros = marcado.value.json()["item"]["registros"]
    assert registros and registros[0] in (vault / marcado.value.json()["rel"]).read_text(encoding="utf-8")
    card.locator("[data-habito-editar]").click()
    page.locator("#habito-titulo").fill("Leitura diária")
    with page.expect_response(lambda r: r.url.endswith("/api/habitos")) as habito_editado:
        page.locator("#habito-salvar").click()
    assert habito_editado.value.status == 200
    expect(page.locator("[data-habito]").filter(has_text="Leitura diária")).to_be_visible()
    assert habito_editado.value.json()["item"]["registros"] == registros

    # Pomodoro conserva intenção e prazo ao navegar na mesma sessão.
    page.goto(base + "/foco", wait_until="domcontentloaded")
    page.locator("#foco-tarefa").fill("Revisar o projeto")
    page.locator("#foco-iniciar").click()
    expect(page.locator("#foco-acao")).to_contain_text("Pausar")
    prazo = page.evaluate("JSON.parse(sessionStorage.getItem('orquestra:foco:v2:'+document.body.dataset.vaultId)).fim")
    page.goto(base + "/agenda", wait_until="domcontentloaded")
    page.goto(base + "/foco", wait_until="domcontentloaded")
    expect(page.locator("#foco-tarefa")).to_have_value("Revisar o projeto")
    expect(page.locator("#foco-acao")).to_contain_text("Pausar")
    assert page.evaluate("JSON.parse(sessionStorage.getItem('orquestra:foco:v2:'+document.body.dataset.vaultId)).fim") == prazo
    page.locator("#foco-iniciar").click()

    # Capturas atuais das novas páginas, em dados sintéticos e três larguras.
    if capturas:
        for largura in (1440, 390, 320):
            page.set_viewport_size({"width": largura, "height": 900})
            for nome, rota in (("agenda", "/agenda?visao=lista"), ("habitos", "/m/habitos"), ("foco", "/foco")):
                page.goto(base + rota, wait_until="domcontentloaded")
                conferir_layout(page)
                page.screenshot(path=str(capturas / f"{nome}-{largura}.png"), full_page=True)

    # Modo claro e fonte ampliada também passam pelo formulário e persistem no vault.
    page.goto(base + "/ajustes/aparencia", wait_until="domcontentloaded")
    for chave, valor in (("modo", "claro"), ("tamanho", "grande")):
        botao = page.locator(f'[data-visual="{chave}"][data-valor="{valor}"]')
        with page.expect_response(lambda r: r.url.endswith("/api/config")) as visual:
            botao.click()
        assert visual.value.status == 200
        expect(botao).to_be_enabled()
    for rota in ("/agenda?visao=semana", "/m/habitos", "/foco"):
        page.goto(base + rota, wait_until="domcontentloaded")
        conferir_layout(page)
        assert page.evaluate("getComputedStyle(document.documentElement).fontSize") == "18px"
        if capturas:
            nome = urlsplit(page.url).path.strip("/").replace("/", "-")
            page.screenshot(path=str(capturas / f"{nome}-claro-fonte-grande-320.png"), full_page=True)

    page.goto(base, wait_until="domcontentloaded")
    page.wait_for_timeout(350)
    assert page.locator('.slide[aria-hidden="true"]').evaluate_all("els => els.every(e=>e.tabIndex===-1)")
    assert page.locator(".pontos button").evaluate_all("els => els.every(e=>{ const r=e.getBoundingClientRect(); return r.width>=24 && r.height>=24; })")
    quadros = page.evaluate("window.__quadros")
    page.wait_for_timeout(450)
    assert page.evaluate("window.__quadros") == quadros, "Animação continua em movimento reduzido"
    preparadas = page.locator("canvas[data-cena]").evaluate_all("els=>els.filter(e=>e._cena).length")
    assert preparadas < page.locator("canvas[data-cena]").count(), "Cenas fora da tela foram preparadas antecipadamente"
    page.emulate_media(reduced_motion="no-preference")
    page.wait_for_timeout(550)
    assert page.evaluate("window.__quadros") > quadros, "Animação não retomou após mudar preferência"
    assert page.evaluate("window.__quadros") - quadros < 14, "Animação ociosa acima da cadência"
    page.emulate_media(reduced_motion="reduce")
    page.wait_for_timeout(100)
    quadros = page.evaluate("window.__quadros")
    page.wait_for_timeout(350)
    assert page.evaluate("window.__quadros") == quadros
    assert not erros, erros
    contexto.close()
    return {"rotas_por_largura": len(rotas), "larguras": [1440, 390, 320], "erros_javascript": erros,
            "jornadas": ["primeiro uso", "navegação e gaveta", "criar e editar", "recuperação", "conflito externo e cópia",
                         "personalização pendente", "números", "decisão", "falha e repetição de captura", "contagem do Kanban",
                         "agenda e falha recuperável", "hábitos e preservação de registros", "Pomodoro ao navegar",
                         "modo claro e fonte ampliada", "animação e movimento reduzido"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium")
    parser.add_argument("--capturas", type=Path)
    args = parser.parse_args()
    if args.capturas:
        args.capturas.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="orquestra-browser-") as pasta:
        raiz = Path(pasta)
        ambiente = {**os.environ, "ORQUESTRA_HOME": str(raiz / "home")}
        ambiente.pop("ORQUESTRA_VAULT", None)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta = s.getsockname()[1]
        codigo = ("import uvicorn; from orquestra.hospedeiro import Hospedeiro; "
                  f"uvicorn.run(Hospedeiro(None, agendar=False), host='127.0.0.1', port={porta}, log_level='warning', proxy_headers=False)")
        with (raiz / "servidor.log").open("w", encoding="utf-8") as log:
            processo = subprocess.Popen([sys.executable, "-c", codigo], env=ambiente, stdout=log, stderr=log)
            try:
                base = f"http://127.0.0.1:{porta}"
                aguardar_servidor(base, processo)
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path=args.chromium, headless=True)
                    try:
                        print(json.dumps(jornadas(browser, base, raiz, args.capturas), ensure_ascii=False, indent=2))
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
