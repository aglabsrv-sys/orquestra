"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { runInNewContext } = require("node:vm");
const fonte = readFileSync(join(__dirname, "../../src/orquestra/static/js/pastas-vidro.js"), "utf8");

test("Nova nota usa a pasta atual após substituir o painel", () => {
  let secao = null, botao = null;
  const capturas = [];
  const document = { querySelector(s) {
    return s === ".pasta-dentro" ? secao : s === "[data-pasta-nova]" ? botao : null;
  }, querySelectorAll() { return []; }, getElementById() { return null; } };
  const window = { Orquestra: { capturar: dados => capturas.push(dados) } };
  runInNewContext(fonte, { document, window });
  for (const vinculo of ["projetos/itens/Um.md", "estudos/itens/Dois.md"]) {
    const eventos = {};
    secao = { dataset: { vinculo, titulo: vinculo } };
    botao = { addEventListener: (nome, cb) => { eventos[nome] = cb; } };
    window.Orquestra.prepararPastasModulo();
    let duplicados = 0;
    botao.addEventListener = () => { duplicados++; };
    window.Orquestra.prepararPastasModulo();
    assert.equal(duplicados, 0, "preservar o cabeçalho não deve duplicar ações");
    eventos.click();
    assert.equal(capturas.at(-1).vinculo, vinculo);
  }
  assert.equal(capturas.length, 2);
});

test("trocar de visão desconecta observadores da grade anterior", () => {
  const observadores = [];
  class Observador {
    constructor() { this.desconectado = false; observadores.push(this); }
    disconnect() { this.desconectado = true; }
  }
  let raiz = { querySelectorAll: () => [] };
  const document = { querySelector: () => null, querySelectorAll: s => s === ".pastas-vidro" && raiz ? [raiz] : [] };
  const window = { IntersectionObserver: Observador };
  runInNewContext(fonte, { document, window, ResizeObserver: Observador,
    IntersectionObserver: Observador, getComputedStyle: () => ({ getPropertyValue: () => "" }) });
  assert.equal(observadores.length, 2);
  raiz = null;
  window.Orquestra.prepararPastasModulo();
  assert.ok(observadores.every(o => o.desconectado));
});
