(function () {
  'use strict';
  var raiz = document.getElementById('habitos-pagina'); if (!raiz) return;
  var $ = function (s,r) { return (r || document).querySelector(s); };
  var dados = JSON.parse($('#habitos-dados').textContent), itens = new Map(dados.itens.map(function (i) { return [i.rel,i]; }));
  var editor = $('#habito-editor'), form = $('#habito-form'), atual = null, ocupado = false, sujo = false, foco = null;
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
    $('#habito-tags').value=item ? item.tags.join(', ') : modelo ? modelo.tags.join(', ') : '';
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
      var r=await api('/api/habitos',{titulo:$('#habito-titulo').value,meta_semanal:Number($('input[name=habito-meta]:checked').value),tags:$('#habito-tags').value.split(',').map(function (t) { return t.trim(); }).filter(Boolean),rel:atual ? atual.rel : '',versao:atual ? atual.versao : ''});
      sujo=false; editor.close();
      // Ativar o módulo acrescenta o acesso à navegação e à home; só esta transição abre a página completa.
      if (r.ativado) { location.assign('/m/habitos'); return; }
      var doc=new DOMParser().parseFromString(r.html,'text/html'), card=doc.querySelector('[data-habito]');
      var anterior=Array.from(raiz.querySelectorAll('[data-habito]')).find(function (c) { return c.dataset.habito===r.rel; });
      if (anterior) anterior.replaceWith(card); else $('#habitos-grade').appendChild(card);
      if ($('#habitos-grade').classList.contains('habitos-lista')) { var mapa=$('.habito-mapa-wrap',card); if (mapa) mapa.remove(); }
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
        marcar.setAttribute('aria-pressed',String(item.marcado)); marcar.classList.toggle('feito',item.marcado); card.classList.toggle('habito-feito',item.marcado);
        $('[data-habito-rotulo]',card).textContent=item.marcado ? 'Feito por hoje' : 'Marcar hoje'; $('[data-habito-check]',card).textContent=item.marcado ? '✓' : '+';
        $('[data-habito-semana]',card).textContent=item.semana; $('[data-habito-meta-estado]',card).textContent=item.semana>=item.meta ? 'Meta alcançada' : 'No seu ritmo';
        var progresso=$('.habito-progresso',card); progresso.setAttribute('aria-valuenow',item.semana); progresso.setAttribute('aria-valuemax',Math.max(item.meta,item.semana)); $('i',progresso).style.width=item.percentual+'%';
        var dia=$('[data-habito-dia="'+r.hoje+'"]',card); if (dia) { var dadoDia=item.dias.find(function (d) { return d.iso===r.hoje; }); dia.classList.toggle('feito',item.marcado); dia.title=dadoDia.rotulo+' · '+(item.marcado?'realizado':'sem registro'); $('i',dia).textContent=item.marcado?'✓':dadoDia.nome; }
        var ponto=$('[data-mapa-dia="'+r.hoje+'"]',card); if (ponto) { ponto.classList.toggle('realizado',item.marcado); ponto.title=r.hoje+' · '+(item.marcado?'realizado':'sem registro'); }
        var mapa=$('.habito-mapa',card); if (mapa) mapa.setAttribute('aria-label','Histórico das últimas treze semanas de '+item.titulo+'. '+item.total_registros+' dias realizados ao todo.');
      } catch (erro) { estado.textContent=erro.message; }
      finally { marcar.disabled=false; }
    }
  });
  window.addEventListener('beforeunload',function (e) { if (sujo || ocupado) { e.preventDefault(); e.returnValue=''; } });
})();
