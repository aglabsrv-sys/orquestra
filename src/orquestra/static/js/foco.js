(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var chave = 'orquestra:foco:v2:' + (document.body.dataset.vaultId || 'local');
  var pagina = $('#foco-pagina'), token = $('#abrir-foco'), bruto = null, disponivel = true;
  try { bruto = JSON.parse(sessionStorage.getItem(chave) || 'null'); } catch (_) { disponivel = false; }
  var motor = new window.OrquestraFoco.Motor(bruto, Date.now()), tick = 0, audio = null;
  var nomes = {foco:'MOMENTO DE FOCO', curta:'RESPIRE UM POUCO', longa:'UM DESCANSO MAIOR'};
  function guardar() { try { sessionStorage.setItem(chave,JSON.stringify(motor.exportar())); disponivel = true; } catch (_) { disponivel = false; } if (pagina) $('#foco-armazenamento').hidden = disponivel; }
  function toque() {
    if (!motor.s.som || !audio) return;
    try { [0,.23].forEach(function (tempo) { var os = audio.createOscillator(), ganho = audio.createGain(), inicio = audio.currentTime + tempo; os.type = 'sine'; os.frequency.value = tempo ? 880 : 660; ganho.gain.setValueAtTime(0,inicio); ganho.gain.linearRampToValueAtTime(.12,inicio+.02); ganho.gain.exponentialRampToValueAtTime(.001,inicio+.4); os.connect(ganho); ganho.connect(audio.destination); os.start(inicio); os.stop(inicio+.42); }); } catch (_) { /* som opcional */ }
  }
  function ativarAudio() { if (!motor.s.som) return; try { var Contexto = window.AudioContext || window.webkitAudioContext; if (Contexto) { audio = audio || new Contexto(); audio.resume().catch(function () {}); } } catch (_) { /* navegador sem áudio */ } }
  function pintar() {
    var s = motor.s, mm = String(Math.floor(s.restante/60)).padStart(2,'0'), ss = String(s.restante%60).padStart(2,'0');
    if (token) { token.toggleAttribute('data-rodando',!!s.fim); $('#foco-indicador').hidden = !s.fim; token.title = s.fim ? 'Pomodoro · ' + mm + ':' + ss : 'Pomodoro'; }
    if (!pagina) return;
    $('#foco-tempo').textContent = mm + ':' + ss;
    $('#foco-etapa').textContent = nomes[s.modo];
    var estado = s.concluido ? (s.modo === 'foco' ? 'Foco concluído. Hora de respirar.' : 'Pausa concluída. Vamos com calma.') : s.fim ? (s.modo === 'foco' ? 'Seu tempo está protegido.' : 'Solte os ombros. Respire.') : s.restante < s.duracoes[s.modo]*60 ? 'Pausado. Continue no seu ritmo.' : 'Pronto quando você estiver.';
    if ($('#foco-estado').textContent !== estado) $('#foco-estado').textContent = estado;
    $('#foco-acao').textContent = s.fim ? 'Pausar' : s.concluido ? 'Começar ' + (motor.proximo() === 'foco' ? 'foco' : 'pausa') : s.restante < s.duracoes[s.modo]*60 ? 'Continuar' : 'Começar ' + (s.modo === 'foco' ? 'foco' : 'pausa');
    $('#foco-play').textContent = s.fim ? 'Ⅱ' : '▶';
    var progresso = 1-s.restante/(s.duracoes[s.modo]*60);
    $('#foco-progresso').setAttribute('stroke-dashoffset',String(progresso*100));
    $('#foco-ponteiro').setAttribute('transform','rotate(' + progresso*360 + ' 200 200)');
    var ciclos = s.ciclos % 4 || (s.ciclos ? 4 : 0);
    $('#foco-ciclos').setAttribute('aria-label',ciclos+' de 4 ciclos');
    Array.from($('#foco-ciclos').children).forEach(function (p,i) { p.classList.toggle('feito',i<ciclos); });
    $('#foco-hoje').textContent = s.hoje ? s.hoje + (s.hoje === 1 ? ' ciclo concluído hoje' : ' ciclos concluídos hoje') : 'Um ciclo de cada vez';
    document.title = (s.fim ? mm+':'+ss+' · ' : '')+'Pomodoro · '+document.querySelector('.marca').textContent;
    document.querySelectorAll('[data-foco-modo]').forEach(function (b) { var selecionado = b.dataset.focoModo === s.modo; b.setAttribute('aria-selected',String(selecionado)); b.tabIndex = selecionado ? 0 : -1; });
  }
  function atualizar() {
    clearTimeout(tick); var terminou = motor.atualizar(Date.now());
    if (terminou) { guardar(); toque(); }
    pintar();
    // Sem laço ocioso: só acorda com um timer em execução e a aba visível.
    if (motor.s.fim && !document.hidden) tick = setTimeout(atualizar,1000);
  }
  function aplicar() { guardar(); atualizar(); }
  if (pagina) {
    $('#foco-tarefa').value = motor.s.tarefa;
    $('#foco-tarefa').onchange = function () { motor.s.tarefa = this.value.slice(0,120); guardar(); };
    $('#foco-tarefa').oninput = function () { motor.s.tarefa = this.value.slice(0,120); };
    $('#foco-iniciar').onclick = function () { ativarAudio(); motor.alternar(Date.now()); aplicar(); };
    async function confirmarTroca() { return !motor.s.fim || await window.OrquestraInterface.confirmar({titulo:'Trocar de etapa?',texto:'O ciclo em andamento será encerrado sem contar como concluído.',confirmar:'Trocar etapa'}); }
    $('#foco-reiniciar').onclick = async function () { if (await confirmarTroca()) { motor.reiniciar(); aplicar(); } };
    $('#foco-proxima').onclick = async function () { if (await confirmarTroca()) { motor.mudar(motor.proximo()); aplicar(); } };
    document.querySelectorAll('[data-foco-modo]').forEach(function (b) { b.onclick = async function () { if (b.dataset.focoModo !== motor.s.modo && await confirmarTroca()) { motor.mudar(b.dataset.focoModo); aplicar(); } }; b.onkeydown = function (e) { if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return; e.preventDefault(); var botoes = Array.from(b.parentElement.children), i=botoes.indexOf(b); var alvo = e.key === 'Home' ? 0 : e.key === 'End' ? 2 : (i+(e.key === 'ArrowRight'?1:2))%3; botoes[alvo].focus(); botoes[alvo].click(); }; });
    $('#foco-configurar').onclick = function () { ['foco','curta','longa'].forEach(function (m) { $('#foco-minutos-'+m).value = motor.s.duracoes[m]; }); $('#foco-som').checked = motor.s.som; $('#foco-ajustes').showModal(); };
    document.querySelectorAll('[data-foco-passo]').forEach(function (b) { b.onclick = function () { var campo=$('#foco-minutos-'+b.dataset.alvo); campo.value=Math.max(1,Math.min(180,(Number(campo.value)||1)+Number(b.dataset.focoPasso))); }; });
    $('#foco-ajustes-form').onsubmit = async function (e) { e.preventDefault(); if (!this.reportValidity() || !await confirmarTroca()) return; var d={}; ['foco','curta','longa'].forEach(function (m) { d[m]=Number($('#foco-minutos-'+m).value); }); motor.configurar(d,$('#foco-som').checked); ativarAudio(); $('#foco-ajustes').close(); aplicar(); };
  }
  document.addEventListener('visibilitychange',atualizar);
  window.addEventListener('pageshow',atualizar);
  window.addEventListener('pagehide',guardar);
  guardar(); atualizar();
})();
