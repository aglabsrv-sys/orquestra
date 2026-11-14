/* Agenda progressiva: o servidor continua sendo a fonte dos eventos e das versões. */
(function () {
  'use strict';
  var raiz = document.getElementById('calendario');
  if (!raiz) return;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var editor = $('#cal-evento-dialogo'), formulario = $('#cal-evento-form'), atual = null;
  var sujo = false, ocupado = false, requisicao = null, numero = 0, arrastado = null, retornoFoco = null;
  var estado = $('#cal-editor-estado'), salvar = $('#cal-salvar'), ultimaURL = location.href;
  function avisar(texto, tipo) { window.OrquestraInterface.avisar(texto, tipo || ''); }
  function headers() { return {'Content-Type':'application/json', 'X-Orquestra-Vault':document.body.dataset.vaultId || ''}; }
  async function json(url, metodo, dados) {
    var r;
    try { r = await fetch(url, {method:metodo || 'GET', cache:'no-store', headers:headers(), body:dados ? JSON.stringify(dados) : undefined}); }
    catch (_) { throw new Error('Sem conexão com o Orquestra. Preserve o formulário e tente novamente.'); }
    var resultado;
    try { resultado = await r.json(); } catch (_) { throw new Error('Resposta inesperada. Preserve suas alterações e tente novamente.'); }
    if (!r.ok) throw new Error(resultado.erro || 'Não foi possível concluir.');
    if (metodo && resultado.versao) document.dispatchEvent(new CustomEvent('orquestra:nota-salva', {detail:{versao:resultado.versao}}));
    return resultado;
  }
  function inicializar() {
    var rolagem = $('.cal-tempo-rolagem', raiz);
    if (rolagem) {
      var eventos = JSON.parse($('#cal-eventos', raiz).textContent);
      var horas = eventos.filter(function (e) { return e.hora; }).map(function (e) { return Number(e.hora.slice(0, 2)); });
      rolagem.scrollTop = Math.max(0, Math.min(8, horas.length ? Math.min.apply(null, horas) : 8) * 64);
    }
  }
  async function navegar(url, historico) {
    var destino = new URL(url, location.href);
    if (destino.origin !== location.origin || !/^\/agenda(?:\/|$)/.test(destino.pathname)) return;
    if (requisicao) requisicao.abort();
    requisicao = new AbortController(); var id = ++numero;
    var foco = document.activeElement, nomeFoco = foco && foco.name, selecao = nomeFoco === 'q' ? foco.selectionStart : null;
    raiz.setAttribute('aria-busy', 'true');
    try {
      var r = await fetch(destino.href, {signal:requisicao.signal, headers:{'X-Orquestra-Vault':document.body.dataset.vaultId || ''}});
      if (!r.ok) throw new Error('Não consegui abrir este período. Tente novamente.');
      var doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      var nova = doc.getElementById('calendario');
      if (!nova || nova.dataset.vaultId !== raiz.dataset.vaultId) throw new Error('O vault mudou. Reabra a agenda antes de continuar.');
      if (id !== numero) return;
      raiz.replaceWith(nova); raiz = nova; document.title = doc.title;
      if (historico !== false) history.pushState({}, '', destino.pathname + destino.search);
      ultimaURL = destino.href;
      inicializar();
      if (nomeFoco === 'q') { var campo = $('[name=q]', raiz); campo.focus({preventScroll:true}); campo.setSelectionRange(selecao, selecao); }
      else {
        var alvoFoco = $('.cal-visoes [aria-current]', raiz);
        if (foco && foco.closest('[aria-label="Navegar no calendário"]')) alvoFoco = $('[aria-label="' + foco.getAttribute('aria-label') + '"]', raiz) || alvoFoco;
        if (alvoFoco) alvoFoco.focus({preventScroll:true});
      }
    } catch (erro) { if (erro.name !== 'AbortError') avisar(erro.message, 'erro'); }
    finally { if (id === numero) raiz.removeAttribute('aria-busy'); }
  }
  function datas(inicio, fim, inteiro) {
    $('#cal-inicio').type = $('#cal-fim').type = inteiro ? 'date' : 'datetime-local';
    $('#cal-inicio').value = inteiro ? inicio.slice(0, 10) : inicio;
    $('#cal-fim').value = inteiro ? fim.slice(0, 10) : fim;
    $('#cal-dia-inteiro').checked = inteiro;
  }
  function preparar(evento) {
    atual = evento; sujo = false; estado.textContent = ''; formulario.reset();
    $('#cal-editor-titulo').textContent = evento ? 'Editar evento' : 'Novo evento';
    $('#cal-editor-ajuda').textContent = evento ? 'Salvo na nota de ' + evento.pasta + '. Alterações aqui são locais ao vault.' : 'Salvo como nota de compromisso no vault. A pasta é criada no primeiro evento.';
    $('#cal-titulo').value = evento ? evento.titulo : '';
    $('#cal-categoria').value = evento ? evento.categoria : 'Compromisso';
    $('#cal-tags').value = evento ? evento.tags.join(', ') : '';
    $('#cal-corpo').value = evento ? evento.corpo : '';
    var cor = $('input[name=cal-cor][value="' + (evento ? evento.cor : 'azul') + '"]');
    if (cor) cor.checked = true;
    salvar.textContent = evento ? 'Salvar alterações' : 'Criar evento';
    salvar.disabled = !!(evento && !evento.editavel);
    $('#cal-arquivar').hidden = !evento || !evento.editavel;
    $('#cal-abrir-nota').hidden = !evento;
    if (evento) $('#cal-abrir-nota').href = evento.url;
  }
  function abrirNovo(dia, hora) {
    if (ocupado) return;
    retornoFoco = document.activeElement; preparar(null);
    dia = dia || raiz.dataset.data;
    if (hora) {
      var h = Number(hora.slice(0, 2));
      // A última faixa termina à meia-noite do dia seguinte.
      var fim = new Date(dia + 'T12:00:00'); if (h === 23) fim.setDate(fim.getDate() + 1);
      var fimDia = h === 23 ? dataCivil(fim) : dia;
      datas(dia + 'T' + hora, fimDia + 'T' + String((h + 1) % 24).padStart(2,'0') + ':00', false);
    } else datas(dia, dia, true);
    editor.showModal(); $('#cal-titulo').focus();
  }
  function dataCivil(d) { return String(d.getFullYear()).padStart(4,'0') + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); }
  async function abrirEvento(rel) {
    if (ocupado) return;
    retornoFoco = document.activeElement; ocupado = true;
    try {
      var evento = await json('/api/agenda/evento/' + rel.split('/').map(encodeURIComponent).join('/'));
      preparar(evento); datas(evento.data + (evento.hora ? 'T' + evento.hora : ''), evento.data_fim + (evento.hora_fim ? 'T' + evento.hora_fim : ''), evento.dia_inteiro);
      editor.showModal(); $('#cal-titulo').focus();
    } catch (erro) { avisar(erro.message, 'erro'); }
    finally { ocupado = false; }
  }
  async function fechar() {
    if (ocupado) return;
    if (sujo && !await window.OrquestraInterface.confirmar({titulo:'Descartar alterações?', texto:'As alterações deste formulário ainda não foram salvas no vault.', confirmar:'Descartar'})) return;
    sujo = false; editor.close();
  }
  editor.addEventListener('cancel', function (e) { e.preventDefault(); fechar(); });
  editor.addEventListener('close', function () { if (retornoFoco && retornoFoco.isConnected) retornoFoco.focus(); });
  formulario.addEventListener('input', function () { sujo = true; estado.textContent = ''; });
  $('#cal-dia-inteiro').onchange = function () {
    var inicio = $('#cal-inicio').value, fim = $('#cal-fim').value, inteiro = this.checked;
    datas(inicio.includes('T') || inteiro ? inicio : inicio + 'T09:00', fim.includes('T') || inteiro ? fim : fim + 'T10:00', inteiro);
    sujo = true;
  };
  formulario.onsubmit = async function (e) {
    e.preventDefault(); if (ocupado || !formulario.reportValidity()) return;
    var inicio = $('#cal-inicio').value, fim = $('#cal-fim').value, inteiro = $('#cal-dia-inteiro').checked;
    if (fim < inicio || (!inteiro && fim === inicio)) { estado.textContent = 'O término precisa ser posterior ao início.'; $('#cal-fim').focus(); return; }
    var dados = {rel:atual ? atual.rel : '', versao:atual ? atual.versao : '', titulo:$('#cal-titulo').value.trim(), corpo:$('#cal-corpo').value,
      data:inicio.slice(0,10), data_fim:fim.slice(0,10), hora:inteiro ? '' : inicio.slice(11,16), hora_fim:inteiro ? '' : fim.slice(11,16), dia_inteiro:inteiro,
      categoria:$('#cal-categoria').value, cor:$('input[name=cal-cor]:checked').value, tags:$('#cal-tags').value.split(',').map(function (t) { return t.trim(); }).filter(Boolean)};
    ocupado = true; salvar.disabled = true; estado.textContent = 'Salvando no vault…';
    try { await json('/api/agenda/eventos', 'POST', dados); sujo = false; editor.close(); avisar('Evento salvo.'); await navegar(location.href, false); }
    catch (erro) { estado.textContent = erro.message; }
    finally { ocupado = false; salvar.disabled = !!(atual && !atual.editavel); }
  };
  $('#cal-arquivar').onclick = async function () {
    if (ocupado || !atual) return;
    if (!await window.OrquestraInterface.confirmar({titulo:'Arquivar evento?', texto:'A nota será movida para a pasta de arquivo. Você poderá recuperá-la pelo vault.', confirmar:'Arquivar'})) return;
    ocupado = true; this.disabled = true;
    try {
      await json('/api/arquivar/' + atual.rel.split('/').map(encodeURIComponent).join('/'), 'POST', {versao:atual.versao});
      document.dispatchEvent(new CustomEvent('orquestra:nota-salva', {detail:{rel:atual.rel, removido:true}}));
      sujo = false; editor.close(); avisar('Evento arquivado.'); await navegar(location.href, false);
    }
    catch (erro) { estado.textContent = erro.message; }
    finally { ocupado = false; this.disabled = false; }
  };
  var filtrosOriginais = [];
  document.addEventListener('click', function (e) {
    var fecharBotao = e.target.closest('[data-cal-fechar]');
    if (fecharBotao) {
      var dialogo = fecharBotao.closest('dialog');
      if (dialogo === editor) fechar(); else dialogo.close();
      return;
    }
    var alvo = e.target.closest('[data-cal-nav], [data-cal-novo], [data-evento], [data-cal-filtros]');
    if (!alvo || !raiz.contains(alvo) || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (alvo.hasAttribute('data-cal-nav')) { e.preventDefault(); navegar(alvo.href); }
    else if (alvo.hasAttribute('data-cal-novo')) abrirNovo(alvo.dataset.calNovo, alvo.dataset.calHora);
    else if (alvo.hasAttribute('data-evento')) abrirEvento(alvo.dataset.evento);
    else {
      var filtro = $('#cal-filtros-dialogo', raiz);
      filtrosOriginais = Array.from(filtro.querySelectorAll('[name]')).map(function (c) { return [c,c.value,c.checked]; });
      filtro.onclose = function () { filtrosOriginais.forEach(function (r) { r[0].value = r[1]; r[0].checked = r[2]; }); };
      filtro.showModal();
    }
  });
  document.addEventListener('submit', function (e) {
    if (e.target.id !== 'cal-filtros') return;
    e.preventDefault(); var form = e.target;
    var filtro = $('#cal-filtros-dialogo', raiz); filtro.onclose = null;
    var query = new URLSearchParams(new FormData(form));
    if (filtro.open) filtro.close(); navegar(form.action + '?' + query.toString());
  });
  document.addEventListener('change', function (e) { if (e.target.name === 'pasta' && raiz.contains(e.target)) $('#cal-filtros', raiz).requestSubmit(); });
  document.addEventListener('dragstart', function (e) {
    var botao = e.target.closest('[data-evento]');
    if (!botao || !raiz.contains(botao) || botao.draggable !== true || ocupado) return;
    arrastado = {rel:botao.dataset.evento, versao:botao.dataset.versao}; botao.classList.add('cal-arrastando');
    e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', arrastado.rel);
  });
  function limparArrasto() { arrastado = null; raiz.querySelectorAll('.cal-arrastando,.cal-drop-ativo').forEach(function (e) { e.classList.remove('cal-arrastando','cal-drop-ativo'); }); }
  document.addEventListener('dragend', limparArrasto);
  document.addEventListener('dragover', function (e) {
    var celula = e.target.closest('[data-cal-data]'); if (!arrastado || !celula || !raiz.contains(celula)) return;
    e.preventDefault(); e.dataTransfer.dropEffect = 'move'; raiz.querySelectorAll('.cal-drop-ativo').forEach(function (c) { if (c !== celula) c.classList.remove('cal-drop-ativo'); }); celula.classList.add('cal-drop-ativo');
  });
  document.addEventListener('drop', async function (e) {
    var celula = e.target.closest('[data-cal-data]'); if (!arrastado || !celula || !raiz.contains(celula) || ocupado) return;
    e.preventDefault(); var dados = {rel:arrastado.rel, versao:arrastado.versao, data:celula.dataset.calData};
    if (celula.classList.contains('cal-coluna-tempo')) { var h = Math.max(0,Math.min(23,Math.floor((e.clientY-celula.getBoundingClientRect().top)/64))); dados.hora = String(h).padStart(2,'0')+':00'; }
    limparArrasto(); ocupado = true;
    try { await json('/api/agenda/mover','POST',dados); avisar('Evento reagendado.'); await navegar(location.href,false); }
    catch (erro) { avisar(erro.message,'erro'); }
    finally { ocupado = false; }
  });
  window.addEventListener('popstate', async function () {
    if (editor.open) { await fechar(); if (editor.open) { history.pushState({},'',ultimaURL); return; } }
    navegar(location.href,false);
  });
  window.addEventListener('beforeunload', function (e) { if (sujo || ocupado) { e.preventDefault(); e.returnValue = ''; } });
  inicializar();
})();
