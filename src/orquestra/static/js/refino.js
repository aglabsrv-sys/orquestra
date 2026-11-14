/* Fluxos pequenos, sem dependências e sem inserir conteúdo externo como HTML. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var capacidadeLocal = null;
  function headersExtras(tipo) { return {'Content-Type':tipo || 'application/json', 'X-Orquestra-Vault':document.body.dataset.vaultId || ''}; }
  async function local(url, dados) {
    if (!capacidadeLocal) capacidadeLocal = fetch('/api/local/capacidade', {cache: 'no-store'}).then(async function (r) { if (!r.ok) throw new Error('Abra localhost neste computador para configurar.'); return r.json(); }).catch(function (e) { capacidadeLocal = null; throw e; });
    var capacidade = await capacidadeLocal, headers = headersExtras(); headers['X-Orquestra-Local'] = capacidade.token;
    var r = await fetch(url, {method: dados ? 'POST' : 'GET', cache: 'no-store', headers: headers, body: dados ? JSON.stringify(dados) : undefined});
    var resultado = await r.json();
    if (!r.ok) { if (r.status === 403) capacidadeLocal = null; throw new Error(resultado.erro || 'Não foi possível concluir.'); }
    return resultado;
  }

  var linksTailscale = $('#tailscale-links');
  if (linksTailscale) {
    var estadoTailscale = $('#tailscale-estado'), modeloTailscale = $('#tailscale-linha-modelo');
    async function atualizarTailscale() {
      var dados = await local('/api/tailscale/hosts');
      linksTailscale.replaceChildren();
      dados.urls.forEach(function (url) {
        var linha = modeloTailscale.content.firstElementChild.cloneNode(true), link = $('a', linha);
        link.href = url; link.textContent = url;
        linha.querySelectorAll('[data-ts-acao]').forEach(function (b) { b.dataset.url = url; });
        linksTailscale.appendChild(linha);
      });
    }
    document.addEventListener('orquestra:tailscale-salvo', function () { atualizarTailscale().catch(function (e) { estadoTailscale.textContent = e.message; }); });
    linksTailscale.addEventListener('click', async function (e) {
      var b = e.target.closest('[data-ts-acao]'); if (!b || b.disabled) return;
      if (b.dataset.tsAcao === 'copiar') {
        try { await navigator.clipboard.writeText(b.dataset.url); estadoTailscale.textContent = 'Endereço copiado.'; }
        catch (_) { estadoTailscale.textContent = 'Não consegui copiar. Selecione o endereço acima.'; }
        return;
      }
      if (!await window.OrquestraInterface.confirmar({titulo:'Revogar este endereço?', texto:b.dataset.url, confirmar:'Revogar'})) return;
      b.disabled = true;
      try {
        document.dispatchEvent(new Event('orquestra:config-salva'));
        await local('/api/tailscale/host/revogar', {url:b.dataset.url}); await atualizarTailscale(); estadoTailscale.textContent = 'Endereço revogado.';
      } catch (erro) { b.disabled = false; estadoTailscale.textContent = erro.message; }
    });
  }
  var guias = {
    celular: [
      ['Conecte seu celular', 'Instale o Tailscale no computador e no celular. Entre com a mesma conta nos dois dispositivos. O acesso fica restrito à sua rede privada.', 'https://tailscale.com/download'],
      ['Compartilhe o painel', 'Com o Orquestra aberto, execute no computador: tailscale serve --bg 8420. Se você usa outra porta, substitua 8420. Autorize o HTTPS se o Tailscale solicitar.'],
      ['Abra no celular', 'Cole o endereço HTTPS mostrado pelo Tailscale para permitir somente este nome no painel. Depois abra no celular com o Tailscale conectado. Pessoas com acesso ao seu Serve poderão ler e editar notas. Mantenha o computador ligado. Nunca use Funnel.', null, 'tailscale']
    ],
    github: [
      ['Conectar ao GitHub', 'Instale o GitHub CLI. O login oficial abre seu navegador; o Orquestra não precisa receber sua senha ou token.', 'https://cli.github.com/'],
      ['Faça login', 'Execute: gh auth login --web --git-protocol https. Escolha sua conta e aprove no navegador. Depois execute: gh auth setup-git.'],
      ['Escolha o repositório', 'Use um repositório privado dedicado ao vault. Dentro da pasta do vault, configure: git remote add origin https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git. Se origin já existe, confira o destino antes de mudar.'],
      ['Revise e envie', 'Volte a Ajustes → Backup, prepare o histórico e autorize a configuração revisada. “Guardar e enviar” usa a branch orquestra-backup. Não envie notas privadas para um repositório público.']
    ],
    agenda: [
      ['Conecte sua agenda', 'O endereço iCal importa compromissos para as tarefas. É uma leitura periódica: editar uma tarefa aqui não altera a agenda original.'],
      ['Encontre o link', 'Google Agenda (Android): configurações da agenda → Integrar agenda → endereço secreto iCal. iPhone/iCloud: Calendário → Calendários → informações → compartilhar calendário público → copiar link. Um link público pode ser lido por quem o conhecer.'],
      ['Aplicar endereço', 'Cole o link HTTPS ou webcal. Ele será guardado no .env local, fora do vault. A automação importa os próximos 14 dias. Recorrências complexas, exclusões e mudanças de eventos ainda precisam de conferência.', null, 'agenda']
    ]
  };
  function abrirGuia(nome) {
    var passos = guias[nome];
    if (!passos) return;
    var pos = 0, d = document.createElement('dialog');
    d.className = 'dialogo'; d.setAttribute('aria-label', passos[0][0]);
    var corpo = document.createElement('div'); corpo.className = 'dialogo-corpo';
    var titulo = document.createElement('h2'), texto = document.createElement('p'), link = document.createElement('a'), campo = document.createElement('input'), aviso = document.createElement('p'), acoes = document.createElement('div');
    campo.type = 'url'; campo.placeholder = 'https://…/basic.ics'; campo.setAttribute('aria-label', 'Endereço iCal da agenda');
    acoes.className = 'dialogo-acoes'; link.className = 'link'; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = 'Abrir site oficial'; aviso.setAttribute('role', 'status');
    function botao(texto, fazer) { var b = document.createElement('button'); b.type = 'button'; b.className = 'botao'; b.textContent = texto; b.onclick = fazer; acoes.appendChild(b); return b; }
    var acionador = document.activeElement;
    var fechar = botao('Fechar', function () { d.close(); });
    var anterior = botao('Anterior', function () { pos--; pintar(); });
    var proximo = botao('Continuar', async function () {
      if (passos[pos][3]) {
        if (!campo.value || !campo.reportValidity()) return;
        proximo.disabled = true;
        try { var resultado = await local(passos[pos][3] === 'agenda' ? '/api/agenda/conectar' : '/api/tailscale/host', {url: campo.value}); campo.value = ''; aviso.textContent = resultado.mensagem || 'Link salvo. Em Tarefas → Máquina → Compromissos da agenda, revise e aprove a configuração; depois use Rodar agora ou ligue o automático.'; if (passos[pos][3] === 'tailscale') document.dispatchEvent(new Event('orquestra:tailscale-salvo')); }
        catch (erro) { aviso.textContent = erro.message; }
        finally { proximo.disabled = false; }
        return;
      }
      if (pos < passos.length - 1) { pos++; pintar(); } else d.close();
    });
    function pintar() {
      titulo.textContent = passos[pos][0] + ' · ' + (pos + 1) + '/' + passos.length;
      texto.textContent = passos[pos][1]; link.hidden = !passos[pos][2]; if (passos[pos][2]) link.href = passos[pos][2];
      campo.hidden = !passos[pos][3]; campo.setAttribute('aria-label', passos[pos][3] === 'tailscale' ? 'Endereço HTTPS do Tailscale Serve' : 'Endereço iCal da agenda'); anterior.hidden = pos === 0; aviso.textContent = '';
      proximo.textContent = passos[pos][3] === 'agenda' ? 'Conectar agenda' : passos[pos][3] === 'tailscale' ? 'Permitir este endereço' : pos === passos.length - 1 ? 'Concluir' : 'Continuar';
    }
    [titulo, texto, link, campo, aviso, acoes].forEach(function (e) { corpo.appendChild(e); }); d.appendChild(corpo); document.body.appendChild(d); pintar();
    d.addEventListener('close', function () { d.remove(); if (acionador && acionador.isConnected) acionador.focus(); }); d.showModal(); fechar.focus();
  }
  document.addEventListener('click', function (e) { var b = e.target.closest('[data-guia]'); if (b) abrirGuia(b.dataset.guia); });
  var conectarGitHub = $('#github-conectar');
  if (conectarGitHub) conectarGitHub.onclick = async function () {
    var dialogo = document.createElement('dialog'), corpo = document.createElement('div'), titulo = document.createElement('h2'), estadoGit = document.createElement('p'), codigoGit = document.createElement('code'), linkGit = document.createElement('a'), repos = document.createElement('select'), carregarRepos = document.createElement('button'), vincular = document.createElement('button'), fecharGit = document.createElement('button');
    dialogo.className = 'dialogo'; dialogo.setAttribute('aria-label','Login no GitHub'); corpo.className = 'dialogo-corpo'; titulo.textContent = 'Conecte ao GitHub'; estadoGit.setAttribute('role','status');
    estadoGit.textContent = 'O GitHub CLI abre o login oficial. O token fica no seu computador. Instale o GitHub CLI se ainda não tiver.';
    linkGit.href = 'https://github.com/login/device'; linkGit.target = '_blank'; linkGit.rel = 'noopener noreferrer'; linkGit.textContent = 'Abrir autorização no GitHub'; linkGit.className = 'link';
    repos.setAttribute('aria-label','Repositório privado de backup'); repos.hidden = true;
    carregarRepos.textContent = 'Já entrei: escolher repositório'; vincular.textContent = 'Vincular repositório privado'; vincular.hidden = true; fecharGit.textContent = 'Fechar';
    [carregarRepos,vincular,fecharGit].forEach(function (b) { b.type = 'button'; b.className = 'botao'; });
    [titulo,estadoGit,codigoGit,linkGit,carregarRepos,repos,vincular,fecharGit].forEach(function (e) { corpo.appendChild(e); }); dialogo.appendChild(corpo); document.body.appendChild(dialogo); dialogo.showModal();
    var intervalo = 0;
    fecharGit.onclick = function () { dialogo.close(); }; dialogo.onclose = function () { clearInterval(intervalo); dialogo.remove(); };
    carregarRepos.onclick = async function () {
      carregarRepos.disabled = true;
      try { var dados = await local('/api/github/repositorios'); repos.replaceChildren(); dados.repositorios.forEach(function (nome) { var o = document.createElement('option'); o.value = nome; o.textContent = nome; repos.appendChild(o); }); repos.hidden = false; vincular.hidden = !dados.repositorios.length; estadoGit.textContent = dados.repositorios.length ? 'Escolha um repositório privado dedicado ao vault. Vincular altera o destino origin; nenhum arquivo será enviado agora.' : 'Crie um repositório privado no GitHub e tente novamente.'; }
      catch (erro) { estadoGit.textContent = erro.message; }
      finally { carregarRepos.disabled = false; }
    };
    vincular.onclick = async function () { vincular.disabled = true; try { var r = await local('/api/github/vincular', {repositorio:repos.value}); estadoGit.textContent = r.mensagem; } catch (erro) { estadoGit.textContent = erro.message; } finally { vincular.disabled = false; } };
    try {
      await local('/api/github/login', {});
      intervalo = setInterval(async function () { try { var s = await local('/api/github/estado'); codigoGit.textContent = s.codigo ? 'Código: ' + s.codigo : ''; if (s.estado === 'conectado' || s.estado === 'falhou') { clearInterval(intervalo); estadoGit.textContent = s.estado === 'conectado' ? 'Login concluído. Escolha o repositório.' : 'Login não concluído. Feche e tente novamente.'; } } catch (e) { clearInterval(intervalo); estadoGit.textContent = e.message; } }, 1800);
    } catch (erro) { estadoGit.textContent = erro.message; }
  };
  var botoesAutostart = Array.from(document.querySelectorAll('[data-autostart]'));
  if (botoesAutostart.length) {
    var estadoAutostart = null, mudandoAutostart = false;
    function mostrarAutostart(estado) {
      estadoAutostart = estado;
      $('#autostart-estado').textContent = estado.descricao;
      botoesAutostart.forEach(function (b) {
        b.disabled = mudandoAutostart || estado.estado === 'indisponivel' || (b.dataset.autostart === 'ativar' ? estado.ativo && !estado.precisa_aplicar : !estado.presente);
        if (b.dataset.autostart === 'ativar') b.textContent = estado.precisa_aplicar ? 'Aplicar agora' : 'Ativar';
        b.setAttribute('aria-pressed',String(b.dataset.autostart === 'ativar' ? estado.ativo : !estado.presente));
      });
    }
    local('/api/autostart').then(mostrarAutostart).catch(function (e) { $('#autostart-estado').textContent = e.message; });
    botoesAutostart.forEach(function (b) {
      b.onclick = async function () {
        if (mudandoAutostart || b.disabled) return;
        mudandoAutostart = true; botoesAutostart.forEach(function (alvo) { alvo.disabled = true; });
        try {
          var resultado = await local('/api/autostart', {acao:b.dataset.autostart});
          if (resultado.reiniciando) {
            $('#autostart-estado').textContent = 'Aplicando em segundo plano… aguarde a confirmação antes de fechar o terminal.';
            var confirmado = false;
            for (var tentativa = 0; tentativa < 40; tentativa++) {
              await new Promise(function (resolver) { setTimeout(resolver, 500); });
              capacidadeLocal = null;
              try {
                resultado = await local('/api/autostart');
                if (resultado.segundo_plano) { confirmado = true; break; }
              } catch (_) { /* O servidor está trocando de processo. */ }
            }
            if (!confirmado) throw new Error('Não consegui confirmar o painel em segundo plano. Mantenha o terminal aberto e tente Aplicar agora novamente.');
          }
          estadoAutostart = resultado; window.OrquestraInterface.avisar('Pronto');
        }
        catch (e) {
          window.OrquestraInterface.avisar(e.message,'erro');
          try { estadoAutostart = await local('/api/autostart'); }
          catch (_) { estadoAutostart = null; $('#autostart-estado').textContent = e.message; }
        }
        finally { mudandoAutostart = false; if (estadoAutostart) mostrarAutostart(estadoAutostart); }
      };
    });
  }

  var escolherCena = $('#escolher-cena'), arquivoCapa = $('#p-capa-arquivo');
  var prepararAprovacao = $('#preparar-aprovacao');
  if (prepararAprovacao) prepararAprovacao.onclick = async function () {
    prepararAprovacao.disabled = true;
    try { var r = await fetch('/api/conteudo/aprovacao', {method:'POST',headers:headersExtras(),body:'{}'}); var dados = await r.json(); if (!r.ok) throw new Error(dados.erro || 'Não foi possível ativar.'); $('#aprovacao-estado').textContent = 'Aprovação ativada. Reabra o pipeline para ver as novas opções.'; prepararAprovacao.hidden = true; }
    catch (erro) { $('#aprovacao-estado').textContent = erro.message; prepararAprovacao.disabled = false; }
  };
  var uploadsPendentes = 0, formulariosUpload = new Map();
  function segurarEnvio(input, estadoUpload) {
    var formulario = input.closest('form'), grupo = formulario && formulariosUpload.get(formulario);
    if (formulario && !grupo) {
      grupo = {pendentes:0, botoes:[], ocupado:null, estado:estadoUpload}; formulariosUpload.set(formulario, grupo);
      formulario.addEventListener('submit', function (e) {
        if (!grupo.pendentes) return;
        e.preventDefault(); e.stopImmediatePropagation();
        grupo.estado.textContent = 'Aguarde o envio da imagem antes de salvar.';
      }, true);
    }
    if (grupo) {
      if (!grupo.pendentes) {
        grupo.ocupado = formulario.getAttribute('aria-busy');
        grupo.botoes = Array.from(formulario.querySelectorAll('button[type=submit], input[type=submit]')).map(function (b) { var anterior=b.disabled; b.disabled=true; return [b,anterior]; });
        formulario.setAttribute('aria-busy','true');
      }
      grupo.pendentes++; grupo.estado=estadoUpload;
    }
    uploadsPendentes++;
    return function () {
      uploadsPendentes--;
      if (grupo && !--grupo.pendentes) {
        grupo.botoes.forEach(function (b) { b[0].disabled=b[1]; });
        if (grupo.ocupado === null) formulario.removeAttribute('aria-busy'); else formulario.setAttribute('aria-busy',grupo.ocupado);
      }
    };
  }
  window.addEventListener('beforeunload', function (e) { if (uploadsPendentes) { e.preventDefault(); e.returnValue=''; } });
  document.querySelectorAll('[data-miniatura-para]').forEach(function (input) {
    input.onchange = async function () {
      var arquivo = input.files[0], campo = document.getElementById(input.dataset.miniaturaPara);
      if (!arquivo) return;
      var estadoUpload = input.parentElement.querySelector('.campo-ajuda');
      estadoUpload.setAttribute('role','status');
      if (arquivo.size > 2 * 1024 * 1024) { estadoUpload.textContent = 'Escolha uma imagem de até 2 MB.'; input.value = ''; return; }
      var liberarEnvio = segurarEnvio(input,estadoUpload);
      input.disabled = true; estadoUpload.textContent = 'Enviando imagem…';
      try {
        var capacidade = await fetch('/api/local/capacidade', {cache:'no-store'}), token = await capacidade.json(); if (!capacidade.ok) throw new Error('Envie arquivos pelo localhost deste computador.');
        var headers = headersExtras('application/octet-stream'); headers['X-Orquestra-Local'] = token.token;
        var r = await fetch('/api/capas', {method:'POST', headers:headers,body:arquivo}); var dados = await r.json(); if (!r.ok) throw new Error(dados.erro || 'Falha ao enviar imagem.');
        campo.value = dados.caminho; campo.dispatchEvent(new Event('change', {bubbles:true})); estadoUpload.textContent = 'Imagem enviada.';
      } catch (erro) { estadoUpload.textContent = erro.message; }
      finally { input.disabled = false; liberarEnvio(); }
    };
  });
  function previaCena(cena, origem){
    var previa=document.querySelector('.personalizar-previa');if(!previa)return;
    var anterior=previa.querySelector('.capa'),canvas=document.createElement('canvas');canvas.className='capa';canvas.width=320;canvas.height=180;canvas.dataset.cena=cena;canvas.dataset.semente=(origem&&origem.dataset.semente)||'42';canvas.dataset.paleta=(origem&&origem.dataset.paleta)||(anterior&&anterior.dataset.paleta)||'{}';
    if(anterior)anterior.replaceWith(canvas);else previa.prepend(canvas);
    window.Orquestra.iniciarCenas(previa);
    escolherCena.textContent=$('#p-cena').selectedOptions[0].textContent+' · Alterar';
    document.querySelectorAll('[data-escolher-cena]').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.escolherCena===cena?'true':'false');});
    document.querySelectorAll('[data-capa-catalogo]').forEach(function(b){b.setAttribute('aria-pressed','false');});
  }
  if (escolherCena) escolherCena.onclick = function () { $('#cenas-dialogo').showModal(); window.Orquestra.iniciarCenas($('#cenas-dialogo')); };
  document.querySelectorAll('[data-escolher-cena]').forEach(function (b) {
    b.onclick = function () { $('#p-cena').value = b.dataset.escolherCena; $('#p-capa').value = ''; $('#p-capa-arquivo').value = ''; previaCena(b.dataset.escolherCena, b.querySelector('canvas')); $('#p-cena').dispatchEvent(new Event('change',{bubbles:true})); $('#p-capa-estado').textContent = 'Cena escolhida. Salve para aplicar.'; $('#cenas-dialogo').close(); };
  });
  function previaMidia(url,tipo){
    var anterior=$('.personalizar-previa .capa'),midia=document.createElement(tipo==='video'?'video':'img');midia.className='capa midia';midia.src=url;
    if(tipo==='video'){midia.loop=true;midia.muted=true;midia.playsInline=true;if(!matchMedia('(prefers-reduced-motion: reduce)').matches)midia.play().catch(function(){});}
    anterior.replaceWith(midia);escolherCena.textContent='Capa própria · Alterar';
  }
  document.querySelectorAll('[data-capa-catalogo]').forEach(function(b){b.onclick=function(){
    $('#p-capa').value=b.dataset.capaCatalogo;$('#p-cena').value='';$('#p-capa-arquivo').value='';previaMidia(b.dataset.capaCatalogo,b.dataset.tipo);document.querySelectorAll('[data-escolher-cena],[data-capa-catalogo]').forEach(function(o){o.setAttribute('aria-pressed',o===b?'true':'false');});$('#p-capa').dispatchEvent(new Event('change',{bubbles:true}));$('#p-capa-estado').textContent='Capa escolhida. Salve para aplicar.';$('#cenas-dialogo').close();
  };});
  if ($('#p-enviar-capa')) $('#p-enviar-capa').onclick=function() { arquivoCapa.click(); };
  if (arquivoCapa) arquivoCapa.onchange = async function () {
    var arquivo = arquivoCapa.files[0], estadoCapa = $('#p-capa-estado'), salvar = $('#p-salvar');
    if (!arquivo) return;
    if (arquivo.size > 2 * 1024 * 1024) { estadoCapa.textContent = 'Escolha um arquivo de até 2 MB.'; arquivoCapa.value = ''; return; }
    salvar.disabled = true; estadoCapa.textContent = 'Enviando capa…';
    try {
      var r = await fetch('/api/local/capacidade', {cache:'no-store'}), token = await r.json();
      if (!r.ok) throw new Error('Envie a capa pelo localhost deste computador.');
      var headers = headersExtras('application/octet-stream'); headers['X-Orquestra-Local'] = token.token;
      r = await fetch('/api/capas', {method:'POST', headers:headers, body:arquivo});
      var dados = await r.json(); if (!r.ok) throw new Error(dados.erro || 'Falha no envio.');
      $('#p-capa').value = dados.caminho; $('#p-cena').value = ''; previaMidia('/arquivo/'+dados.caminho.split('/').map(encodeURIComponent).join('/'),arquivo.type.startsWith('video/')?'video':'imagem'); $('#p-capa').dispatchEvent(new Event('change',{bubbles:true})); estadoCapa.textContent = 'Capa enviada. Salve para aplicar.';
    } catch (erro) { estadoCapa.textContent = erro.message; }
    finally { salvar.disabled = false; }
  };
  var videos = document.querySelectorAll('video.capa');
  var movimento = window.matchMedia('(prefers-reduced-motion: reduce)');
  var videosVisiveis = new Set();
  function atualizarVideos() {
    videos.forEach(function (v) {
      if (videosVisiveis.has(v) && !document.hidden && !movimento.matches) v.play().catch(function () {});
      else v.pause();
    });
  }
  if ('IntersectionObserver' in window) {
    var observador = new IntersectionObserver(function (entradas) { entradas.forEach(function (e) { if (e.isIntersecting) videosVisiveis.add(e.target); else videosVisiveis.delete(e.target); }); atualizarVideos(); });
    videos.forEach(function (v) { observador.observe(v); });
  }
  document.addEventListener('visibilitychange',atualizarVideos);
  if (movimento.addEventListener) movimento.addEventListener('change',atualizarVideos);

})();
