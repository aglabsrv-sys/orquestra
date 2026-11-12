"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {runInNewContext} = require("node:vm");
const fonte = readFileSync(join(__dirname,"../../src/orquestra/static/js/app.js"),"utf8");
const tick = () => new Promise(resolve => setImmediate(resolve));

function tela(responder = async () => ({ok:true,json:async()=>({selos:{},hoje:3,decidir:2})})) {
  const ouvintes = {}, timers = new Map(), avisos = [], pedidos = [];
  let agora = 0, numero = 0, stream, recargas = 0;
  const hoje = {textContent:"antes"}, decidir = {textContent:"antes"};
  const document = {
    body:{dataset:{observa:"tudo",vaultId:"sintetico"}}, activeElement:null,
    querySelector:()=>null,
    querySelectorAll:s=>s === '[data-conta="hoje"]' ? [hoje] : s === '[data-conta="decidir"]' ? [decidir] : [],
    addEventListener(n,fn) {(ouvintes[n] ||= []).push(fn);}
  };
  function EventSource() {stream=this;}
  const window = {EventSource,addEventListener(){},OrquestraInterface:{avisar:t=>avisos.push(t)}};
  runInNewContext(fonte, {
    window,document,EventSource,Date,console,
    fetch(url) {pedidos.push(url); return Promise.resolve(responder(url)).then(r => ({...r, json:async()=>({vault_id:"sintetico",...await r.json()})}));},
    setTimeout(fn,ms) {timers.set(++numero,{fn,at:agora+ms}); return numero;},
    clearTimeout(id) {timers.delete(id);},
    location:{reload(){recargas++;}}
  });
  for (const fn of ouvintes.DOMContentLoaded || []) fn();
  function emitir(ev) {stream.onmessage({data:JSON.stringify(ev)});}
  async function avancar(ms) {
    const fim=agora+ms;
    for (;;) {
      const proximo=Array.from(timers).filter(([,t])=>t.at<=fim).sort((a,b)=>a[1].at-b[1].at || a[0]-b[0])[0];
      if (!proximo) break;
      agora=proximo[1].at; timers.delete(proximo[0]); proximo[1].fn(); await tick();
    }
    agora=fim; await tick();
  }
  return {emitir,avancar,pedidos,avisos,hoje,decidir,
    salvo(detail) {for(const fn of ouvintes['orquestra:nota-salva'] || []) fn({detail});},
    get recargas(){return recargas;}};
}
const nota = i => ({tipo:"nota",acao:"editado",rel:"tarefas/itens/"+i+".md",modulo:"tarefas",versao:String(i)});

test("rajada de 100 eventos solicita um resumo e mantém a página", async () => {
  const p=tela();
  for(let i=0;i<100;i++)p.emitir(nota(i));
  await p.avancar(1000);
  assert.deepEqual(p.pedidos,["/api/resumo"]);
  assert.equal(p.hoje.textContent,3); assert.equal(p.decidir.textContent,2);
  assert.equal(p.avisos.length,1); assert.equal(p.recargas,0);
});

test("eventos durante pedido em voo disparam uma nova leitura após a resposta", async () => {
  const pendentes=[];
  const p=tela(()=>new Promise(resolve=>pendentes.push(resolve)));
  p.emitir(nota(0)); await p.avancar(600);
  assert.equal(p.pedidos.length,1);
  for(let i=1;i<=100;i++)p.emitir(nota(i));
  await p.avancar(1000);
  assert.equal(p.pedidos.length,1,"não deve existir pedido concorrente");
  pendentes.shift()({ok:true,json:async()=>({selos:{},hoje:1,decidir:1})}); await tick();
  await p.avancar(180);
  assert.equal(p.pedidos.length,2,"uma mudança durante a leitura não pode se perder");
  pendentes.shift()({ok:true,json:async()=>({selos:{},hoje:101,decidir:9})}); await tick();
  await p.avancar(1000);
  assert.equal(p.pedidos.length,2); assert.equal(p.hoje.textContent,101); assert.equal(p.decidir.textContent,9);
});

test("falha preserva contadores e permite revalidação por evento posterior", async () => {
  let tentativa=0;
  const p=tela(async()=>++tentativa === 1 ? {ok:false} : {ok:true,json:async()=>({selos:{},hoje:8,decidir:4})});
  p.emitir(nota(1)); await p.avancar(1000);
  assert.equal(p.hoje.textContent,"antes"); assert.equal(p.pedidos.length,1);
  p.emitir(nota(2)); await p.avancar(1000);
  assert.equal(p.hoje.textContent,8); assert.equal(p.pedidos.length,2);
});

test("eventos próprios atualizam contadores sem anunciar mudanças externas", async () => {
  const p=tela(); p.salvo({versao:"minha"}); p.emitir({...nota(0),versao:"minha"});
  await p.avancar(1000);
  assert.equal(p.pedidos.length,1); assert.equal(p.avisos.length,0); assert.equal(p.recargas,0);
  p.salvo({rel:"tarefas/itens/1.md",removido:true}); p.emitir({...nota(1),acao:"removido",versao:""});
  await p.avancar(1000);
  assert.equal(p.pedidos.length,2); assert.equal(p.avisos.length,0);
});
