'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {runInNewContext}=require('node:vm');
const fonte=readFileSync(join(__dirname,'../../src/orquestra/static/js/atualizacao.js'),'utf8');

function ambiente({disponivel=false,local=true,confirmar=true}={}) {
  const eventos={},pedidos=[],confirmacoes=[],avisos=[];
  let automatico,posts=0,recargas=0;
  const botao={hidden:true,classList:{toggle(){},add(){},remove(){}},setAttribute(){},addEventListener(n,f){eventos[n]=f;}};
  const document={hidden:false,body:{dataset:{vaultId:'vault-ficticio'}},querySelector(){return botao;},addEventListener(){}};
  const window={OrquestraInterface:{confirmar:async dados=>{confirmacoes.push(dados);return confirmar;},avisar:(...args)=>avisos.push(args)}};
  const fetch=async(url,opcoes)=>{
    pedidos.push({url,opcoes});
    if(url==='/api/local/capacidade') return {ok:true,json:async()=>({token:'capacidade-ficticia'})};
    if(opcoes.method==='POST') { posts++;return {ok:true,json:async()=>({revisao:'nova'})}; }
    return {ok:true,json:async()=>({disponivel,local,pid:posts?2:1,instalada:posts?'nova':'antiga',revisao:'nova'})};
  };
  runInNewContext(fonte,{document,window,fetch,AbortSignal,Date,location:{reload(){recargas++;}},setInterval(){},setTimeout(f,tempo){if(tempo===3000)automatico=f;else f();}});
  return {botao,pedidos,confirmacoes,avisos,verificar:()=>automatico(),clicar:()=>eventos.click(),recargas:()=>recargas};
}

test('aviso só aparece quando há atualização publicada',async()=>{
  for(const disponivel of [true,false]) {
    const p=ambiente({disponivel});await p.verificar();
    assert.equal(p.botao.hidden,!disponivel);
  }
});

test('sem revisão disponível o clique oculta o aviso e não reinicia nem atualiza',async()=>{
  const p=ambiente();await p.clicar();
  assert.equal(p.confirmacoes.length,0);
  const posts=p.pedidos.filter(p=>p.opcoes.method==='POST');
  assert.equal(posts.length,0);
  assert.equal(p.botao.hidden,true);
  assert.equal(p.recargas(),0);
});

test('revisão publicada usa atualização e confirma a revisão após reiniciar',async()=>{
  const p=ambiente({disponivel:true});await p.verificar();await p.clicar();
  assert.equal(p.confirmacoes[0].confirmar,'Atualizar e reiniciar');
  assert.equal(p.pedidos.filter(p=>p.opcoes.method==='POST')[0].url,'/api/atualizacao');
  const post=p.pedidos.find(p=>p.opcoes.method==='POST');
  assert.equal(post.opcoes.headers['X-Orquestra-Local'],'capacidade-ficticia');
  assert.equal(post.opcoes.headers['X-Orquestra-Vault'],'vault-ficticio');
  assert.equal(p.recargas(),1);
});

test('cancelar ou acessar remotamente não inicia atualização nem reinício',async()=>{
  for(const opcoes of [{confirmar:false},{local:false}]) {
    const p=ambiente({disponivel:true,...opcoes});await p.clicar();
    assert.equal(p.pedidos.some(p=>p.opcoes.method==='POST'),false);
    assert.equal(p.recargas(),0);
  }
});
