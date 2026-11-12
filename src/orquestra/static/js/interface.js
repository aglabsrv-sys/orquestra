/* Interações comuns: confirmações no painel e avisos que podem ser lidos com calma. */
(function (raiz, construir) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = construir;
  else raiz.OrquestraInterface = construir(raiz.document, raiz);
})(typeof globalThis !== "undefined" ? globalThis : this, function (documento, ambiente) {
  "use strict";

  var avisos = new Map(), fila = [], confirmacaoAtiva = false, numero = 0;
  var agendar = ambiente.setTimeout.bind(ambiente), cancelar = ambiente.clearTimeout.bind(ambiente);
  var agora = ambiente.performance && ambiente.performance.now ? ambiente.performance.now.bind(ambiente.performance) : Date.now;

  function criar(tag, classe, texto) {
    var el = documento.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  }

  function mensagemErro(erro, status) {
    if (erro && typeof erro.message === "string" && erro.message.trim()) return erro.message;
    var mensagens = {
      400: "Revise os dados informados e tente novamente.",
      401: "A autorização expirou. Reabra o painel para continuar.",
      403: "Esta ação precisa de autorização. Confira as permissões em Ajustes.",
      404: "Este item não está mais disponível. Atualize a página para conferir o vault.",
      409: "O arquivo ou a configuração mudou. Atualize a página antes de tentar novamente.",
      413: "O conteúdo é maior do que o painel aceita. Reduza o tamanho e tente novamente.",
      422: "Revise os campos informados. Há um valor que não pôde ser aceito.",
      429: "Há muitas operações em andamento. Aguarde um momento e tente novamente.",
      503: "O painel não conseguiu concluir a gravação. Confira o espaço em disco e tente novamente."
    };
    return mensagens[status] || "Não foi possível concluir esta ação. Tente novamente em instantes.";
  }

  function avisar(texto, tipo, acao) {
    // Fora do diálogo modal, o conteúdo fica inert. O aviso precisa continuar acessível.
    var abertos = documento.querySelectorAll("dialog[open]"), modal = abertos.length ? abertos[abertos.length - 1] : null;
    var caixa = modal ? modal.querySelector(".avisos-dialogo") : documento.querySelector("#avisos");
    if (modal && !caixa) { caixa = criar("div", "avisos-dialogo"); modal.appendChild(caixa); }
    if (!caixa || !texto) return;
    tipo = tipo === "erro" || tipo === "alerta" || tipo === "info" ? tipo : "sucesso";
    function revelar(el) {
      // O formulário pode ser maior que a janela; mostrar a falha sem tirar o foco do campo.
      if (modal && (tipo === "erro" || tipo === "alerta") && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "nearest", behavior: "auto" });
    }
    var chave = tipo + ":" + texto;
    if (avisos.has(chave)) {
      var existente = avisos.get(chave);
      if (existente.elemento.parentNode !== caixa) { existente.origem(documento.activeElement); caixa.appendChild(existente.elemento); }
      existente.renovar(); revelar(existente.elemento); return existente.fechar;
    }
    var focoAnterior = documento.activeElement;
    var el = criar("div", "aviso " + tipo);
    el.setAttribute("role", tipo === "erro" ? "alert" : "status");
    el.setAttribute("aria-live", tipo === "erro" ? "assertive" : "polite");
    el.setAttribute("aria-atomic", "true");
    var icone = criar("span", "aviso-icone", tipo === "sucesso" ? "✓" : tipo === "info" ? "i" : "!");
    icone.setAttribute("aria-hidden", "true");
    var conteudo = criar("div", "aviso-conteudo");
    var titulo = criar("strong", "aviso-titulo", { erro: "Não foi possível concluir", alerta: "Atenção", info: "Informação", sucesso: "Pronto" }[tipo]);
    conteudo.appendChild(titulo);
    conteudo.appendChild(criar("p", "aviso-texto", String(texto)));
    el.appendChild(icone); el.appendChild(conteudo);
    var tempo = tipo === "erro" || tipo === "alerta" || acao ? 0 : 6000, restante = tempo, iniciou = 0, timer = null;
    var ponteiro = false, foco = false, removido = false;
    function fechar() {
      if (removido) return;
      var devolverFoco = el.contains(documento.activeElement);
      removido = true; cancelar(timer); avisos.delete(chave); el.remove();
      if (devolverFoco && focoAnterior && focoAnterior.isConnected && !focoAnterior.disabled && typeof focoAnterior.focus === "function") focoAnterior.focus();
    }
    function pausar() { if (timer !== null) { cancelar(timer); timer = null; restante = Math.max(0, restante - (agora() - iniciou)); } }
    function continuar() {
      if (tempo && !ponteiro && !foco && !removido && timer === null) {
        iniciou = agora(); timer = agendar(fechar, Math.max(0, restante));
      }
    }
    if (acao) {
      var acoes = criar("div", "aviso-acoes"), botao = criar("button", "botao discreto", acao.rotulo);
      botao.type = "button";
      botao.addEventListener("click", function () {
        if (botao.disabled) return;
        botao.disabled = true;
        Promise.resolve().then(acao.fazer).then(fechar).catch(function (erro) { botao.disabled = false; avisar(mensagemErro(erro), "erro"); });
      });
      acoes.appendChild(botao); conteudo.appendChild(acoes);
    }
    var encerrar = criar("button", "aviso-fechar", "×"); encerrar.type = "button";
    encerrar.setAttribute("aria-label", "Fechar aviso");
    encerrar.addEventListener("click", fechar); el.appendChild(encerrar);
    el.addEventListener("mouseenter", function () { ponteiro = true; pausar(); });
    el.addEventListener("mouseleave", function () { ponteiro = false; continuar(); });
    el.addEventListener("focusin", function () { foco = true; pausar(); });
    el.addEventListener("focusout", function (e) { foco = el.contains(e.relatedTarget); if (!foco) continuar(); });
    avisos.set(chave, { elemento: el, fechar: fechar, origem: function (alvo) { focoAnterior = alvo; }, renovar: function () { pausar(); restante = tempo; continuar(); } });
    caixa.appendChild(el); continuar(); revelar(el);
    return fechar;
  }

  function proximaConfirmacao() {
    if (confirmacaoAtiva || !fila.length) return;
    confirmacaoAtiva = true;
    var pedido = fila.shift(), opcoes = pedido.opcoes, anterior = documento.activeElement;
    var dialogo = criar("dialog", "dialogo confirmacao"), corpo = criar("div", "dialogo-corpo"), id = "confirmacao-" + (++numero);
    var titulo = criar("h2", "", opcoes.titulo || "Confirmar ação"), texto = criar("p", "suave", opcoes.texto || "");
    titulo.id = id + "-titulo"; texto.id = id + "-texto";
    dialogo.setAttribute("aria-labelledby", titulo.id);
    if (opcoes.texto) dialogo.setAttribute("aria-describedby", texto.id);
    var icone = criar("span", "confirmacao-icone" + (opcoes.perigoso ? " perigo" : ""), opcoes.perigoso ? "!" : "?");
    icone.setAttribute("aria-hidden", "true"); corpo.appendChild(icone);
    corpo.appendChild(titulo); if (opcoes.texto) corpo.appendChild(texto);
    if (opcoes.detalhes) corpo.appendChild(criar("pre", "confirmacao-detalhes", opcoes.detalhes));
    var acoes = criar("div", "dialogo-acoes"), nao = criar("button", "botao", opcoes.cancelar || "Cancelar");
    var sim = criar("button", "botao " + (opcoes.perigoso ? "perigo" : "principal"), opcoes.confirmar || "Confirmar");
    nao.type = "button"; sim.type = "button"; nao.autofocus = true;
    acoes.appendChild(nao); acoes.appendChild(sim); corpo.appendChild(acoes); dialogo.appendChild(corpo);
    var encerrado = false, confirmado = false;
    function terminar() {
      if (encerrado) return;
      encerrado = true; dialogo.remove(); confirmacaoAtiva = false;
      if (anterior && anterior.isConnected && !anterior.disabled && typeof anterior.focus === "function") anterior.focus();
      pedido.resolver(confirmado); proximaConfirmacao();
    }
    nao.addEventListener("click", function () { dialogo.close(); });
    sim.addEventListener("click", function () { confirmado = true; dialogo.close(); });
    dialogo.addEventListener("cancel", function () { confirmado = false; });
    dialogo.addEventListener("close", terminar);
    dialogo.addEventListener("click", function (e) { if (e.target === dialogo) dialogo.close(); });
    documento.body.appendChild(dialogo);
    try { dialogo.showModal(); nao.focus(); }
    catch (erro) { terminar(); avisar("Não foi possível abrir a confirmação. A ação foi cancelada; tente novamente.", "erro"); }
  }

  function confirmar(opcoes) {
    return new Promise(function (resolver) { fila.push({ opcoes: opcoes || {}, resolver: resolver }); proximaConfirmacao(); });
  }

  function ocupado(botao, rotulo) {
    var desabilitado = botao.disabled, alvo = botao.querySelector("span") || botao;
    var textoOriginal = alvo.textContent;
    botao.disabled = true; botao.setAttribute("aria-busy", "true");
    if (rotulo) alvo.textContent = rotulo;
    return function () {
      if (rotulo) alvo.textContent = textoOriginal;
      botao.disabled = desabilitado; botao.removeAttribute("aria-busy");
    };
  }

  return { avisar: avisar, confirmar: confirmar, mensagemErro: mensagemErro, ocupado: ocupado };
});
