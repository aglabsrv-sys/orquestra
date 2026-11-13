"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const criarInterface = require("../../src/orquestra/static/js/interface.js");

// DOM mínimo de teste: exercita os eventos públicos e os tempos de interação.
function preparar() {
  let agora = 0, numero = 0;
  const timers = new Map();
  class Elemento {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.eventos = {}; this.className = ""; this.textContent = ""; this.disabled = false; }
    get isConnected() { return this === doc.body || !!this.parentNode?.isConnected; }
    appendChild(el) { el.remove(); this.children.push(el); el.parentNode = this; return el; }
    remove() { if (this.parentNode) this.parentNode.children.splice(this.parentNode.children.indexOf(this), 1); this.parentNode = null; }
    setAttribute(k, v) { this.attributes[k] = String(v); }
    removeAttribute(k) { delete this.attributes[k]; }
    getAttribute(k) { return this.attributes[k] ?? null; }
    addEventListener(tipo, cb) { (this.eventos[tipo] ||= []).push(cb); }
    evento(tipo, dados = {}) { for (const cb of this.eventos[tipo] || []) cb({ target: this, ...dados }); }
    click() { if (!this.disabled) this.evento("click"); }
    focus() { doc.activeElement = this; }
    scrollIntoView(opcoes) { (this.rolagens ||= []).push(opcoes); }
    contains(el) { return el === this || this.children.some(c => c.contains(el)); }
    querySelectorAll(seletor) {
      const combina = el => seletor === "dialog[open]" ? el.tagName === "DIALOG" && el.open : seletor.startsWith("#") ? el.id === seletor.slice(1) : seletor.startsWith(".") ? el.className.split(" ").includes(seletor.slice(1)) : el.tagName === seletor.toUpperCase();
      return this.children.flatMap(c => [...(combina(c) ? [c] : []), ...c.querySelectorAll(seletor)]);
    }
    querySelector(s) { return this.querySelectorAll(s)[0] || null; }
    showModal() { this.open = true; }
    close() { this.open = false; this.evento("close"); }
  }
  const doc = { createElement: tag => new Elemento(tag), querySelector: s => doc.body.querySelector(s), querySelectorAll: s => doc.body.querySelectorAll(s), activeElement: null };
  doc.body = new Elemento("body");
  const caixa = new Elemento("div"); caixa.id = "avisos"; doc.body.appendChild(caixa);
  const ambiente = { setTimeout: (cb, atraso) => { const id = ++numero; timers.set(id, { cb, quando: agora + atraso }); return id; }, clearTimeout: id => timers.delete(id), performance: { now: () => agora } };
  function avancar(ms) { agora += ms; for (const [id, timer] of [...timers]) if (timer.quando <= agora) { timers.delete(id); timer.cb(); } }
  return { doc, caixa, avancar, timers, api: criarInterface(doc, ambiente), Elemento };
}

test("erro persiste até fechar; texto externo é inserido sem interpretação HTML", () => {
  const { api, caixa, avancar } = preparar();
  api.avisar('<img src=x onerror="roubar()">', "erro");
  const aviso = caixa.children[0];
  assert.equal(aviso.getAttribute("role"), "alert");
  assert.equal(aviso.getAttribute("aria-live"), "assertive");
  assert.equal(aviso.querySelector("p").textContent, '<img src=x onerror="roubar()">');
  assert.equal(aviso.querySelector("img"), null);
  avancar(120000);
  assert.equal(caixa.children.length, 1);
  aviso.querySelector("button").click();
  assert.equal(caixa.children.length, 0);
});

test("sucesso Pronto aparece uma vez e mensagens de erro mantêm seu conteúdo", () => {
  const { api, caixa } = preparar();
  api.avisar("Pronto");
  const sucesso = caixa.children[0];
  assert.equal(sucesso.querySelector("strong").textContent, "Pronto");
  assert.equal(sucesso.querySelector("p"), null);
  api.avisar("Não foi possível concluir", "erro");
  assert.equal(caixa.children[1].querySelector("p").textContent, "Não foi possível concluir");
});

test("aviso temporário pausa no ponteiro e no teclado, retomando só depois de ambos saírem", () => {
  const { api, caixa, avancar } = preparar();
  api.avisar("Salvo"); const aviso = caixa.children[0];
  assert.equal(aviso.getAttribute("aria-live"), "polite");
  avancar(2000); aviso.evento("mouseenter"); aviso.evento("focusin");
  avancar(30000); aviso.evento("mouseleave"); avancar(30000);
  assert.equal(caixa.children.length, 1);
  aviso.evento("focusout", { relatedTarget: null });
  avancar(3999); assert.equal(caixa.children.length, 1);
  avancar(1); assert.equal(caixa.children.length, 0);
});

test("repetir a mesma falha não cria uma pilha de anúncios", () => {
  const { api, caixa } = preparar();
  api.avisar("Sem conexão", "erro"); api.avisar("Sem conexão", "erro");
  assert.equal(caixa.children.length, 1);
});

test("falha em modal longo é revelada ao mover e repetir o aviso sem roubar o foco", () => {
  const { api, doc, caixa, Elemento } = preparar();
  api.avisar("Sem conexão", "erro");
  const modal = new Elemento("dialog"), campo = new Elemento("input");
  modal.appendChild(campo); doc.body.appendChild(modal); modal.showModal(); campo.focus();
  api.avisar("Sem conexão", "erro");
  assert.equal(caixa.children.length, 0);
  assert.equal(modal.querySelectorAll(".aviso").length, 1);
  const aviso = modal.querySelector(".aviso");
  assert.deepEqual(aviso.rolagens, [{ block: "nearest", behavior: "auto" }]);
  assert.equal(doc.activeElement, campo);
  api.avisar("Sem conexão", "erro");
  assert.equal(aviso.rolagens.length, 2);
  assert.equal(doc.activeElement, campo);
  api.avisar("Outra falha", "erro");
  const outro = modal.querySelectorAll(".aviso")[1];
  assert.equal(outro.rolagens.length, 1);
  assert.equal(doc.activeElement, campo);
  const fechar = aviso.querySelector("button"); fechar.focus(); fechar.click();
  assert.equal(doc.activeElement, campo);
});

test("fechar pelo teclado devolve foco ao controle de origem; remoção externa não rouba foco", () => {
  const { api, doc, Elemento } = preparar();
  const salvar = new Elemento("button"), outro = new Elemento("input");
  doc.body.appendChild(salvar); doc.body.appendChild(outro); salvar.focus();
  api.avisar("Sem conexão", "erro");
  const aviso = doc.querySelector(".aviso"), botao = aviso.querySelector("button");
  botao.focus(); botao.click(); assert.equal(doc.activeElement, salvar);
  const fecharOutro = api.avisar("Outra falha", "erro"); outro.focus(); fecharOutro();
  assert.equal(doc.activeElement, outro);
});

test("confirmação dá foco ao cancelamento e Escape resolve false restaurando o acionador", async () => {
  const { api, doc, Elemento } = preparar();
  const acionador = new Elemento("button"); doc.body.appendChild(acionador); acionador.focus();
  const pedido = api.confirmar({ titulo: "Descartar?", texto: "O rascunho será removido.", perigoso: true, confirmar: "Descartar" });
  const dialogo = doc.querySelector("dialog[open]");
  assert.equal(doc.activeElement.textContent, "Cancelar");
  assert.ok(dialogo.getAttribute("aria-labelledby"));
  assert.ok(dialogo.getAttribute("aria-describedby"));
  dialogo.evento("cancel"); dialogo.close();
  assert.equal(await pedido, false);
  assert.equal(doc.activeElement, acionador);
  assert.equal(doc.querySelector("dialog"), null);
});

test("confirmações concorrentes ficam em fila e só a escolha explícita resolve true", async () => {
  const { api, doc } = preparar();
  const um = api.confirmar({ titulo: "Primeira", confirmar: "Executar" });
  const dois = api.confirmar({ titulo: "Segunda", confirmar: "Guardar" });
  assert.equal(doc.querySelectorAll("dialog[open]").length, 1);
  doc.querySelector("dialog").querySelectorAll("button")[1].click();
  assert.equal(await um, true);
  assert.equal(doc.querySelector("h2").textContent, "Segunda");
  doc.querySelector("dialog").querySelectorAll("button")[0].click();
  assert.equal(await dois, false);
});

test("confirmação pode abrir sobre outro modal e devolve o foco a ele", async () => {
  const { api, doc, Elemento } = preparar();
  const anterior = new Elemento("dialog"), botao = new Elemento("button");
  anterior.appendChild(botao); doc.body.appendChild(anterior); anterior.showModal(); botao.focus();
  const pedido = api.confirmar({ titulo: "Confirmar" });
  const dialogos = doc.querySelectorAll("dialog[open]"); assert.equal(dialogos.length, 2);
  dialogos[1].querySelectorAll("button")[0].click();
  assert.equal(await pedido, false); assert.equal(anterior.open, true); assert.equal(doc.activeElement, botao);
});

test("ação de aviso é protegida contra duplo clique e uma falha fica visível", async () => {
  const { api, caixa, avancar } = preparar(); let tentativas = 0;
  api.avisar("Há novidades", "info", { rotulo: "Atualizar", fazer: async () => { tentativas++; throw new Error("Sem conexão"); } });
  avancar(60000); const aviso = caixa.children[0], botao = aviso.querySelectorAll("button")[0];
  botao.click(); botao.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(tentativas, 1); assert.equal(botao.disabled, false);
  assert.equal(caixa.children.length, 2);
  assert.equal(caixa.children[1].querySelector("p").textContent, "Sem conexão");
});

test("estado ocupado preserva o rótulo e restaura permissão anterior do botão", () => {
  const { api, Elemento } = preparar(); const botao = new Elemento("button"); botao.textContent = "Salvar";
  const concluir = api.ocupado(botao, "Salvando…");
  assert.equal(botao.disabled, true); assert.equal(botao.getAttribute("aria-busy"), "true");
  assert.equal(botao.textContent, "Salvando…"); concluir();
  assert.equal(botao.disabled, false); assert.equal(botao.textContent, "Salvar"); assert.equal(botao.getAttribute("aria-busy"), null);
});

test("erros de HTTP desconhecidos têm mensagem útil e erros do servidor são preservados", () => {
  const { api } = preparar();
  assert.match(api.mensagemErro(null, 409), /mudou/);
  assert.match(api.mensagemErro(null, 422), /campos/);
  assert.match(api.mensagemErro(null, 500), /Tente novamente/);
  assert.equal(api.mensagemErro(new Error("Disco cheio"), 503), "Disco cheio");
});
