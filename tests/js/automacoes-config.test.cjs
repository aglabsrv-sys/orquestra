'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const fonte = readFileSync(join(__dirname,'../../src/orquestra/static/js/automacoes.js'),'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function corresponde(el,seletor) {
  if(seletor.startsWith('.'))return el.className.split(' ').includes(seletor.slice(1));
  if(seletor.startsWith('#'))return el.id===seletor.slice(1);
  const atributo=/^\[data-([a-z-]+)\]$/.exec(seletor);
  if(atributo)return Object.prototype.hasOwnProperty.call(el.dataset,atributo[1].replace(/-([a-z])/g,(_,c)=>c.toUpperCase()));
  return el.tagName===seletor.toUpperCase();
}

function pagina({definicao,instancia,responder}={}) {
  const elementos=new Map(),chamadas=[],pastas=[],avisos=[],navegacoes=[];
  class E {
    constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.eventos={};this.className='';this._value='';this.textContent='';this.hidden=false;this.disabled=false;this.style={};}
    append(...filhos){filhos.forEach(f=>{if(typeof f==='string'){const t=new E('text');t.textContent=f;f=t;}if(f.parentNode)f.remove();f.parentNode=this;this.children.push(f);});}
    appendChild(f){this.append(f);return f;}
    replaceChildren(...filhos){this.children.forEach(f=>f.parentNode=null);this.children=[];this.append(...filhos);}
    remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(f=>f!==this);this.parentNode=null;}
    setAttribute(n,v){this.attributes[n]=String(v);}
    getAttribute(n){return this.attributes[n]??null;}
    removeAttribute(n){delete this.attributes[n];}
    toggleAttribute(n){if(n in this.attributes)delete this.attributes[n];else this.attributes[n]='';}
    addEventListener(n,fn){(this.eventos[n] ||= []).push(fn);}
    async emitir(n){for(const fn of this.eventos[n]||[])await fn({target:this,preventDefault(){},stopPropagation(){}});}
    querySelectorAll(s){return this.children.flatMap(f=>[...(s.split(',').some(parte=>corresponde(f,parte.trim()))?[f]:[]),...f.querySelectorAll(s)]);}
    querySelector(s){return this.querySelectorAll(s)[0]||null;}
    closest(s){for(let e=this;e;e=e.parentNode)if(corresponde(e,s))return e;return null;}
    contains(e){return e===this||this.children.some(f=>f.contains(e));}
    focus(){this.focado=true;}
    reset(){this.querySelectorAll('input,select,textarea').forEach(e=>e.value=e.tagName==='SELECT'?(e.children[0]?.value||''):'');}
    reportValidity(){return true;}
    showModal(){this.open=true;}
    close(){this.open=false;this.emitir('close');}
    get selectedIndex(){return this.tagName==='SELECT'?this.children.findIndex(e=>e.value===this.value):0;}
    set value(v){this._value=String(v);}
    get value(){return this._value;}
  }
  function id(nome,tag='div',pai){const el=new E(tag);el.id=nome;elementos.set('#'+nome,el);if(pai)pai.append(el);return el;}
  const raiz=id('automacoes'),form=id('automacao-form','form'),dialogo=id('automacao-dialogo','dialog');dialogo.append(form);
  const entrada=id('automacoes-dados','script');
  const catalogo=definicao||{id:'radar/rss.py',nome:'Blogs e newsletters',ajuda:'Escolha os feeds.',config:{feeds:['https://padrao.test/feed'],maximo_por_feed:4},requer:[],parametros:[{nome:'feeds',rotulo:'Feeds',tipo:'lista',padrao:['https://padrao.test/feed']},{nome:'maximo_por_feed',rotulo:'Máximo',tipo:'numero',padrao:4}]};
  const atual=instancia||{id:'legado:rss',definicao:catalogo.id,nome:'Fontes da equipe',destino:'Clientes/Pesquisa',config:{feeds:['https://equipe.test/artigos','https://cliente.test/feed'],maximo_por_feed:9},mapeamento:{},a_cada:'12h',diario_as:'',ativo:true,legado:{modulo:'radar',script:'rss.py'},codigo_nativo:true,confianca:{confiavel:true,assinatura:'hash'},versao:'versao-1'};
  entrada.textContent=JSON.stringify({catalogo:[catalogo],instancias:atual.legado?[]:[atual],legadas:atual.legado?[atual]:[]});
  const ids=['automacao-config','automacao-config-avancada','automacao-mapeamentos','automacao-previa','automacao-previa-destino','automacao-previa-texto','automacao-form-estado','automacao-titulo','automacao-descricao','automacao-segredos','automacao-pasta-nome','automacao-pasta-atual','automacao-pasta-estado','automacao-pasta-lista','automacao-pasta-picker','automacao-horario-campo','automacao-atualizacao'];
  ids.forEach(n=>id(n,'div',form));
  ['automacao-nome','automacao-destino','automacao-horario'].forEach(n=>id(n,'input',form));
  ['automacao-salvar','automacao-mapear','automacao-pasta-abrir','automacao-pasta-voltar','automacao-pasta-usar','automacao-atualizar'].forEach(n=>id(n,'button',form));
  ['automacao-campos-avancados','automacao-parametros-avancados'].forEach(n=>{const d=id(n,'details',form);d.className='auto-campos-avancados';});
  const frequencia=id('automacao-frequencia','select',form);
  ['manual','diaria','1h','6h','12h','24h'].forEach(v=>{const o=new E('option');o.value=v;frequencia.append(o);});
  const linha=new E();linha.dataset.autoId=atual.id;raiz.append(linha);
  const editar=new E('button');editar.dataset.autoAcao='editar';linha.append(editar);
  const document={body:{dataset:{vaultId:'cofre-teste'}},querySelector:s=>elementos.get(s)||null,
    querySelectorAll:s=>s==='[data-auto-acao]'?[editar]:[],createElement:tag=>new E(tag),createTextNode:text=>{const t=new E('text');t.textContent=text;return t;},addEventListener(){}};
  const ui={mensagemErro:e=>e.message||'Falha',avisar:(texto,tipo)=>avisos.push({texto,tipo}),confirmar:async()=>true,ocupado:b=>{b.disabled=true;return ()=>{b.disabled=false;};}};
  const api=async(method,url,corpo)=>{chamadas.push({method,url,corpo:JSON.parse(JSON.stringify(corpo))});return responder?responder(url,corpo):{destino:corpo.destino,politica:'Uma nota por item.'};};
  const fetch=(url,opcoes)=>new Promise((resolve,reject)=>pastas.push({url,opcoes,resolve:d=>resolve({ok:true,json:async()=>d}),reject}));
  runInNewContext(fonte,{document,window:{Orquestra:{api},OrquestraInterface:ui},fetch,AbortController,innerWidth:1280,innerHeight:800,console,sessionStorage:{setItem(){},getItem(){return null;},removeItem(){}},location:{assign:u=>navegacoes.push(u),reload:()=>navegacoes.push('reload')}});
  return {get:n=>elementos.get('#'+n),editar,form,dialogo,linha,chamadas,pastas,avisos,navegacoes,E};
}

test('Configurar legado abre feeds realmente salvos e envia edição com versão atual',async()=>{
  const p=pagina();await p.editar.emitir('click');
  assert.equal(p.dialogo.open,true);assert.equal(p.get('automacao-nome').value,'Fontes da equipe');
  assert.equal(p.get('automacao-config').querySelector('textarea').value,'https://equipe.test/artigos\nhttps://cliente.test/feed');
  assert.equal(p.get('automacao-config-avancada').querySelector('input').value,'9');
  assert.equal(p.get('automacao-pasta-abrir').disabled,true);
  p.get('automacao-config').querySelector('textarea').value='https://nova-fonte.test/feed';
  await p.form.emitir('submit');
  assert.equal(p.chamadas[0].url,'/api/automacoes/legado/prever');
  assert.deepEqual(p.chamadas[0].corpo,{modulo:'radar',script:'rss.py',config:{feeds:['https://nova-fonte.test/feed'],maximo_por_feed:9},nome:'Fontes da equipe',a_cada:'12h',diario_as:'',versao:'versao-1'});
});

test('navegação de subpastas só escolhe ao confirmar e ignora resposta antiga',async()=>{
  const instancia={id:'auto-1',definicao:'radar/rss.py',nome:'Pesquisa',destino:'Clientes',config:{feeds:['https://teste.test/feed']},mapeamento:{},a_cada:'',diario_as:'',ativo:false,confianca:{confiavel:true}};
  const p=pagina({instancia});await p.editar.emitir('click');p.get('automacao-pasta-abrir').onclick();
  p.pastas[0].resolve({pastas:[{nome:'Empresa',rel:'Clientes/Empresa'}]});await tick();
  p.get('automacao-pasta-lista').children[0].onclick();
  assert.equal(p.get('automacao-destino').value,'Clientes');assert.equal(p.get('automacao-pasta-usar').disabled,true);
  p.get('automacao-pasta-voltar').onclick();
  assert.equal(p.pastas[1].opcoes.signal.aborted,true);
  p.pastas[2].resolve({pastas:[{nome:'Projetos',rel:'Projetos'}]});await tick();
  p.pastas[1].resolve({pastas:[{nome:'Resposta antiga',rel:'Clientes/Empresa/Velha'}]});await tick();
  assert.equal(p.get('automacao-pasta-atual').textContent,'Raiz do cofre');
  assert.equal(p.get('automacao-pasta-lista').children[0].children[0].textContent,'Projetos');
  assert.equal(p.get('automacao-destino').value,'Clientes');
  p.get('automacao-pasta-lista').children[0].onclick();p.pastas[3].resolve({pastas:[{nome:'Pesquisa',rel:'Projetos/Pesquisa'}]});await tick();
  p.get('automacao-pasta-lista').children[0].onclick();p.pastas[4].resolve({pastas:[]});await tick();
  assert.equal(p.get('automacao-destino').value,'Clientes');p.get('automacao-pasta-usar').onclick();
  assert.equal(p.get('automacao-destino').value,'Projetos/Pesquisa');assert.equal(p.get('automacao-pasta-picker').hidden,true);
});

test('código legado alterado durante edição não recebe autorização nem ativação automática',async()=>{
  const p=pagina({responder:async(url,corpo)=>url.endsWith('/prever')?{destino:'radar/itens',politica:'Uma nota por item.'}:{codigo_nativo:false,confianca:{confiavel:false,assinatura:'codigo-alterado'}}});
  await p.editar.emitir('click');await p.form.emitir('submit');await p.form.emitir('submit');
  assert.deepEqual(p.chamadas.map(c=>c.url),['/api/automacoes/legado/prever','/api/automacoes/legado/editar']);
  assert.deepEqual(p.navegacoes,['/ajustes/automacoes']);
});

test('configurar preserva campos extras e valores de registros customizados',async()=>{
  const definicao={id:'tarefas/recorrentes.py',nome:'Recorrências',ajuda:'Rotinas',config:{tarefas:[{titulo:'Padrão',quando:'sexta',prioridade:'media'}]},parametros:[{nome:'tarefas',rotulo:'Tarefas',tipo:'registros',padrao:[{titulo:'Padrão',quando:'sexta',prioridade:'media'}]}],requer:[]};
  const instancia={id:'rotina-1',definicao:definicao.id,nome:'Minha rotina',destino:'Projeto/Rotinas',config:{tarefas:[{titulo:'Revisar',quando:'todo dia',prioridade:'alta',estimativa:2,urgente:true,tags:['cliente'],dados:{preservar:'sim'}}],opcao_propria:'valor existente'},mapeamento:{},a_cada:'',diario_as:'',ativo:false,confianca:{confiavel:true}};
  const p=pagina({definicao,instancia});await p.editar.emitir('click');
  const titulo=p.get('automacao-config').querySelectorAll('input')[0];titulo.value='Revisar contrato';
  await p.form.emitir('submit');
  const config=p.chamadas[0].corpo.config;
  assert.equal(config.opcao_propria,'valor existente');
  assert.deepEqual(config.tarefas,[{titulo:'Revisar contrato',quando:'todo dia',prioridade:'alta',estimativa:2,urgente:true,tags:['cliente'],dados:{preservar:'sim'}}]);
});
