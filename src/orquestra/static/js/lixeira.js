/* A limpeza é explícita e individual; notas restauradas nunca substituem outras. */
(function () {
  "use strict";
  document.querySelectorAll('[data-lixeira-acao]').forEach(function (botao) {
    botao.addEventListener('click', async function () {
      var item = botao.closest('[data-lixeira-id]'), acao = botao.dataset.lixeiraAcao;
      if (acao === 'apagar' && !await window.OrquestraInterface.confirmar({
        titulo: 'Excluir definitivamente?', texto: 'A cópia desta nota será removida da lixeira. Não será possível restaurá-la por aqui.', confirmar: 'Excluir definitivamente'
      })) return;
      botao.disabled = true;
      try {
        var resposta = await window.Orquestra.api('POST', '/api/lixeira/' + item.dataset.lixeiraId + '/' + acao, {versao: item.dataset.versao});
        if (resposta.url) location.href = resposta.url;
        else location.reload();
      } catch (erro) { botao.disabled = false; window.OrquestraInterface.avisar(erro.message, 'erro'); }
    });
  });
})();
