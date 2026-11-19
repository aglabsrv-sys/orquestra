/* O calendário usa datas civis do painel. UTC serve apenas para contar dias e meses. */
(function () {
  'use strict';
  const porId = (id) => document.getElementById(id);
  const calendario = porId('diario-calendario');
  const abrir = porId('diario-abrir-calendario');
  const grade = porId('diario-grade');
  const titulo = porId('diario-mes');
  const anterior = porId('diario-mes-anterior');
  const seguinte = porId('diario-mes-seguinte');
  const legenda = porId('diario-legenda');
  const selecionada = calendario.dataset.dia;
  const hoje = calendario.dataset.hoje;
  const anotadas = new Set(JSON.parse(porId('diario-datas-anotadas').textContent));
  const formatoMes = new Intl.DateTimeFormat('pt-BR', {month: 'long', year: 'numeric', timeZone: 'UTC'});
  const formatoDia = new Intl.DateTimeFormat('pt-BR', {dateStyle: 'full', timeZone: 'UTC'});
  const dataCivil = (iso) => new Date(iso + 'T12:00:00Z');
  const iso = (data) => data.toISOString().slice(0, 10);
  const diaDaSemana = (data) => (data.getUTCDay() + 6) % 7;
  const dataValida = (data) => data.getUTCFullYear() >= 1 && data.getUTCFullYear() <= 9999;
  let dataDoFoco = dataCivil(selecionada);

  function renderizar() {
    const mes = new Date(dataDoFoco);
    mes.setUTCDate(1);
    const rotulo = formatoMes.format(mes);
    if (titulo.textContent !== rotulo) titulo.textContent = rotulo;
    anterior.disabled = mes.getUTCFullYear() === 1 && mes.getUTCMonth() === 0;
    seguinte.disabled = mes.getUTCFullYear() === 9999 && mes.getUTCMonth() === 11;

    const dias = document.createDocumentFragment();
    const data = new Date(mes);
    data.setUTCDate(1 - diaDaSemana(mes));
    const foco = iso(dataDoFoco);
    let temAnotacao = false;
    for (let semana = 0; semana < 6; semana++) {
      const linha = document.createElement('tr');
      for (let coluna = 0; coluna < 7; coluna++) {
        const celula = document.createElement('td');
        if (dataValida(data)) {
          const dia = iso(data);
          const temNota = anotadas.has(dia);
          const botao = document.createElement('button');
          botao.type = 'button';
          botao.className = 'diario-calendario-dia';
          botao.classList.toggle('fora', data.getUTCMonth() !== mes.getUTCMonth());
          botao.classList.toggle('anotado', temNota);
          botao.dataset.dia = dia;
          botao.tabIndex = dia === foco ? 0 : -1;
          botao.textContent = data.getUTCDate();
          botao.setAttribute('aria-label', formatoDia.format(data) + (temNota ? ', com anotação' : ''));
          if (dia === hoje) botao.setAttribute('aria-current', 'date');
          celula.setAttribute('aria-selected', String(dia === selecionada));
          celula.append(botao);
          temAnotacao ||= temNota;
        }
        linha.append(celula);
        data.setUTCDate(data.getUTCDate() + 1);
      }
      dias.append(linha);
    }
    grade.replaceChildren(dias);
    legenda.hidden = !temAnotacao;
  }

  function escolher(dia) {
    if (dia === selecionada) { calendario.close(); return; }
    const url = new URL(location.href);
    url.searchParams.set('dia', dia);
    // Trocar de dia mantém a entrada do Diário no histórico e o retorno à tela de origem.
    history.replaceState(history.state, '', url);
    location.reload();
  }

  function deslocarMes(data, passo) {
    const destino = new Date(data);
    destino.setUTCMonth(destino.getUTCMonth() + passo, 1);
    const ultimo = new Date(destino);
    ultimo.setUTCMonth(ultimo.getUTCMonth() + 1, 0);
    destino.setUTCDate(Math.min(data.getUTCDate(), ultimo.getUTCDate()));
    return destino;
  }

  function navegarMes(passo, botao) {
    dataDoFoco = deslocarMes(dataDoFoco, passo);
    renderizar();
    if (botao.disabled) grade.querySelector('[tabindex="0"]').focus();
  }

  abrir.hidden = false;
  abrir.addEventListener('click', function () {
    dataDoFoco = dataCivil(selecionada);
    renderizar();
    calendario.showModal();
    grade.querySelector('[tabindex="0"]').focus();
  });
  anterior.addEventListener('click', () => navegarMes(-1, anterior));
  seguinte.addEventListener('click', () => navegarMes(1, seguinte));
  porId('diario-hoje').addEventListener('click', () => escolher(hoje));
  grade.addEventListener('click', function (evento) {
    const botao = evento.target.closest('[data-dia]');
    if (botao) escolher(botao.dataset.dia);
  });
  grade.addEventListener('keydown', function (evento) {
    const botao = evento.target.closest('[data-dia]');
    if (!botao || evento.altKey || evento.ctrlKey || evento.metaKey) return;
    const atual = dataCivil(botao.dataset.dia);
    const passos = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -diaDaSemana(atual), End: 6 - diaDaSemana(atual)};
    let destino = new Date(atual);
    if (Object.hasOwn(passos, evento.key)) destino.setUTCDate(destino.getUTCDate() + passos[evento.key]);
    else if (evento.key === 'PageUp' || evento.key === 'PageDown') destino = deslocarMes(atual, evento.key === 'PageUp' ? -1 : 1);
    else return;
    evento.preventDefault();
    if (!dataValida(destino)) return;
    dataDoFoco = destino;
    renderizar();
    grade.querySelector('[tabindex="0"]').focus();
  });
})();
