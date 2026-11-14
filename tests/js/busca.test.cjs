const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function tela() {
  const elementos = {};
  for (const id of ['busca-flutuante', 'bf-campo', 'bf-lista', 'bf-estado', 'bf-completa']) {
    elementos[id] = {
      value: '', children: [], eventos: {}, open: false,
      addEventListener(nome, fn) { this.eventos[nome] = fn; },
      setAttribute() {}, removeAttribute() {}, replaceChildren() { this.children = []; },
      focus() {}, select() {}, showModal() { this.open = true; },
      close() { this.open = false; this.eventos.close(); }
    };
  }
  let sequencia = 0;
  const timers = new Map(), pedidos = [];
  const document = {
    getElementById: id => elementos[id], querySelectorAll: () => [], addEventListener() {}
  };
  const window = {};
  vm.runInNewContext(fs.readFileSync('src/orquestra/static/js/busca.js', 'utf8'), {
    document, window, AbortController, location: {},
    setTimeout(fn, ms) { const id = ++sequencia; timers.set(id, { fn, ms }); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch(url, opcoes) { return new Promise((resolve, reject) => pedidos.push({ url, opcoes, resolve, reject })); }
  });
  function digitar(termo) { elementos['bf-campo'].value = termo; elementos['bf-campo'].eventos.input(); }
  function disparar(ms) {
    for (const [id, t] of timers) if (t.ms === ms) { timers.delete(id); t.fn(); break; }
  }
  return { elementos, window, digitar, disparar, pedidos };
}
const drenar = () => new Promise(resolve => setImmediate(resolve));

test('fechar antes do debounce impede requisição', () => {
  const t = tela(); t.window.OrquestraBusca.abrir(); t.digitar('nota');
  t.window.OrquestraBusca.fechar(); t.disparar(200);
  assert.equal(t.pedidos.length, 0);
});

test('trocar ou limpar termo cancela imediatamente e ignora falha antiga', async () => {
  const t = tela(); t.window.OrquestraBusca.abrir(); t.digitar('antigo'); t.disparar(200);
  t.digitar('novo');
  assert.equal(t.pedidos[0].opcoes.signal.aborted, true);
  t.pedidos[0].reject(new Error('erro antigo')); await drenar();
  assert.equal(t.elementos['bf-estado'].textContent, 'Buscando…');
  t.disparar(200); t.digitar('');
  assert.equal(t.pedidos[1].opcoes.signal.aborted, true);
  t.pedidos[1].resolve({ ok: true, json: async () => ({ total: 9, resultados: [] }) });
  await drenar();
  assert.match(t.elementos['bf-estado'].textContent, /Digite para buscar/);
});

test('falha e tempo esgotado permitem tentar novamente', async () => {
  const t = tela(); t.window.OrquestraBusca.abrir(); t.digitar('nota'); t.disparar(200);
  t.disparar(10000);
  assert.equal(t.pedidos[0].opcoes.signal.aborted, true);
  t.pedidos[0].reject(new DOMException('tempo esgotado', 'AbortError')); await drenar();
  assert.match(t.elementos['bf-estado'].textContent, /Não foi possível buscar/);
  t.digitar('outra'); t.disparar(200);
  t.pedidos[1].resolve({ ok: false }); await drenar();
  assert.match(t.elementos['bf-estado'].textContent, /Tente novamente/);
});

test('resposta anterior não reaparece após fechar e reabrir com o mesmo termo', async () => {
  const t = tela(); t.window.OrquestraBusca.abrir(); t.digitar('nota'); t.disparar(200);
  t.window.OrquestraBusca.fechar(); t.window.OrquestraBusca.abrir();
  t.pedidos[0].resolve({ ok: true, json: async () => ({ total: 9, resultados: [] }) });
  await drenar();
  assert.equal(t.elementos['bf-estado'].textContent, 'Buscando…');
  t.disparar(200);
  t.pedidos[1].resolve({ ok: true, json: async () => ({ total: 0, resultados: [] }) });
  await drenar();
  assert.match(t.elementos['bf-estado'].textContent, /Nenhuma nota encontrada/);
});
