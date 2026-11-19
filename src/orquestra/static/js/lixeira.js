/* A limpeza exige confirmação; restaurações nunca substituem outras notas. */
(function () {
  "use strict";
  var todos=document.querySelector('#lixeira-todos'),executar=document.querySelector('#lixeira-executar'),ocupado=false;
  function caixas(){return Array.from(document.querySelectorAll('[data-lixeira-selecao]'));}
  function atualizar(){var itens=caixas(),marcadas=itens.filter(function(c){return c.checked;});document.querySelector('#lixeira-contagem').textContent=marcadas.length+' selecionados';executar.disabled=ocupado||!marcadas.length;todos.checked=!!itens.length&&marcadas.length===itens.length;todos.indeterminate=!!marcadas.length&&marcadas.length<itens.length;}
  if(todos){
    todos.onchange=function(){caixas().forEach(function(c){c.checked=todos.checked;});atualizar();};caixas().forEach(function(c){c.onchange=atualizar;});
    executar.onclick=async function(){
      if(ocupado)return;var marcadas=caixas().filter(function(c){return c.checked;}),acao=document.querySelector('#lixeira-acao').value;if(!marcadas.length)return;
      if(acao==='apagar'&&!await window.OrquestraInterface.confirmar({titulo:'Excluir definitivamente a seleção?',texto:'Serão removidos '+marcadas.length+' itens da lixeira, incluindo o conteúdo das pastas selecionadas.',confirmar:'Excluir definitivamente',perigoso:true}))return;
      ocupado=true;document.querySelectorAll('.lixeira-lote input,.lixeira-lote select,[data-lixeira-selecao],[data-lixeira-acao]').forEach(function(c){c.disabled=true;});atualizar();
      var salvas=0,erros=[];
      for(var c of marcadas){var item=c.closest('[data-lixeira-id]');try{await window.Orquestra.api('POST','/api/lixeira/'+item.dataset.lixeiraId+'/'+acao,{versao:item.dataset.versao});item.remove();salvas++;}catch(e){erros.push(item.querySelector('b').textContent+': '+e.message);}}
      ocupado=false;document.querySelectorAll('.lixeira-lote input,.lixeira-lote select,[data-lixeira-selecao],[data-lixeira-acao]').forEach(function(c){c.disabled=false;});atualizar();document.querySelector('#lixeira-resultado').textContent=salvas+(acao==='restaurar'?' itens restaurados.':' itens excluídos.')+(erros.length?' '+erros.join(' '):'');
    };
  }
  document.querySelectorAll('[data-lixeira-acao]').forEach(function (botao) {
    botao.addEventListener('click', async function () {
      var item = botao.closest('[data-lixeira-id]'), acao = botao.dataset.lixeiraAcao;
      if (acao === 'apagar' && !await window.OrquestraInterface.confirmar({
        titulo: 'Excluir definitivamente?', texto: item.dataset.tipo === 'pasta' ? 'A pasta e todo o seu conteúdo serão removidos da lixeira.' : 'A cópia desta nota será removida da lixeira.', confirmar: 'Excluir definitivamente', perigoso: true
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
