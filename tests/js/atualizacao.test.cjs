'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {runInNewContext}=require('node:vm');
const fonte=readFileSync(join(__dirname,'../../src/orquestra/static/js/atualizacao.js'),'utf8');

function ambiente({disponivel=false,local=true,pendente=false,modo,alteracoes_locais=0}={}) {
  const eventos={},pedidos=[],confirmacoes=[],avisos=[];
  let automatico,posts=0,recargas=0;
  const botao={hidden:true,classList:{toggle(){},add(){},remove(){}},setAttribute(){},addEventListener(n,f){eventos[n]=f;}};
  const document={hidden:false,body:{dataset:{vaultId:'vault-ficticio'}},querySelector(){return botao;},addEventListener(){}};
  const window={addEventListener(n,f){eventos[n]=f;},dispatchEvent(){return !pendente;},OrquestraInterface:{confirmar:async dados=>{confirmacoes.push(dados);return false;},avisar:(...args)=>avisos.push(args)}};
  const fetch=async(url,opcoes)=>{
    pedidos.push({url,opcoes});
    if(url==='/api/local/capacidade') return {ok:true,json:async()=>({token:'capacidade-ficticia'})};
    if(opcoes.method==='POST') { posts++;return {ok:true,json:async()=>({revisao:'nova'})}; }
    return {ok:true,json:async()=>({disponivel,local,modo,alteracoes_locais,pid:posts?2:1,instalada:posts?'nova':'antiga',revisao:'nova'})};
  };
  runInNewContext(fonte,{document,window,fetch,AbortController,Date,Event,location:{reload(){recargas++;}},setInterval(f){automatico=f;},
    setTimeout(f,tempo){if(tempo!==25000)f();},clearTimeout(){}});
  return {botao,pedidos,confirmacoes,avisos,verificar:()=>automatico(),clicar:()=>eventos.click(),recargas:()=>recargas,
    pronta:()=>new Promise(setImmediate),restaurar:()=>eventos.pageshow({persisted:true})};
}

test('aviso acompanha a disponibilidade informada pelo painel',async()=>{
  for(const disponivel of [true,false]) {
    const p=ambiente({disponivel});
    assert.equal(p.pedidos[0].url,'/api/atualizacao');
    await p.pronta();
    assert.equal(p.botao.hidden,!disponivel);
  }
});

test('voltar a uma página preservada pelo navegador consulta o aviso novamente',async()=>{
  const p=ambiente();await p.pronta();p.restaurar();await p.pronta();
  assert.equal(p.pedidos.length,2);
});

test('aviso antigo de arquivos locais também sincroniza diretamente',async()=>{
  const p=ambiente({disponivel:true,modo:'reiniciar'});await p.pronta();
  assert.equal(p.botao.hidden,false);
  assert.equal(p.botao.title,'Atualizar Orquestra');
  await p.clicar();
  assert.equal(p.confirmacoes.length,0);
  const post=p.pedidos.find(p=>p.opcoes.method==='POST');
  assert.deepEqual(JSON.parse(post.opcoes.body),{});
  assert.equal(p.recargas(),1);
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
  assert.equal(p.confirmacoes.length,0);
  assert.equal(p.pedidos.filter(p=>p.opcoes.method==='POST')[0].url,'/api/atualizacao');
  const post=p.pedidos.find(p=>p.opcoes.method==='POST');
  assert.equal(post.opcoes.headers['X-Orquestra-Local'],'capacidade-ficticia');
  assert.equal(post.opcoes.headers['X-Orquestra-Vault'],'vault-ficticio');
  assert.equal(p.recargas(),1);
});

test('edições pendentes ou acesso remoto não iniciam atualização nem reinício',async()=>{
  for(const opcoes of [{pendente:true},{local:false}]) {
    const p=ambiente({disponivel:true,...opcoes});await p.clicar();
    assert.equal(p.pedidos.some(p=>p.opcoes.method==='POST'),false);
    assert.equal(p.recargas(),0);
  }
});

test('alterações locais sincronizam direto, sem confirmação ou cópias',async()=>{
  const p=ambiente({disponivel:true,alteracoes_locais:2});await p.clicar();
  assert.equal(p.confirmacoes.length,0);
  const post=p.pedidos.find(p=>p.opcoes.method==='POST');
  assert.equal(JSON.parse(post.opcoes.body).preservar,undefined);
  assert.equal(p.recargas(),1);
});

test('dois cliques durante a consulta iniciam uma única atualização', async () => {
  const p = ambiente({disponivel: true});
  await Promise.all([p.clicar(), p.clicar()]);
  assert.equal(p.confirmacoes.length, 0);
  assert.equal(p.pedidos.filter(pedido => pedido.opcoes.method === 'POST').length, 1);
});
