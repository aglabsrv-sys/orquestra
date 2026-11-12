"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { runInNewContext } = require("node:vm");
const fonte = readFileSync(join(__dirname, "../../src/orquestra/static/js/app.js"), "utf8");
const tick = () => new Promise(resolve => setImmediate(resolve));

function pagina(responder) {
  const eventos = {}, janelas = {}, fontes = [], pedidos = [], avisos = [], tarefas = new Map();
  let agora = 0, contador = 0, recargas = 0;
  const estado = { hidden: true, textContent: "" };
  const selo = { textContent: "", hidden: true };
  const item = { dataset: { seloDe: 'Pasta com "aspas"' }, querySelector: () => selo };
  const document = {
    body: { dataset: { vaultId: "vault-a", observa: "tudo" } }, activeElement: null,
    querySelector: s => s === "#estado-conexao" ? estado : null,
    querySelectorAll: s => s === "[data-selo-de]" ? [item] : [],
    addEventListener: (nome, cb) => { eventos[nome] = cb; }
  };
  class EventSource {
    constructor() { fontes.push(this); this.fechada = false; }
    close() { this.fechada = true; }
  }
  const window = {
    EventSource,
    addEventListener(nome, cb) { (janelas[nome] ||= []).push(cb); },
    OrquestraInterface: { avisar: (...args) => avisos.push(args) }
  };
  const fetch = async url => {
    pedidos.push(url);
    return responder ? responder(url) : { ok: true, json: async () => ({ vault_id: "vault-a", selos: { 'Pasta com "aspas"': 3 } }) };
  };
  const setTimeout = (cb, prazo) => { const id = ++contador; tarefas.set(id, { cb, quando: agora + prazo }); return id; };
  async function avancar(ms) {
    const ate = agora + ms;
    while (true) {
      const proxima = [...tarefas].filter(([, t]) => t.quando <= ate).sort((a, b) => a[1].quando - b[1].quando)[0];
      if (!proxima) break;
      agora = proxima[1].quando; tarefas.delete(proxima[0]); proxima[1].cb(); await tick();
    }
    agora = ate; await tick();
  }
  runInNewContext(fonte, { document, window, EventSource, fetch, setTimeout, clearTimeout: id => tarefas.delete(id), location: { reload() { recargas++; } } });
  eventos.DOMContentLoaded();
  return { estado, selo, document, fontes, pedidos, avisos, avancar, janelas, get recargas() { return recargas; } };
}

test("rajada de 100 eventos agrupa a consulta de resumo e aceita nomes com aspas", async () => {
  const p = pagina(); p.fontes[0].onopen(); await p.avancar(180);
  for (let i = 0; i < 100; i++) p.fontes[0].onmessage({ data: JSON.stringify({ tipo: "nota", rel: "Nota " + i }) });
  await p.avancar(530);
  assert.equal(p.pedidos.length, 2); assert.equal(p.selo.textContent, 3); assert.equal(p.selo.hidden, false);
});

test("reconexão ressincroniza inclusive depois de falha na primeira abertura", async () => {
  for (const abriuAntes of [false, true]) {
    const p = pagina();
    if (abriuAntes) { p.fontes[0].onopen(); await p.avancar(180); }
    p.fontes[0].onerror(); assert.equal(p.estado.hidden, false);
    assert.match(p.estado.textContent, /Reconectando/);
    p.fontes[0].onopen(); await p.avancar(450);
    assert.equal(p.estado.hidden, true); assert.equal(p.recargas, 1);
  }
});

test("reconexão durante digitação oferece atualizar sem recarregar a tela", async () => {
  const p = pagina(); p.fontes[0].onopen(); await p.avancar(180);
  p.document.activeElement = { tagName: "INPUT" };
  p.fontes[0].onerror(); p.fontes[0].onopen(); await p.avancar(450);
  assert.equal(p.recargas, 0); assert.equal(p.avisos.length, 1);
  assert.equal(p.avisos[0][2].rotulo, "Atualizar");
});

test("resumo de outro vault não troca os contadores da aba antiga", async () => {
  const p = pagina(async () => ({ ok: true, json: async () => ({ vault_id: "vault-b", selos: { 'Pasta com "aspas"': 99 } }) }));
  p.fontes[0].onopen(); await p.avancar(700);
  assert.equal(p.selo.textContent, ""); assert.equal(p.recargas, 1);
});

test("consultas lentas não se sobrepõem e repetem apenas uma vez ao terminar", async () => {
  let concluir;
  const p = pagina(() => new Promise(resolve => { concluir = resolve; }));
  p.fontes[0].onopen(); await p.avancar(180);
  for (let i = 0; i < 5; i++) p.fontes[0].onmessage({ data: '{"tipo":"nota"}' });
  await p.avancar(530); assert.equal(p.pedidos.length, 1);
  concluir({ ok: true, json: async () => ({ vault_id: "vault-a", selos: {} }) });
  await tick(); await p.avancar(180); assert.equal(p.pedidos.length, 2);
});

test("voltar pelo cache do navegador reabre um único stream e remove a conexão anterior", async () => {
  const p = pagina();
  for (let i = 0; i < 3; i++) {
    p.janelas.pagehide.forEach(cb => cb({})); assert.equal(p.fontes.at(-1).fechada, true);
    p.janelas.pageshow.forEach(cb => cb({ persisted: true }));
  }
  assert.equal(p.fontes.length, 4); assert.equal(p.janelas.pageshow.length, 1);
});
