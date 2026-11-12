"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { criarFila, criarRascunhos, camposParaCopia } = require("../../src/orquestra/static/js/notas-seguras.js");
const tick = () => new Promise(resolve => setImmediate(resolve));

test("serializa pedidos e só usa a nova versão depois da resposta anterior", async () => {
  let versao = "v1", terminar;
  const enviados = [];
  const fila = criarFila(async dados => {
    enviados.push({ ...dados, versao });
    if (enviados.length === 1) await new Promise(resolve => { terminar = resolve; });
    return { versao: `v${enviados.length + 1}` };
  });
  const um = fila.adicionar({ titulo: "Primeiro" }, r => { versao = r.versao; });
  const dois = fila.adicionar({ campos: { status: "feito" } }, r => { versao = r.versao; });
  await tick();
  assert.equal(enviados.length, 1);
  terminar();
  await Promise.all([um, dois]);
  assert.deepEqual(enviados.map(x => x.versao), ["v1", "v2"]);
});

test("falha pausa a fila; tentar novamente preserva a ordem e os valores capturados", async () => {
  let falhar = true;
  const enviados = [], salvos = [];
  const fila = criarFila(async dados => {
    enviados.push(dados.titulo);
    if (falhar) throw new Error("Sem conexão");
    return { ok: true };
  });
  const dado = { titulo: "A" };
  const primeiro = fila.adicionar(dado, (_, salvo) => salvos.push(salvo.titulo));
  const segundo = fila.adicionar({ titulo: "B" }, (_, salvo) => salvos.push(salvo.titulo));
  dado.titulo = "Alterado depois";
  await assert.rejects(primeiro, /Sem conexão/);
  await tick();
  assert.deepEqual(enviados, ["A"]);
  assert.equal(fila.estado().pendentes, 2);
  falhar = false;
  fila.repetir();
  await segundo;
  assert.deepEqual(enviados, ["A", "A", "B"]);
  assert.deepEqual(salvos, ["A", "B"]);
});

test("descarte não cancela uma escrita em andamento", async () => {
  let concluir;
  const fila = criarFila(() => new Promise(resolve => { concluir = resolve; }));
  const envio = fila.adicionar({ corpo: "Preservar" });
  await tick();
  assert.equal(fila.descartar(), false);
  concluir({ ok: true });
  await envio;
});

function memoria() {
  const dados = new Map();
  return { get length() { return dados.size; }, key: i => [...dados.keys()][i], getItem: k => dados.get(k) ?? null, setItem: (k, v) => dados.set(k, v), removeItem: k => dados.delete(k) };
}

test("rascunhos ficam separados por vault, nota e sessão; limpar uma aba preserva a outra", () => {
  const storage = memoria();
  const aba1 = criarRascunhos(storage, "vault-a", "Notas/A.md", "aba-1");
  const aba2 = criarRascunhos(storage, "vault-a", "Notas/A.md", "aba-2");
  const outroVault = criarRascunhos(storage, "vault-b", "Notas/A.md", "aba-1");
  aba1.guardar({ corpo: "um", versao: "v1" });
  aba2.guardar({ corpo: "dois", versao: "v1" });
  outroVault.guardar({ corpo: "privado do outro vault" });
  assert.equal(aba1.listar().length, 2);
  aba1.limpar();
  assert.equal(aba2.listar().length, 1);
  assert.equal(aba2.listar()[0].dados.corpo, "dois");
  assert.equal(outroVault.listar().length, 1);
  aba2.remover(outroVault.listar()[0].chave);
  assert.equal(outroVault.listar().length, 1);
});

test("quota ou bloqueio do navegador são erros visíveis ao chamador", () => {
  const storage = memoria(); storage.setItem = () => { throw new Error("QuotaExceededError"); };
  assert.throws(() => criarRascunhos(storage, "v", "a.md", "s").guardar({ corpo: "texto" }), /QuotaExceededError/);
  assert.throws(() => criarRascunhos(storage, "", "a.md", "s"), /obrigatórias/);
});

test("cópia mantém metadados ocultos e aplica apenas os campos editados, sem alterar o original", () => {
  const original = { status: "a_fazer", tags: ["pessoal"], origem: "humano", campo_desconhecido: { autor: "Pessoa" } };
  const editados = { status: "feito" };
  const copia = camposParaCopia(original, editados);
  assert.deepEqual(JSON.parse(JSON.stringify(copia)), { ...original, status: "feito" });
  assert.equal(original.status, "a_fazer");
  assert.deepEqual(editados, { status: "feito" });
});

test("metadados arbitrários da cópia não poluem protótipos", () => {
  const original = JSON.parse('{"__proto__":{"poluido":true},"status":"feito"}');
  const copia = camposParaCopia(original, {});
  assert.equal(Object.getPrototypeOf(copia), null);
  assert.equal({}.poluido, undefined);
  assert.equal(JSON.parse(JSON.stringify(copia)).__proto__.poluido, true);
});
