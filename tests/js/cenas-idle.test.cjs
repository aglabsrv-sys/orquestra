'use strict';
const {test}=require('node:test'); const assert=require('node:assert/strict'); const {runInNewContext}=require('node:vm'); const {readFileSync}=require('node:fs'); const {join}=require('node:path');
const fonte=readFileSync(join(__dirname,'../../src/orquestra/static/js/cenas.js'),'utf8');
function pagina(reduzir=false){
 const listeners={},frames=new Map(),preferencia={matches:reduzir,addEventListener(n,f){this.mudar=f;}};let n=0,pinturas=0;
 const ambiente={width:48,height:27,classList:{add(){}},getContext(){return {drawImage(){pinturas++;}};}};
 const document={hidden:false,querySelectorAll(){return [];},querySelector(){return null;},getElementById(){return ambiente;},addEventListener(n,f){listeners[n]=f;}};
 const window={matchMedia(){return preferencia;}};
 runInNewContext(fonte,{window,document,requestAnimationFrame(f){frames.set(++n,f);return n;},cancelAnimationFrame(id){frames.delete(id);},console});
 listeners.DOMContentLoaded();
 return {window,document,frames,listeners,preferencia,get pinturas(){return pinturas;},quadro(t){const e=frames.entries().next().value;frames.delete(e[0]);e[1](t);}};
}
test('página sem cenas nem fonte animada não inicia loop RAF',()=>{const p=pagina();assert.equal(p.frames.size,0);});
test('imagem estática pinta uma vez sem manter loop',()=>{const p=pagina();p.window.Orquestra.ambiente({tagName:'IMG',isConnected:true,complete:true,addEventListener(){},removeEventListener(){}});assert.equal(p.pinturas,1);assert.equal(p.frames.size,0);});
test('vídeo ativo acorda e aba oculta cancela todos os frames',()=>{const p=pagina();const video={tagName:'VIDEO',isConnected:true,paused:false,addEventListener(){},removeEventListener(){}};p.window.Orquestra.ambiente(video);assert.equal(p.frames.size,1);p.quadro(1000);assert.equal(p.frames.size,1);p.document.hidden=true;p.listeners.visibilitychange();assert.equal(p.frames.size,0);p.document.hidden=false;p.listeners.visibilitychange();assert.equal(p.frames.size,1);video.paused=true;p.quadro(2000);assert.equal(p.frames.size,0);});
test('reduzir movimento impede RAF e permite retomar dinamicamente',()=>{const p=pagina(true);p.window.Orquestra.ambiente({tagName:'VIDEO',isConnected:true,paused:false,addEventListener(){},removeEventListener(){}});assert.equal(p.frames.size,0);p.preferencia.mudar({matches:false});assert.equal(p.frames.size,1);p.preferencia.mudar({matches:true});assert.equal(p.frames.size,0);});
