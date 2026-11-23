/* Uma central, com gravação explícita e controle de versão em cada fonte. */
(function () {
  'use strict';
  var central = document.querySelector('.central-instrucoes');
  if (!central) return;
  var ui = window.OrquestraInterface, api = window.Orquestra.api;
  var verificacoes = [];
  window.Orquestra.instrucoesPendentes = function () { return verificacoes.some(function (verificar) { return verificar(); }); };
  central.querySelectorAll('[data-instrucoes-form]').forEach(function (form) {
    var texto = form.querySelector('textarea'), estado = form.querySelector('[data-instrucoes-estado]');
    var salvo = texto.value;
    verificacoes.push(function () { return texto.value !== salvo || !!form.dataset.salvando; });
    texto.addEventListener('input', function () { estado.textContent = texto.value === salvo ? '' : 'Alterações ainda não salvas.'; });
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      if (form.dataset.salvando) return;
      var botao = form.querySelector('button[type=submit]');
      var enviado = texto.value, pedido = {texto: enviado, versao: form.dataset.versao};
      if (form.dataset.rel) pedido.rel = form.dataset.rel;
      form.dataset.salvando = '1';
      botao.disabled = true; estado.textContent = 'Salvando…';
      try {
        var resultado = await api('PUT', form.dataset.rel ? '/api/instrucoes/nota' : '/api/instrucoes', pedido);
        form.dataset.versao = resultado.versao;
        document.dispatchEvent(new CustomEvent('orquestra:nota-salva', {detail:resultado}));
        salvo = enviado;
        estado.textContent = texto.value === salvo ? 'Instruções salvas.' : 'Salvo. Há novas alterações ainda não salvas.';
      } catch (erro) {
        estado.textContent = ui.mensagemErro(erro);
      } finally {
        delete form.dataset.salvando; botao.disabled = false;
      }
    });
    window.addEventListener('beforeunload', function (e) {
      if (texto.value !== salvo || form.dataset.salvando) { e.preventDefault(); e.returnValue = ''; }
    });
  });
  if (location.hash.startsWith('#area-')) {
    var grupo = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (grupo) {
      central.querySelector('.instrucoes-anteriores').open = true;
      grupo.querySelectorAll('details').forEach(function (d) { d.open = true; });
    }
  }
})();
