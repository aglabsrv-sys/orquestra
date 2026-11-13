/* Explorador progressivo: carrega apenas os ramos abertos e mantém a navegação. */
(function () {
  'use strict';
  var raiz=document.querySelector('.explorador'); if (!raiz) return;
  var $=function(s,r){return (r||document).querySelector(s);}, $$=function(s,r){return Array.from((r||document).querySelectorAll(s));};
  var arvore=$('#arvore-pastas'), estado=$('#arvore-estado'), abertos=[], sequencia=0, pedido, pararGrafo=function(){};
  try { abertos=JSON.parse(sessionStorage.getItem('orq-pastas:'+document.body.dataset.vaultId)||'[]'); if (!Array.isArray(abertos)) abertos=[]; } catch(e) { abertos=[]; }
  function guardar(){try{sessionStorage.setItem('orq-pastas:'+document.body.dataset.vaultId,JSON.stringify($$('details[open]',arvore).map(function(d){return d.dataset.rel;})));}catch(e){/* Navegação continua sem armazenamento. */}}
  function ativo(){var rel=$('#pasta-painel').dataset.rel; $$('a[data-pasta]',arvore).forEach(function(a){if(a.dataset.pasta===rel)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});}
  async function carregarRamo(rel,alvo){
    alvo.setAttribute('aria-busy','true');
    try{
      var r=await fetch('/api/pastas/arvore?rel='+encodeURIComponent(rel),{cache:'no-store'}); if(!r.ok)throw new Error('Não foi possível ler esta pasta.'); var dados=await r.json(); alvo.replaceChildren();
      dados.pastas.forEach(function(p){
        var d=document.createElement('details'), resumo=document.createElement('summary'), link=document.createElement('a'), filhos=document.createElement('div'); d.dataset.rel=p.rel; d.className='arvore-ramo'; filhos.className='arvore-filhos'; link.href=p.url;link.textContent=p.nome;link.dataset.pasta=p.rel;resumo.appendChild(link);d.append(resumo,filhos);alvo.appendChild(d);
        var carregado=false;
        d.addEventListener('toggle',function(){guardar();if(d.open&&!carregado){carregado=true;carregarRamo(p.rel,filhos).catch(function(){carregado=false;});}});
        var atual=$('#pasta-painel').dataset.rel;
        if(abertos.includes(p.rel)||atual===p.rel||atual.startsWith(p.rel+'/'))d.open=true;
      });
      dados.notas.forEach(function(n){var a=document.createElement('a');a.href=n.url;a.className='arvore-nota';a.textContent=n.titulo;alvo.appendChild(a);});
      (dados.arquivos||[]).forEach(function(n){var a=document.createElement('a');a.href=n.url;a.className='arvore-nota arquivo';a.textContent=n.nome;alvo.appendChild(a);});
      if(dados.total_notas>dados.notas.length){var mais=document.createElement('a');mais.href='/pastas/'+rel.split('/').map(encodeURIComponent).join('/');mais.textContent='Ver todas as notas';alvo.appendChild(mais);}
      if(!dados.pastas.length&&!dados.notas.length&&!(dados.arquivos||[]).length){var vazio=document.createElement('p');vazio.className='campo-ajuda';vazio.textContent='Pasta vazia';alvo.appendChild(vazio);}ativo();
    }catch(e){var b=document.createElement('button');b.className='botao pequeno';b.textContent='Tentar ler pasta novamente';alvo.replaceChildren(b);b.onclick=function(){carregarRamo(rel,alvo);};estado.textContent=e.message;}
    finally{alvo.removeAttribute('aria-busy');}
  }
  async function navegar(url,push){
    var numero=++sequencia;if(pedido)pedido.abort();pedido=new AbortController();var painel=$('#pasta-painel');painel.setAttribute('aria-busy','true');
    try{var r=await fetch(url,{signal:pedido.signal,cache:'no-store'});if(!r.ok)throw new Error('Não foi possível abrir a pasta.');var doc=new DOMParser().parseFromString(await r.text(),'text/html');if(numero!==sequencia)return;
      if(doc.body.dataset.vaultId!==document.body.dataset.vaultId||!$('#pasta-painel',doc)){location.assign(url);return;}pararGrafo();painel.replaceWith(document.importNode($('#pasta-painel',doc),true));var novos=document.importNode($('#pastas-dialogos',doc),true);$('#pastas-dialogos').replaceWith(novos);window.Orquestra.prepararPastas(novos);document.title=doc.title;iniciarGrafo();if(push)history.pushState({},'',url);ativo();$('#pasta-painel h1').setAttribute('tabindex','-1');$('#pasta-painel h1').focus({preventScroll:true});
    }catch(e){if(e.name!=='AbortError')estado.textContent=e.message;}finally{if(numero===sequencia)$('#pasta-painel').removeAttribute('aria-busy');}
  }
  raiz.addEventListener('click',function(e){var a=e.target.closest('a');if(!a||e.defaultPrevented||e.button||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;var url=new URL(a.href,location.href);if(url.origin===location.origin&&/^\/(n|documento)\//.test(url.pathname)){e.preventDefault();abrirArquivo(url.href,a.textContent);return;}if(url.origin!==location.origin||!/^\/pastas(?:\/|$)/.test(url.pathname))return;e.preventDefault();navegar(url.href,true);});
  window.addEventListener('popstate',function(){if(/^\/pastas(?:\/|$)/.test(location.pathname))navegar(location.href,false);else location.reload();});
  raiz.addEventListener('click',function(e){var b=e.target.closest('[data-pasta-visao]');if(!b)return;var grafo=b.dataset.pastaVisao==='grafo';$('#pasta-leitor').hidden=true;$('#leitor-frame').src='about:blank';$('#pasta-notas').hidden=grafo;$('#pasta-grafo').hidden=!grafo;$$('[data-pasta-visao]').forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});if(grafo)iniciarGrafo();else pararGrafo();});
  var grafos=new WeakMap();
  async function iniciarGrafo(){
    pararGrafo();var canvas=$('#grafo-canvas'),mensagem=$('#grafo-estado'),rel=$('#pasta-painel').dataset.rel;mensagem.textContent='Lendo ligações…';
    try{var dados=grafos.get(canvas);if(!dados){var r=await fetch('/api/pastas/grafo?rel='+encodeURIComponent(rel),{cache:'no-store'});if(!r.ok)throw new Error('Não foi possível carregar as ligações.');dados=await r.json();grafos.set(canvas,dados);}if(!canvas.isConnected||$('#pasta-grafo').hidden)return;
      mensagem.textContent=dados.notas.length+' notas · '+dados.ligacoes.length+' ligações'+(dados.limitado?' · visualização parcial':'');
      var lista=$('#grafo-notas');lista.replaceChildren();dados.notas.forEach(function(n){var li=document.createElement('li'),a=document.createElement('a');a.href=n.url;a.textContent=n.titulo;li.appendChild(a);lista.appendChild(li);});desenharGrafo(canvas,dados);
    }catch(e){mensagem.textContent=e.message;}
  }
  function desenharGrafo(canvas,dados){
    var g=canvas.getContext('2d'),largura=0,altura=0,quadro=0,iteracao=0,zoom=1,dx=0,dy=0,pressionado=null,arrastou=false,sobre=null;
    var nos=dados.notas.map(function(n,i){var ang=i*2.39996,r=35+Math.sqrt(i)*14;return Object.assign({},n,{x:Math.cos(ang)*r,y:Math.sin(ang)*r,vx:0,vy:0,grau:0});}),indice=new Map(nos.map(function(n){return[n.id,n];}));
    var linhas=dados.ligacoes.map(function(l){return[indice.get(l[0]),indice.get(l[1])];}).filter(function(l){return l[0]&&l[1];});linhas.forEach(function(l){l[0].grau++;l[1].grau++;});
    function tamanho(){var b=canvas.getBoundingClientRect(),d=window.devicePixelRatio||1;largura=b.width;altura=b.height;canvas.width=largura*d;canvas.height=altura*d;g.setTransform(d,0,0,d,0,0);pintar();}
    function pintar(){var cor=getComputedStyle(document.documentElement);g.clearRect(0,0,largura,altura);g.save();g.translate(largura/2+dx,altura/2+dy);g.scale(zoom,zoom);g.strokeStyle=cor.getPropertyValue('--texto-suave');g.globalAlpha=.18;g.lineWidth=.7/zoom;g.beginPath();linhas.forEach(function(l){g.moveTo(l[0].x,l[0].y);g.lineTo(l[1].x,l[1].y);});g.stroke();g.globalAlpha=1;
      nos.forEach(function(n){g.beginPath();g.fillStyle=cor.getPropertyValue(n===sobre?'--destaque':'--texto-suave');g.arc(n.x,n.y,3+Math.min(6,n.grau*.6),0,Math.PI*2);g.fill();if(nos.length<35||zoom>1.2){g.fillStyle=cor.getPropertyValue('--texto-suave');g.font=(11/zoom)+'px system-ui';g.fillText(n.titulo.length>30?n.titulo.slice(0,28)+'…':n.titulo,n.x+10/zoom,n.y+4/zoom);}});
      if(sobre){g.fillStyle=cor.getPropertyValue('--texto');g.font=(12/zoom)+'px sans-serif';g.fillText(sobre.titulo,sobre.x+10/zoom,sobre.y-10/zoom);}g.restore();}
    function passo(){quadro=0;if(document.hidden||!canvas.isConnected||$('#pasta-grafo').hidden)return;
      // Repulsão amostrada: trabalho linear por quadro, inclusive em cofres maiores.
      nos.forEach(function(n,i){for(var j=1;j<=Math.min(14,nos.length-1);j++){var outro=nos[(i+j*37+iteracao)%nos.length];if(outro===n)continue;var x=n.x-outro.x,y=n.y-outro.y,d=x*x+y*y+15;n.vx+=x*35/d;n.vy+=y*35/d;}n.vx-=n.x*.0008;n.vy-=n.y*.0008;});
      linhas.forEach(function(l){var x=l[1].x-l[0].x,y=l[1].y-l[0].y,d=Math.sqrt(x*x+y*y)||1,f=(d-75)*.001;l[0].vx+=x/d*f;l[0].vy+=y/d*f;l[1].vx-=x/d*f;l[1].vy-=y/d*f;});
      nos.forEach(function(n){n.x+=n.vx;n.y+=n.vy;n.vx*=.82;n.vy*=.82;});iteracao++;pintar();if(iteracao<160)quadro=requestAnimationFrame(passo);else centralizar();
    }
    function ponto(e){var b=canvas.getBoundingClientRect();return{x:(e.clientX-b.left-largura/2-dx)/zoom,y:(e.clientY-b.top-altura/2-dy)/zoom};}
    canvas.onpointermove=function(e){if(pressionado){dx+=e.clientX-pressionado.x;dy+=e.clientY-pressionado.y;arrastou=true;pressionado={x:e.clientX,y:e.clientY};}var p=ponto(e);sobre=nos.find(function(n){return Math.hypot(n.x-p.x,n.y-p.y)<12/zoom;})||null;canvas.style.cursor=sobre?'pointer':pressionado?'grabbing':'grab';pintar();};
    canvas.onpointerdown=function(e){pressionado={x:e.clientX,y:e.clientY};arrastou=false;canvas.setPointerCapture(e.pointerId);};canvas.onpointerup=function(){pressionado=null;if(sobre&&!arrastou)abrirArquivo(sobre.url,sobre.titulo);};canvas.onpointercancel=function(){pressionado=null;};canvas.onwheel=function(e){e.preventDefault();zoom=Math.max(.2,Math.min(3,zoom*(e.deltaY<0?1.1:.9)));pintar();};canvas.onkeydown=function(e){if(e.key==='+'||e.key==='='){e.preventDefault();zoom=Math.min(3,zoom*1.1);pintar();}if(e.key==='-'){e.preventDefault();zoom=Math.max(.2,zoom/1.1);pintar();}};
    function centralizar(){
      if(!nos.length){zoom=1;dx=dy=0;pintar();return;}
      var xs=nos.map(function(n){return n.x;}),ys=nos.map(function(n){return n.y;});
      var minX=Math.min.apply(null,xs),maxX=Math.max.apply(null,xs),minY=Math.min.apply(null,ys),maxY=Math.max.apply(null,ys);
      zoom=Math.max(.05,Math.min(1.8,(largura-100)/(maxX-minX+60),(altura-100)/(maxY-minY+60)));
      dx=-(minX+maxX)*zoom/2;dy=-(minY+maxY)*zoom/2;pintar();
    }
    $('#grafo-centralizar').onclick=centralizar;
    var observar=new ResizeObserver(tamanho);observar.observe(canvas);tamanho();$('#grafo-centralizar').click();
    var reduz=window.matchMedia('(prefers-reduced-motion: reduce)').matches;if(!reduz)quadro=requestAnimationFrame(passo);
    function visibilidade(){if(!document.hidden&&iteracao<160&&!quadro&&!reduz)quadro=requestAnimationFrame(passo);}document.addEventListener('visibilitychange',visibilidade);
    pararGrafo=function(){cancelAnimationFrame(quadro);observar.disconnect();document.removeEventListener('visibilitychange',visibilidade);};
  }
  function abrirArquivo(url,titulo){
    pararGrafo();
    $('#pasta-notas').hidden=true;$('#pasta-grafo').hidden=true;$('#pasta-leitor').hidden=false;
    var frame=$('#leitor-frame'),u=new URL(url,location.href);
    $('#leitor-titulo').textContent=titulo||decodeURIComponent(u.pathname.split('/').pop());
    $$('.arvore-nota',arvore).forEach(function(a){if(new URL(a.href).pathname===u.pathname)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    if(u.pathname.startsWith('/documento/'))frame.setAttribute('sandbox','');else{frame.removeAttribute('sandbox');u.searchParams.set('explorador','1');}
    frame.src=u.href;
    $('#leitor-fechar').onclick=function(){frame.src='about:blank';$('#pasta-leitor').hidden=true;$('#pasta-grafo').hidden=false;iniciarGrafo();};
  }
  window.addEventListener('message',function(e){
    var frame=$('#leitor-frame');if(e.origin!==location.origin||!frame||e.source!==frame.contentWindow||!e.data||e.data.tipo!=='orquestra:leitor')return;
    var u;try{u=new URL(e.data.url,location.href);}catch(erro){return;}if(u.origin!==location.origin)return;
    if(/^\/(n|documento)\//.test(u.pathname))abrirArquivo(u.href,e.data.titulo);
    else if(/^\/pastas(?:\/|$)/.test(u.pathname))navegar(u.href,true);
  });
  carregarRamo('',arvore);
  iniciarGrafo();
})();
