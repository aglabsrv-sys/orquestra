(function () {
  'use strict';
  var raiz = document.querySelector('.personalizar-pagina');
  if (!raiz) return;
  var form = document.getElementById('pagina-aparencia'), estado = document.getElementById('pagina-capa-estado');
  var arquivo = document.getElementById('pagina-capa-arquivo'), pendente = false, enviando = false;
  function alterado() { pendente = true; estado.textContent = 'Há alterações para salvar.'; }
  form.addEventListener('change', alterado);
  window.addEventListener('beforeunload', function (e) { if (pendente) { e.preventDefault(); e.returnValue = ''; } });
  async function cabecalhos(tipo) {
    var r = await fetch('/api/local/capacidade', {cache:'no-store'}), local = r.ok ? await r.json() : {};
    return {'Content-Type':tipo, 'X-Orquestra-Vault':document.body.dataset.vaultId || '', 'X-Orquestra-Local':local.token || ''};
  }
  async function resposta(r) { var dados = await r.json(); if (!r.ok) throw new Error(dados.erro || 'Não foi possível salvar.'); return dados; }
  arquivo.addEventListener('change', async function () {
    var f = arquivo.files[0]; if (!f) return;
    if (f.size > 2 * 1024 * 1024) { estado.textContent = 'Envie um arquivo de até 2 MB.'; arquivo.value = ''; return; }
    enviando = true; arquivo.disabled = true; estado.textContent = 'Enviando capa…';
    try {
      var dados = await resposta(await fetch('/api/capas', {method:'POST', headers:await cabecalhos('application/octet-stream'), body:f}));
      var label = document.createElement('label'), input = document.createElement('input'), span = document.createElement('span');
      input.type = 'radio'; input.name = 'escolha'; input.value = 'arquivo:' + dados.caminho;
      span.textContent = f.name; label.append(input,span); form.querySelector('fieldset').append(label); input.checked = true; alterado();
    } catch (e) { estado.textContent = e.message; }
    finally { enviando = false; arquivo.disabled = false; arquivo.value = ''; }
  });
  form.addEventListener('submit', async function (e) {
    e.preventDefault(); if (enviando) return;
    var escolha = form.querySelector('[name=escolha]:checked'); if (!escolha) { estado.textContent = 'Escolha uma capa.'; return; }
    var dados = {versao:raiz.dataset.versao}, valor = escolha.value;
    if (valor === 'tema') dados.padrao = true;
    else if (valor === 'ocultar') dados.ocultar = true;
    else if (valor.startsWith('cena:')) dados.cena = valor.slice(5);
    else dados.capa = valor.slice(8);
    var botao = document.querySelector('[form=pagina-aparencia]'); botao.disabled = true; estado.textContent = 'Salvando…';
    try { var r = await resposta(await fetch('/api/paginas/' + raiz.dataset.alvo + '/personalizar', {method:'POST', headers:await cabecalhos('application/json'), body:JSON.stringify(dados)})); pendente = false; location.assign(r.url); }
    catch (erro) { estado.textContent = erro.message; botao.disabled = false; }
  });
})();
