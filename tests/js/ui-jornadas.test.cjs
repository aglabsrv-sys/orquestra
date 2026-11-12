'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const app = readFileSync(join(__dirname,'../../src/orquestra/static/js/app.js'),'utf8');
const refino = readFileSync(join(__dirname,'../../src/orquestra/static/js/refino.js'),'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function elemento(tagName='DIV') {
  const ouvintes = new Map(), atributos = new Map();
  const el = {tagName, dataset:{}, disabled:false, value:'', textContent:'', isConnected:true,
    classList:{toggle(){},add(){},remove(){}}, querySelector(){return null;},querySelectorAll(){return [];},
    setAttribute(n,v){atributos.set(n,String(v));},getAttribute(n){return atributos.get(n) ?? null;},removeAttribute(n){atributos.delete(n);},
    addEventListener(n,fn,opcoes){const lista=ouvintes.get(n)||[];lista.push({fn,captura:opcoes===true});ouvintes.set(n,lista);},
    removeEventListener(n,fn){ouvintes.set(n,(ouvintes.get(n)||[]).filter(o=>o.fn!==fn));},
    dispatchEvent(e){for(const o of [...(ouvintes.get(e.type)||[])].sort((a,b)=>Number(b.captura)-Number(a.captura))) {o.fn(e);if(e.imediato)break;}return !e.defaultPrevented;},
    emitir(tipo,dados={}){const e={type:tipo,target:el,defaultPrevented:false,preventDefault(){this.defaultPrevented=true;},stopImmediatePropagation(){this.imediato=true;},...dados};el.dispatchEvent(e);return e;}
  };
  return el;
}

function paginaApp({dialogo=null,carrossel=false}={}) {
  const document=elemento('DOCUMENT'),window=elemento('WINDOW'),raiz=elemento(),trilho=elemento(),slide=elemento('A');
  const anterior=elemento('BUTTON'),proximo=elemento('BUTTON'),botaoFechar=elemento('BUTTON');
  let aberturas=0,movimentos=0;
  document.body={dataset:{vaultId:'teste'}};
  slide.offsetLeft=0;slide.offsetWidth=300;slide.click=()=>{aberturas++;};
  trilho.clientWidth=500;trilho.scrollTo=()=>{movimentos++;};
  raiz.querySelector=s=>({'.trilho':trilho,'.seta.esq':anterior,'.seta.dir':proximo}[s]||null);
  trilho.querySelectorAll=s=>s==='.slide'?[slide]:[];
  document.querySelector=s=>s==='#carrossel'&&carrossel?raiz:null;
  document.querySelectorAll=s=>s==='dialog'&&dialogo?[dialogo]:s==='[data-fechar]'&&dialogo?[botaoFechar]:[];
  botaoFechar.closest=()=>dialogo;
  window.Orquestra={ambiente(){}};window.OrquestraInterface={avisar(){}};
  runInNewContext(app,{window,document,Event,console,setTimeout,clearTimeout,sessionStorage:{getItem(){return null;},setItem(){}}});
  document.emitir('DOMContentLoaded');
  return {document,botaoFechar,get aberturas(){return aberturas;},get movimentos(){return movimentos;}};
}

test('backdrop e botão respeitam cancel guardado; espaço interno não fecha o modal',()=>{
  const d=elemento('DIALOG');let fechamentos=0,pedidos=0;
  d.close=()=>{fechamentos++;};d.getBoundingClientRect=()=>({left:100,right:500,top:100,bottom:500});
  const p=paginaApp({dialogo:d});
  const guardar=e=>{pedidos++;e.preventDefault();};d.addEventListener('cancel',guardar);
  d.emitir('click',{clientX:120,clientY:120});assert.equal(pedidos,0);assert.equal(fechamentos,0);
  d.emitir('click',{clientX:20,clientY:20});assert.equal(pedidos,1);assert.equal(fechamentos,0);
  p.botaoFechar.onclick();assert.equal(pedidos,2);assert.equal(fechamentos,0);
  d.removeEventListener('cancel',guardar);p.botaoFechar.onclick();assert.equal(fechamentos,1);
});

test('Enter e setas sobre links e botões não acionam o carrossel da home',()=>{
  const p=paginaApp({carrossel:true}),link=elemento('A');link.closest=()=>link;
  const inicio=p.movimentos;
  for(const key of ['Enter','ArrowLeft','ArrowRight']) assert.equal(p.document.emitir('keydown',{target:link,key}).defaultPrevented,false);
  assert.equal(p.aberturas,0);assert.equal(p.movimentos,inicio);
  const fundo=elemento();fundo.closest=()=>null;
  assert.equal(p.document.emitir('keydown',{target:fundo,key:'Enter'}).defaultPrevented,true);
  assert.equal(p.aberturas,1);
  assert.equal(p.document.emitir('keydown',{target:fundo,key:'ArrowRight'}).defaultPrevented,true);
  assert.equal(p.movimentos,inicio+1);
  p.document.emitir('keydown',{target:fundo,key:'Enter',ctrlKey:true});assert.equal(p.aberturas,1);
});

function paginaRefino({quantidade=0,videos=[]}={}) {
  const document=elemento('DOCUMENT'),window=elemento('WINDOW'),form=elemento('FORM'),salvar=elemento('BUTTON'),bloqueado=elemento('BUTTON');
  const pedidos=[],pendentes=[],preferencia={matches:false,addEventListener(n,fn){this.mudar=fn;}};
  document.body={dataset:{vaultId:'teste'}};document.hidden=false;bloqueado.disabled=true;
  form.querySelectorAll=()=>[salvar,bloqueado];
  const campos=[],estados=[],inputs=Array.from({length:quantidade},(_,i)=>{
    const input=elemento('INPUT'),campo=elemento('INPUT'),estado=elemento('SMALL');
    campos.push(campo);estados.push(estado);input.dataset.miniaturaPara='imagem-'+i;
    input.closest=()=>form;input.parentElement={querySelector(){return estado;}};input.files=[{size:2048}];return input;
  });
  document.getElementById=id=>campos[Number(id.split('-')[1])];
  document.querySelectorAll=s=>s==='[data-miniatura-para]'?inputs:s==='video.capa'?videos:[];
  window.matchMedia=()=>preferencia;
  function IntersectionObserver(fn){this.observe=()=>{};this.atualizar=fn;window.observador=this;}
  window.IntersectionObserver=IntersectionObserver;
  const fetch=async(url,opcoes)=>{pedidos.push({url,opcoes});if(url==='/api/local/capacidade')return {ok:true,json:async()=>({token:'local'})};return new Promise((resolve,reject)=>pendentes.push({resolve,reject}));};
  runInNewContext(refino,{window,document,Event,Map,Set,IntersectionObserver,fetch,console});
  return {document,window,form,salvar,bloqueado,inputs,campos,estados,preferencia,pendentes,pedidos};
}

test('upload mantém criação bloqueada até a imagem chegar e restaura estado dos botões',async()=>{
  const p=paginaRefino({quantidade:1});let criacoes=0;
  const envio=p.inputs[0].onchange();p.form.addEventListener('submit',()=>{criacoes++;});await tick();
  assert.equal(p.salvar.disabled,true);assert.equal(p.form.getAttribute('aria-busy'),'true');
  assert.equal(p.form.emitir('submit').defaultPrevented,true);assert.equal(criacoes,0);
  assert.match(p.estados[0].textContent,/Aguarde/);
  assert.equal(p.window.emitir('beforeunload').defaultPrevented,true);
  p.pendentes[0].resolve({ok:true,json:async()=>({caminho:'anexos/teste.webp'})});await envio;
  assert.equal(p.campos[0].value,'anexos/teste.webp');assert.equal(p.salvar.disabled,false);assert.equal(p.bloqueado.disabled,true);
  assert.equal(p.form.getAttribute('aria-busy'),null);assert.equal(p.window.emitir('beforeunload').defaultPrevented,false);
  assert.equal(p.form.emitir('submit').defaultPrevented,false);assert.equal(criacoes,1);
});

test('uploads simultâneos só liberam criação ao terminar todos; falha preserva caminho anterior',async()=>{
  const p=paginaRefino({quantidade:2});p.campos[1].value='anexos/anterior.png';
  const primeiro=p.inputs[0].onchange(),segundo=p.inputs[1].onchange();await tick();
  p.pendentes[0].resolve({ok:true,json:async()=>({caminho:'anexos/novo.webp'})});await primeiro;
  assert.equal(p.salvar.disabled,true);assert.equal(p.form.emitir('submit').defaultPrevented,true);
  p.pendentes[1].reject(new Error('Conexão interrompida'));await segundo;
  assert.equal(p.salvar.disabled,false);assert.equal(p.inputs[1].disabled,false);
  assert.equal(p.campos[1].value,'anexos/anterior.png');assert.match(p.estados[1].textContent,/Conexão interrompida/);
});

test('alterar movimento reduzido pausa vídeos imediatamente e retoma somente os visíveis',()=>{
  function video(){return {playCount:0,pauseCount:0,play(){this.playCount++;return Promise.resolve();},pause(){this.pauseCount++;}};}
  const visivel=video(),fora=video(),p=paginaRefino({videos:[visivel,fora]});
  p.window.observador.atualizar([{target:visivel,isIntersecting:true},{target:fora,isIntersecting:false}]);
  assert.equal(visivel.playCount,1);assert.equal(fora.playCount,0);
  const antes=visivel.pauseCount;p.preferencia.matches=true;p.preferencia.mudar();assert.equal(visivel.pauseCount,antes+1);
  p.preferencia.matches=false;p.preferencia.mudar();assert.equal(visivel.playCount,2);assert.equal(fora.playCount,0);
  p.document.hidden=true;p.document.emitir('visibilitychange');
  p.preferencia.matches=true;p.preferencia.mudar();p.preferencia.matches=false;p.preferencia.mudar();assert.equal(visivel.playCount,2);
  p.document.hidden=false;p.document.emitir('visibilitychange');assert.equal(visivel.playCount,3);
});
