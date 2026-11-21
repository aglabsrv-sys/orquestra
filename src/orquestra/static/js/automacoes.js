/* Automações independentes: configuração por formulário e revisão antes de salvar. */
(function () {
  'use strict';
  var raizPreparada=null, ciclo=null;
  function preparar() {
  var raiz = document.querySelector('#automacoes');
  if (raiz===raizPreparada) return;
  if(ciclo){ciclo.abort();ciclo=null;}
  raizPreparada=raiz;
  if (!raiz) return;
  ciclo=new AbortController();
  var ouvintes={signal:ciclo.signal};
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.from((r || document).querySelectorAll(s)); };
  var dados = JSON.parse($('#automacoes-dados').textContent), dialogo = $('#automacao-dialogo');
  dados.instancias = dados.instancias.concat(dados.legadas || []);
  var form = $('#automacao-form'), selecionada, editando = null, configInicial = {}, leitores = {}, revisao = null, ocupada = false;
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
  document.addEventListener('click',function(e){$$('.auto-ajuda[data-aberto]').forEach(function(c){if(!c.contains(e.target))c.removeAttribute('data-aberto');});},ouvintes);
  document.addEventListener('keydown',function(e){if(e.key==='Escape'){$$('.auto-ajuda[data-aberto]').forEach(function(c){c.removeAttribute('data-aberto');});if(!$('#automacao-pasta-picker').hidden){e.preventDefault();e.stopPropagation();fecharPastas();$('#automacao-pasta-abrir').focus();}}},Object.assign({capture:true},ouvintes));
  var pastaAtual='',pastaPedido=0,pastaControle=null;
  ciclo.signal.addEventListener('abort',function(){pastaPedido++;if(pastaControle)pastaControle.abort();});
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
  document.addEventListener('click',function(e){if(!e.target.closest('.auto-pasta-campo'))fecharPastas();},ouvintes);
  dialogo.addEventListener('close',fecharPastas,ouvintes);
  dialogo.addEventListener('cancel',function(e){if(ocupada)e.preventDefault();},ouvintes);
  function erro(e) { ui.avisar(ui.mensagemErro(e), 'erro'); }
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
    if(nome==='titulo')input.required=true;
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
  function recorrencia(valor) {
    var caixa=criar('fieldset','auto-recorrencia'),tipo=criar('select'),dias=criar('div','auto-semana'),mensal=criar('input'),personalizada=criar('input');
    caixa.append(criar('legend','','Repetir tarefa'));
    [['todo dia','Todos os dias'],['semana','Toda semana · escolher dias'],['dia util','De segunda a sexta'],['fim de semana','Sábado e domingo'],['mes','Uma vez por mês'],['personalizada','Regra existente']].forEach(function(o){var el=criar('option','',o[1]);el.value=o[0];tipo.append(el);});
    tipo.setAttribute('aria-label','Frequência da tarefa');mensal.type='number';mensal.min='1';mensal.max='31';mensal.required=true;mensal.value='5';mensal.setAttribute('aria-label','Dia do mês');
    var mensalRotulo=criar('label','campo');mensalRotulo.append(criar('span','','Dia do mês'),mensal);
    personalizada.value=valor || '';personalizada.setAttribute('aria-label','Regra existente');
    var nomes=['segunda','terca','quarta','quinta','sexta','sabado','domingo'],rotulosDias=['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'];
    nomes.forEach(function(nome,i){var l=criar('label'),c=criar('input');c.type='checkbox';c.value=nome;c.setAttribute('aria-label',['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'][i]);l.append(c,criar('span','',rotulosDias[i]));dias.append(l);});
    var texto=String(valor||'sexta').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim(),partes=texto.replace(/ e /g,',').split(',').map(function(d){return d.trim().replace(/-feira$/,'');});
    texto=({'todos os dias':'todo dia',diario:'todo dia',diaria:'todo dia','dias uteis':'dia util','fins de semana':'fim de semana'})[texto]||texto;
    if(partes.length&&partes.every(function(d){return nomes.includes(d);})){tipo.value='semana';$$('input',dias).forEach(function(c){c.checked=partes.includes(c.value);});}
    else if(/^dia ([1-9]|[12][0-9]|3[01])$/.test(texto)){tipo.value='mes';mensal.value=texto.slice(4);}
    else tipo.value=['todo dia','dia util','fim de semana'].includes(texto)?texto:'personalizada';
    function mostrar(){dias.hidden=tipo.value!=='semana';mensalRotulo.hidden=tipo.value!=='mes';mensal.disabled=mensalRotulo.hidden;personalizada.hidden=tipo.value!=='personalizada';personalizada.disabled=personalizada.hidden;}
    tipo.onchange=function(){mostrar();mudou();};mostrar();
    caixa.append(tipo,dias,mensalRotulo,personalizada,criar('small','campo-ajuda','A tarefa é criada uma vez na data escolhida. Dia 31 usa o último dia dos meses mais curtos.'));
    return {el:caixa,ler:function(){if(tipo.value==='semana'){var marcados=$$('input',dias).filter(function(c){return c.checked;}).map(function(c){return c.value;});if(!marcados.length)throw new Error('Escolha pelo menos um dia da semana.');return marcados.join(', ');}if(tipo.value==='mes')return 'dia '+mensal.value;return tipo.value==='personalizada'?personalizada.value.trim():tipo.value;}};
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
        Object.keys(modelo).sort(function (a,b) { var ia = ordem.indexOf(a), ib = ordem.indexOf(b); return (ia < 0 ? 100 : ia) - (ib < 0 ? 100 : ib); }).forEach(function (k) { var c = p.nome==='tarefas'&&k==='quando'?recorrencia(v[k]):simples(k,v[k] == null ? '' : v[k]); campos[k] = c.ler; caixa.append(c.el); });
        if (p.nome==='tarefas') caixa.className+=' auto-regra-tarefa';
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
  function secaoFormulario(nome) {
    var principal=$('#automacao-regras'), avancada=$('#automacao-opcoes');
    if (!principal || !avancada) return;
    principal.hidden=nome!=='regras'; avancada.hidden=nome!=='opcoes';
    $$('[data-auto-form-aba]',form).forEach(function(b){
      b.setAttribute('aria-pressed',String(b.dataset.autoFormAba===nome));
    });
  }
  $$('[data-auto-form-aba]',form).forEach(function(b){b.onclick=function(){secaoFormulario(b.dataset.autoFormAba);};});
  function frequencia() {
    var horario=$('#automacao-horario-campo');
    horario.hidden=$('#automacao-frequencia').value!=='diaria';
    $('#automacao-horario').disabled=horario.hidden;
    var campoAtivo=$('#automacao-ativo-campo');
    if(campoAtivo)campoAtivo.hidden=$('#automacao-frequencia').value==='manual';
  }
  $('#automacao-frequencia').addEventListener('change',frequencia);
  $('#automacao-mapear').onclick = function () { par($('#automacao-mapeamentos'),'','',true); mudou(); };
  form.addEventListener('input',mudou); form.addEventListener('change',mudou);
  function abrir(id, instancia, copiar, destino) {
    if (ocupada) return;
    if (instancia && instancia.legado && !instancia.codigo_nativo) { ui.avisar('Esta automação tem código próprio. Revise-a na aba Máquina da pasta.', 'info'); return; }
    selecionada = dados.catalogo.find(function (a) { return a.id === id; }); if (!selecionada) return;
    editando = copiar ? null : instancia || null;
    var gerenciar=$('#automacao-gerenciar');
    if(gerenciar){gerenciar.hidden=!editando;gerenciar.open=false;gerenciar.dataset.autoId=editando?editando.id:'';
      $('[data-auto-acao="testar"]',gerenciar).hidden=!!(editando&&editando.legado);
      $('[data-auto-acao="copiar"]',gerenciar).hidden=!!selecionada.legada;
      $('[data-auto-acao="revogar"]',gerenciar).hidden=!(editando&&editando.legado&&editando.confianca.confiavel);
      $('[data-auto-resultado]',gerenciar).textContent='';$('[data-auto-amostra]',gerenciar).hidden=true;}
    $$('input,select,textarea',form).forEach(function(c){c.disabled=false;});$('#automacao-salvar').disabled=false;
    var valores = instancia || selecionada;
    configInicial=Object.assign({},valores.config);
    revisao = null; leitores = {}; form.reset(); $('#automacao-config').replaceChildren(); $('#automacao-config-avancada').replaceChildren(); $('#automacao-mapeamentos').replaceChildren();
    secaoFormulario('regras');
    $('#automacao-previa').hidden = true; $('#automacao-form-estado').textContent = ''; $('#automacao-salvar').textContent = 'Continuar';
    $('#automacao-titulo').textContent = (editando ? 'Configurar ' : '')+selecionada.nome; $('#automacao-descricao').textContent = selecionada.ajuda;
    $('#automacao-nome').value = valores.nome;
    definirPasta(destino !== undefined ? destino : copiar ? raiz.dataset.destino || '' : editando ? editando.destino : raiz.dataset.destino || '');
    $('#automacao-pasta-abrir').disabled = !!(editando && editando.legado);
    var campoPasta=$('#automacao-pasta-campo');
    if(campoPasta)campoPasta.hidden=$('#automacao-pasta-abrir').disabled;
    fecharPastas();
    (selecionada.parametros || []).forEach(function (padrao) {
      var p = Object.assign({},padrao);
      if (Object.prototype.hasOwnProperty.call(valores.config,p.nome)) p.padrao = valores.config[p.nome];
      // Só o par de exemplos distribuído é reduzido; regras pessoais continuam intactas.
      if(!instancia&&p.nome==='tarefas'&&p.padrao.length===2&&JSON.stringify(p.padrao)===JSON.stringify([{titulo:'Revisar a semana',quando:'sexta',prioridade:'media'},{titulo:'Conferir as contas do mês',quando:'dia 5'}]))p.padrao=p.padrao.slice(0,1);
      if (p.tipo === 'registros') p.modelo = padrao.padrao[0];
      if (p.nome === 'agendas') { p.tipo = 'registros'; p.modelo = {nome:'',url:'',variavel:''}; p.padrao = p.padrao.map(function (v) { return typeof v === 'string' ? {nome:'',url:v,variavel:''} : v; }); }
      var primario = ['canais','feeds','termos','tarefas','agendas','canal','moedas','repositorios'].includes(p.nome) || selecionada.id.endsWith('google_trends.py') && p.nome === 'pais';
      var c = parametro(p); leitores[p.nome] = c.ler; $(primario ? '#automacao-config' : '#automacao-config-avancada').append(c.el);
    });
    Object.keys(valores.mapeamento || {}).forEach(function (k) { par($('#automacao-mapeamentos'),k,valores.mapeamento[k],true); });
    $('#automacao-campos-avancados').hidden = !!(editando && editando.legado);
    $('#automacao-parametros-avancados').hidden = !$('#automacao-config-avancada').children.length;
    var abasForm=$('#automacao-abas');
    if(abasForm)abasForm.hidden=$('#automacao-campos-avancados').hidden&&$('#automacao-parametros-avancados').hidden;
    var segredos = selecionada.requer || []; $('#automacao-segredos').hidden = !segredos.length;
    $('#automacao-segredos').replaceChildren();
    if (segredos.length) { $('#automacao-segredos').append(document.createTextNode('Requer '+segredos.join(', ')+'. ')); var link = criar('a','link','Configurar segredos'); link.href = '/ajustes/variaveis'; $('#automacao-segredos').append(link); }
    var agenda = valores;
    $$('#automacao-frequencia option[data-personalizada]').forEach(function(o){o.remove();});
    $('#automacao-frequencia').value = agenda.diario_as ? 'diaria' : agenda.a_cada || 'manual';
    if ($('#automacao-frequencia').selectedIndex < 0) { var opcao = criar('option','','A cada '+agenda.a_cada); opcao.value=agenda.a_cada; opcao.dataset.personalizada='1'; $('#automacao-frequencia').append(opcao); $('#automacao-frequencia').value=agenda.a_cada; }
    $('#automacao-horario').value = agenda.diario_as || '08:00'; frequencia();
    if($('#automacao-ativo'))$('#automacao-ativo').checked=editando?!!editando.ativo:true;
    var recorrente=selecionada.id.endsWith('/recorrentes.py');
    var rotuloAgendamento=$('.auto-agendamento label > span');if(rotuloAgendamento)rotuloAgendamento.textContent=recorrente?'Verificar regras':'Executar';
    var dica=$('#automacao-recorrencia-ajuda');if(dica)dica.hidden=!recorrente;
    dialogo.showModal(); $('#automacao-nome').focus();
  }
  var escolha=$('#automacao-escolha'), catalogoDialogo=$('#automacao-catalogo-dialogo');
  function escolher(titulo, ajuda, itens) {
    if (ocupada) return;
    $('#automacao-escolha-titulo').textContent=titulo;
    $('#automacao-escolha-ajuda').textContent=ajuda;
    var lista=$('#automacao-escolha-lista');lista.replaceChildren();
    itens.forEach(function(item){var b=criar('button','auto-escolha-item');b.type='button';b.append(criar('b','',item.nome),criar('small','',item.detalhe));b.onclick=function(){escolha.close();item.abrir();};lista.append(b);});
    escolha.showModal();
  }
  function adicionar(id, valores) {
    if (ocupada) return;
    var definicao=dados.catalogo.find(function(a){return a.id===id;});
    if(definicao&&definicao.legada){ui.avisar('Use Conectar agenda na Agenda para leitura sem criar tarefas.','info');return;}
    if(dialogo.open)dialogo.close();
    if(catalogoDialogo&&catalogoDialogo.open)catalogoDialogo.close();
    if(raiz.dataset.porPasta!==undefined&&!valores){abrir(id,null,false,raiz.dataset.destino||'');return;}
    var itens=(dados.areas||[]).map(function(area){return {nome:area.nome,detalhe:area.destino,abrir:function(){abrir(id,valores,!!valores,area.destino);}};});
    itens.push({nome:'Outra pasta do cofre',detalhe:'Escolher uma pasta existente',abrir:function(){abrir(id,valores,!!valores,'');$('#automacao-pasta-abrir').click();}});
    escolher('Onde adicionar?', 'Escolha a pasta para esta automação. Cada automação adicionada tem sua própria configuração.',itens);
  }
  $$('[data-auto-adicionar]').forEach(function (b) { b.onclick = function () { adicionar(b.dataset.autoAdicionar); }; });
  $$('[data-auto-catalogo]').forEach(function(b){b.onclick=function(){catalogoDialogo.showModal();};});
  $$('[data-auto-escolher]').forEach(function(b){b.onclick=function(){
    escolher('Qual configuração abrir?', 'Confira o nome e a pasta de destino antes de editar.',dados.instancias.filter(function(a){return a.definicao===b.dataset.autoEscolher;}).map(function(a){return {nome:a.nome,detalhe:(a.destino||'Raiz do cofre')+' · '+(!a.a_cada&&!a.diario_as?'Manual':a.ativo?'Ativa':'Pausada'),abrir:function(){abrir(a.definicao,a);}};}));
  };});
  function pedido() {
    var config = Object.assign({},configInicial), freq = $('#automacao-frequencia').value;
    Object.keys(leitores).forEach(function (k) { config[k] = leitores[k](); });
    return {definicao:selecionada.id,nome:$('#automacao-nome').value.trim(),destino:$('#automacao-destino').value,config:config,mapeamento:lerPares($('#automacao-mapeamentos')),a_cada:freq === 'manual' || freq === 'diaria' ? '' : freq,diario_as:freq === 'diaria' ? $('#automacao-horario').value : ''};
  }
  function pedidoLegado(atual){return Object.assign({},editando.legado,{config:atual.config,nome:atual.nome,a_cada:atual.a_cada,diario_as:atual.diario_as,versao:editando.versao});}
  function mostrarPrevia(previa) {
    var freq=$('#automacao-frequencia').value, horario=freq==='manual'?'Manualmente':freq==='diaria'?'Todos os dias às '+$('#automacao-horario').value:'A cada '+freq;
    $('#automacao-previa-destino').textContent = (previa.destino || 'Raiz do cofre')+' · '+horario;
    $('#automacao-previa-texto').textContent = previa.politica + (previa.avisos && previa.avisos.length ? '\n\n' + previa.avisos.join('\n\n') : '');
    $('#automacao-previa').hidden = false;
    $('#automacao-form-estado').textContent = '';
    $('#automacao-salvar').textContent = textoSalvar();
  }
  function textoSalvar() {
    if (editando) return 'Salvar alterações';
    var manual=$('#automacao-frequencia').value==='manual', ativo=$('#automacao-ativo');
    return manual || ativo && !ativo.checked ? 'Adicionar' : 'Adicionar e ativar';
  }
  form.addEventListener('submit',async function (e) {
    e.preventDefault(); if (ocupada) return;
    var invalido=$(':invalid',form);
    if(invalido)secaoFormulario(invalido.closest('#automacao-opcoes')?'opcoes':'regras');
    if(!form.reportValidity())return;
    ocupada = true; var fim = ui.ocupado($('#automacao-salvar'),revisao ? 'Adicionando…' : 'Revisando…');
    var controles=$$('input,select,textarea',form).map(function(c){var anterior=c.disabled;c.disabled=true;return {campo:c,anterior:anterior};});
    try {
      var atual = pedido();
      var legado=editando&&editando.legado;
      var ativo=!!(atual.a_cada||atual.diario_as)&&($('#automacao-ativo')?$('#automacao-ativo').checked:!editando||editando.ativo);
      var revisaoAtual=JSON.stringify({pedido:atual,ativo:ativo});
      if (!revisao) {
        var previa = await api('POST',legado?'/api/automacoes/legado/prever':'/api/automacoes/prever',legado?pedidoLegado(atual):editando ? Object.assign({id:editando.id},atual) : atual);
        if(ouvintes.signal.aborted)return;
        revisao = revisaoAtual; mostrarPrevia(previa);
      }
      else {
        if (revisao !== revisaoAtual) { mudou(); return; }
        var instancia = await api('POST',legado?'/api/automacoes/legado/editar':editando ? '/api/automacoes/editar' : '/api/automacoes/criar',legado?pedidoLegado(atual):editando ? Object.assign({id:editando.id},atual) : atual), mensagem = editando ? 'Automação atualizada.' : 'Automação adicionada.';
        if(ouvintes.signal.aborted)return;
        try {
          if (legado && !instancia.codigo_nativo) throw new Error('O código desta automação mudou. Revise-o na aba Máquina antes de permitir a execução.');
          if(!instancia.confianca.confiavel)await api('POST',legado?'/api/coletores/confiar':'/api/automacoes/confiar',legado?Object.assign({},legado,{assinatura:instancia.confianca.assinatura}):{id:instancia.id,assinatura:instancia.confianca.assinatura});
          if(ouvintes.signal.aborted)return;
          if (ativo !== !!instancia.ativo) await api('POST',legado?'/api/coletores/ativo':'/api/automacoes/ativo',legado?Object.assign({},legado,{ativo:ativo}):{id:instancia.id,ativo:ativo});
        } catch (autorizacao) { mensagem = 'Configuração salva. Autorize a execução neste computador. '+ui.mensagemErro(autorizacao); }
        if(ouvintes.signal.aborted)return;
        try { sessionStorage.setItem('orquestra-automacao-aviso',mensagem); } catch (_) { /* armazenamento opcional */ }
        location.reload();
      }
    } catch (err) { if(!ouvintes.signal.aborted){$('#automacao-form-estado').textContent = ui.mensagemErro(err); erro(err);} }
    finally { ocupada = false; controles.forEach(function(c){c.campo.disabled=c.anterior;});fim();if(!ouvintes.signal.aborted&&revisao)$('#automacao-salvar').textContent = textoSalvar(); }
  });
  async function autorizar(instancia) {
    if (instancia.legado && !instancia.codigo_nativo) throw new Error('Revise o código personalizado na aba Máquina da pasta.');
    if (instancia.confianca.confiavel) return;
    if (!await ui.confirmar({titulo:'Autorizar automação',texto:'Executar “'+instancia.nome+'” com sua configuração atual. As notas produzidas serão guardadas em '+(instancia.destino || 'Raiz do cofre')+'.',confirmar:'Autorizar'})) throw {cancelado:true};
    if(ouvintes.signal.aborted)throw {cancelado:true};
    var nova = await api('POST',instancia.legado?'/api/coletores/confiar':'/api/automacoes/confiar',instancia.legado?Object.assign({},instancia.legado,{assinatura:instancia.confianca.assinatura}):{id:instancia.id,assinatura:instancia.confianca.assinatura});if(instancia.legado)instancia.confianca=nova;else Object.assign(instancia,nova);
  }
  $$('[data-auto-acao]').forEach(function (botao) {
    botao.addEventListener('click',async function () {
      if(ocupada)return;
      var linha = botao.closest('[data-auto-id]'), instancia = dados.instancias.find(function (a) { return a.id === linha.dataset.autoId; }); if (!instancia) return;
      if (botao.dataset.autoAcao === 'editar') { abrir(instancia.definicao,instancia); return; }
      if (botao.dataset.autoAcao === 'copiar') { adicionar(instancia.definicao,instancia); return; }
      var fim = ui.ocupado(botao,'…'), acao = botao.dataset.autoAcao;
      try {
        if (acao === 'remover') {
          if (!await ui.confirmar({titulo:'Remover automação?',texto:'Remover “'+instancia.nome+'” de '+(instancia.destino||'Raiz do cofre')+' e encerrar seu agendamento. As notas já produzidas serão preservadas.',confirmar:'Remover'})) return;
          if(ouvintes.signal.aborted)return;
          await api('POST',instancia.legado?'/api/automacoes/legado/remover':'/api/automacoes/remover',instancia.legado?Object.assign({},instancia.legado,{versao:instancia.versao}):{id:instancia.id});if(!ouvintes.signal.aborted)location.reload();
        } else if (acao === 'revogar' && instancia.legado) {
          if (!await ui.confirmar({titulo:'Revogar permissão?',texto:'“'+instancia.nome+'” deixará de ter autorização para executar neste computador.',confirmar:'Revogar permissão'})) return;
          await api('POST','/api/coletores/confiar',Object.assign({},instancia.legado,{acao:'revogar',assinatura:instancia.confianca.assinatura}));if(!ouvintes.signal.aborted)location.reload();
        } else {
          await autorizar(instancia);
          if(ouvintes.signal.aborted)return;
          var previa = acao === 'testar', resultado = await api('POST',instancia.legado?'/api/coletores/rodar':'/api/automacoes/rodar',instancia.legado?instancia.legado:{id:instancia.id,previa:previa});
          if(ouvintes.signal.aborted)return;
          $('[data-auto-resultado]',linha).textContent = previa ? resultado.total+(resultado.total === 1 ? ' item encontrado. ' : ' itens encontrados. ')+'Nenhuma nota gravada.' : resultado.novos+(resultado.novos === 1 ? ' nota gravada' : ' notas gravadas')+' · '+resultado.repetidos+' já presentes.';
          var amostra = $('[data-auto-amostra]',linha); amostra.hidden = !previa;
          if (previa) amostra.textContent = (resultado.amostra || []).map(function (item) { var campos = item.campos || {}; return item.titulo+'\n'+Object.keys(campos).map(function (k) { return k+': '+(Array.isArray(campos[k]) ? campos[k].join(', ') : campos[k]); }).join('\n')+(item.corpo ? '\n\n'+item.corpo : ''); }).join('\n\n') || 'A fonte não retornou itens nesta execução.';
          ui.avisar(previa ? 'Teste concluído.' : 'Execução concluída.');
        }
      } catch (err) { if (!ouvintes.signal.aborted&&!err.cancelado) erro(err); }
      finally { fim(); }
    });
  });
  if(raiz.dataset.modulo&&raiz.dataset.script){var existente=dados.instancias.find(function(a){return a.legado&&a.legado.modulo===raiz.dataset.modulo&&a.legado.script===raiz.dataset.script;});if(existente)abrir(existente.definicao,existente);}
  try { var aviso = sessionStorage.getItem('orquestra-automacao-aviso'); if (aviso) { sessionStorage.removeItem('orquestra-automacao-aviso'); ui.avisar(aviso,aviso.includes('Autorize') ? 'alerta' : 'sucesso'); } } catch (_) { /* armazenamento opcional */ }
  }
  window.Orquestra=window.Orquestra||{};
  window.Orquestra.prepararAutomacoes=preparar;
  preparar();
})();
