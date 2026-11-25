/* Arraste de arquivos externos. Arrastar cartões internos mantém suas próprias ações. */
(function(){
  'use strict';
  var camada=document.getElementById('soltar-arquivos'), dialogo=document.getElementById('importar-arquivos');
  if(!camada||!dialogo)return;
  var profundidade=0, importando=false, copiados=0;
  function destino(){
    if(document.querySelector('dialog[open], .explorador.lendo-nota') || new URLSearchParams(location.search).get('aba')==='maquina')return null;
    var explorador=document.getElementById('pasta-painel'), modulo=document.getElementById('modulo-painel');
    if(explorador)return {pasta:explorador.dataset.rel||'',vinculo:'',nome:explorador.querySelector('h1').textContent};
    if(modulo && modulo.hasAttribute('data-importar-pasta'))return {pasta:modulo.dataset.importarPasta,vinculo:modulo.dataset.importarVinculo||'',nome:modulo.dataset.importarNome};
    return null;
  }
  function arquivos(e){return e.dataTransfer && Array.from(e.dataTransfer.types||[]).includes('Files');}
  function esconder(){profundidade=0;camada.hidden=true;}
  function mostrar(alvo){if(window.Orquestra.fecharMenuContexto)window.Orquestra.fecharMenuContexto();document.getElementById('soltar-arquivos-destino').textContent='Em '+alvo.nome;camada.hidden=false;}
  document.addEventListener('dragenter',function(e){if(!arquivos(e)||importando)return;e.preventDefault();var alvo=destino();if(!alvo)return;profundidade++;mostrar(alvo);});
  document.addEventListener('dragover',function(e){if(!arquivos(e))return;e.preventDefault();var alvo=destino(),anexo=e.target.closest('[data-imagem-campo]');e.dataTransfer.dropEffect=!importando&&(alvo||anexo&&anexo.dataset.imagemCampo)?'copy':'none';if(alvo&&!importando)mostrar(alvo);});
  document.addEventListener('dragleave',function(e){if(camada.hidden)return;if(!e.relatedTarget||--profundidade<=0)esconder();});
  document.addEventListener('dragend',esconder);
  window.addEventListener('blur',esconder);
  document.addEventListener('keydown',function(e){if(e.key==='Escape')esconder();});
  document.addEventListener('drop',async function(e){
    if(!arquivos(e))return;
    e.preventDefault();esconder();
    var alvo=destino();if(!alvo||importando)return;
    e.stopPropagation();
    var lista=Array.from(e.dataTransfer.files||[]), itens=Array.from(e.dataTransfer.items||[]);
    if(itens.some(function(i){var entrada=i.webkitGetAsEntry&&i.webkitGetAsEntry();return entrada&&entrada.isDirectory;})){
      window.OrquestraInterface.avisar('Arraste os arquivos da pasta. Pastas inteiras ainda não são importadas.','info');return;
    }
    if(!lista.length)return;
    if(lista.length>20){window.OrquestraInterface.avisar('Adicione até 20 arquivos por vez.','info');return;}
    var estado=document.getElementById('importar-arquivos-estado'), resultados=document.getElementById('importar-arquivos-resultados'), fechar=document.getElementById('importar-arquivos-fechar');
    importando=true;copiados=0;resultados.replaceChildren();fechar.disabled=true;dialogo.showModal();
    var token='';
    try{var r=await fetch('/api/local/capacidade',{cache:'no-store'});if(r.ok)token=(await r.json()).token||'';}catch(erro){/* A falha será apresentada junto aos arquivos. */}
    for(var i=0;i<lista.length;i++){
      var arquivo=lista[i], linha=document.createElement('li');resultados.appendChild(linha);
      estado.textContent='Adicionando '+(i+1)+' de '+lista.length+' em '+alvo.nome+'…';
      linha.textContent=arquivo.name+' · copiando…';
      try{
        if(arquivo.size>20*1024*1024)throw new Error('Limite de 20 MB por arquivo.');
        if(!token)throw new Error('Abra o painel em localhost neste computador para adicionar arquivos.');
        var consulta=new URLSearchParams({destino:alvo.pasta,nome:arquivo.name,vinculo:alvo.vinculo});
        var resposta=await fetch('/api/pastas/importar?'+consulta,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Orquestra-Local':token,'X-Orquestra-Vault':document.body.dataset.vaultId},body:arquivo});
        var dados=await resposta.json();if(!resposta.ok)throw new Error(dados.erro||'Não foi possível copiar este arquivo.');
        copiados++;linha.textContent=dados.nome+(dados.renomeado?' · cópia com novo nome':' · adicionado');
      }catch(erro){linha.className='erro';linha.textContent=arquivo.name+' · '+erro.message;}
    }
    importando=false;fechar.disabled=false;
    estado.textContent=copiados+' de '+lista.length+' arquivos adicionados. Os originais permanecem no seu computador.';
    fechar.focus();
  },true);
  function concluir(){if(importando)return;dialogo.close();if(copiados)location.reload();}
  document.getElementById('importar-arquivos-fechar').onclick=concluir;
  dialogo.addEventListener('cancel',function(e){e.preventDefault();concluir();});
  window.addEventListener('beforeunload',function(e){if(importando){e.preventDefault();e.returnValue='';}});
  window.Orquestra=window.Orquestra||{};
  window.Orquestra.arquivosOcupados=function(){return importando||!camada.hidden||dialogo.open;};
})();
