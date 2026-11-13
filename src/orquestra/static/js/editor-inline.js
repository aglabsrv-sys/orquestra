/* Edição no lugar: a nota renderizada vira o próprio editor.

   Um duplo clique deixa o texto editável sem trocar a aparência: tabelas continuam
   tabelas, listas continuam listas, e dá para passar de um bloco a outro direto.
   Cada bloco de primeiro nível traz as linhas do Markdown de onde veio
   (data-md-inicio/fim). Ao mudar, só os blocos alterados são convertidos de volta
   para Markdown e recolocados nessas linhas; o resto do arquivo fica byte a byte
   igual. Links internos, embeds e imagens guardam a fonte original em data-md e
   são tratados como peças inteiras.

   Quando não há mapa confiável (rascunho recuperado, alias de link em várias
   linhas) ou a pessoa pede para selecionar tudo, o editor cai no modo texto:
   uma caixa com o Markdown da nota inteira. */
(function (raiz) {
  'use strict';

  // ------------------------------------------------------------ trechos da fonte

  function intervalo(texto, inicio, fim) {
    var linhas=[0],achado,quebras=/\n/g;
    while((achado=quebras.exec(texto)))linhas.push(achado.index+1);
    inicio=Math.max(0,Math.min(linhas.length,Number(inicio)||0));
    fim=Math.max(inicio,Math.min(linhas.length,Number(fim)||0));
    var a=inicio<linhas.length?linhas[inicio]:texto.length,b=fim<linhas.length?linhas[fim]:texto.length;
    var conteudo=texto.slice(a,b),quebra=(conteudo.match(/\n+$/)||[''])[0];
    return {inicio:a,fim:b,conteudo:quebra?conteudo.slice(0,-quebra.length):conteudo,quebra:quebra};
  }
  function substituir(texto,trecho,conteudo) {
    // Bloco apagado: sai com as linhas em branco que o separavam do próximo.
    if(conteudo==='')return texto.slice(0,trecho.inicio)+texto.slice(trecho.fim).replace(/^(?:[ \t]*\n)+/,'');
    return texto.slice(0,trecho.inicio)+conteudo+trecho.quebra+texto.slice(trecho.fim);
  }
  /* Aplica várias trocas [{inicio,fim,conteudo}] (em linhas da fonte original), do fim para o começo. */
  function aplicar(texto,trocas) {
    return trocas.slice().sort(function(a,b){return b.inicio-a.inicio;}).reduce(function(atual,t){
      return substituir(atual,intervalo(atual,t.inicio,t.fim),t.conteudo);
    },texto);
  }

  // ------------------------------------------------------------ HTML -> Markdown

  // O texto digitado é Markdown: `**x**`, `[[Nota]]` ou `- item` viram formatação ao
  // salvar, como no Obsidian. Por isso nada é escapado.
  function escapar(texto){return texto;}
  function comeco(texto){return texto;}
  function fonteDe(el) {
    var original=el.getAttribute&&el.getAttribute('data-md');
    if(original===null||original===undefined)return original;
    var antes=el.getAttribute('data-md-texto');
    if(antes===null||el.textContent===antes)return original;
    // O rótulo de um [[link]] foi editado: mantém o alvo e troca só o texto visível.
    var wiki=original.match(/^(!?)\[\[([^|\]]+)(?:\|[^\]]*)?\]\]$/);
    var texto=el.textContent.replace(/[\[\]|\n]/g,' ').trim();
    if(!wiki)return original;
    if(!texto)return '';
    return wiki[1]+'[['+wiki[2]+(texto===wiki[2].trim()?'':'|'+texto)+']]';
  }
  function inline(no) {
    var saida='';
    Array.prototype.forEach.call(no.childNodes,function(filho){
      if(filho.nodeType===3){saida+=escapar(filho.nodeValue.replace(/\u00a0/g,' ').replace(/[ \t]*\n[ \t]*/g,' '));return;}
      if(filho.nodeType!==1)return;
      var nome=filho.nodeName,original=fonteDe(filho);
      if(original!==null&&original!==undefined){saida+=original;return;}
      if(nome==='BR'){saida+='\n';return;}
      if(nome==='INPUT')return;
      var dentro=inline(filho);
      // Espaços nas pontas ficam fora da marca: `**Linha **` não seria negrito no Markdown.
      var marcar=function(marca){var m=dentro.match(/^(\s*)([\s\S]*?)(\s*)$/);saida+=m[2]?m[1]+marca+m[2]+marca+m[3]:dentro;};
      if(nome==='STRONG'||nome==='B'){marcar('**');return;}
      if(nome==='EM'||nome==='I'){marcar('*');return;}
      if(nome==='DEL'||nome==='S'||nome==='STRIKE'){marcar('~~');return;}
      if(nome==='CODE'){var codigo=filho.textContent,cerca=codigo.indexOf('`')>=0?'``':'`';saida+=cerca+codigo+cerca;return;}
      if(nome==='A'){var destino=filho.getAttribute('data-md-alvo')||filho.getAttribute('href')||'';saida+='['+dentro+']('+destino+')';return;}
      if(nome==='IMG'){saida+='!['+(filho.getAttribute('alt')||'')+']('+(filho.getAttribute('data-md-alvo')||filho.getAttribute('src')||'')+')';return;}
      if(nome==='DIV'||nome==='P'){saida+=(saida&&!/\n$/.test(saida)?'\n':'')+dentro;return;}
      saida+=dentro;
    });
    return saida;
  }
  function limpar(texto){return texto.replace(/ *\n */g,'\n').replace(/ {2,}/g,' ').trim();}
  function linhas(texto,prefixo,seguinte){return texto.split('\n').map(function(l,i){return (i?seguinte:prefixo)+l;}).join('\n');}
  function lista(el) {
    var ordenada=el.nodeName==='OL',numero=Number(el.getAttribute('start'))||1,itens=[];
    Array.prototype.forEach.call(el.children,function(li){
      if(li.nodeName!=='LI')return;
      var marcador=ordenada?(numero++)+'. ':'- ',recuo=' '.repeat(marcador.length),caixa=li.querySelector(':scope > input[type=checkbox]');
      if(caixa)marcador+=caixa.checked?'[x] ':'[ ] ';
      var texto=[],sub=[];
      Array.prototype.forEach.call(li.childNodes,function(filho){
        if(filho.nodeType===1&&(filho.nodeName==='UL'||filho.nodeName==='OL'))sub.push(linhas(lista(filho),recuo,recuo));
        else if(filho.nodeType===1&&filho.nodeName==='P')texto.push(limpar(inline(filho)));
        else{var pedaco=document.createElement('span');pedaco.appendChild(filho.cloneNode(true));texto.push(inline(pedaco));}
      });
      var corpo=limpar(texto.join(''));
      itens.push(linhas(marcador+corpo,'',recuo)+(sub.length?'\n'+sub.join('\n'):''));
    });
    return itens.join('\n');
  }
  function tabela(el,original) {
    var linhasTabela=Array.prototype.slice.call(el.querySelectorAll('tr'));
    if(!linhasTabela.length)return '';
    var celulas=function(tr){return Array.prototype.map.call(tr.children,function(td){return limpar(inline(td)).replace(/\n/g,' ').replace(/\|/g,'\\|');});};
    var cabeca=celulas(linhasTabela[0]),largura=cabeca.length;
    var alinhar=Array.prototype.map.call(linhasTabela[0].children,function(th){
      var a=(th.style&&th.style.textAlign)||th.getAttribute('align')||'';
      return a==='center'?':---:':a==='right'?'---:':a==='left'?':---':'---';
    });
    var fmt=function(c){while(c.length<largura)c.push('');return '| '+c.slice(0,largura).join(' | ')+' |';};
    var separador='| '+alinhar.join(' | ')+' |',antigo=(original||'').split('\n')[1]||'';
    if(/^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(antigo)&&antigo.replace(/^\s*\||\|\s*$/g,'').split('|').length===largura)separador=antigo;
    return [fmt(cabeca),separador].concat(linhasTabela.slice(1).map(function(tr){return fmt(celulas(tr));})).join('\n');
  }
  function bloco(no,original) {
    if(no.nodeType===3)return comeco(limpar(escapar(no.nodeValue.replace(/\u00a0/g,' '))));
    if(no.nodeType!==1)return '';
    var nome=no.nodeName,propria=fonteDe(no);
    if(propria!==null&&propria!==undefined)return propria;
    if(/^H[1-6]$/.test(nome))return '#'.repeat(Number(nome[1]))+' '+limpar(inline(no)).replace(/\n/g,' ');
    if(nome==='UL'||nome==='OL')return lista(no);
    if(nome==='TABLE')return tabela(no,original);
    if(nome==='HR')return '---';
    if(nome==='PRE'){
      var codigo=no.querySelector('code')||no,linguagem=((codigo.className||'').match(/language-(\S+)/)||['',''])[1];
      var texto=codigo.textContent.replace(/\n$/,''),cerca=/```/.test(texto)?'~~~~':'```';
      return cerca+linguagem+'\n'+texto+'\n'+cerca;
    }
    if(nome==='BLOCKQUOTE')return linhas(markdown(Array.prototype.slice.call(no.childNodes)),'> ','> ').replace(/^> $/gm,'>');
    // Parágrafos e as <div> que o navegador cria ao apertar Enter.
    var temBlocos=Array.prototype.some.call(no.children,function(f){return /^(P|DIV|UL|OL|TABLE|PRE|BLOCKQUOTE|H[1-6]|HR)$/.test(f.nodeName);});
    if(nome==='DIV'&&temBlocos)return markdown(Array.prototype.slice.call(no.childNodes));
    return comeco(limpar(inline(no)));
  }
  function markdown(nos,original) {
    return nos.map(function(no,i){return bloco(no,i===0?original:'');}).filter(function(t){return t.trim()!=='';}).join('\n\n');
  }

  // ------------------------------------------------------------ editor

  // Só elementos sem texto viram peças inteiras: ilhas não editáveis no meio de uma
  // linha atrapalham o cursor do navegador. Links continuam editáveis como texto.
  var PECAS='img, input, hr, [data-md]:empty';

  function criar(ver,fonte,opcoes) {
    opcoes=opcoes||{};
    var ativo=null,renderizado=fonte.value;
    fonte.id='nota-fonte';

    function mapasDeTopo() {
      var blocos=[];
      Array.prototype.forEach.call(ver.children,function(el){
        var mapa=el.hasAttribute('data-md-inicio')?el:el.querySelector(':scope > [data-md-inicio]');
        if(mapa)blocos.push({el:el,inicio:Number(mapa.dataset.mdInicio),fim:Number(mapa.dataset.mdFim)});
      });
      return blocos;
    }

    // -------- modo rico: o próprio texto renderizado, editável
    function abrirRico() {
      var blocos=mapasDeTopo(),selecao=window.getSelection(),faixa=selecao&&selecao.rangeCount?selecao.getRangeAt(0).cloneRange():null;
      var html=ver.innerHTML;
      // As quebras de linha do HTML entre blocos (e entre itens de lista e células)
      // não aparecem na tela, mas o cursor cai nelas e o texto digitado iria para
      // o lugar errado. Fora da edição, o HTML original volta inteiro.
      [ver].concat(Array.prototype.slice.call(ver.querySelectorAll('ul,ol,li,table,thead,tbody,tr,blockquote'))).forEach(function(pai){
        Array.prototype.slice.call(pai.childNodes).forEach(function(no){
          if(no.nodeType!==3||no.nodeValue.trim())return;
          var vizinhos=[no.previousSibling,no.nextSibling];
          if(pai===ver||vizinhos.every(function(v){return !v||(v.nodeType===1&&/^(LI|UL|OL|P|TR|TD|TH|THEAD|TBODY|BLOCKQUOTE|TABLE|PRE|INPUT)$/.test(v.nodeName));}))no.remove();
        });
      });
      Array.prototype.forEach.call(ver.querySelectorAll(PECAS),function(p){p.setAttribute('contenteditable','false');p.dataset.peca='';});
      Array.prototype.forEach.call(ver.querySelectorAll('[data-md]'),function(el){el.setAttribute('data-md-texto',el.textContent);});
      blocos.forEach(function(b){b.html=b.el.outerHTML;});
      var base=fonte.value;
      ver.setAttribute('contenteditable','true');ver.spellcheck=true;
      ver.classList.add('em-edicao','edicao-rica');
      ver.setAttribute('aria-label','Texto da nota em edição');
      function recompor() {
        var segmentos=blocos.map(function(){return [];}),atual=-1;
        Array.prototype.forEach.call(ver.childNodes,function(no){
          for(var i=0;i<blocos.length;i++)if(blocos[i].el===no){atual=i;break;}
          if(no.nodeType===3&&!no.nodeValue.trim())return;
          segmentos[Math.max(0,atual)].push(no);
        });
        var trocas=[];
        blocos.forEach(function(b,i){
          var nos=segmentos[i];
          if(nos.length===1&&nos[0]===b.el&&b.el.outerHTML===b.html)return;
          trocas.push({inicio:b.inicio,fim:b.fim,conteudo:markdown(nos,intervalo(base,b.inicio,b.fim).conteudo)});
        });
        fonte.value=trocas.length?aplicar(base,trocas):base;
      }
      function aoDigitar(){recompor();if(opcoes.aoMudar)opcoes.aoMudar();}
      function aoTeclar(e){if(e.key==='Escape'){e.preventDefault();if(opcoes.aoConcluir)opcoes.aoConcluir();}}
      function aoColar(e){ // só texto: HTML colado de fora traria estilos e estruturas que o Markdown não guarda
        if(!e.clipboardData)return;
        e.preventDefault();
        document.execCommand('insertText',false,e.clipboardData.getData('text/plain'));
      }
      ver.addEventListener('input',aoDigitar);ver.addEventListener('keydown',aoTeclar);ver.addEventListener('paste',aoColar);
      ativo={rico:true,contem:function(alvo){return ver.contains(alvo);},fechar:function(){
        ver.removeEventListener('input',aoDigitar);ver.removeEventListener('keydown',aoTeclar);ver.removeEventListener('paste',aoColar);
        ver.removeAttribute('contenteditable');ver.removeAttribute('aria-label');ver.classList.remove('em-edicao','edicao-rica');
        // Volta ao HTML de antes; depois de salvar, quem chamou troca pelo HTML novo do servidor.
        ver.innerHTML=html;
        Array.prototype.forEach.call(ver.querySelectorAll('[data-peca]'),function(p){p.removeAttribute('contenteditable');delete p.dataset.peca;});
        Array.prototype.forEach.call(ver.querySelectorAll('[data-md-texto]'),function(el){el.removeAttribute('data-md-texto');});
      },focar:function(){ver.focus({preventScroll:true});}};
      ver.focus({preventScroll:true});
      // O duplo clique já deixou o cursor (ou a palavra) no lugar certo: mantém.
      if(faixa&&ver.contains(faixa.startContainer)){
        // Duplo clique no vazio depois de um texto seleciona até o bloco seguinte;
        // digitar apagaria o que estiver lá. Nesse caso fica só o cursor no ponto clicado.
        var topo=function(no){while(no&&no.parentNode!==ver)no=no.parentNode;return no;};
        if(topo(faixa.startContainer)!==topo(faixa.endContainer))faixa.collapse(true);
        selecao.removeAllRanges();selecao.addRange(faixa);
      }
    }

    // -------- modo texto: o Markdown inteiro numa caixa com a tipografia da nota
    function abrirTexto() {
      var estilo=getComputedStyle(ver),medida=ver.getBoundingClientRect(),nodes=Array.from(ver.childNodes);
      var area=document.createElement('textarea');
      area.id='editor';area.className='nota-editor-bloco';area.dataset.editorBloco='';area.value=fonte.value;area.spellcheck=true;area.maxLength=1000000;
      area.setAttribute('aria-label','Editar a nota em Markdown');area.setAttribute('aria-describedby','estado-salvo');
      ['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color'].forEach(function(chave){area.style[chave]=estilo[chave];});
      ver.replaceChildren(area);ver.classList.add('em-edicao');
      function ajustar(){area.style.height='0';area.style.height=Math.max(medida.height,area.scrollHeight,32)+'px';}
      area.addEventListener('input',function(){fonte.value=area.value;ajustar();if(opcoes.aoMudar)opcoes.aoMudar();});
      area.addEventListener('keydown',function(e){if(e.key==='Escape'){e.preventDefault();if(opcoes.aoConcluir)opcoes.aoConcluir();}});
      ativo={rico:false,area:area,contem:function(alvo){return alvo===area||area.contains(alvo);},fechar:function(){
        if(area.isConnected)ver.replaceChildren.apply(ver,nodes);ver.classList.remove('em-edicao');
      },focar:function(){area.focus();}};
      ajustar();area.focus();area.setSelectionRange(area.value.length,area.value.length);
    }

    // Cada bloco com texto precisa apontar para linhas com texto na fonte. Se não,
    // o mapa está desalinhado e gravar no lugar dele poderia mexer em outra parte.
    function mapaConfere() {
      var blocos=mapasDeTopo();
      return blocos.length>0&&blocos.every(function(b){
        return !b.el.textContent.trim()||intervalo(fonte.value,b.inicio,b.fim).conteudo.trim()!=='';
      });
    }
    function abrir(alvo,tudo) {
      if(ativo){ativo.focar();return;}
      var confiavel=fonte.value===renderizado&&mapaConfere();
      if(tudo||!confiavel)abrirTexto();else abrirRico(alvo);
    }
    function fechar(){if(!ativo)return;var atual=ativo;ativo=null;atual.fechar();}
    return {
      abrir:abrir,fechar:fechar,
      atualizar:function(texto){renderizado=texto;},
      contem:function(alvo){return !!ativo&&ativo.contem(alvo);},
      selecionar:function(){fechar();abrirTexto();ativo.area.select();},
      get ativo(){return !!ativo;},
      get rico(){return !!ativo&&ativo.rico;}
    };
  }

  var api={criar:criar,intervalo:intervalo,substituir:substituir,aplicar:aplicar,markdown:markdown};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else raiz.OrquestraEdicao=api;
})(typeof globalThis!=='undefined'?globalThis:this);
