/* Atualização do aplicativo: aviso discreto, confirmação e espera pela retomada. */
(function () {
  "use strict";
  var botao = document.querySelector("#atualizar-app"), ocupado = false, verificando = false;
  if (!botao) return;
  var ui = window.OrquestraInterface;
  async function consultar() {
    var controle = new AbortController();
    var limite = setTimeout(function () { controle.abort(); }, 25000);
    try {
      var resposta = await fetch("/api/atualizacao", {cache:"no-store", credentials:"same-origin", signal:controle.signal});
      if (!resposta.ok) throw new Error("Não foi possível consultar a atualização.");
      return await resposta.json();
    } finally { clearTimeout(limite); }
  }
  function mostrarEstado(estado) {
    botao.hidden = !estado.disponivel;
    botao.classList.toggle("tem-atualizacao", !!estado.disponivel);
    botao.title = estado.modo === "reiniciar"
      ? (estado.local ? "Arquivos novos · reiniciar Orquestra" : "Arquivos novos · abra localhost para reiniciar")
      : (estado.local ? "Atualização disponível · atualizar Orquestra" : "Atualização disponível · abra localhost para instalar");
    botao.setAttribute("aria-label", botao.title);
  }
  async function verificar() {
    if (ocupado || verificando || document.hidden) return;
    verificando = true;
    try {
      var estado = await consultar();
      if (!ocupado) mostrarEstado(estado);
    } catch (_) { /* Sem rede, o painel continua funcionando. */ }
    finally { verificando = false; }
  }
  botao.addEventListener("click", async function () {
    if (ocupado) return;
    ocupado = true;
    try {
      // O clique consulta novamente, porque o resultado automático pode ter mudado.
      var estado = await consultar();
      mostrarEstado(estado);
      if (!estado.disponivel) { ui.avisar("O Orquestra já está atualizado.", "info"); return; }
      if (!estado.local) { ui.avisar("Abra o painel em localhost no computador para atualizar.", "info"); return; }
      var reinicio = estado.modo === "reiniciar", pid = estado.pid, revisao = estado.revisao;
      if (!await ui.confirmar(reinicio
        ? {titulo:"Reiniciar o Orquestra?", texto:"Salve as edições abertas antes de continuar. O painel vai reiniciar com os arquivos locais.", confirmar:"Reiniciar com os novos arquivos"}
        : {titulo:"Atualizar o Orquestra?", texto:"Salve as edições abertas antes de continuar. O aplicativo será atualizado e o painel reiniciado. Suas notas serão mantidas.", confirmar:"Atualizar e reiniciar"})) return;
      botao.disabled = true; botao.classList.add("atualizando");
      var resposta = await fetch("/api/local/capacidade", {cache:"no-store", credentials:"same-origin"});
      var credencial = await resposta.json();
      if (!resposta.ok || !credencial.token) throw new Error("Abra localhost diretamente neste computador para atualizar.");
      resposta = await fetch("/api/atualizacao", {method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json", "X-Orquestra-Local":credencial.token, "X-Orquestra-Vault":document.body.dataset.vaultId}, body:JSON.stringify({modo:reinicio?"reiniciar":"baixar"})});
      var dados = await resposta.json();
      if (!resposta.ok) throw new Error(dados.erro || "Não foi possível iniciar a atualização.");
      revisao = dados.revisao || revisao;
      ui.avisar(reinicio ? "Reiniciando com os arquivos locais…" : "Atualizando o Orquestra. Aguarde a retomada do painel…", "info");
      var prazo = Date.now() + 360000;
      while (Date.now() < prazo) {
        await new Promise(function (resolve) { setTimeout(resolve, 2000); });
        var novo;
        try { novo = await consultar(); } catch (_) { continue; }
        if (novo.pid && novo.pid !== pid && (reinicio || novo.instalada === revisao)) { location.reload(); return; }
        if (novo.estado === "falhou") throw new Error(novo.mensagem);
      }
      throw new Error("A retomada ainda não foi confirmada. Confira se o Orquestra está rodando antes de atualizar esta página.");
    } catch (erro) { ui.avisar(erro.message, "erro"); }
    finally { ocupado = false; botao.disabled = false; botao.classList.remove("atualizando"); }
  });
  verificar();
  setInterval(verificar, 15000);
  window.addEventListener("pageshow", function (evento) { if (evento.persisted) verificar(); });
  document.addEventListener("visibilitychange", function () { if (!document.hidden) verificar(); });
})();
