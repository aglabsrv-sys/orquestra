/* Explorador progressivo: carrega apenas os ramos abertos e mantém a navegação. */
(function () {
  'use strict';
  var raiz=document.querySelector('.explorador'); if (!raiz) return;
  var $=function(s,r){return (r||document).querySelector(s);}, $$=function(s,r){return Array.from((r||document).querySelectorAll(s));};
  var arvore=$('#arvore-pastas'), estado=$('#arvore-estado'), abertos=[], sequencia=0, pedido, grafoAtivo=null, geracaoGrafo=0, dadosGrafo=null;
  function pararGrafo(){
    geracaoGrafo++;
    if(grafoAtivo){grafoAtivo.parar();grafoAtivo=null;}
  }
  var alternar=$('#pastas-alternar');
  function mostrarPastas(aberto){raiz.classList.toggle('pastas-expandidas',aberto);alternar.setAttribute('aria-expanded',String(aberto));alternar.setAttribute('aria-label',aberto?'Recolher pastas':'Mostrar pastas');var atual=aberto&&$('#arvore-pastas .arvore-nota[aria-current]');if(atual)atual.scrollIntoView({block:'center'});}
  alternar.onclick=function(){mostrarPastas(alternar.getAttribute('aria-expanded')!=='true');};
  raiz.addEventListener('keydown',function(e){if(e.key==='Escape'&&raiz.classList.contains('pastas-expandidas')){mostrarPastas(false);alternar.focus();}});
  try { abertos=JSON.parse(sessionStorage.getItem('orq-pastas:'+document.body.dataset.vaultId)||'[]'); if (!Array.isArray(abertos)) abertos=[]; } catch(e) { abertos=[]; }
  function guardar(){try{sessionStorage.setItem('orq-pastas:'+document.body.dataset.vaultId,JSON.stringify($$('details[open]',arvore).map(function(d){return d.dataset.rel;})));}catch(e){/* Navegação continua sem armazenamento. */}}
  function ativo(expandir){var rel=$('#pasta-painel').dataset.rel; if(expandir)$$('details[data-rel]',arvore).forEach(function(d){if(rel===d.dataset.rel||rel.startsWith(d.dataset.rel+'/'))d.open=true;}); $$('a[data-pasta]',arvore).forEach(function(a){if(a.dataset.pasta===rel)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});}
  async function carregarRamo(rel,alvo){
    alvo.setAttribute('aria-busy','true');
    try{
      var r=await fetch('/api/pastas/arvore?ocultar_desligadas=1&rel='+encodeURIComponent(rel),{cache:'no-store'}); if(!r.ok)throw new Error('Não foi possível ler esta pasta.'); var dados=await r.json(); alvo.replaceChildren();
      dados.pastas.forEach(function(p){
        var d=document.createElement('details'), resumo=document.createElement('summary'), link=document.createElement('a'), filhos=document.createElement('div'); d.dataset.rel=p.rel; d.className='arvore-ramo'; filhos.className='arvore-filhos'; link.href=p.url;link.textContent=p.nome;link.dataset.pasta=p.rel;link.setAttribute('aria-expanded','false');resumo.appendChild(link);d.append(resumo,filhos);alvo.appendChild(d);
        var carregado=false;
        d.addEventListener('toggle',function(){link.setAttribute('aria-expanded',String(d.open));guardar();if(d.open&&!carregado){carregado=true;carregarRamo(p.rel,filhos).catch(function(){carregado=false;});}});
        var atual=new URL(location.href).searchParams.get('nota')||$('#pasta-painel').dataset.rel;
        if(abertos.includes(p.rel)||atual===p.rel||atual.startsWith(p.rel+'/'))d.open=true;
      });
      dados.notas.forEach(function(n){var a=document.createElement('a');a.href=n.url;a.className='arvore-nota';a.textContent=n.titulo;if(n.rel===new URL(location.href).searchParams.get('nota')){a.setAttribute('aria-current','page');requestAnimationFrame(function(){if(a.isConnected)a.scrollIntoView({block:'center'});});}alvo.appendChild(a);});
      (dados.arquivos||[]).forEach(function(n){var a=document.createElement('a');a.href=n.url;a.className='arvore-nota arquivo';a.textContent=n.nome;alvo.appendChild(a);});
      if(dados.total_notas>dados.notas.length){var mais=document.createElement('a');mais.href='/pastas/'+rel.split('/').map(encodeURIComponent).join('/');mais.textContent='Ver todas as notas';alvo.appendChild(mais);}
      if(!dados.pastas.length&&!dados.notas.length&&!(dados.arquivos||[]).length){var vazio=document.createElement('p');vazio.className='campo-ajuda';vazio.textContent='Pasta vazia';alvo.appendChild(vazio);}ativo();
    }catch(e){var b=document.createElement('button');b.className='botao pequeno';b.textContent='Tentar ler pasta novamente';alvo.replaceChildren(b);b.onclick=function(){carregarRamo(rel,alvo);};estado.textContent=e.message;}
    finally{alvo.removeAttribute('aria-busy');}
  }
  async function navegar(url,push){
    var numero=++sequencia;if(pedido)pedido.abort();pedido=new AbortController();var painel=$('#pasta-painel');painel.setAttribute('aria-busy','true');
    try{var r=await fetch(url,{signal:pedido.signal,cache:'no-store'});if(!r.ok)throw new Error('Não foi possível abrir a pasta.');var doc=new DOMParser().parseFromString(await r.text(),'text/html');if(numero!==sequencia)return;
      if(doc.body.dataset.vaultId!==document.body.dataset.vaultId||!$('#pasta-painel',doc)){location.assign(url);return;}var novoPainel=document.importNode($('#pasta-painel',doc),true);
      $('#pasta-grafo',novoPainel).replaceWith($('#pasta-grafo',painel));painel.replaceWith(novoPainel);var novos=document.importNode($('#pastas-dialogos',doc),true);$('#pastas-dialogos').replaceWith(novos);window.Orquestra.prepararPastas(novos);
      if(window.Orquestra.prepararPastasModulo)window.Orquestra.prepararPastasModulo();
      document.title=doc.title;var destino=new URL(url,location.href),visao=destino.searchParams.get('visao');
      if(push){
        visao=visao||visaoAtual;
        destino.searchParams.set('visao',visao);
        history.pushState({},'',destino.href);
      }
      aplicarVisao(visao||visaoGuardada(),false);ativo(true);$('#pasta-painel h1').setAttribute('tabindex','-1');$('#pasta-painel h1').focus({preventScroll:true});abrirSolicitada(url);
    }catch(e){if(e.name!=='AbortError')estado.textContent=e.message;}finally{if(numero===sequencia)$('#pasta-painel').removeAttribute('aria-busy');}
  }
  raiz.addEventListener('click',function(e){var a=e.target.closest('a');if(!a||e.defaultPrevented||e.button||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;var url=new URL(a.href,location.href);if(url.origin===location.origin&&/^\/(n|documento)\//.test(url.pathname)){e.preventDefault();abrirArquivo(url.href,a.textContent);return;}if(url.origin!==location.origin||!/^\/pastas(?:\/|$)/.test(url.pathname))return;e.preventDefault();var ramo=a.closest('.arvore-ramo');if(ramo&&a.hasAttribute('data-pasta'))ramo.open=true;mostrarPastas(false);navegar(url.href,true);});
  window.addEventListener('popstate',function(){if(/^\/pastas(?:\/|$)/.test(location.pathname))navegar(location.href,false);else location.reload();});
  var visaoAtual='grafo';
  function chaveVisao(){return 'orq-explorador:v2:'+document.body.dataset.vaultId+':'+$('#pasta-painel').dataset.rel;}
  function aplicarVisao(visao,lembrar){
    visaoAtual=visao==='grafo'?'grafo':visao==='colecao'?'colecao':'notas';var grafo=visaoAtual==='grafo';raiz.classList.toggle('com-grafo',grafo);raiz.classList.remove('lendo-nota');
    $('#pasta-leitor').hidden=true;$('#leitor-frame').src='about:blank';$('#pasta-notas').hidden=grafo;$('#pasta-grafo').hidden=!grafo;
    var colecao=$('#explorador-colecao'),lista=$('#explorador-lista');
    if(colecao&&lista){colecao.hidden=visaoAtual!=='colecao';lista.hidden=visaoAtual==='colecao';}
    $$('[data-pasta-visao]').forEach(function(x){x.setAttribute('aria-pressed',x.dataset.pastaVisao===visaoAtual?'true':'false');});
    if(lembrar)try{localStorage.setItem(chaveVisao(),visaoAtual);}catch(e){/* A escolha continua válida nesta página. */}
    if(grafo)iniciarGrafo();else pararGrafo();
  }
  function visaoGuardada(){try{return localStorage.getItem(chaveVisao())||'grafo';}catch(e){return 'grafo';}}
  function restaurarVisao(){aplicarVisao(new URL(location.href).searchParams.get('visao')||visaoGuardada(),false);}
  raiz.addEventListener('click',function(e){
    var b=e.target.closest('[data-pasta-visao]');
    if(b){
      var url=new URL(location.href);
      url.searchParams.set('visao',b.dataset.pastaVisao);
      history.replaceState(history.state,'',url.href);
      aplicarVisao(b.dataset.pastaVisao,true);
    }
    if(e.target.closest('#abrir-config-pastas'))$('#config-pastas').showModal();
  });
  document.addEventListener('click',function(e){
    if(e.target.closest('[data-fechar-config]')){$('#config-pastas').close();return;}
    var aba=e.target.closest('[data-config-pastas]');
    if(!aba)return;
    $$('[data-config-pastas]').forEach(function(b){
      var escolhida=b===aba;
      b.setAttribute('aria-pressed',String(escolhida));
      document.getElementById(b.getAttribute('aria-controls')).hidden=!escolhida;
    });
  });
  var estadosGrafo=new WeakMap();
  async function iniciarGrafo(){
    if(grafoAtivo){grafoAtivo.realcar();return;}
    var geracao=++geracaoGrafo,canvas=$('#grafo-canvas'),mensagem=$('#grafo-estado');
    mensagem.textContent='Lendo ligações…';
    if(!dadosGrafo){
      dadosGrafo=fetch('/api/pastas/grafo',{cache:'no-store'}).then(function(r){
        if(!r.ok)throw new Error('Não foi possível carregar as ligações.');
        return r.json();
      }).catch(function(erro){dadosGrafo=null;throw erro;});
    }
    try{
      var dados=await dadosGrafo;
      if(geracao!==geracaoGrafo||!canvas.isConnected||$('#pasta-grafo').hidden)return;
      var lista=$('#grafo-notas');
      if(!lista.childElementCount){
        var itens=document.createDocumentFragment();
        dados.notas.forEach(function(n){var li=document.createElement('li'),a=document.createElement('a');a.href=n.url;a.textContent=n.titulo;li.appendChild(a);itens.appendChild(li);});
        lista.appendChild(itens);
      }
      grafoAtivo=desenharGrafo(canvas,dados);
    }catch(e){if(geracao===geracaoGrafo&&canvas.isConnected)mensagem.textContent=e.message;}
  }

  // Forças do grafo, com os mesmos nomes e escalas do Obsidian. Ficam neste navegador.
  var FORCAS_PADRAO={centro:.52,repulsao:10,links:1,distancia:174};
  function chaveForcas(){return 'orq-grafo-forcas:'+document.body.dataset.vaultId;}
  function lerForcas(){
    var f=Object.assign({},FORCAS_PADRAO);
    var limites={centro:[0,1],repulsao:[0,20],links:[0,1],distancia:[30,500]};
    try{var salvo=JSON.parse(localStorage.getItem(chaveForcas())||'{}');Object.keys(f).forEach(function(k){if(salvo[k]==null)return;var v=Number(salvo[k]);if(isFinite(v))f[k]=Math.max(limites[k][0],Math.min(limites[k][1],v));});}catch(e){/* Armazenamento opcional. */}
    return f;
  }
  function ligarForcas(f,aoMudar){
    var campos={centro:'#grafo-centro',repulsao:'#grafo-repulsao',links:'#grafo-links',distancia:'#grafo-distancia'};
    function mostrar(k){var c=$(campos[k]);if(!c)return;c.value=f[k];var saida=c.parentElement.querySelector('output');if(saida)saida.textContent=k==='distancia'?String(Math.round(f[k])):Number(f[k]).toFixed(2);}
    function guardar(){try{localStorage.setItem(chaveForcas(),JSON.stringify(f));}catch(e){/* Armazenamento opcional. */}}
    Object.keys(campos).forEach(function(k){var c=$(campos[k]);if(!c)return;mostrar(k);c.oninput=function(){f[k]=Number(c.value);mostrar(k);guardar();aoMudar();};});
    var padrao=$('#grafo-forcas-padrao');
    if(padrao)padrao.onclick=function(){Object.assign(f,FORCAS_PADRAO);Object.keys(campos).forEach(mostrar);guardar();aoMudar();};
  }
  function desenharGrafo(canvas,dados){
    var g=canvas.getContext('2d'),largura=0,altura=0,quadro=0,iteracao=0,zoom=1,dx=0,dy=0,sobre=null,teclado=false,arrastou=false,gesto=null,encerrado=false;
    var busca=$('#grafo-busca'),isoladas=$('#grafo-isoladas'),rotulos=$('#grafo-rotulos'),ponteiros=new Map();
    var forcas=lerForcas();
    var reduz=window.matchMedia('(prefers-reduced-motion: reduce)'),indice=new Map(),vizinhos=new Map(),anterior=estadosGrafo.get(canvas);
    var nos=dados.notas.map(function(n,i){var ang=i*2.399963,r=12*Math.sqrt(i+.5),salvo=anterior&&anterior.posicoes.get(n.id);return Object.assign({},n,{x:Math.cos(ang)*r,y:Math.sin(ang)*r,vx:0,vy:0,grau:0},salvo||{});});
    nos.forEach(function(n){indice.set(n.id,n);vizinhos.set(n.id,new Set());});
    var linhas=dados.ligacoes.map(function(l){return[indice.get(l[0]),indice.get(l[1])];}).filter(function(l){return l[0]&&l[1];});
    linhas.forEach(function(l){l[0].grau++;l[1].grau++;vizinhos.get(l[0].id).add(l[1].id);vizinhos.get(l[1].id).add(l[0].id);});
    // Cada par troca forças iguais. Em cofres grandes, uma amostra fixa de pares
    // limita o custo por passo e evita oscilações na fase de acomodação.
    var metade=Math.floor((nos.length-1)/2),amostra=Math.min(32,metade),saltos=[];
    for(var j=0;j<amostra;j++)saltos.push(1+Math.floor(j*metade/amostra));
    var visiveis=nos,idsVisiveis=new Set(nos.map(function(n){return n.id;}));
    // O zoom organiza o espaço, mas não pode reduzir uma nota a um subpixel.
    function raio(n){return (3.6+Math.min(5.4,Math.sqrt(n.grau)*.85))*Math.min(1.6,.8+.2*Math.sqrt(zoom))/zoom;}
    function tamanho(){var b=canvas.getBoundingClientRect(),d=Math.min(2,window.devicePixelRatio||1);if(!b.width||!b.height||(b.width===largura&&b.height===altura))return false;largura=b.width;altura=b.height;canvas.width=largura*d;canvas.height=altura*d;canvas.parentElement.style.setProperty('--grafo-filtros-altura',Math.max(48,altura-66)+'px');g.setTransform(d,0,0,d,0,0);pintar();return true;}
    var selecionada,prefixo,temPasta=false;
    function lerContexto(){
      var rel=$('#pasta-painel').dataset.rel;
      prefixo=rel?rel+'/':'';
      temPasta=!!prefixo&&nos.some(naPasta);
      selecionada=indice.get(new URL(location.href).searchParams.get('nota'))||null;
      sobre=selecionada;
    }
    function naPasta(n){return n.id.startsWith(prefixo);}
    function realce(n){return sobre?n===sobre||vizinhos.get(sobre.id).has(n.id):!temPasta||naPasta(n);}
    lerContexto();
    var hoverQuadro=0,ultimoPintar=0;
    function pintar(){
      if(encerrado)return;
      // A transição do realce depende do tempo, não de quantas vezes se pinta:
      // ~0,3 s para assentar, igual com o mouse parado ou em movimento.
      var agora=performance.now(),dt=ultimoPintar?Math.min(64,agora-ultimoPintar):16,k=reduz.matches?1:1-Math.exp(-dt/95),pendente=false;ultimoPintar=agora;
      function ir(obj,chave,destino,inicial){var atual=obj[chave]==null?inicial:obj[chave],novo=atual+(destino-atual)*k;if(Math.abs(novo-destino)<.004)novo=destino;else pendente=true;obj[chave]=novo;}
      var vizinhanca=sobre?vizinhos.get(sobre.id):null;
      nos.forEach(function(n){ir(n,'enfase',realce(n)?1:.34,1);ir(n,'foco',n===sobre?1:0,0);ir(n,'vizinho',(vizinhanca&&vizinhanca.has(n.id))||(!sobre&&temPasta&&naPasta(n))?1:0,0);});
      linhas.forEach(function(l){
        var toca=sobre?l[0]===sobre||l[1]===sobre:temPasta&&naPasta(l[0])&&naPasta(l[1]);
        ir(l,'enfase',toca?.8:sobre||temPasta?.16:.3,.3);ir(l,'foco',toca?1:0,0);
      });
      desenhar();
      if(pendente&&!hoverQuadro&&!document.hidden)hoverQuadro=requestAnimationFrame(function(){hoverQuadro=0;pintar();});
      if(!pendente)ultimoPintar=0;
    }
    var coresLidas={};
    function rgbDe(cor){
      if(coresLidas[cor])return coresLidas[cor];
      var antes=g.fillStyle;g.fillStyle='#000';g.fillStyle=cor;var v=g.fillStyle;g.fillStyle=antes;
      var hex=/^#([0-9a-f]{6})$/i.exec(v),r;
      if(hex){var n=parseInt(hex[1],16);r=[n>>16&255,n>>8&255,n&255];}else{var p=v.match(/[\d.]+/g)||[0,0,0];r=[+p[0],+p[1],+p[2]];}
      return (coresLidas[cor]=r);
    }
    function misturar(a,b,t){
      if(!(t>0))return a;if(t>=1)return b;
      var x=rgbDe(a),y=rgbDe(b);
      return 'rgb('+Math.round(x[0]+(y[0]-x[0])*t)+','+Math.round(x[1]+(y[1]-x[1])*t)+','+Math.round(x[2]+(y[2]-x[2])*t)+')';
    }
    function desenhar(){
      if(encerrado)return;
      var cor=getComputedStyle(document.documentElement),texto=cor.getPropertyValue('--texto').trim(),suave=cor.getPropertyValue('--texto-suave').trim(),destaque=cor.getPropertyValue('--destaque').trim(),fundo=cor.getPropertyValue('--fundo').trim();
      g.clearRect(0,0,largura,altura);g.save();g.translate(largura/2+dx,altura/2+dy);g.scale(zoom,zoom);
      linhas.forEach(function(l){if(!idsVisiveis.has(l[0].id)||!idsVisiveis.has(l[1].id))return;var f=l.foco||0;g.strokeStyle=misturar(suave,destaque,f);g.globalAlpha=l.enfase==null?.3:l.enfase;g.lineWidth=(.85+.55*f)/zoom;g.beginPath();g.moveTo(l[0].x,l[0].y);g.lineTo(l[1].x,l[1].y);g.stroke();});
      // Rótulos só surgem quando há espaço, e a vizinhança fica legível ao passar o mouse.
      var caixas=[];
      visiveis.slice().sort(function(a,b){return (a.foco||0)-(b.foco||0);}).forEach(function(n){
        var ativo=n===sobre,proximo=realce(n),f=n.foco||0,v=n.vizinho||0,enfase=n.enfase==null?1:n.enfase;g.globalAlpha=enfase;
        if(f>.01){g.globalAlpha=enfase*f;g.beginPath();g.strokeStyle=destaque;g.lineWidth=1.4/zoom;g.arc(n.x,n.y,raio(n)*(1+.3*f)+(2+3*f)/zoom,0,Math.PI*2);g.stroke();g.globalAlpha=enfase;}
        g.beginPath();g.fillStyle=misturar(misturar(texto,destaque,n.grau?0:.6),destaque,Math.max(f,v*.45));g.arc(n.x,n.y,raio(n)*(1+.3*f),0,Math.PI*2);g.fill();
        if(!rotulos.checked||!proximo||(!sobre&&((visiveis.length>18&&zoom<.6)||(visiveis.length>70&&zoom<1.4))))return;
        var titulo=n.titulo.length>40?n.titulo.slice(0,38)+'…':n.titulo,fonte=10.5+1.5*f;g.font=(f>.5?'500 ':'')+(fonte/zoom)+'px system-ui';
        var sx=n.x*zoom+largura/2+dx,sy=n.y*zoom+altura/2+dy;if(sx<0||sx>largura||sy<0||sy>altura)return;
        var limite=(largura-16)/zoom,w=g.measureText(titulo).width;while(w>limite&&titulo.length>2){titulo=titulo.slice(0,-2)+'…';w=g.measureText(titulo).width;}
        var esquerda=(-largura/2-dx+8)/zoom,direita=(largura/2-dx-8)/zoom,topo=(-altura/2-dy+54)/zoom,baixo=(altura/2-dy-8)/zoom;
        var x=Math.max(esquerda,Math.min(direita-w,n.x-w/2)),y=n.y+raio(n)+16/zoom;if(ativo)y=Math.max(topo+12/zoom,Math.min(baixo,y));else if(y-12/zoom<topo||y>baixo)return;
        var caixa={x:x,y:y-12/zoom,w:w,h:16/zoom};
        if(!ativo&&caixas.some(function(c){return caixa.x<c.x+c.w&&caixa.x+caixa.w>c.x&&caixa.y<c.y+c.h&&caixa.y+caixa.h>c.y;}))return;
        caixas.push(caixa);g.globalAlpha=Math.min(1,(.7+.15*v+.3*f)*enfase);g.lineJoin='round';g.strokeStyle=fundo;g.lineWidth=4/zoom;g.strokeText(titulo,x,y);g.fillStyle=misturar(suave,texto,Math.max(f,v*.5));g.fillText(titulo,x,y);
      });g.restore();
      if(!visiveis.length){g.fillStyle=suave;g.font='13px system-ui';g.textAlign='center';g.fillText(nos.length?'Nenhuma nota corresponde ao filtro.':'As ligações entre suas notas aparecem aqui.',largura/2,altura/2);g.textAlign='start';}
    }
    function simular(){
      var energia=Math.max(.03,Math.pow(1-iteracao/200,1.5));
      function repelir(n,outro){
        var x=n.x-outro.x,y=n.y-outro.y,forca=forcas.repulsao*8*energia/(x*x+y*y+64);
        var fx=x*forca,fy=y*forca;
        n.vx+=fx;n.vy+=fy;outro.vx-=fx;outro.vy-=fy;
      }
      nos.forEach(function(n,i){
        saltos.forEach(function(salto){repelir(n,nos[(i+salto)%nos.length]);});
        if(nos.length%2===0&&i<nos.length/2)repelir(n,nos[i+nos.length/2]);
        n.vx-=n.x*forcas.centro*.005*energia;
        n.vy-=n.y*forcas.centro*.005*energia;
      });
      linhas.forEach(function(l){
        var a=l[0],b=l[1],x=b.x-a.x,y=b.y-a.y,d=Math.hypot(x,y)||1;
        var f=(d-forcas.distancia)*.035*forcas.links*energia/(d*Math.max(1,Math.sqrt(Math.min(a.grau,b.grau))));
        a.vx+=x*f;a.vy+=y*f;b.vx-=x*f;b.vy-=y*f;
      });
      nos.forEach(function(n){
        if(gesto&&gesto.no===n){n.vx=n.vy=0;return;}
        n.vx*=.58;n.vy*=.58;
        var velocidade=Math.hypot(n.vx,n.vy),limite=8*energia+.2;
        if(velocidade>limite){n.vx*=limite/velocidade;n.vy*=limite/velocidade;}
        n.x+=n.vx;n.y+=n.vy;
      });
      iteracao++;
    }
    var ultimoPasso=0;
    function passo(agora){
      quadro=0;
      if(encerrado||document.hidden||!canvas.isConnected||$('#pasta-grafo').hidden)return;
      if(agora-ultimoPasso>=14){ultimoPasso=agora;simular();pintar();}
      animar();
    }
    function animar(){if(!quadro&&!reduz.matches&&iteracao<200&&!document.hidden)quadro=requestAnimationFrame(passo);}
    function aquecer(quanto){
      iteracao=Math.max(0,Math.min(iteracao,200-quanto));
      if(reduz.matches){while(iteracao<200)simular();pintar();}else animar();
    }
    function ponto(e){var b=canvas.getBoundingClientRect();return{x:(e.clientX-b.left-largura/2-dx)/zoom,y:(e.clientY-b.top-altura/2-dy)/zoom};}
    function atingir(p){return visiveis.find(function(n){return Math.hypot(n.x-p.x,n.y-p.y)<raio(n)+7/zoom;})||null;}
    canvas.oncontextmenu=function(e){var no=atingir(ponto(e));if(!no||!window.Orquestra.abrirMenuContexto)return;e.preventDefault();e.stopPropagation();window.Orquestra.abrirMenuContexto({elemento:canvas,rel:no.id,url:no.url},e);};
    function aproximar(fator,cx,cy){

      var anterior=zoom,novo=Math.max(.01,Math.min(6,zoom*fator));cx=cx==null?largura/2:cx;cy=cy==null?altura/2:cy;
      dx=cx-largura/2-(cx-largura/2-dx)*novo/anterior;dy=cy-altura/2-(cy-altura/2-dy)*novo/anterior;zoom=novo;pintar();
    }
    canvas.onpointerdown=function(e){

      if(e.button&&e.button!==0)return;teclado=false;canvas.focus({preventScroll:true});ponteiros.set(e.pointerId,{x:e.clientX,y:e.clientY});canvas.setPointerCapture(e.pointerId);sobre=atingir(ponto(e));arrastou=false;
      gesto={x:e.clientX,y:e.clientY,inicioX:e.clientX,inicioY:e.clientY,no:sobre};
      if(ponteiros.size===2){var ps=Array.from(ponteiros.values());gesto={dist:Math.hypot(ps[1].x-ps[0].x,ps[1].y-ps[0].y),x:(ps[0].x+ps[1].x)/2,y:(ps[0].y+ps[1].y)/2};arrastou=true;}
    };
    canvas.onpointermove=function(e){
      teclado=false;
      if(ponteiros.has(e.pointerId))ponteiros.set(e.pointerId,{x:e.clientX,y:e.clientY});
      if(gesto&&ponteiros.size===2){var ps=Array.from(ponteiros.values()),dist=Math.hypot(ps[1].x-ps[0].x,ps[1].y-ps[0].y),cx=(ps[0].x+ps[1].x)/2,cy=(ps[0].y+ps[1].y)/2,b=canvas.getBoundingClientRect();if(gesto.dist)aproximar(dist/gesto.dist,cx-b.left,cy-b.top);dx+=cx-gesto.x;dy+=cy-gesto.y;gesto={dist:dist,x:cx,y:cy};arrastou=true;}
      else if(gesto){
        if(Math.hypot(e.clientX-gesto.inicioX,e.clientY-gesto.inicioY)>4)arrastou=true;
        if(arrastou&&gesto.no){var p=ponto(e);gesto.no.x=p.x;gesto.no.y=p.y;gesto.no.vx=gesto.no.vy=0;sobre=gesto.no;aquecer(60);}
        else if(arrastou){dx+=e.clientX-gesto.x;dy+=e.clientY-gesto.y;}
        gesto.x=e.clientX;gesto.y=e.clientY;
      }else sobre=atingir(ponto(e))||selecionada;
      canvas.style.cursor=gesto?'grabbing':sobre?'pointer':'grab';pintar();
    };
    function soltar(e){
      var no=gesto&&gesto.no;ponteiros.delete(e.pointerId);
      if(e.type==='pointerup'&&!arrastou&&no)abrirArquivo(no.url,no.titulo);
      var reposicionado=!!no&&arrastou;
      gesto=null;arrastou=ponteiros.size>0;canvas.style.cursor='grab';
      if(reposicionado)aquecer(120);else pintar();
    }
    canvas.onpointerup=soltar;canvas.onpointercancel=soltar;canvas.onpointerleave=function(){if(!gesto){sobre=selecionada;pintar();}};
    canvas.onwheel=function(e){e.preventDefault();var b=canvas.getBoundingClientRect();aproximar(Math.exp(-Math.max(-100,Math.min(100,e.deltaY))*.002),e.clientX-b.left,e.clientY-b.top);};
    canvas.onkeydown=function(e){
      if((e.key==='ContextMenu'||e.shiftKey&&e.key==='F10')&&sobre&&window.Orquestra.abrirMenuContexto){e.preventDefault();e.stopPropagation();var caixa=canvas.getBoundingClientRect();window.Orquestra.abrirMenuContexto({elemento:canvas,rel:sobre.id,url:sobre.url},{clientX:caixa.left+largura/2+dx+sobre.x*zoom,clientY:caixa.top+altura/2+dy+sobre.y*zoom},true);return;}
      if(['+','=','-','0','Home','ArrowRight','ArrowDown','ArrowLeft','ArrowUp','Enter','Escape'].indexOf(e.key)<0)return;e.preventDefault();
      if(e.key==='+'||e.key==='=')aproximar(1.2);else if(e.key==='-')aproximar(1/1.2);else if(e.key==='0'||e.key==='Home')recentralizar();
      else if(e.key==='Enter'&&sobre)abrirArquivo(sobre.url,sobre.titulo);
      else if(e.key==='Escape'){sobre=null;teclado=false;pintar();}
      else if(e.key.startsWith('Arrow')&&visiveis.length){var direcao=e.key==='ArrowLeft'||e.key==='ArrowUp'?-1:1,i=visiveis.indexOf(sobre);sobre=visiveis[(i+direcao+visiveis.length)%visiveis.length];teclado=true;dx=-sobre.x*zoom;dy=-sobre.y*zoom;$('#grafo-estado').textContent=sobre.titulo+' · Enter para abrir';pintar();}
    };
    canvas.onblur=function(){if(teclado){sobre=null;teclado=false;pintar();}};
    function centralizar(){
      if(!visiveis.length){zoom=1;dx=dy=0;pintar();return;}
      var minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
      visiveis.forEach(function(n){minX=Math.min(minX,n.x);maxX=Math.max(maxX,n.x);minY=Math.min(minY,n.y);maxY=Math.max(maxY,n.y);});
      var lateral=Math.min(44,largura*.09),topo=Math.min(54,Math.max(40,altura*.26)),base=Math.min(20,Math.max(12,altura*.08));
      zoom=Math.max(.01,Math.min(1.5,(largura-lateral*2)/(maxX-minX+48),(altura-topo-base)/(maxY-minY+48)));dx=-(minX+maxX)*zoom/2;dy=-(minY+maxY)*zoom/2+(topo-base)/2;pintar();
    }
    function filtrar(enquadrar){
      var termo=busca.value.trim().toLocaleLowerCase();visiveis=nos.filter(function(n){return (isoladas.checked||n.grau>0)&&(!termo||n.titulo.toLocaleLowerCase().includes(termo));});idsVisiveis=new Set(visiveis.map(function(n){return n.id;}));sobre=selecionada;
      $('#grafo-estado').textContent=visiveis.length+' de '+nos.length+' notas · '+linhas.filter(function(l){return idsVisiveis.has(l[0].id)&&idsVisiveis.has(l[1].id);}).length+' ligações'+(dados.limitado?' · visualização parcial':'');
      $('#grafo-sem-ligacoes').hidden=!visiveis.length||linhas.some(function(l){return idsVisiveis.has(l[0].id)&&idsVisiveis.has(l[1].id);});
      $$('#grafo-notas li').forEach(function(li,i){li.hidden=!idsVisiveis.has(nos[i].id);});if(enquadrar!==false){centralizar();}else pintar();
    }
    ligarForcas(forcas,function(){aquecer(200);});
    function recentralizar(){centralizar();}
    $('#grafo-centralizar').onclick=recentralizar;$('#grafo-mais').onclick=function(){aproximar(1.25);};$('#grafo-menos').onclick=function(){aproximar(.8);};busca.oninput=filtrar;isoladas.onchange=filtrar;rotulos.onchange=pintar;
    // Acomodar sem animação também entrega uma disposição útil no modo reduzido.
    if(!anterior){for(var i=0;i<(reduz.matches?200:Math.max(12,Math.min(120,Math.floor(12000/Math.max(1,nos.length)))));i++)simular();}else{zoom=anterior.zoom;dx=anterior.dx;dy=anterior.dy;iteracao=anterior.iteracao;}
    var observar=new ResizeObserver(function(){
      if(tamanho()&&!gesto)centralizar();
    });
    observar.observe(canvas);tamanho();filtrar(!anterior);animar();
    function visibilidade(){if(document.hidden){cancelAnimationFrame(quadro);quadro=0;}else animar();}
    function movimento(){if(reduz.matches){cancelAnimationFrame(quadro);quadro=0;for(var i=iteracao;i<200;i++)simular();pintar();}else animar();}
    document.addEventListener('visibilitychange',visibilidade);reduz.addEventListener('change',movimento);
    function parar(){estadosGrafo.set(canvas,{zoom:zoom,dx:dx,dy:dy,iteracao:iteracao,posicoes:new Map(nos.map(function(n){return[n.id,{x:n.x,y:n.y}];}))});encerrado=true;cancelAnimationFrame(quadro);cancelAnimationFrame(hoverQuadro);observar.disconnect();document.removeEventListener('visibilitychange',visibilidade);reduz.removeEventListener('change',movimento);}
    return {parar:parar,realcar:function(){lerContexto();pintar();}};
  }
  function abrirArquivo(url,titulo){
    mostrarPastas(false);
    pararGrafo();raiz.classList.add('lendo-nota');
    $('#pasta-notas').hidden=true;$('#pasta-grafo').hidden=true;$('#pasta-leitor').hidden=false;
    var frame=$('#leitor-frame'),u=new URL(url,location.href);
    $('#leitor-titulo').textContent=titulo||decodeURIComponent(u.pathname.split('/').pop());
    $$('.arvore-nota',arvore).forEach(function(a){if(new URL(a.href).pathname===u.pathname)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    if(u.pathname.startsWith('/documento/'))frame.setAttribute('sandbox','');else{frame.removeAttribute('sandbox');u.searchParams.set('explorador','1');}
    frame.src=u.href;
    var voltarLeitor=visaoAtual==='grafo'?'Voltar ao grafo':'Voltar às notas';$('#leitor-fechar').setAttribute('aria-label',voltarLeitor);$('#leitor-fechar').title=voltarLeitor;
    $('#leitor-fechar').onclick=function(){aplicarVisao(visaoAtual,false);};
  }
  window.addEventListener('message',function(e){
    var frame=$('#leitor-frame');if(e.origin!==location.origin||!frame||e.source!==frame.contentWindow||!e.data)return;
    if(e.data.tipo==='orquestra:leitor-voltar'){aplicarVisao(visaoAtual,false);return;}
    if(e.data.tipo==='orquestra:leitor-excluiu'){
      var origem=new URL(location.href);origem.searchParams.delete('nota');origem.searchParams.set('visao',visaoAtual);
      pararGrafo();dadosGrafo=null;estadosGrafo.delete($('#grafo-canvas'));$('#grafo-notas').replaceChildren();
      history.replaceState(history.state,'',origem.href);navegar(origem.href,false);carregarRamo('',arvore);return;
    }
    if(e.data.tipo!=='orquestra:leitor')return;
    var u;try{u=new URL(e.data.url,location.href);}catch(erro){return;}if(u.origin!==location.origin)return;
    if(/^\/(n|documento)\//.test(u.pathname))abrirArquivo(u.href,e.data.titulo);
    else if(/^\/pastas(?:\/|$)/.test(u.pathname))navegar(u.href,true);
  });
  carregarRamo('',arvore);
  restaurarVisao();
  function abrirSolicitada(){ativo(true);}
  abrirSolicitada(location.href);
})();
