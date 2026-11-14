'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const segredos = readFileSync(join(__dirname,'../../src/orquestra/static/js/experiencia.js'),'utf8');
const refino = readFileSync(join(__dirname,'../../src/orquestra/static/js/refino.js'),'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function elemento(tag='DIV') {
  const eventos = {}, atributos = {};
  return {tagName:tag,dataset:{},children:[],value:'',type:'',disabled:false,textContent:'',hidden:false,readOnly:false,
    append(...filhos){this.children.push(...filhos);},appendChild(filho){this.children.push(filho);return filho;},replaceChildren(...filhos){this.children=[...filhos];},
    setAttribute(k,v){atributos[k]=String(v);},getAttribute(k){return atributos[k]??null;},
    addEventListener(tipo,fn){(eventos[tipo] ||= []).push(fn);},emitir(tipo,e={}){for(const fn of eventos[tipo]||[])fn({target:this,...e});},
    querySelector(){return null;},querySelectorAll(){return [];},focus(){},
    classList:{add(){},remove(){},toggle(){}},
    cloneNode(){return elemento(tag);}
  };
}

function ambiente(fonte,mapa={},responder=async()=>({})) {
  const pedidos=[],avisos=[],document=elemento('DOCUMENT'),window=elemento('WINDOW');
  document.body={dataset:{vaultId:'cofre-teste'}};
  document.querySelector=s=>mapa[s]||null;
  document.createElement=tag=>elemento(tag.toUpperCase());
  window.matchMedia=()=>({matches:true,addEventListener(){}});
  window.OrquestraInterface={avisar:(texto,tipo)=>avisos.push({texto,tipo}),confirmar:async()=>true};
  const fetch=async(url,opcoes)=>{
    pedidos.push({url,opcoes});
    if(url==='/api/local/capacidade')return {ok:true,json:async()=>({token:'token-local'})};
    const dados=await responder(url,opcoes);
    return {ok:dados?.ok!==false,json:async()=>dados};
  };
  if(mapa.botoes)document.querySelectorAll=s=>s==='[data-autostart]'?mapa.botoes:[];
  runInNewContext(fonte,{document,window,fetch,console,Event,Set,Map,URL,setTimeout:fn=>setImmediate(fn),location:{href:'http://localhost:8420/'}});
  return {pedidos,avisos,document,window};
}

function paginaSegredos(nomes=[],falharSalvar=false) {
  const form=elemento('FORM'),dialogo=elemento('DIALOG'),nome=elemento('INPUT'),valor=elemento('INPUT');
  const olho=elemento('BUTTON'),adicionar=elemento('BUTTON'),salvar=elemento('BUTTON'),lista=elemento('UL');
  const contagem=elemento(),estado=elemento(),titulo=elemento(),erro=elemento(),dica=elemento('TEMPLATE');
  dica.content=elemento('DETAILS');
  form.reset=()=>{nome.value=valor.value='';}; form.reportValidity=()=>!!nome.value&&!!valor.value;
  form.querySelector=s=>s==='button[type=submit]'?salvar:null;
  dialogo.showModal=()=>{dialogo.open=true;};dialogo.close=()=>{dialogo.open=false;dialogo.emitir('close');};
  const mapa={'#variaveis-form':form,'#variavel-dialogo':dialogo,'#variavel-nome':nome,'#variavel-valor':valor,
    '#variavel-revelar':olho,'#variavel-adicionar':adicionar,'#variaveis-lista':lista,'#variaveis-contagem':contagem,
    '#variaveis-estado':estado,'#variavel-titulo':titulo,'#variavel-form-estado':erro,'#segredo-youtube-dica':dica};
  const p=ambiente(segredos,mapa,async(url,opcoes)=>{
    if(url==='/api/variaveis'&&opcoes.method==='POST') {
      if(falharSalvar)return {ok:false,erro:'Não foi possível gravar.'};
      const dado=JSON.parse(opcoes.body);nomes=dado.valor===null?nomes.filter(n=>n!==dado.nome):Array.from(new Set([...nomes,dado.nome]));
      return {ok:true};
    }
    return {nomes};
  });
  return {...p,form,dialogo,nome,valor,olho,adicionar,salvar,lista,contagem,titulo,erro};
}

function descendentes(el) { return [el,...(el.children||[]).flatMap(descendentes)]; }

test('YouTube aparece sem criar um segredo vazio e abre somente o valor',async()=>{
  const p=paginaSegredos();await tick();
  assert.equal(p.lista.children.length,1);
  const linha=p.lista.children[0];assert.equal(linha.dataset.segredo,'YOUTUBE_API_KEY');
  const adicionar=descendentes(linha).find(e=>e.tagName==='BUTTON'&&e.textContent==='Adicionar valor');
  assert.ok(adicionar);adicionar.onclick();
  assert.equal(p.nome.value,'YOUTUBE_API_KEY');assert.equal(p.nome.readOnly,true);
  assert.equal(p.valor.value,'');assert.equal(p.valor.type,'password');
  assert.equal(p.pedidos.filter(e=>e.opcoes.method==='POST').length,0);
  assert.equal(p.contagem.textContent,'0 configurados');
});

test('olho só revela o valor digitado e fecha ocultando e limpando o formulário',async()=>{
  const p=paginaSegredos(['YOUTUBE_API_KEY']);await tick();
  descendentes(p.lista).find(e=>e.tagName==='BUTTON'&&e.textContent==='Atualizar').onclick();
  assert.equal(p.valor.value,'');p.valor.value='valor-novo-ficticio';p.olho.onclick();
  assert.equal(p.valor.type,'text');assert.equal(p.olho.getAttribute('aria-pressed'),'true');
  assert.equal(p.olho.getAttribute('aria-label'),'Ocultar valor');
  p.dialogo.close();assert.equal(p.valor.value,'');assert.equal(p.valor.type,'password');
  assert.equal(p.olho.getAttribute('aria-pressed'),'false');
  assert.ok(p.pedidos.every(e=>!e.url.includes('valor')));
});

test('salvar envia apenas o valor novo e falha preserva formulário para tentar de novo',async()=>{
  const p=paginaSegredos(['YOUTUBE_API_KEY'],true);await tick();
  descendentes(p.lista).find(e=>e.tagName==='BUTTON'&&e.textContent==='Atualizar').onclick();
  p.valor.value='valor-ficticio';await p.form.onsubmit({preventDefault(){}});
  const post=p.pedidos.find(e=>e.opcoes.method==='POST');
  assert.deepEqual(JSON.parse(post.opcoes.body),{nome:'YOUTUBE_API_KEY',valor:'valor-ficticio'});
  assert.equal(p.dialogo.open,true);assert.equal(p.valor.value,'valor-ficticio');
  assert.equal(p.erro.textContent,'Não foi possível gravar.');assert.equal(p.salvar.disabled,false);
});

test('preencher a chave nativa salva uma vez e volta ao estado oculto',async()=>{
  const p=paginaSegredos();await tick();
  descendentes(p.lista).find(e=>e.tagName==='BUTTON'&&e.textContent==='Adicionar valor').onclick();
  p.valor.value='chave-ficticia-nova';p.olho.onclick();await p.form.onsubmit({preventDefault(){}});
  assert.equal(p.pedidos.filter(e=>e.opcoes.method==='POST').length,1);
  assert.equal(p.dialogo.open,false);assert.equal(p.valor.type,'password');assert.equal(p.valor.value,'');
  assert.equal(p.contagem.textContent,'1 configurado');assert.equal(p.lista.children.length,1);
  assert.ok(descendentes(p.lista).some(e=>e.tagName==='BUTTON'&&e.textContent==='Atualizar'));
});

test('excluir o valor do YouTube mantém a referência nativa disponível',async()=>{
  const p=paginaSegredos(['YOUTUBE_API_KEY']);await tick();
  await descendentes(p.lista).find(e=>e.tagName==='BUTTON'&&e.textContent==='Excluir').onclick();
  assert.equal(p.lista.children.length,1);assert.equal(p.lista.children[0].dataset.segredo,'YOUTUBE_API_KEY');
  assert.equal(p.contagem.textContent,'0 configurados');
  assert.ok(descendentes(p.lista).some(e=>e.tagName==='BUTTON'&&e.textContent==='Adicionar valor'));
  const post=p.pedidos.find(e=>e.opcoes.method==='POST');assert.equal(JSON.parse(post.opcoes.body).valor,null);
});

function paginaStartup(inicial,responder,consultar) {
  const ativar=elemento('BUTTON'),desativar=elemento('BUTTON'),estado=elemento();
  ativar.dataset.autostart='ativar';desativar.dataset.autostart='desativar';ativar.disabled=desativar.disabled=true;
  let atual=inicial;
  const p=ambiente(refino,{'#autostart-estado':estado,botoes:[ativar,desativar]},async(url,opcoes)=>{
    if(opcoes.method==='GET')return consultar ? consultar(atual) : atual;
    const resultado=await responder(JSON.parse(opcoes.body));if(resultado.ok!==false)atual=resultado;return resultado;
  });
  return {...p,ativar,desativar,estado};
}

test('inicialização consulta estado real, alterna botões e mostra só Pronto',async()=>{
  const p=paginaStartup({ativo:true,presente:true,estado:'ativo',descricao:'Ativado para este cofre.'},async()=>({ativo:false,presente:false,estado:'desligado',descricao:'Desativado neste computador.',mensagem:'Arquivo criado: caminho técnico'}));
  await tick();assert.equal(p.ativar.disabled,true);assert.equal(p.desativar.disabled,false);
  await p.desativar.onclick();assert.equal(p.ativar.disabled,false);assert.equal(p.desativar.disabled,true);
  assert.equal(p.estado.textContent,'Desativado neste computador.');
  assert.deepEqual(p.avisos,[{texto:'Pronto',tipo:undefined}]);
});

test('falha ao alterar início automático relê estado e não anuncia sucesso',async()=>{
  const p=paginaStartup({ativo:false,presente:false,estado:'desligado',descricao:'Desativado neste computador.'},async()=>({ok:false,erro:'Sem permissão.'}));
  await tick();await p.ativar.onclick();
  assert.equal(p.ativar.disabled,false);assert.equal(p.desativar.disabled,true);
  assert.equal(p.pedidos.filter(e=>e.url==='/api/autostart'&&e.opcoes.method==='GET').length,2);
  assert.deepEqual(p.avisos,[{texto:'Sem permissão.',tipo:'erro'}]);
});

test('início já configurado permite aplicar agora sem esperar outro login',async()=>{
  const p=paginaStartup({ativo:true,presente:true,estado:'ativo',precisa_aplicar:true,descricao:'Aplique agora.'},async()=>({}));
  await tick();
  assert.equal(p.ativar.disabled,false);assert.equal(p.ativar.textContent,'Aplicar agora');
});

test('só confirma Pronto após reconectar ao processo independente com nova capacidade',async()=>{
  const p=paginaStartup({ativo:false,presente:false,estado:'desligado',descricao:'Desativado.'},
    async()=>({ativo:true,presente:true,estado:'ativo',reiniciando:true,precisa_aplicar:true}),
    atual=>atual.reiniciando ? {ativo:true,presente:true,estado:'ativo',segundo_plano:true,descricao:'Pode fechar o terminal.'} : atual);
  await tick();await p.ativar.onclick();
  assert.deepEqual(p.avisos,[{texto:'Pronto',tipo:undefined}]);
  assert.equal(p.estado.textContent,'Pode fechar o terminal.');
  assert.ok(p.pedidos.filter(e=>e.url==='/api/local/capacidade').length>=2);
});

test('retomada não confirmada mantém Aplicar agora e não libera fechar o terminal',async()=>{
  const p=paginaStartup({ativo:false,presente:false,estado:'desligado',descricao:'Desativado.'},
    async()=>({ativo:true,presente:true,estado:'ativo',reiniciando:true,precisa_aplicar:true,descricao:'Aplique agora.'}));
  await tick();await p.ativar.onclick();
  assert.equal(p.avisos.length,1);assert.equal(p.avisos[0].tipo,'erro');
  assert.match(p.avisos[0].texto,/Mantenha o terminal aberto/);
  assert.equal(p.ativar.disabled,false);assert.equal(p.ativar.textContent,'Aplicar agora');
});
