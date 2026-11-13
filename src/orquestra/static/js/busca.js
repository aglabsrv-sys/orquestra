/* Busca flutuante: abre por cima da página (botão de busca, Ctrl+K ou /),
   mostra resultados enquanto você digita e abre a nota com Enter.
   Sem JavaScript, o botão continua levando à página /buscar. */
(function () {
  'use strict';
  var dialogo = document.getElementById('busca-flutuante');
  if (!dialogo || typeof dialogo.showModal !== 'function') return;
  var campo = document.getElementById('bf-campo'), lista = document.getElementById('bf-lista');
  var estado = document.getElementById('bf-estado'), completa = document.getElementById('bf-completa');
  var escolhido = -1, resultados = [], espera = 0, pedido = null, ultimo = null;

  function digitando(e) {
    var alvo = e.target;
    return alvo && (alvo.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName));
  }
  function abrir() {
    if (dialogo.open) { campo.focus(); campo.select(); return; }
    ultimo = document.activeElement;
    dialogo.showModal();
    campo.focus(); campo.select();
    if (campo.value.trim()) buscar(); else mostrarDica();
  }
  function fechar() { if (dialogo.open) dialogo.close(); }
  dialogo.addEventListener('close', function () {
    if (pedido) pedido.abort();
    if (ultimo && ultimo.isConnected && typeof ultimo.focus === 'function') ultimo.focus({ preventScroll: true });
  });
  // Clicar fora da caixa fecha, como no Claude.
  dialogo.addEventListener('mousedown', function (e) { if (e.target === dialogo) fechar(); });

  function mostrarDica() {
    resultados = []; escolhido = -1; lista.replaceChildren();
    estado.textContent = 'Digite para buscar no título e no texto das notas.';
    campo.setAttribute('aria-expanded', 'false'); campo.removeAttribute('aria-activedescendant');
    completa.href = '/buscar';
  }
  function marcar(texto, termo) { // destaca o termo sem montar HTML a partir do texto
    var frag = document.createDocumentFragment(), baixo = texto.toLocaleLowerCase(), alvo = termo.toLocaleLowerCase(), i = 0;
    while (alvo && i < texto.length) {
      var achado = baixo.indexOf(alvo, i);
      if (achado < 0) break;
      frag.appendChild(document.createTextNode(texto.slice(i, achado)));
      var m = document.createElement('mark'); m.textContent = texto.slice(achado, achado + alvo.length); frag.appendChild(m);
      i = achado + alvo.length;
    }
    frag.appendChild(document.createTextNode(texto.slice(i)));
    return frag;
  }
  function selecionar(i) {
    var itens = lista.children;
    if (!itens.length) return;
    escolhido = (i + itens.length) % itens.length;
    Array.prototype.forEach.call(itens, function (li, j) { li.setAttribute('aria-selected', j === escolhido ? 'true' : 'false'); });
    campo.setAttribute('aria-activedescendant', itens[escolhido].id);
    itens[escolhido].scrollIntoView({ block: 'nearest' });
  }
  function desenhar(termo, dados) {
    resultados = dados.resultados || [];
    lista.replaceChildren();
    resultados.forEach(function (r, i) {
      var li = document.createElement('li'), a = document.createElement('a');
      li.id = 'bf-item-' + i; li.setAttribute('role', 'option'); li.setAttribute('aria-selected', 'false');
      a.href = r.url; a.tabIndex = -1;
      var titulo = document.createElement('b'); titulo.appendChild(marcar(r.titulo, termo));
      var trecho = document.createElement('span'); trecho.appendChild(marcar(r.trecho || '', termo));
      var onde = document.createElement('small'); onde.textContent = r.onde || 'Raiz do vault';
      a.append(titulo, trecho, onde); li.appendChild(a); lista.appendChild(li);
      li.addEventListener('mousemove', function () { if (escolhido !== i) selecionar(i); });
    });
    var total = dados.total || 0;
    estado.textContent = !resultados.length ? 'Nenhuma nota encontrada para “' + termo + '”.'
      : total > resultados.length ? 'Mostrando ' + resultados.length + ' de ' + total + ' resultados.' : total + (total === 1 ? ' resultado.' : ' resultados.');
    campo.setAttribute('aria-expanded', resultados.length ? 'true' : 'false');
    completa.href = '/buscar?q=' + encodeURIComponent(termo);
    escolhido = -1; if (resultados.length) selecionar(0);
  }
  function buscar() {
    var termo = campo.value.trim();
    clearTimeout(espera);
    if (!termo) { mostrarDica(); return; }
    espera = setTimeout(function () {
      if (pedido) pedido.abort();
      pedido = new AbortController();
      estado.textContent = 'Buscando…';
      fetch('/api/buscar?q=' + encodeURIComponent(termo), { signal: pedido.signal, cache: 'no-store' })
        .then(function (r) { if (!r.ok) throw new Error('A busca não respondeu.'); return r.json(); })
        .then(function (dados) { if (campo.value.trim() === termo) desenhar(termo, dados); })
        .catch(function (e) { if (e.name !== 'AbortError') estado.textContent = e.message; });
    }, 120);
  }
  campo.addEventListener('input', buscar);
  campo.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); selecionar(escolhido + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); selecionar(escolhido - 1); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      var r = resultados[escolhido];
      if (r) { if (e.ctrlKey || e.metaKey) window.open(r.url, '_blank'); else location.href = r.url; }
      else if (campo.value.trim()) location.href = '/buscar?q=' + encodeURIComponent(campo.value.trim());
    }
  });
  document.querySelectorAll('[data-abrir-busca]').forEach(function (b) {
    b.addEventListener('click', function (e) { if (e.ctrlKey || e.metaKey || e.shiftKey || e.button) return; e.preventDefault(); abrir(); });
  });
  document.addEventListener('keydown', function (e) {
    var atalho = (e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k';
    var barra = e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !digitando(e) && !document.querySelector('dialog[open]');
    if (atalho || barra) { e.preventDefault(); abrir(); }
  });
  window.OrquestraBusca = { abrir: abrir, fechar: fechar };
})();
