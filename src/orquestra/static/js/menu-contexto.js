/* Menu único, com delegação para listas e pastas atualizadas sem recarregar. */
(function () {
  'use strict';
  var menu = document.getElementById('menu-contexto');
  if (!menu) return;
  var botoes = Array.from(menu.querySelectorAll('[data-contexto-acao]'));
  var origem = null, dados = null, sequencia = 0, ocupado = false, teclaPendente = null;
  var estado = document.getElementById('menu-contexto-estado');
  function fechar(devolver) {
    sequencia++;
    if (menu.hidePopover && menu.matches(':popover-open')) menu.hidePopover();
    menu.hidden = true;
    if (devolver && origem && origem.isConnected) origem.focus({preventScroll:true});
  }
  function alvo(elemento) {
    if (!elemento || elemento.closest('input, textarea, select, [contenteditable="true"], dialog, #menu-contexto')) return null;
    var externo = elemento.closest('a[href]');
    if (externo && new URL(externo.href,location.href).origin !== location.origin) return null;
    var pasta = elemento.closest('[data-contexto-pasta], a[data-pasta]');
    if (pasta) {
      var chave = pasta.dataset.contextoPasta || pasta.dataset.pasta;
      return {elemento:pasta, rel:pasta.dataset.contextoModulo ? '' : chave.replace(/^diretorio:/, ''),
        modulo:pasta.dataset.contextoModulo || '', chave:pasta.dataset.contextoModulo ? chave : '', url:pasta.dataset.contextoUrl || pasta.href};
    }
    var nota = elemento.closest('[data-contexto-nota], .cartao[data-rel]');
    if (nota) return {elemento:nota, rel:nota.dataset.contextoNota || nota.dataset.rel};
    var link = elemento.closest('a[href]');
    if (link && link.closest('#conteudo, #grafo-notas') && !link.classList.contains('botao')) {
      var url = new URL(link.href, location.href);
      if (url.origin === location.origin && url.pathname.startsWith('/n/')) return {elemento:link, rel:decodeURIComponent(url.pathname.slice(3)), url:link.href};
    }
    return null;
  }
  function posicionar(x, y) {
    var caixa = menu.getBoundingClientRect(), margem = 8;
    menu.style.left = Math.max(margem, Math.min(x, innerWidth - caixa.width - margem)) + 'px';
    menu.style.top = Math.max(margem, Math.min(y, innerHeight - caixa.height - margem)) + 'px';
  }
  async function abrir(item, x, y, teclado) {
    if (ocupado) return;
    fechar(false);
    var numero = ++sequencia;
    origem = item.elemento; dados = null; teclaPendente = null;
    if (!origem.hasAttribute('tabindex') && !origem.matches('a,button')) origem.tabIndex = -1;
    document.getElementById('menu-contexto-tipo').textContent = 'Ações';
    document.getElementById('menu-contexto-nome').textContent = 'Carregando…';
    estado.textContent = '';
    botoes.forEach(function (b) { b.disabled = true; b.tabIndex = -1; });
    menu.hidden = false;
    if (menu.showPopover) menu.showPopover();
    posicionar(x,y);
    try {
      var consulta = new URLSearchParams({rel:item.rel || '', modulo:item.modulo || '', chave:item.chave || ''});
      var resposta = await fetch('/api/contexto?' + consulta, {cache:'no-store', headers:{'X-Orquestra-Vault':document.body.dataset.vaultId}});
      var resultado = await resposta.json();
      if (numero !== sequencia) return;
      if (!resposta.ok) throw new Error(resultado.erro || 'Não foi possível consultar este item.');
      dados = resultado;
      dados.url = item.url || dados.url;
      if (item.modulo && item.url) { var propriedadesUrl = new URL(item.url,location.href); propriedadesUrl.searchParams.set('propriedades','1'); dados.propriedades = propriedadesUrl.href; }
      document.getElementById('menu-contexto-tipo').textContent = dados.tipo === 'pasta' ? 'Pasta' : 'Nota';
      document.getElementById('menu-contexto-nome').textContent = dados.titulo;
      menu.setAttribute('aria-label','Ações de ' + dados.titulo);
      botoes.forEach(function (b) {
        var acao = b.dataset.contextoAcao;
        b.disabled = (acao === 'arquivar' || acao === 'excluir') && !dados[acao];
        b.title = b.disabled ? dados.aviso || 'Este item já está arquivado.' : '';
      });
      estado.textContent = dados.aviso;
      posicionar(x,y);
      var primeiro = botoes.find(function (b) { return !b.disabled; });
      if (teclaPendente === 'End' || teclaPendente === 'ArrowUp') primeiro = botoes.filter(function(b){return !b.disabled;}).pop();
      primeiro.tabIndex = 0;
      if (teclado || teclaPendente) primeiro.focus({preventScroll:true});
      teclaPendente = null;
    } catch (erro) {
      if (numero !== sequencia) return;
      fechar(true);
      window.OrquestraInterface.avisar(erro.message,'erro');
    }
  }
  document.addEventListener('contextmenu',function (e) {
    var item = alvo(e.target);
    if (!item || String(window.getSelection()).trim()) return;
    e.preventDefault();
    var caixa = item.elemento.getBoundingClientRect(), teclado = !e.clientX && !e.clientY;
    abrir(item, teclado ? caixa.left + 12 : e.clientX, teclado ? caixa.bottom : e.clientY, teclado);
  });
  document.addEventListener('keydown',function (e) {
    if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {
      var item = alvo(e.target);
      if (!item) return;
      e.preventDefault(); var caixa = item.elemento.getBoundingClientRect(); abrir(item,caixa.left + 12,caixa.bottom,true); return;
    }
    if (menu.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); fechar(true); return; }
    if (e.key === 'Tab') { fechar(false); return; }
    if (!['ArrowDown','ArrowUp','Home','End'].includes(e.key)) return;
    e.preventDefault();
    var ativos = botoes.filter(function (b) { return !b.disabled; }), indice = ativos.indexOf(document.activeElement);
    if (!ativos.length) { teclaPendente = e.key; return; }
    indice = e.key === 'Home' ? 0 : e.key === 'End' ? ativos.length - 1 : (indice + (e.key === 'ArrowDown' ? 1 : -1) + ativos.length) % ativos.length;
    botoes.forEach(function (b) { b.tabIndex = -1; }); ativos[indice].tabIndex = 0; ativos[indice].focus({preventScroll:true});
  },true);
  document.addEventListener('pointerdown',function(e){if(!menu.hidden && !menu.contains(e.target))fechar(false);},true);
  window.addEventListener('resize',function(){fechar(false);});
  document.addEventListener('scroll',function(e){if(!menu.hidden && !menu.contains(e.target))fechar(false);},true);
  window.addEventListener('blur',function(){fechar(false);});
  function propriedades(item) {
    if (item.propriedades) { location.assign(item.propriedades); return; }
    var dialogo = document.getElementById('contexto-propriedades');
    document.getElementById('contexto-propriedades-nome').textContent = item.titulo;
    document.getElementById('contexto-propriedades-caminho').textContent = item.caminho;
    document.getElementById('contexto-personalizar').href = '/personalizar/pastas?rel=' + encodeURIComponent(item.rel);
    dialogo.showModal();
  }
  document.querySelector('[data-contexto-fechar]').onclick = function(){document.getElementById('contexto-propriedades').close();};
  menu.addEventListener('click',async function(e){
    var botao = e.target.closest('[data-contexto-acao]');
    if (!botao || botao.disabled || !dados || ocupado) return;
    var acao = botao.dataset.contextoAcao, item = dados;
    fechar(true);
    if (acao === 'abrir') {
      var link = origem.matches('a') ? origem : origem.querySelector('a[href]');
      if(link)link.click();else location.assign(item.url);
      return;
    }
    if (acao === 'propriedades') { propriedades(item); return; }
    ocupado = true;
    try {
      var excluir = acao === 'excluir';
      if (!await window.OrquestraInterface.confirmar({titulo:(excluir ? 'Excluir “' : 'Arquivar “') + item.titulo + '”?',
        texto:item.descricao + (excluir ? ' Você poderá restaurar em Pastas → Lixeira.' : ' O conteúdo fica em arquivo/ para consulta futura.'),
        confirmar:excluir ? 'Mover para a lixeira' : 'Arquivar', perigoso:excluir})) return;
      var resultado = await window.Orquestra.api('POST','/api/contexto/acao',{acao:acao,versao:item.versao,rel:item.rel,modulo:item.modulo,chave:item.chave});
      if (resultado.parcial) { window.OrquestraInterface.avisar(resultado.movidas + ' notas movidas. Atualize para conferir o restante.','alerta'); return; }
      var explorador = document.getElementById('pasta-painel');
      if (explorador && item.tipo === 'pasta' && item.rel && (explorador.dataset.rel === item.rel || explorador.dataset.rel.startsWith(item.rel + '/'))) {
        location.assign('/pastas/' + item.rel.split('/').slice(0,-1).map(encodeURIComponent).join('/')); return;
      }
      location.reload();
    } catch(erro) { window.OrquestraInterface.avisar(erro.message,'erro'); }
    finally { ocupado = false; }
  });
  window.Orquestra = window.Orquestra || {};
  window.Orquestra.abrirMenuContexto = function(item,e,teclado){abrir(item,e.clientX,e.clientY,!!teclado);};
  window.Orquestra.fecharMenuContexto = function(){fechar(false);};
  window.Orquestra.contextoOcupado = function(){return !menu.hidden || ocupado;};
  document.addEventListener('DOMContentLoaded',function(){
    if (new URLSearchParams(location.search).get('propriedades') !== '1') return;
    var botao = document.querySelector('#abrir-propriedades, [data-pasta-ajustes]');
    if (botao) botao.click();
  });
})();
