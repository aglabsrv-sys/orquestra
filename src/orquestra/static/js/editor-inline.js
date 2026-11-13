/* Live preview: só o bloco em edição mostra Markdown. O restante fica intacto. */
(function (raiz) {
  'use strict';
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
    return texto.slice(0,trecho.inicio)+conteudo+trecho.quebra+texto.slice(trecho.fim);
  }
  function criar(ver,fonte,opcoes) {
    opcoes=opcoes||{};
    var ativo=null,renderizado=fonte.value;
    fonte.id='nota-fonte';
    function fechar() {
      if(!ativo)return;
      var atual=ativo;ativo=null;
      if(atual.area.isConnected){if(atual.todos)ver.replaceChildren.apply(ver,atual.nodes);else atual.area.replaceWith(atual.bloco);}
      ver.classList.remove('em-edicao');
    }
    function abrir(alvo,tudo) {
      if(ativo){ativo.area.focus();return;}
      var mapa=alvo&&alvo.closest?alvo.closest('[data-md-inicio][data-md-fim]'):null;
      if(!mapa||!ver.contains(mapa))mapa=ver.querySelector('[data-md-inicio][data-md-fim]');
      var trechoMapeado=mapa?intervalo(fonte.value,mapa.dataset.mdInicio,mapa.dataset.mdFim):null;
      // Um bloco visível nunca pode abrir um trecho vazio por desalinhamento da fonte.
      var mapaVazio=trechoMapeado&&!trechoMapeado.conteudo.trim()&&mapa.textContent.trim();
      var completo=tudo||fonte.value!==renderizado||!mapa||mapaVazio;
      var bloco=completo?ver:mapa;
      while(bloco!==ver&&bloco.parentElement!==ver)bloco=bloco.parentElement;
      var trecho=completo?{inicio:0,fim:fonte.value.length,conteudo:fonte.value,quebra:''}:trechoMapeado;
      var area=document.createElement('textarea'),estilo=getComputedStyle(bloco),medida=bloco.getBoundingClientRect(),base=fonte.value;
      area.id='editor';area.className='nota-editor-bloco';area.dataset.editorBloco='';area.value=trecho.conteudo;area.spellcheck=true;area.maxLength=1000000;
      area.setAttribute('aria-label','Editar este trecho da nota em Markdown');area.setAttribute('aria-describedby','estado-salvo');
      ['fontFamily','fontSize','fontWeight','fontStyle','lineHeight','letterSpacing','textAlign','color','marginTop','marginBottom'].forEach(function(chave){area.style[chave]=estilo[chave];});
      area.style.minHeight=Math.max(32,medida.height)+'px';
      var nodes=completo?Array.from(ver.childNodes):null;
      ativo={area:area,bloco:bloco,todos:completo,nodes:nodes};
      if(completo)ver.replaceChildren(area);else bloco.replaceWith(area);
      ver.classList.add('em-edicao');
      function ajustar(){area.style.height='0';area.style.height=Math.max(medida.height,area.scrollHeight,32)+'px';}
      area.addEventListener('input',function(){fonte.value=substituir(base,trecho,area.value);ajustar();if(opcoes.aoMudar)opcoes.aoMudar();});
      area.addEventListener('keydown',function(e){if(e.key==='Escape'){e.preventDefault();if(opcoes.aoConcluir)opcoes.aoConcluir();}});
      ajustar();area.focus();
      // O duplo clique deixa a seleção de texto no local de edição, sem mudar a rolagem.
      area.setSelectionRange(area.value.length,area.value.length);
    }
    return {
      abrir:abrir,fechar:fechar,
      atualizar:function(texto){renderizado=texto;},
      contem:function(alvo){return !!ativo&&(alvo===ativo.area||ativo.area.contains(alvo));},
      selecionar:function(){fechar();abrir(null,true);ativo.area.select();},
      get ativo(){return !!ativo;}
    };
  }
  var api={criar:criar,intervalo:intervalo,substituir:substituir};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else raiz.OrquestraEdicao=api;
})(typeof globalThis!=='undefined'?globalThis:this);
