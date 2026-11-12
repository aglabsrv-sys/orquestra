/* Estado independente do DOM: o relógio continua correto ao navegar ou suspender a aba. */
(function (raiz, criar) {
  var api = criar();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else raiz.OrquestraFoco = api;
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';
  var MODOS = ['foco', 'curta', 'longa'], PADROES = {foco:25, curta:5, longa:15};
  function dia(agora) { var d = new Date(agora); return d.getFullYear() + '-' + (d.getMonth()+1) + '-' + d.getDate(); }
  function estado(bruto, agora) {
    bruto = bruto && typeof bruto === 'object' ? bruto : {};
    var duracoes = {};
    MODOS.forEach(function (m) { var n = bruto.duracoes && bruto.duracoes[m]; duracoes[m] = Number.isInteger(n) && n >= 1 && n <= 180 ? n : PADROES[m]; });
    var modo = MODOS.includes(bruto.modo) ? bruto.modo : 'foco', total = duracoes[modo] * 60;
    var restante = Number.isFinite(bruto.restante) && bruto.restante >= 0 && bruto.restante <= total ? bruto.restante : total;
    var fim = Number.isFinite(bruto.fim) && bruto.fim > 0 && bruto.fim <= agora + total * 1000 ? bruto.fim : 0;
    return {modo:modo, duracoes:duracoes, restante:restante, fim:fim, concluido:!!bruto.concluido && !fim,
      ciclos:Number.isInteger(bruto.ciclos) && bruto.ciclos >= 0 ? Math.min(bruto.ciclos,9999) : 0,
      hoje:bruto.hoje === dia(agora) && Number.isInteger(bruto.hojeCiclos) ? Math.max(0,Math.min(bruto.hojeCiclos,9999)) : 0,
      data:dia(agora), tarefa:typeof bruto.tarefa === 'string' ? bruto.tarefa.slice(0,120) : '', som:!!bruto.som};
  }
  function Motor(bruto, agora) { this.s = estado(bruto, agora); this.atualizar(agora); }
  Motor.prototype.atualizar = function (agora) {
    var s = this.s, terminou = false;
    if (s.data !== dia(agora)) { s.data = dia(agora); s.hoje = 0; }
    if (s.fim) {
      s.restante = Math.max(0,Math.min(s.duracoes[s.modo]*60,Math.ceil((s.fim-agora)/1000)));
      if (!s.restante) { var terminouHoje = dia(s.fim) === dia(agora); s.fim = 0; s.concluido = true; terminou = true; if (s.modo === 'foco') { s.ciclos++; if (terminouHoje) s.hoje++; } }
    }
    return terminou;
  };
  Motor.prototype.proximo = function () { return this.s.modo === 'foco' ? (this.s.ciclos && this.s.ciclos % 4 === 0 ? 'longa' : 'curta') : 'foco'; };
  Motor.prototype.mudar = function (modo) { if (!MODOS.includes(modo)) return; this.s.modo = modo; this.reiniciar(); };
  Motor.prototype.reiniciar = function () { this.s.fim = 0; this.s.restante = this.s.duracoes[this.s.modo]*60; this.s.concluido = false; };
  Motor.prototype.alternar = function (agora) {
    this.atualizar(agora);
    if (this.s.fim) this.s.fim = 0;
    else { if (this.s.concluido) this.mudar(this.proximo()); this.s.fim = agora + this.s.restante*1000; }
  };
  Motor.prototype.configurar = function (duracoes, som) {
    var self = this;
    MODOS.forEach(function (m) { if (!Number.isInteger(duracoes[m]) || duracoes[m] < 1 || duracoes[m] > 180) throw new Error('Use de 1 a 180 minutos.'); });
    MODOS.forEach(function (m) { self.s.duracoes[m] = duracoes[m]; }); this.s.som = !!som; this.reiniciar();
  };
  Motor.prototype.exportar = function () {
    return {modo:this.s.modo, duracoes:this.s.duracoes, restante:this.s.restante, fim:this.s.fim, concluido:this.s.concluido,
      ciclos:this.s.ciclos, hoje:this.s.data, hojeCiclos:this.s.hoje, tarefa:this.s.tarefa, som:this.s.som};
  };
  return {Motor:Motor, padroes:PADROES};
});
