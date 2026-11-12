"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const tick = () => new Promise(resolve => setImmediate(resolve));
const codigo = fs.readFileSync(path.join(__dirname, "../../src/orquestra/static/js/boasvindas.js"), "utf8");

// DOM mínimo para exercitar corridas de rede e preservação das escolhas, sem navegador ou vault real.
function tela() {
  class Elemento {
    constructor(tagName = "DIV") {
      this.tagName = tagName.toUpperCase(); this.dataset = {}; this.attributes = {};
      this.value = ""; this.textContent = ""; this.children = []; this.listeners = {};
      this.hidden = false; this.disabled = false; this.checked = false;
    }
    appendChild(item) { this.children.push(item); return item; }
    addEventListener(nome, fn) { (this.listeners[nome] ||= []).push(fn); }
    emitir(nome, dados = {}) { for (const fn of this.listeners[nome] || []) fn(dados); }
    setAttribute(nome, valor) { this.attributes[nome] = valor; }
    removeAttribute(nome) { delete this.attributes[nome]; }
    scrollIntoView() {}
    focus() { document.activeElement = this; }
    querySelector(s) { return buscar(s); }
    querySelectorAll(s) { return buscarTodos(s); }
    contains(e) { return e === this || this.children.includes(e); }
    remove() { this.removido = true; }
  }
  const mapa = {};
  for (const id of codigo.matchAll(/#([\w-]+)/g)) mapa[id[1]] ||= new Elemento();
  for (const id of ["caminho-existente", "caminho-novo", "nome", "exemplos", "backup"]) {
    mapa[id].tagName = "INPUT"; mapa[id].id = id;
    mapa["erro-" + id] = new Elemento("p"); mapa["erro-" + id].hidden = true;
  }
  for (const id of ["analisar", "concluir"]) mapa[id].tagName = "BUTTON";
  mapa.nome.value = "Orquestra";
  mapa["caminho-novo"].value = "/vault-novo";
  mapa.analise.hidden = true; mapa["bloco-comum"].hidden = true; mapa["bv-erro"].hidden = true;
  const existente = new Elemento("button"); existente.dataset.modo = "existente";
  const novo = new Elemento("button"); novo.dataset.modo = "novo";
  const voltar = new Elemento("button");
  const procurar = new Elemento("button"); procurar.dataset.procurar = "caminho-novo";
  const perfil = new Elemento("input"); perfil.dataset.modulos = "";
  const tema = new Elemento("input"); tema.value = "noturno";
  const etapas = [1, 2, 3].map(n => { const e = new Elemento("li"); e.dataset.etapa = String(n); return e; });
  function buscar(s) {
    if (s.startsWith("#")) return mapa[s.slice(1)] || null;
    if (s === 'input[name="perfil"]:checked') return perfil;
    if (s === 'input[name="tema"]:checked') return tema;
    return null;
  }
  function buscarTodos(s) {
    if (s === "[data-modo]") return [existente, novo];
    if (s === "[data-recomecar]") return [voltar];
    if (s === "[data-procurar]") return [procurar];
    if (s === "[data-etapa]") return etapas;
    if (s === 'input[name="perfil"]') return [perfil];
    if (s === 'input[name="tema"]') return [tema];
    if (s === "input, select, button") return [...Object.values(mapa).filter(e => /^(INPUT|BUTTON|SELECT)$/.test(e.tagName)), existente, novo, voltar, procurar];
    return [];
  }
  const document = {
    querySelector: buscar, querySelectorAll: buscarTodos,
    createElement: tag => new Elemento(tag), createTextNode: texto => ({ textContent: texto })
  };
  const requisicoes = [];
  const contexto = {
    document, window: { matchMedia: () => ({ matches: true }), scrollTo() {} },
    location: { href: "" }, CSS: { escape: x => x },
    requestAnimationFrame: fn => fn(), setTimeout() {},
    fetch: (url, opcoes) => {
      if (url === "/api/local/capacidade") return Promise.resolve({ ok: true, json: async () => ({ token: "capacidade-local" }) });
      return new Promise((resolve, reject) => requisicoes.push({ url, opcoes, resolve: dados => resolve({ ok: true, json: async () => dados }), reject }));
    }
  };
  vm.runInNewContext(codigo, contexto);
  return { mapa, existente, novo, voltar, procurar, requisicoes, document, contexto };
}

test("informa caminho ausente junto ao campo, sem fazer requisição", () => {
  const t = tela(); t.existente.onclick(); t.mapa.analisar.onclick();
  assert.equal(t.mapa["caminho-existente"].attributes["aria-invalid"], "true");
  assert.equal(t.mapa["erro-caminho-existente"].hidden, false);
  assert.equal(t.document.activeElement, t.mapa["caminho-existente"]);
  assert.equal(t.requisicoes.length, 0);
});

test("descarta análise atrasada depois que a pessoa troca o caminho", async () => {
  const t = tela(); t.existente.onclick();
  t.mapa["caminho-existente"].value = "/primeiro"; t.mapa.analisar.onclick(); await tick();
  assert.equal(t.requisicoes.length, 1);
  t.mapa["caminho-existente"].value = "/segundo"; t.mapa["caminho-existente"].emitir("input");
  t.requisicoes[0].resolve({ existe: true, caminho: "/primeiro", nome: "Primeiro", notas: 0, pastas: [], modulos: [] }); await tick();
  assert.equal(t.mapa["caminho-existente"].value, "/segundo");
  assert.equal(t.mapa.analise.hidden, true);
  assert.equal(t.mapa["bloco-comum"].hidden, true);
  assert.equal(t.mapa.analisar.disabled, false);
});

test("falha de análise antiga não aparece no modo de criar outro vault", async () => {
  const t = tela(); t.existente.onclick();
  t.mapa["caminho-existente"].value = "/primeiro"; t.mapa.analisar.onclick(); await tick();
  t.novo.onclick(); t.requisicoes[0].reject(new Error("Falha antiga")); await tick();
  assert.equal(t.mapa["bv-erro"].hidden, true);
  assert.equal(t.mapa["bloco-novo"].hidden, false);
});

test("valida nome em branco e conserva as escolhas ao falhar a preparação", async () => {
  const t = tela(); t.novo.onclick(); t.mapa.nome.value = "  "; t.mapa.concluir.onclick();
  assert.equal(t.mapa.nome.attributes["aria-invalid"], "true");
  assert.equal(t.requisicoes.length, 0);
  t.mapa.nome.value = "Meu painel"; t.mapa.nome.emitir("input"); t.mapa.concluir.onclick(); await tick();
  assert.equal(t.mapa["boas-vindas"].attributes["aria-busy"], "true");
  assert.equal(t.mapa["caminho-novo"].disabled, true);
  t.mapa.concluir.onclick(); await tick(); assert.equal(t.requisicoes.length, 1);
  t.requisicoes[0].reject(new Error("Pasta sem permissão")); await tick();
  assert.equal(t.mapa["caminho-novo"].disabled, false);
  assert.equal(t.mapa["caminho-novo"].value, "/vault-novo");
  assert.equal(t.mapa.nome.value, "Meu painel");
  assert.equal(t.mapa["bv-erro"].textContent, "Pasta sem permissão");
  assert.equal(t.mapa["bv-erro"].hidden, false);
});

test("seletor de pasta atrasado não sobrescreve um caminho digitado depois", async () => {
  const t = tela(); t.novo.onclick(); t.procurar.onclick(); await tick();
  t.mapa["caminho-novo"].value = "/minha-escolha";
  t.requisicoes[0].resolve({ caminho: "/escolha-antiga" }); await tick();
  assert.equal(t.mapa["caminho-novo"].value, "/minha-escolha");
});
