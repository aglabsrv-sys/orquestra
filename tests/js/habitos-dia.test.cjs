'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {runInNewContext}=require('node:vm');
const fonte=readFileSync(join(__dirname,'../../src/orquestra/static/js/habitos.js'),'utf8');

test('marcar após virar a semana remonta o período em vez de pintar os dias antigos',async()=>{
  const listeners={},estado={textContent:''},card={dataset:{habito:'habitos/itens/Ler.md',versao:'anterior'},querySelector(){return estado;}};
  const marcar={disabled:false,closest(){return card;}};
  const root={dataset:{hoje:'2026-11-15'}};
  const elementos={
    '#habitos-dados':{textContent:JSON.stringify({itens:[],modelos:[]})},
    '#habito-editor':{addEventListener(){}},
    '#habito-form':{},
  };
  let recargas=0,pedido;
  const document={body:{dataset:{vaultId:'vault-teste'}},getElementById(){return root;},querySelector(s){return elementos[s];},addEventListener(n,f){listeners[n]=f;},dispatchEvent(){}};
  runInNewContext(fonte,{document,window:{addEventListener(){}},Map,DOMParser:class {},CustomEvent:class {},location:{reload(){recargas++;}},fetch:async(url,opcoes)=>{
    pedido=JSON.parse(opcoes.body);
    return {ok:true,json:async()=>({rel:card.dataset.habito,versao:'nova',hoje:'2026-11-16',item:{},resumo:{}})};
  }});
  await listeners.click({target:{closest(s){return s==='[data-habito-marcar]' ? marcar : null;}}});
  assert.equal(recargas,1);
  assert.equal(marcar.disabled,false);
  assert.equal(pedido.versao,'anterior');
  assert.equal(estado.textContent,'');
});
