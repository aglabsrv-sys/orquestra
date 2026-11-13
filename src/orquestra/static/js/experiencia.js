/* Interações de acabamento: navegação contínua, anexos e preferências. */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.from((r || document).querySelectorAll(s)); };
  function erro(e) { window.OrquestraInterface.avisar(e.message || 'Não foi possível concluir.', 'erro'); }
  var capacidade = null, uploads = 0;
  async function localHeaders(tipo) {
    if (!capacidade) capacidade = fetch('/api/local/capacidade', {cache:'no-store'}).then(async function (r) { if (!r.ok) throw new Error('Abra localhost neste computador para configurar.'); return (await r.json()).token; }).catch(function (e) { capacidade = null; throw e; });
    return {'Content-Type':tipo || 'application/json', 'X-Orquestra-Local':await capacidade, 'X-Orquestra-Vault':document.body.dataset.vaultId || ''};
  }
  async function requisitar(url, dados) {
    var r = await fetch(url, {method:dados === undefined ? 'GET' : 'POST', headers:await localHeaders(), cache:'no-store', body:dados === undefined ? undefined : JSON.stringify(dados)});
    var resultado = await r.json(); if (!r.ok) throw new Error(resultado.erro || 'Não foi possível concluir.'); if (url === '/api/config') document.dispatchEvent(new Event('orquestra:config-salva')); return resultado;
  }

  // Só o painel da visão é substituído. A capa e seu relógio continuam vivos.
  var pedido = 0, controlador;
  async function navegar(url, historico) {
    if (uploads) return;
    var painel = $('#modulo-painel');
    if (!painel) { location.assign(url); return; }
    var numero = ++pedido;
    if (controlador) controlador.abort();
    controlador = new AbortController(); painel.setAttribute('aria-busy','true');
    try {
      var r = await fetch(url, {signal:controlador.signal, cache:'no-store'});
      if (!r.ok) throw new Error('Não foi possível abrir esta visão. Tente novamente.');
      var doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      if (numero !== pedido) return;
      if (!$('#modulo-painel',doc) || doc.body.dataset.vaultId !== document.body.dataset.vaultId) { location.assign(url); return; }
      painel.replaceWith(document.importNode($('#modulo-painel',doc),true));
      $('.abas').replaceWith(document.importNode($('.abas',doc),true));
      var dialogos = $('#modulo-dialogos'), novos = document.importNode($('#modulo-dialogos',doc),true);
      dialogos.replaceWith(novos);
      var numeros = $('.cab-numeros'), novosNumeros = $('.cab-numeros',doc);
      if (numeros && novosNumeros) numeros.replaceWith(document.importNode(novosNumeros,true));
      document.title = doc.title;
      if (historico) history.pushState({},'',url);
      window.Orquestra.prepararModulo(novos);
      var ativa = $('.aba[aria-current]'); if (ativa) ativa.focus({preventScroll:true});
    } catch (e) { if (e.name !== 'AbortError') erro(e); }
    finally { if (numero === pedido && $('#modulo-painel')) $('#modulo-painel').removeAttribute('aria-busy'); }
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest('.abas .aba');
    if (!a || !$('#modulo-painel') || e.defaultPrevented || e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    var url = new URL(a.href,location.href);
    if (url.pathname !== location.pathname || url.origin !== location.origin) return;
    e.preventDefault(); if (url.href !== location.href) navegar(url.href,true);
  });
  window.addEventListener('popstate', function () { if ($('#modulo-painel')) navegar(location.href,false); });

  // Imagens entram por arrastar, colar ou pelo botão de anexo; nenhuma URL é pedida.
  async function anexar(alvo, arquivo) {
    if (!arquivo || !alvo.dataset.imagemCampo || alvo.hasAttribute('data-travada') || alvo.getAttribute('aria-busy') === 'true') return;
    if (!/^image\/(png|jpeg|webp)$/.test(arquivo.type) || arquivo.size > 2*1024*1024) { erro(new Error('Use uma imagem PNG, JPEG ou WebP de até 2 MB.')); return; }
    uploads++; alvo.setAttribute('aria-busy','true');
    var estado = $('#anexo-estado',alvo); if (estado) estado.textContent = 'Enviando imagem…';
    try {
      var r = await fetch('/api/capas', {method:'POST',headers:await localHeaders('application/octet-stream'),body:arquivo});
      var dados = await r.json(); if (!r.ok) throw new Error(dados.erro || 'Não foi possível enviar a imagem.');
      if (!/\.(png|jpg|webp)$/.test(dados.caminho)) throw new Error('Use uma imagem estática.');
      if (alvo.classList.contains('nota')) {
        if (estado) estado.textContent = 'Salvando imagem…';
        alvo.dispatchEvent(new CustomEvent('orquestra:anexo', {detail:dados}));
      } else {
        var campos = {}; campos[alvo.dataset.imagemCampo] = dados.caminho;
        r = await fetch('/api/notas/'+alvo.dataset.rel.split('/').map(encodeURIComponent).join('/'), {method:'PUT',headers:await localHeaders(),body:JSON.stringify({versao:alvo.dataset.versao,campos:campos})});
        var nota = await r.json(); if (!r.ok) throw new Error(nota.erro || 'Não foi possível salvar a imagem.');
        alvo.dataset.versao = nota.versao;
        document.dispatchEvent(new CustomEvent('orquestra:nota-salva',{detail:nota}));
        var img = $('.cartao-img img',alvo);
        if (!img) { var link = document.createElement('a'); link.className='cartao-img'; link.href=$('.cartao-titulo',alvo).href; img=document.createElement('img'); img.alt=''; link.appendChild(img); alvo.prepend(link); }
        img.src='/arquivo/'+dados.caminho;
      }
    } catch (e) { if (estado) estado.textContent=e.message; erro(e); }
    finally { uploads--; alvo.removeAttribute('aria-busy'); }
  }
  document.addEventListener('dragover', function (e) {
    var alvo = e.target.closest('[data-imagem-campo]');
    if (!alvo || !alvo.dataset.imagemCampo || !Array.from(e.dataTransfer.types).includes('Files')) return;
    e.preventDefault(); alvo.classList.add('recebe-imagem');
  });
  document.addEventListener('dragleave', function (e) { var alvo=e.target.closest('.recebe-imagem'); if (alvo && !alvo.contains(e.relatedTarget)) alvo.classList.remove('recebe-imagem'); });
  document.addEventListener('drop', function (e) { var alvo=e.target.closest('[data-imagem-campo]'); if (!alvo || !e.dataTransfer.files.length || !alvo.dataset.imagemCampo) return; e.preventDefault(); alvo.classList.remove('recebe-imagem'); anexar(alvo,e.dataTransfer.files[0]); });
  document.addEventListener('paste', function (e) { var alvo=e.target.closest('[data-imagem-campo]'); if (!alvo || !e.clipboardData) return; var imagem=Array.from(e.clipboardData.files).find(function (f) { return f.type.startsWith('image/'); }); if (imagem && alvo.dataset.imagemCampo) { e.preventDefault(); anexar(alvo,imagem); } });
  var anexo=$('#nota-anexo'); if (anexo) anexo.onchange=function () { anexar($('.nota'),anexo.files[0]); anexo.value=''; };
  window.addEventListener('beforeunload',function (e) { if (uploads) { e.preventDefault(); e.returnValue=''; } });

  var cenaGlobal=$('#ap-cena');if(cenaGlobal)cenaGlobal.onchange=async function(){cenaGlobal.disabled=true;try{await requisitar('/api/config',{aparencia:{cena:cenaGlobal.value}});location.reload();}catch(e){erro(e);cenaGlobal.disabled=false;}};
  // Ordem das pastas: uma única alteração atômica na configuração do cofre.
  var lista=$('#areas-ordem'), movida=null, salvando=false;
  if (lista) {
    function linhas() { return $$('.area-linha',lista); }
    function botoes() { var itens=linhas(); itens.forEach(function (l,i) { $('[data-mover="-1"]',l).disabled=salvando || i===0; $('[data-mover="1"]',l).disabled=salvando || i===itens.length-1; l.draggable=!salvando; }); }
    async function salvar(antes) {
      salvando=true; botoes();
      try { await requisitar('/api/config',{ordem_pastas:linhas().map(function (l) { return l.dataset.modulo; })}); var estado=$('#estado-config'); if (estado) estado.textContent='Ordem das pastas atualizada.'; }
      catch (e) { antes.forEach(function (l) { lista.appendChild(l); }); erro(e); }
      finally { salvando=false; botoes(); }
    }
    var antesArraste;
    lista.addEventListener('dragstart',function (e) { if (salvando || e.target.closest('a,button,input')) { e.preventDefault(); return; } movida=e.target.closest('.area-linha'); if (!movida) return; antesArraste=linhas(); movida.classList.add('arrastando'); e.dataTransfer.setData('text/plain',movida.dataset.modulo); e.dataTransfer.effectAllowed='move'; });
    lista.addEventListener('dragover',function (e) { if (!movida) return; e.preventDefault(); var l=e.target.closest('.area-linha'); if (!l || l===movida) return; var b=l.getBoundingClientRect(); lista.insertBefore(movida,e.clientY<b.top+b.height/2 ? l : l.nextSibling); });
    lista.addEventListener('drop',function (e) { if (!movida) return; e.preventDefault(); var antes=antesArraste; movida.classList.remove('arrastando'); movida=null; salvar(antes); });
    lista.addEventListener('dragend',function () { if (movida) { movida.classList.remove('arrastando'); antesArraste.forEach(function (l) { lista.appendChild(l); }); movida=null; } });
    lista.addEventListener('click',function (e) { var b=e.target.closest('[data-mover]'); if (!b || salvando) return; var antes=linhas(), l=b.closest('.area-linha'), i=antes.indexOf(l), alvo=antes[i+Number(b.dataset.mover)]; if (!alvo) return; lista.insertBefore(l,Number(b.dataset.mover)<0 ? alvo : alvo.nextSibling); salvar(antes); b.focus(); }); botoes();
  }

  // Variáveis: mostrar nomes e estado, nunca solicitar valores existentes.
  var form=$('#variaveis-form');
  if (form) {
    var dialogo=$('#variavel-dialogo'), estado=$('#variaveis-estado'), nomes=[], ocupado=false;
    function abrir(nome) { form.reset(); $('#variavel-valor').type='password'; $('#variavel-nome').value=nome || ''; $('#variavel-nome').readOnly=!!nome; $('#variavel-titulo').textContent=nome ? 'Atualizar variável' : 'Nova variável'; $('#variavel-form-estado').textContent=''; dialogo.showModal(); $(nome ? '#variavel-valor' : '#variavel-nome').focus(); }
    $('#variavel-adicionar').onclick=function () { abrir(''); };
    $('#variavel-revelar').onchange=function () { $('#variavel-valor').type=this.checked ? 'text' : 'password'; };
    dialogo.addEventListener('close',function () { form.reset(); $('#variavel-valor').type='password'; });
    dialogo.addEventListener('cancel',function (e) { if (ocupado) e.preventDefault(); });
    function pintar() {
      var lista=$('#variaveis-lista'), busca=$('#variavel-busca').value.trim().toUpperCase(), filtrados=nomes.filter(function (n) { return n.includes(busca); }); lista.replaceChildren();
      $('#variaveis-contagem').textContent=nomes.length+' configurada'+(nomes.length===1 ? '' : 's');
      if (!filtrados.length) { var vazio=document.createElement('li'); vazio.className='vazio'; var t=document.createElement('b'), p=document.createElement('p'); t.textContent=busca ? 'Nenhuma variável encontrada' : 'Suas conexões começam aqui'; p.textContent=busca ? 'Experimente outro nome.' : 'Adicione a chave exigida pelo seu coletor. O valor fica fora do cofre.'; vazio.append(t,p); lista.appendChild(vazio); }
      filtrados.forEach(function (nome) {
        var li=document.createElement('li'), info=document.createElement('div'), n=document.createElement('code'), detalhe=document.createElement('small'), acoes=document.createElement('div'), editar=document.createElement('button'), excluir=document.createElement('button');
        n.textContent=nome; detalhe.textContent='Configurada · valor não exibido'; info.append(n,detalhe); acoes.className='linha-botoes sem-topo';
        editar.type=excluir.type='button'; editar.className=excluir.className='botao pequeno discreto'; editar.textContent='Atualizar'; excluir.textContent='Excluir'; editar.setAttribute('aria-label','Atualizar '+nome); excluir.setAttribute('aria-label','Excluir '+nome); editar.onclick=function () { abrir(nome); };
        excluir.onclick=async function () { if (!await window.OrquestraInterface.confirmar({titulo:'Excluir '+nome+'?',texto:'Coletores que dependem desta variável precisarão de um novo valor para funcionar.',confirmar:'Excluir variável',perigoso:true})) return; excluir.disabled=true; try { await requisitar('/api/variaveis',{nome:nome,valor:null}); await carregar(); estado.textContent='Variável excluída.'; } catch (e) { erro(e); excluir.disabled=false; } };
        acoes.append(editar,excluir); li.append(info,acoes); lista.appendChild(li);
      });
    }
    async function carregar() { try { nomes=(await requisitar('/api/variaveis')).nomes.sort(); pintar(); } catch (e) { estado.textContent=e.message; } }
    $('#variavel-busca').oninput=pintar;
    $('#variavel-nome').addEventListener('input',function () { this.value=this.value.toUpperCase().replace(/\s/g,'_'); });
    form.onsubmit=async function (e) { e.preventDefault(); if (ocupado || !form.reportValidity()) return; ocupado=true; var b=$('button[type=submit]',form); b.disabled=true; try { await requisitar('/api/variaveis',{nome:$('#variavel-nome').value,valor:$('#variavel-valor').value}); dialogo.close(); await carregar(); estado.textContent='Variável salva.'; } catch (e) { $('#variavel-form-estado').textContent=e.message; } finally { ocupado=false; b.disabled=false; } }; carregar();
  }
})();
