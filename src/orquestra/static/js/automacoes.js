/* Automações independentes: configuração por formulário e revisão antes de salvar. */
(function () {
  'use strict';
  var raiz = document.querySelector('#automacoes');
  if (!raiz) return;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.from((r || document).querySelectorAll(s)); };
  var dados = JSON.parse($('#automacoes-dados').textContent), dialogo = $('#automacao-dialogo');
  dados.instancias = dados.instancias.concat(dados.legadas || []);
  var form = $('#automacao-form'), selecionada, editando = null, leitores = {}, revisao = null, ocupada = false;
  var api = window.Orquestra.api, ui = window.OrquestraInterface;
  var rotulos = {titulo:'Título', quando:'Quando', prioridade:'Prioridade', repo:'Repositório (dono/nome)', campo_estrelas:'Campo de estrelas', campo_forks:'Campo de forks', canal:'Canal', campo_inscritos:'Campo de inscritos', campo_visualizacoes:'Campo de visualizações',nome:'Nome da agenda',url:'Endereço iCal',variavel:'Nome do segredo para endereço privado (opcional)'};
  function criar(tag, classe, texto) {
    var el = document.createElement(tag); if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto; return el;
  }
  $$('[data-auto-ajuda]').forEach(function(botao){
    var caixa=botao.closest('.auto-ajuda'),dica=$('[role=tooltip]',caixa);
    function posicionar(){var r=botao.getBoundingClientRect();dica.style.left=Math.max(12,Math.min(r.left-12,innerWidth-Math.min(300,innerWidth-32)-12))+'px';dica.style.top=Math.max(12,Math.min(r.bottom+8,innerHeight-dica.getBoundingClientRect().height-12))+'px';}
    botao.addEventListener('pointerenter',posicionar);botao.addEventListener('focus',posicionar);
    botao.addEventListener('click',function(){posicionar();caixa.toggleAttribute('data-aberto');});
  });
  document.addEventListener('click',function(e){$$('.auto-ajuda[data-aberto]').forEach(function(c){if(!c.contains(e.target))c.removeAttribute('data-aberto');});});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'){$$('.auto-ajuda[data-aberto]').forEach(function(c){c.removeAttribute('data-aberto');});if(!$('#automacao-pasta-picker').hidden){e.preventDefault();e.stopPropagation();fecharPastas();$('#automacao-pasta-abrir').focus();}}},true);
  var pastaAtual='',pastaPedido=0,pastaControle=null;
  function definirPasta(rel){$('#automacao-destino').value=rel;$('#automacao-pasta-nome').textContent=rel||'Raiz do cofre';}
  function fecharPastas(){pastaPedido++;if(pastaControle)pastaControle.abort();$('#automacao-pasta-picker').hidden=true;$('#automacao-pasta-abrir').setAttribute('aria-expanded','false');}
  async function carregarPasta(rel){
    var pedido=++pastaPedido;if(pastaControle)pastaControle.abort();pastaControle=new AbortController();
    $('#automacao-pasta-usar').disabled=true;$('#automacao-pasta-estado').textContent='Lendo pastas…';$('#automacao-pasta-lista').replaceChildren();
    try{
      var resposta=await fetch('/api/pastas/arvore?rel='+encodeURIComponent(rel),{signal:pastaControle.signal,cache:'no-store',credentials:'same-origin'});
      var conteudo=await resposta.json();if(!resposta.ok)throw new Error(conteudo.erro||'Não consegui abrir esta pasta.');
      if(pedido!==pastaPedido)return;if(!Array.isArray(conteudo.pastas))throw new Error('Não consegui ler as subpastas.');
      pastaAtual=rel;$('#automacao-pasta-atual').textContent=rel||'Raiz do cofre';$('#automacao-pasta-voltar').disabled=!rel;
      var pastas=conteudo.pastas.filter(function(p){return !p.nome.startsWith('_');});
      pastas.forEach(function(p){var b=criar('button','auto-pasta-linha'),nome=criar('span','',p.nome);b.type='button';b.append(nome,criar('span','','›'));b.onclick=function(){carregarPasta(p.rel);};$('#automacao-pasta-lista').append(b);});
      $('#automacao-pasta-estado').textContent=pastas.length?'':'Nenhuma subpasta.';$('#automacao-pasta-usar').disabled=false;
    }catch(e){if(e.name==='AbortError'||pedido!==pastaPedido)return;$('#automacao-pasta-estado').textContent=ui.mensagemErro(e);var tentar=criar('button','botao pequeno','Tentar novamente');tentar.type='button';tentar.onclick=function(){carregarPasta(rel);};$('#automacao-pasta-lista').append(tentar);}
  }
  $('#automacao-pasta-abrir').onclick=function(){if(!$('#automacao-pasta-picker').hidden){fecharPastas();return;}$('#automacao-pasta-picker').hidden=false;this.setAttribute('aria-expanded','true');carregarPasta($('#automacao-destino').value);};
  $('#automacao-pasta-voltar').onclick=function(){carregarPasta(pastaAtual.split('/').slice(0,-1).join('/'));};
  $('#automacao-pasta-usar').onclick=function(){definirPasta(pastaAtual);fecharPastas();mudou();$('#automacao-pasta-abrir').focus();};
  document.addEventListener('click',function(e){if(!e.target.closest('.auto-pasta-campo'))fecharPastas();});
  dialogo.addEventListener('close',fecharPastas);
  function erro(e) { ui.avisar(ui.mensagemErro(e), 'erro'); }
  function aba(nome, foco) {
    $$('[data-auto-aba]').forEach(function (b) { var atual = b.dataset.autoAba === nome; b.setAttribute('aria-selected', String(atual)); b.tabIndex = atual ? 0 : -1; if (atual && foco) b.focus(); });
    $('#auto-minhas').hidden = nome !== 'minhas'; $('#auto-catalogo').hidden = nome !== 'catalogo';
  }
  $$('[data-auto-aba]').forEach(function (b) {
    b.addEventListener('click', function () { aba(b.dataset.autoAba); });
    b.addEventListener('keydown', function (e) { if (['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) { e.preventDefault(); aba(e.key === 'Home' ? 'minhas' : e.key === 'End' ? 'catalogo' : b.dataset.autoAba === 'minhas' ? 'catalogo' : 'minhas', true); } });
  });
  $$('[data-auto-ver-catalogo]').forEach(function (b) { b.onclick = function () { aba('catalogo', true); }; });
  function mudou() {
    if (!revisao) return;
    revisao = null; $('#automacao-previa').hidden = true; $('#automacao-salvar').textContent = 'Continuar';
  }
  function simples(nome, valor, legenda) {
    var label = criar('label','campo'), span = criar('span','',legenda || rotulos[nome] || nome.replace(/_/g,' '));
    var input = criar('input'); input.type = typeof valor === 'number' ? 'number' : typeof valor === 'boolean' ? 'checkbox' : 'text';
    if (input.type === 'checkbox') input.checked = valor; else input.value = valor == null ? '' : String(valor);
    if (input.type === 'number') { input.min = '1'; input.max = '10000'; input.step = '1'; }
    else input.maxLength = 2000;
    label.append(span,input);
    return {el:label, ler:function () { return input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value.trim(); }};
  }
  function par(container, chave, valor, mapeamento) {
    var linha = criar('div','auto-map-linha'), origem = criar('input'), destino = criar('input'), tirar = criar('button','botao pequeno discreto','×');
    origem.value = chave || ''; destino.value = valor || ''; origem.maxLength = destino.maxLength = 100;
    origem.placeholder = mapeamento ? 'Campo produzido' : 'Campo'; destino.placeholder = mapeamento ? 'Campo na pasta' : 'Par, ex.: USD-BRL';
    origem.setAttribute('aria-label', origem.placeholder); destino.setAttribute('aria-label', destino.placeholder);
    tirar.type = 'button'; tirar.setAttribute('aria-label','Remover campo'); tirar.onclick = function () { linha.remove(); mudou(); };
    linha.append(origem,destino,tirar); container.append(linha);
  }
  function lerPares(container) {
    var resultado = {};
    $$('.auto-map-linha',container).forEach(function (linha) {
      var inputs = $$('input',linha), chave = inputs[0].value.trim(), valor = inputs[1].value.trim();
      if (!chave && !valor) return;
      if (!chave || !valor) throw new Error('Preencha os dois campos do mapeamento.');
      if (Object.prototype.hasOwnProperty.call(resultado,chave) || ['__proto__','constructor','prototype'].includes(chave)) throw new Error('Use nomes de campos únicos.');
      resultado[chave] = valor;
    });
    return resultado;
  }
  function parametro(p) {
    var valor = p.padrao, bloco = criar('fieldset','auto-lista-config');
    if (p.tipo === 'lista') {
      var label = criar('label','campo'), area = criar('textarea'); area.rows = 3; area.maxLength = 30000; area.value = valor.join('\n');
      label.append(criar('span','',p.rotulo),area,criar('small','campo-ajuda','Um por linha')); bloco.append(label);
      return {el:bloco,ler:function () { return area.value.split('\n').map(function (v) { return v.trim(); }).filter(Boolean); }};
    }
    if (p.tipo === 'mapa') {
      var linhas = criar('div'), adicionar = criar('button','botao pequeno discreto','+ Campo'); adicionar.type = 'button';
      Object.keys(valor).forEach(function (k) { par(linhas,k,valor[k],false); });
      adicionar.onclick = function () { par(linhas,'','',false); mudou(); };
      bloco.append(criar('legend','',p.rotulo),linhas,adicionar); return {el:bloco,ler:function () { return lerPares(linhas); }};
    }
    if (p.tipo === 'registros') {
      var itens = criar('div'), adicionarItem = criar('button','botao pequeno discreto','+ Adicionar'); adicionarItem.type = 'button';
      var modelo = p.modelo || valor[0] || {}, registros = [];
      function item(v) {
        var caixa = criar('div','auto-config-item'), campos = {}, tirar = criar('button','botao pequeno discreto','Remover'); tirar.type = 'button';
        var ordem = ['titulo','quando','prioridade','nome','url','variavel','repo','campo_estrelas','campo_forks'];
        Object.keys(modelo).sort(function (a,b) { var ia = ordem.indexOf(a), ib = ordem.indexOf(b); return (ia < 0 ? 100 : ia) - (ib < 0 ? 100 : ib); }).forEach(function (k) { var c = simples(k,v[k] == null ? '' : v[k]); campos[k] = c.ler; caixa.append(c.el); });
        var registro = {caixa:caixa,campos:campos,original:Object.assign({},v)}; registros.push(registro);
        tirar.onclick = function () { caixa.remove(); registros = registros.filter(function (r) { return r !== registro; }); mudou(); };
        caixa.append(tirar); itens.append(caixa);
      }
      valor.forEach(item); adicionarItem.onclick = function () { item(Object.fromEntries(Object.keys(modelo).map(function (k) { return [k,'']; }))); mudou(); };
      bloco.append(criar('legend','',p.rotulo),itens,adicionarItem);
      return {el:bloco,ler:function () { return registros.map(function (r) { var obj = Object.assign({},r.original); Object.keys(r.campos).forEach(function (k) { obj[k] = r.campos[k](); }); return obj; }); }};
    }
    return simples(p.nome,valor,p.rotulo);
  }
  function frequencia() { $('#automacao-horario-campo').hidden = $('#automacao-frequencia').value !== 'diaria'; }
  $('#automacao-frequencia').addEventListener('change',frequencia);
  $('#automacao-mapear').onclick = function () { par($('#automacao-mapeamentos'),'','',true); mudou(); };
  form.addEventListener('input',mudou); form.addEventListener('change',mudou);
  function abrir(id, instancia, copiar) {
    if (instancia && instancia.legado && !instancia.codigo_nativo) { ui.avisar('Esta automação tem código próprio. Revise-a na aba Máquina da pasta.', 'info'); return; }
    selecionada = dados.catalogo.find(function (a) { return a.id === id; }); if (!selecionada) return;
    editando = copiar ? null : instancia || null;
    $$('input,select,textarea',form).forEach(function(c){c.disabled=false;});$('#automacao-salvar').disabled=false;
    var valores = instancia || selecionada;
    revisao = null; leitores = {}; form.reset(); $('#automacao-config').replaceChildren(); $('#automacao-config-avancada').replaceChildren(); $('#automacao-mapeamentos').replaceChildren();
    $$('.auto-campos-avancados',form).forEach(function(d){d.open=false;});
    $('#automacao-previa').hidden = true; $('#automacao-form-estado').textContent = ''; $('#automacao-salvar').textContent = 'Continuar';
    $('#automacao-titulo').textContent = (editando ? 'Configurar ' : '')+selecionada.nome; $('#automacao-descricao').textContent = selecionada.ajuda;
    $('#automacao-nome').value = valores.nome;
    definirPasta(copiar ? '' : editando ? editando.destino : raiz.dataset.destino || '');
    $('#automacao-pasta-abrir').disabled = !!(editando && editando.legado);
    $('#automacao-pasta-abrir').title = editando && editando.legado ? 'Pasta da área. Use “Usar em outra pasta” para adicionar outra automação.' : 'Escolher uma pasta';
    fecharPastas();
    (selecionada.parametros || []).forEach(function (padrao) {
      var p = Object.assign({},padrao);
      if (Object.prototype.hasOwnProperty.call(valores.config,p.nome)) p.padrao = valores.config[p.nome];
      if (p.tipo === 'registros') p.modelo = padrao.padrao[0];
      if (p.nome === 'agendas') { p.tipo = 'registros'; p.modelo = {nome:'',url:'',variavel:''}; p.padrao = p.padrao.map(function (v) { return typeof v === 'string' ? {nome:'',url:v,variavel:''} : v; }); }
      var primario = ['canais','feeds','termos','tarefas','agendas','canal','moedas','repositorios'].includes(p.nome) || selecionada.id.endsWith('google_trends.py') && p.nome === 'pais';
      var c = parametro(p); leitores[p.nome] = c.ler; $(primario ? '#automacao-config' : '#automacao-config-avancada').append(c.el);
    });
    if (editando) Object.keys(editando.mapeamento || {}).forEach(function (k) { par($('#automacao-mapeamentos'),k,editando.mapeamento[k],true); });
    $('#automacao-campos-avancados').hidden = !!(editando && editando.legado);
    $('#automacao-parametros-avancados').hidden = !$('#automacao-config-avancada').children.length;
    var segredos = selecionada.requer || []; $('#automacao-segredos').hidden = !segredos.length;
    $('#automacao-segredos').replaceChildren();
    if (segredos.length) { $('#automacao-segredos').append(document.createTextNode('Requer '+segredos.join(', ')+'. ')); var link = criar('a','link','Configurar segredos'); link.href = '/ajustes/variaveis'; $('#automacao-segredos').append(link); }
    var agenda = valores;
    $$('#automacao-frequencia option[data-personalizada]').forEach(function(o){o.remove();});
    $('#automacao-frequencia').value = agenda.diario_as ? 'diaria' : agenda.a_cada || 'manual';
    if ($('#automacao-frequencia').selectedIndex < 0) { var opcao = criar('option','','A cada '+agenda.a_cada); opcao.value=agenda.a_cada; opcao.dataset.personalizada='1'; $('#automacao-frequencia').append(opcao); $('#automacao-frequencia').value=agenda.a_cada; }
    $('#automacao-horario').value = agenda.diario_as || '08:00'; frequencia();
    var atualizar=!!(editando&&editando.atualizacao_disponivel);$('#automacao-atualizacao').hidden=!atualizar;
    if(atualizar){$$('input,select,textarea',form).forEach(function(c){c.disabled=true;});$('#automacao-salvar').disabled=true;}
    dialogo.showModal(); $('#automacao-nome').focus();
  }
  $$('[data-auto-adicionar]').forEach(function (b) { b.onclick = function () { abrir(b.dataset.autoAdicionar); }; });
  function pedido() {
    var config = Object.assign({},editando ? editando.config : {}), freq = $('#automacao-frequencia').value;
    Object.keys(leitores).forEach(function (k) { config[k] = leitores[k](); });
    return {definicao:selecionada.id,nome:$('#automacao-nome').value.trim(),destino:$('#automacao-destino').value,config:config,mapeamento:lerPares($('#automacao-mapeamentos')),a_cada:freq === 'manual' || freq === 'diaria' ? '' : freq,diario_as:freq === 'diaria' ? $('#automacao-horario').value : ''};
  }
  function pedidoLegado(atual){return Object.assign({},editando.legado,{config:atual.config,nome:atual.nome,a_cada:atual.a_cada,diario_as:atual.diario_as,versao:editando.versao});}
  function mostrarPrevia(previa) {
    var freq=$('#automacao-frequencia').value, horario=freq==='manual'?'Manualmente':freq==='diaria'?'Todos os dias às '+$('#automacao-horario').value:'A cada '+freq;
    $('#automacao-previa-destino').textContent = (previa.destino || 'Raiz do cofre')+' · '+horario;
    $('#automacao-previa-texto').textContent = previa.politica;
    $('#automacao-previa').hidden = false;
    $('#automacao-form-estado').textContent = '';
    $('#automacao-salvar').textContent = editando ? 'Salvar alterações' : $('#automacao-frequencia').value === 'manual' ? 'Adicionar' : 'Adicionar e ativar';
  }
  form.addEventListener('submit',async function (e) {
    e.preventDefault(); if (ocupada || !form.reportValidity()) return;
    ocupada = true; var fim = ui.ocupado($('#automacao-salvar'),revisao ? 'Adicionando…' : 'Revisando…');
    try {
      var atual = pedido();
      var legado=editando&&editando.legado;
      if (!revisao) { var previa = await api('POST',legado?'/api/automacoes/legado/prever':'/api/automacoes/prever',legado?pedidoLegado(atual):editando ? Object.assign({id:editando.id},atual) : atual); revisao = JSON.stringify(atual); mostrarPrevia(previa); }
      else {
        if (revisao !== JSON.stringify(atual)) { mudou(); return; }
        var instancia = await api('POST',legado?'/api/automacoes/legado/editar':editando ? '/api/automacoes/editar' : '/api/automacoes/criar',legado?pedidoLegado(atual):editando ? Object.assign({id:editando.id},atual) : atual), mensagem = editando ? 'Automação atualizada.' : 'Automação adicionada.';
        try {
          if (legado && !instancia.codigo_nativo) throw new Error('O código desta automação mudou. Revise-o na aba Máquina antes de permitir a execução.');
          if(!instancia.confianca.confiavel)await api('POST',legado?'/api/coletores/confiar':'/api/automacoes/confiar',legado?Object.assign({},legado,{assinatura:instancia.confianca.assinatura}):{id:instancia.id,assinatura:instancia.confianca.assinatura});
          if ((!editando || editando.ativo) && (atual.a_cada || atual.diario_as)) await api('POST',legado?'/api/coletores/ativo':'/api/automacoes/ativo',legado?Object.assign({},legado,{ativo:true}):{id:instancia.id,ativo:true});
        } catch (autorizacao) { mensagem = 'Configuração salva. Autorize a execução neste computador. '+ui.mensagemErro(autorizacao); }
        try { sessionStorage.setItem('orquestra-automacao-aviso',mensagem); } catch (_) { /* armazenamento opcional */ }
        location.assign('/ajustes/automacoes');
      }
    } catch (err) { $('#automacao-form-estado').textContent = ui.mensagemErro(err); erro(err); }
    finally { ocupada = false; fim(); if (revisao) $('#automacao-salvar').textContent = editando ? 'Salvar alterações' : $('#automacao-frequencia').value === 'manual' ? 'Adicionar' : 'Adicionar e ativar'; }
  });
  async function autorizar(instancia) {
    if (instancia.legado && !instancia.codigo_nativo) throw new Error('Revise o código personalizado na aba Máquina da pasta.');
    if (instancia.confianca.confiavel) return;
    if (!await ui.confirmar({titulo:'Autorizar automação',texto:'Executar “'+instancia.nome+'” com sua configuração atual. As notas produzidas serão guardadas em '+(instancia.destino || 'Raiz do cofre')+'.',confirmar:'Autorizar'})) throw {cancelado:true};
    var nova = await api('POST',instancia.legado?'/api/coletores/confiar':'/api/automacoes/confiar',instancia.legado?Object.assign({},instancia.legado,{assinatura:instancia.confianca.assinatura}):{id:instancia.id,assinatura:instancia.confianca.assinatura});if(instancia.legado)instancia.confianca=nova;else Object.assign(instancia,nova);
  }
  async function atualizarNativa(instancia){
    var nova=await api('POST','/api/automacoes/legado/atualizar',Object.assign({},instancia.legado,{versao:instancia.versao,assinatura:instancia.confianca.assinatura}));
    if(!nova.confianca.confiavel)await autorizar(nova);
    location.assign('/ajustes/automacoes?modulo='+encodeURIComponent(instancia.legado.modulo)+'&script='+encodeURIComponent(instancia.legado.script));
  }
  $('#automacao-atualizar').onclick=async function(){if(!editando)return;var fim=ui.ocupado(this,'Atualizando…');try{await atualizarNativa(editando);}catch(e){if(!e.cancelado)erro(e);}finally{fim();}};
  $$('[data-auto-acao]').forEach(function (botao) {
    botao.addEventListener('click',async function () {
      var linha = botao.closest('[data-auto-id]'), instancia = dados.instancias.find(function (a) { return a.id === linha.dataset.autoId; }); if (!instancia) return;
      if (botao.dataset.autoAcao === 'editar') { abrir(instancia.definicao,instancia); return; }
      if (botao.dataset.autoAcao === 'copiar') { abrir(instancia.definicao,instancia,true); return; }
      var fim = ui.ocupado(botao,'…'), acao = botao.dataset.autoAcao;
      try {
        if(acao==='atualizar'){await atualizarNativa(instancia);}
        else if (acao === 'remover') {
          if (!await ui.confirmar({titulo:'Remover automação?',texto:'As notas já produzidas serão preservadas.',confirmar:'Remover'})) return;
          await api('POST','/api/automacoes/remover',{id:instancia.id}); location.reload();
        } else if (acao === 'ativo') {
          var ativo = botao.dataset.ativo === 'true'; if (ativo) await autorizar(instancia);
          await api('POST',instancia.legado?'/api/coletores/ativo':'/api/automacoes/ativo',instancia.legado?Object.assign({},instancia.legado,{ativo:ativo}):{id:instancia.id,ativo:ativo}); location.reload();
        } else {
          await autorizar(instancia);
          var previa = acao === 'testar', resultado = await api('POST',instancia.legado?'/api/coletores/rodar':'/api/automacoes/rodar',instancia.legado?instancia.legado:{id:instancia.id,previa:previa});
          $('[data-auto-resultado]',linha).textContent = previa ? resultado.total+(resultado.total === 1 ? ' item encontrado. ' : ' itens encontrados. ')+'Nenhuma nota gravada.' : resultado.novos+(resultado.novos === 1 ? ' nota gravada' : ' notas gravadas')+' · '+resultado.repetidos+' já presentes.';
          var amostra = $('[data-auto-amostra]',linha); amostra.hidden = !previa;
          if (previa) amostra.textContent = (resultado.amostra || []).map(function (item) { var campos = item.campos || {}; return item.titulo+'\n'+Object.keys(campos).map(function (k) { return k+': '+(Array.isArray(campos[k]) ? campos[k].join(', ') : campos[k]); }).join('\n')+(item.corpo ? '\n\n'+item.corpo : ''); }).join('\n\n') || 'A fonte não retornou itens nesta execução.';
          ui.avisar(previa ? 'Teste concluído.' : 'Execução concluída.');
        }
      } catch (err) { if (!err.cancelado) erro(err); }
      finally { fim(); }
    });
  });
  if (raiz.dataset.destino) aba('catalogo');
  if(raiz.dataset.modulo&&raiz.dataset.script){var existente=dados.instancias.find(function(a){return a.legado&&a.legado.modulo===raiz.dataset.modulo&&a.legado.script===raiz.dataset.script;});if(existente)abrir(existente.definicao,existente);}
  try { var aviso = sessionStorage.getItem('orquestra-automacao-aviso'); if (aviso) { sessionStorage.removeItem('orquestra-automacao-aviso'); ui.avisar(aviso,aviso.includes('Autorize') ? 'alerta' : 'sucesso'); } } catch (_) { /* armazenamento opcional */ }
})();
