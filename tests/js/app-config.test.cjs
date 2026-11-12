"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { runInNewContext } = require("node:vm");
const fonte = readFileSync(join(__dirname, "../../src/orquestra/static/js/app.js"), "utf8");
const tick = () => new Promise(resolve => setImmediate(resolve));

function paginaConfig(responder) {
  const eventos = {}, pedidos = [], avisos = [];
  let recargas = 0;
  function campo(value = "") {
    const ouvintes = {}, atributos = {}, classes = new Set();
    return {
      value, disabled: false, hidden: true, textContent: "", validationMessage: "",
      checkValidity() { return this.value.length <= 60; },
      setAttribute: (nome, valor) => { atributos[nome] = valor; },
      getAttribute: nome => atributos[nome],
      addEventListener: (nome, cb) => { ouvintes[nome] = cb; },
      mudar() { ouvintes.change({ target: this }); },
      classList: { add: nome => classes.add(nome), remove: nome => classes.delete(nome), contains: nome => classes.has(nome) }
    };
  }
  const nome = campo("Orquestra"), erro = campo(), estado = campo();
  const elementos = { "#cfg-nome": nome, "#erro-cfg-nome": erro, "#estado-config": estado };
  const document = { body: { dataset: { vaultId: "vault-teste" } }, querySelector: seletor => elementos[seletor] || null, querySelectorAll: () => [], addEventListener: (nome, cb) => { eventos[nome] = cb; } };
  const window = { OrquestraInterface: { avisar: (texto, tipo) => avisos.push({ texto, tipo }), mensagemErro: (erro, status) => erro?.message || "Erro " + status } };
  const fetch = async (url, opcoes) => {
    pedidos.push({ url, opcoes });
    if (url === "/api/local/capacidade") return { ok: true, json: async () => ({ token: "capacidade-teste" }) };
    return responder(url, opcoes);
  };
  runInNewContext(fonte, { window, document, fetch, location: { reload: () => { recargas++; } }, setTimeout, clearTimeout, console });
  eventos.DOMContentLoaded();
  return { nome, erro, estado, pedidos, avisos, get recargas() { return recargas; } };
}

test("nome branco mostra instrução inline e no status sem enviar configuração", async () => {
  const pagina = paginaConfig(() => { throw new Error("Não deveria enviar"); });
  pagina.nome.value = "   "; pagina.nome.mudar(); await tick();
  assert.equal(pagina.nome.getAttribute("aria-invalid"), "true");
  assert.equal(pagina.erro.hidden, false);
  assert.equal(pagina.erro.textContent, "Informe um nome para o painel.");
  assert.match(pagina.estado.textContent, /não foi salvo.*Informe um nome/);
  assert.equal(pagina.pedidos.length, 0);
  assert.equal(pagina.recargas, 0);
  assert.equal(pagina.nome.disabled, false);
});

test("falha do POST mantém nome editado, reabilita campo e não recarrega", async () => {
  const pagina = paginaConfig(async () => ({ ok: false, status: 503, json: async () => ({ erro: "Disco cheio" }) }));
  pagina.nome.value = "Meu painel"; pagina.nome.mudar(); await tick();
  const envio = pagina.pedidos.find(p => p.url === "/api/config");
  assert.equal(envio.opcoes.method, "POST");
  assert.deepEqual(JSON.parse(envio.opcoes.body), { nome: "Meu painel" });
  assert.equal(envio.opcoes.headers["X-Orquestra-Vault"], "vault-teste");
  assert.equal(pagina.nome.value, "Meu painel"); assert.equal(pagina.nome.disabled, false);
  assert.equal(pagina.estado.textContent, "Disco cheio");
  assert.ok(pagina.avisos.some(aviso => aviso.texto === "Disco cheio" && aviso.tipo === "erro"));
  assert.equal(pagina.recargas, 0);
});

test("sucesso após corrigir nome limpa erro inline e preserva a página", async () => {
  const pagina = paginaConfig(async () => ({ ok: true, json: async () => ({ ok: true }) }));
  pagina.nome.value = ""; pagina.nome.mudar();
  pagina.nome.value = "Meu painel"; pagina.nome.mudar(); await tick();
  assert.equal(pagina.erro.hidden, true); assert.equal(pagina.erro.textContent, "");
  assert.equal(pagina.nome.getAttribute("aria-invalid"), "false");
  assert.equal(pagina.estado.classList.contains("erro-texto"), false);
  assert.equal(pagina.estado.textContent, "Preferências salvas.");
  assert.equal(pagina.recargas, 0);
  assert.equal(pagina.nome.disabled, false);
  assert.equal(pagina.pedidos.filter(p => p.url === "/api/config").length, 1);
});

test("resposta HTTP 200 ilegível mantém o formulário e não anuncia sucesso", async () => {
  const pagina = paginaConfig(async () => ({ ok: true, json: async () => { throw new SyntaxError("Unexpected HTML"); } }));
  pagina.nome.value = "Meu painel"; pagina.nome.mudar(); await tick();
  assert.equal(pagina.recargas, 0); assert.equal(pagina.nome.disabled, false);
  assert.match(pagina.estado.textContent, /formato inesperado/);
  assert.ok(pagina.avisos.every(aviso => aviso.tipo === "erro"));
});

function paginaNota(responder) {
  const eventos = {}, avisos = [], elementos = new Map();
  function elemento(value = "") {
    const ouvintes = {}, classes = new Set();
    return {
      value, textContent: "", dataset: {}, disabled: false, hidden: false, type: "text", name: "",
      addEventListener: (tipo, cb) => { ouvintes[tipo] = cb; },
      disparar(tipo, dados = {}) { return ouvintes[tipo]({ target: this, ...dados }); }, focus() {},
      closest: () => null,
      classList: { toggle: (nome, ativo) => ativo ? classes.add(nome) : classes.delete(nome), contains: nome => classes.has(nome) },
      querySelectorAll: () => []
    };
  }
  for (const id of ["ver", "editor", "nota-titulo", "editar", "salvar", "cancelar", "estado-salvo", "faixa-conflito", "falha-gravacao", "falha-gravacao-texto", "repetir-gravacao", "reverter-gravacao", "salvar-copia", "copiar-rascunho", "recarregar-nota", "aviso-rascunho"]) elementos.set("#" + id, elemento());
  const raiz = elemento(), propriedade = elemento("a_fazer");
  propriedade.name = "status"; raiz.dataset = { rel: "tarefas/Exemplo.md", versao: "v1", vaultId: "vault-teste", metaOriginal: "{}" };
  raiz.querySelectorAll = seletor => seletor === "[data-campo]" ? [propriedade] : [];
  elementos.set(".nota", raiz); elementos.get("#editor").value = "Texto inicial"; elementos.get("#nota-titulo").value = "Exemplo";
  const document = { body: { dataset: { vaultId: "vault-teste" } }, querySelector: s => elementos.get(s) || null, querySelectorAll: () => [], addEventListener: (tipo, cb) => { eventos[tipo] = cb; } };
  const dados = new Map(), storage = { get length() { return dados.size; }, key: i => [...dados.keys()][i], getItem: k => dados.get(k) ?? null, setItem: (k, v) => dados.set(k, v), removeItem: k => dados.delete(k) };
  const window = { addEventListener() {}, OrquestraNotas: require("../../src/orquestra/static/js/notas-seguras.js"), OrquestraInterface: { avisar: (texto, tipo) => avisos.push({ texto, tipo }), mensagemErro: e => e.message } };
  const fetch = async (url, opcoes) => url === "/api/local/capacidade" ? { ok: true, json: async () => ({ token: "local" }) } : responder(url, opcoes);
  runInNewContext(fonte, { window, document, fetch, localStorage: storage, location: { reload() {} }, setTimeout, clearTimeout, console });
  eventos.DOMContentLoaded();
  return { propriedade, eventos, ver: elementos.get("#ver"), editar: elementos.get("#editar"), editor: elementos.get("#editor"), estado: elementos.get("#estado-salvo"), salvar: elementos.get("#salvar"), avisos };
}

test("digitar após salvar propriedade troca tudo salvo por rascunho e desfazer restaura salvo", async () => {
  const pagina = paginaNota(async () => ({ ok: true, json: async () => ({ versao: "v2" }) }));
  pagina.propriedade.value = "feito"; pagina.propriedade.disparar("change"); await tick();
  assert.equal(pagina.estado.textContent, "Tudo salvo no vault.");
  pagina.editor.value = "Texto editado"; pagina.editor.disparar("input");
  assert.equal(pagina.estado.textContent, "Há alterações no rascunho.");
  pagina.editor.value = "Texto inicial"; pagina.editor.disparar("input");
  assert.equal(pagina.estado.textContent, "Tudo salvo no vault.");
});

test("estado salvando prevalece sobre novas edições e falha continua visível ao digitar", async () => {
  let concluir;
  const pagina = paginaNota(() => new Promise(resolve => { concluir = resolve; }));
  pagina.editor.value = "Versão enviada"; pagina.editor.disparar("input"); pagina.salvar.onclick(); await tick();
  assert.equal(pagina.estado.textContent, "Salvando…");
  pagina.editor.value = "Nova edição durante envio"; pagina.editor.disparar("input");
  assert.equal(pagina.estado.textContent, "Salvando…");
  concluir({ ok: false, status: 503, json: async () => ({ erro: "Disco cheio" }) }); await tick();
  assert.equal(pagina.estado.textContent, "Há alterações que não foram salvas.");
  pagina.editor.value += " Mais texto"; pagina.editor.disparar("input");
  assert.equal(pagina.estado.textContent, "Há alterações que não foram salvas.");
  assert.equal(pagina.estado.classList.contains("erro-texto"), true);
});



test("duplo clique abre editor e Escape salva pela fila sem aviso de sucesso", async () => {
  const envios = [];
  const pagina = paginaNota(async (url, opcoes) => {
    envios.push(JSON.parse(opcoes.body));
    return { ok: true, json: async () => ({versao: "v2", html: "<p>Texto novo</p>"}) };
  });
  pagina.ver.disparar("dblclick");
  assert.equal(pagina.editor.hidden, false);
  pagina.editor.value = "Texto novo"; pagina.editor.disparar("input");
  pagina.editor.disparar("keydown", {key: "Escape", preventDefault() {}}); await tick();
  assert.equal(envios.length, 1);
  assert.equal(envios[0].corpo, "Texto novo");
  assert.equal(pagina.editor.hidden, true);
  assert.equal(pagina.estado.textContent, "Tudo salvo no vault.");
  assert.deepEqual(pagina.avisos, []);
});

test("clique fora salva texto depois da propriedade em andamento", async () => {
  const envios = []; let concluir;
  const pagina = paginaNota((url, opcoes) => {
    envios.push(JSON.parse(opcoes.body));
    if (envios.length === 1) return new Promise(resolve => {concluir=resolve;});
    return Promise.resolve({ok: true, json: async () => ({versao:"v3",html:"<p>Texto novo</p>"})});
  });
  pagina.ver.disparar("dblclick");
  pagina.propriedade.value="feito"; pagina.propriedade.disparar("change"); await tick();
  pagina.editor.value="Texto novo"; pagina.editor.disparar("input");
  pagina.eventos.pointerdown({target:{closest:()=>null}});
  assert.equal(envios.length,1);
  concluir({ok:true,json:async()=>({versao:"v2"})}); await tick(); await tick();
  assert.equal(envios.length,2);
  assert.equal(envios[1].versao,"v2");
  assert.equal(envios[1].corpo,"Texto novo");
  assert.equal(pagina.editor.hidden,true);
});
