'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const fonte = readFileSync(join(__dirname, '../../src/orquestra/static/js/calendario.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function contexto() {
  const eventos = {}, elementos = new Map();
  function elemento(id) {
    if (!elementos.has(id)) elementos.set(id, {open:false, value:'', textContent:'',
      eventos:{}, addEventListener(n, f) { this.eventos[n] = f; },
      querySelector() { return null; }, close() { this.open = false; }});
    return elementos.get(id);
  }
  const raiz = elemento('#calendario');
  const editor = elemento('#cal-evento-dialogo');
  const formulario = elemento('#cal-evento-form');
  let permitido = true, confirmacoes = 0;
  const document = {getElementById() { return raiz; }, querySelector:elemento,
    addEventListener(n, f) { eventos[n] = f; }};
  runInNewContext(fonte, {document, window:{addEventListener() {}, OrquestraInterface:{
    async confirmar() { confirmacoes++; return permitido; }}}, location:{href:'http://localhost/agenda'}});
  return {editor, formulario, eventos, get confirmacoes() { return confirmacoes; },
    permitir(valor) { permitido = valor; },
    cancelar(dialogo=editor) {
      const botao = {closest() { return dialogo; }};
      eventos.click({target:{closest(s) { return s === '[data-cal-fechar]' ? botao : null; }}});
    }};
}

test('Cancelar fecha o editor sem confundir o botão Fechar do evento externo', async () => {
  const c = contexto();
  c.editor.open = true;
  c.cancelar();
  await tick();
  assert.equal(c.editor.open, false);
  assert.equal(c.confirmacoes, 0);
});

test('Cancelar preserva rascunho quando descarte é recusado e fecha após confirmação', async () => {
  const c = contexto();
  c.editor.open = true;
  c.formulario.eventos.input();
  c.permitir(false);
  c.cancelar();
  await tick();
  assert.equal(c.editor.open, true);
  c.permitir(true);
  c.cancelar();
  await tick();
  assert.equal(c.editor.open, false);
  assert.equal(c.confirmacoes, 2);
});

test('Cancelar nos filtros fecha apenas o diálogo de filtros', async () => {
  const c = contexto();
  const filtro = {open:true, close() { this.open = false; }};
  c.editor.open = true;
  c.cancelar(filtro);
  await tick();
  assert.equal(filtro.open, false);
  assert.equal(c.editor.open, true);
});
