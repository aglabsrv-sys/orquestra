(function () {
  'use strict';
  var raiz = document.getElementById('habitos-pagina'); if (!raiz) return;
  var $ = function (s,r) { return (r || document).querySelector(s); };
  var dados = JSON.parse($('#habitos-dados').textContent), itens = new Map(dados.itens.map(function (i) { return [i.rel,i]; }));
  var editor = $('#habito-editor'), form = $('#habito-form'), atual = null, ocupado = false, sujo = false, foco = null;
  var grade=$('#habitos-grade'), arraste=null, versaoOrdem=dados.versao_ordem, estadoOrdem=$('#habitos-ordem-estado');
  function cartoes(){return Array.from(grade.querySelectorAll('[data-habito]'));}
  function restaurarOrdem(antes){antes.forEach(function(card){grade.appendChild(card);});}
  async function guardarOrdem(antes,alca){
    var ordem=cartoes().map(function(card){return card.dataset.habito;});
    if(ordem.join('\n')===antes.map(function(card){return card.dataset.habito;}).join('\n'))return;
    ocupado=true;estadoOrdem.textContent='Salvando ordem…';
    document.dispatchEvent(new CustomEvent('orquestra:config-salva'));
    try{var r=await api('/api/habitos/ordem',{ordem:ordem,versao:versaoOrdem});versaoOrdem=r.versao;estadoOrdem.textContent='Ordem salva.';}
    catch(erro){restaurarOrdem(antes);estadoOrdem.textContent=erro.message;}
    finally{ocupado=false;if(alca.isConnected)alca.focus({preventScroll:true});}
  }
  grade.addEventListener('pointerdown',function(e){
    var alca=e.target.closest('[data-habito-arrastar]');if(!alca||e.button!==0||ocupado)return;
    e.preventDefault();alca.focus({preventScroll:true});alca.setPointerCapture(e.pointerId);
    arraste={alca:alca,card:alca.closest('[data-habito]'),antes:cartoes(),x:e.clientX,y:e.clientY,id:e.pointerId,moveu:false};
  });
  window.addEventListener('pointermove',function(e){
    if(!arraste||e.pointerId!==arraste.id)return;
    if(!arraste.moveu&&Math.hypot(e.clientX-arraste.x,e.clientY-arraste.y)<6)return;
    arraste.moveu=true;arraste.card.classList.add('habito-ordenando');grade.classList.add('reordenando');
    var sobre=document.elementFromPoint(e.clientX,e.clientY),alvo=sobre&&sobre.closest('[data-habito]');
    if(alvo&&alvo!==arraste.card&&alvo.parentElement===grade){
      var lista=cartoes();if(lista.indexOf(arraste.card)<lista.indexOf(alvo))alvo.after(arraste.card);else alvo.before(arraste.card);
    }
    if(e.clientY<70)window.scrollBy(0,-12);else if(e.clientY>innerHeight-70)window.scrollBy(0,12);
  });
  function terminarOrdem(e,cancelar){
    if(!arraste||e.pointerId!==arraste.id)return;
    var gesto=arraste;arraste=null;gesto.card.classList.remove('habito-ordenando');grade.classList.remove('reordenando');
    if(gesto.alca.hasPointerCapture(e.pointerId))gesto.alca.releasePointerCapture(e.pointerId);
    if(cancelar)restaurarOrdem(gesto.antes);else guardarOrdem(gesto.antes,gesto.alca);
  }
  window.addEventListener('pointerup',function(e){terminarOrdem(e,false);});
  window.addEventListener('pointercancel',function(e){terminarOrdem(e,true);});
  window.addEventListener('blur',function(){if(arraste)terminarOrdem({pointerId:arraste.id},true);});
  grade.addEventListener('keydown',function(e){
    var alca=e.target.closest('[data-habito-arrastar]');if(!alca)return;
    if(e.key==='Escape'&&arraste){terminarOrdem({pointerId:arraste.id},true);return;}
    var passo={ArrowUp:-1,ArrowLeft:-1,ArrowDown:1,ArrowRight:1}[e.key];if(!passo||ocupado||arraste)return;
    e.preventDefault();var antes=cartoes(),card=alca.closest('[data-habito]'),indice=antes.indexOf(card),alvo=antes[indice+passo];
    if(!alvo)return;if(passo>0)alvo.after(card);else alvo.before(card);guardarOrdem(antes,alca);
  });
  window.Orquestra=window.Orquestra||{};
  window.Orquestra.habitosOcupados=function(){return ocupado||!!arraste;};
  async function api(url,corpo) {
    var r; try { r = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Orquestra-Vault':document.body.dataset.vaultId},body:JSON.stringify(corpo)}); }
    catch (_) { throw new Error('Sem conexão. Mantenha o formulário aberto e tente novamente.'); }
    var resposta = await r.json(); if (!r.ok) throw new Error(resposta.erro || 'Não foi possível salvar.');
    if (resposta.versao) document.dispatchEvent(new CustomEvent('orquestra:nota-salva',{detail:{versao:resposta.versao}}));
    return resposta;
  }
  function atualizarResumo(r) { $('[data-habitos-hoje]').textContent=r.hoje; $('[data-habitos-total]').textContent=r.total; $('[data-habitos-metas]').textContent=r.metas; }
  function abrir(item,modelo) {
    foco=document.activeElement; atual=item || null; form.reset(); sujo=false; $('#habito-editor-estado').textContent='';
    $('#habito-editor-titulo').textContent=item ? 'Seu hábito' : 'Novo hábito'; $('#habito-salvar').textContent=item ? 'Salvar alterações' : 'Criar hábito';
    $('#habito-titulo').value=item ? item.titulo : modelo ? modelo.titulo : '';
    $('#habito-descricao').value=item ? item.descricao || '' : '';
    $('#habito-tags').value=item ? item.tags.join(', ') : modelo ? modelo.tags.join(', ') : '';
    var extras=$('.habito-extras',form);if(extras)extras.open=!!$('#habito-tags').value;
    $('input[name=habito-meta][value="'+(item ? item.meta : modelo ? modelo.meta : 3)+'"]').checked=true;
    editor.showModal(); $('#habito-titulo').focus();
  }
  async function fechar() { if (ocupado) return; if (sujo && !await window.OrquestraInterface.confirmar({titulo:'Descartar alterações?',texto:'Este formulário ainda não foi salvo.',confirmar:'Descartar'})) return; sujo=false; editor.close(); }
  editor.addEventListener('cancel',function (e) { e.preventDefault(); fechar(); });
  editor.addEventListener('close',function () { if (foco && foco.isConnected) foco.focus(); });
  form.oninput=function () { sujo=true; };
  form.onsubmit=async function (e) {
    e.preventDefault(); if (ocupado || !form.reportValidity()) return;
    ocupado=true; $('#habito-salvar').disabled=true; $('#habito-editor-estado').textContent='Salvando…';
    try {
      var r=await api('/api/habitos',{titulo:$('#habito-titulo').value,descricao:$('#habito-descricao').value,meta_semanal:Number($('input[name=habito-meta]:checked').value),tags:$('#habito-tags').value.split(',').map(function (t) { return t.trim(); }).filter(Boolean),rel:atual ? atual.rel : '',versao:atual ? atual.versao : ''});
      sujo=false; editor.close();
      // Ativar o módulo acrescenta o acesso à navegação e à home; só esta transição abre a página completa.
      if (r.ativado) { location.assign('/m/habitos'); return; }
      var doc=new DOMParser().parseFromString(r.html,'text/html'), card=doc.querySelector('[data-habito]');
      var anterior=Array.from(raiz.querySelectorAll('[data-habito]')).find(function (c) { return c.dataset.habito===r.rel; });
      if (anterior) anterior.replaceWith(card); else $('#habitos-grade').appendChild(card);
      itens.set(r.rel,r.item); atualizarResumo(r.resumo); if ($('#habitos-vazio')) $('#habitos-vazio').remove();
      window.OrquestraInterface.avisar('Hábito salvo.'); $('[data-habito-editar]',card).focus({preventScroll:true});
    } catch (erro) { $('#habito-editor-estado').textContent=erro.message; }
    finally { ocupado=false; $('#habito-salvar').disabled=false; }
  };
  document.addEventListener('click',async function (e) {
    if (e.target.closest('[data-habito-fechar]')) { fechar(); return; }
    var novo=e.target.closest('[data-habito-novo]'), modelo=e.target.closest('[data-habito-modelo]'), editar=e.target.closest('[data-habito-editar]'), marcar=e.target.closest('[data-habito-marcar]');
    if (ocupado) return;
    if (novo) abrir();
    else if (modelo) abrir(null,dados.modelos.find(function (m) { return m.id===modelo.dataset.habitoModelo; }));
    else if (editar) abrir(itens.get(editar.closest('[data-habito]').dataset.habito));
    else if (marcar) {
      var card=marcar.closest('[data-habito]'), estado=$('[data-habito-estado]',card); marcar.disabled=true; estado.textContent='';
      try {
        var r=await api('/api/habitos/marcar',{rel:card.dataset.habito,versao:card.dataset.versao}), item=r.item;
        // Ao virar o dia, os sete dias e o mapa precisam do novo período inteiro.
        if (r.hoje !== raiz.dataset.hoje) { location.reload(); return; }
        card.dataset.versao=r.versao; itens.set(r.rel,item); atualizarResumo(r.resumo);
        var quantidade=item.contagem_hoje, contagem=$('[data-habito-contagem]',marcar);
        marcar.classList.toggle('feito',item.marcado); card.classList.toggle('habito-feito',item.marcado);
        marcar.title='Marcar mais uma realização';
        marcar.setAttribute('aria-label',marcar.title+' · '+item.titulo+' · '+quantidade+' hoje');
        $('[data-habito-check]',marcar).textContent='✓';
        $('.habito-marcar-texto',marcar).textContent=quantidade>1?'Feito':'Feito hoje';
        contagem.hidden=quantidade<2; contagem.textContent='x'+quantidade;
        $('[data-habito-semana]',card).textContent=item.semana; $('[data-habito-meta-estado]',card).textContent=item.semana>=item.meta ? 'Meta alcançada' : 'No seu ritmo';
        var dataHoje=r.hoje.slice(8,10)+'/'+r.hoje.slice(5,7)+'/'+r.hoje.slice(0,4), dica=dataHoje+' · '+(quantidade>1?quantidade+' realizações':'realizado');
        var ponto=$('[data-mapa-dia="'+r.hoje+'"]',card); if (ponto) {
          ponto.classList.add('realizado'); ponto.dataset.intensidade=Math.min(quantidade,4);
          ponto.dataset.habitoTooltip=dica; ponto.setAttribute('aria-label',dica+' · Ver notas do dia');
        }
        var mapa=$('.habito-mapa',card);
        mapa.toggleAttribute('data-mapa-intensidade',item.tem_repeticoes);
        mapa.setAttribute('aria-label','Histórico de atividade de '+item.titulo+'. '+item.total_registros+' dias realizados ao todo.');
      } catch (erro) { estado.textContent=erro.message; }
      finally { marcar.disabled=false; }
    }
  });
  // Uma dica compartilhada mantém as datas legíveis também nas bordas do mapa.
  var dicaMapa=document.createElement('div'); dicaMapa.className='habito-dica'; dicaMapa.id='habito-dica'; dicaMapa.role='tooltip'; dicaMapa.hidden=true; document.body.appendChild(dicaMapa);
  var pontoDica=null;
  function esconderDica() { if (pontoDica) pontoDica.removeAttribute('aria-describedby'); pontoDica=null; dicaMapa.hidden=true; }
  function mostrarDica(ponto) {
    esconderDica(); pontoDica=ponto; dicaMapa.textContent=ponto.dataset.habitoTooltip; dicaMapa.hidden=false; ponto.setAttribute('aria-describedby',dicaMapa.id);
    var r=ponto.getBoundingClientRect(), d=dicaMapa.getBoundingClientRect();
    dicaMapa.style.left=Math.max(8,Math.min(innerWidth-d.width-8,r.left+r.width/2-d.width/2))+'px';
    dicaMapa.style.top=(r.top>d.height+12 ? r.top-d.height-8 : r.bottom+8)+'px';
  }
  raiz.addEventListener('pointerover',function (e) { var ponto=e.target.closest('[data-habito-tooltip]'); if (ponto) mostrarDica(ponto); });
  raiz.addEventListener('pointerout',function (e) { if (e.target.closest('[data-habito-tooltip]')) esconderDica(); });
  raiz.addEventListener('focusin',function (e) { if (e.target.matches('[data-habito-tooltip]')) mostrarDica(e.target); });
  raiz.addEventListener('focusout',esconderDica);
  raiz.addEventListener('keydown',function (e) {
    var ponto=e.target.closest('[data-mapa-dia]'); if (!ponto) return;
    if (e.key==='Escape') { esconderDica(); return; }
    var passo={ArrowLeft:-7,ArrowRight:7,ArrowUp:-1,ArrowDown:1}[e.key]; if (!passo) return;
    e.preventDefault(); var pontos=Array.from(ponto.parentElement.children).filter(function (p) { return p.hasAttribute('href') && p.getClientRects().length; }), proximo=pontos[pontos.indexOf(ponto)+passo];
    if (proximo) { ponto.tabIndex=-1; proximo.tabIndex=0; proximo.focus(); }
  });
  window.addEventListener('scroll',esconderDica,true); window.addEventListener('resize',esconderDica);
  window.addEventListener('beforeunload',function (e) { if (sujo || ocupado) { e.preventDefault(); e.returnValue=''; } });
})();
