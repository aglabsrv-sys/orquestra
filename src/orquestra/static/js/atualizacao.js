/* Atualização do aplicativo: aviso discreto, confirmação e espera pela retomada. */
(function () {
  "use strict";
  var botao = document.querySelector("#atualizar-app"), estado = null, ocupado = false;
  if (!botao) return;
  var ui = window.OrquestraInterface;
  async function consultar() {
    var resposta = await fetch("/api/atualizacao", {cache:"no-store", credentials:"same-origin", signal:AbortSignal.timeout(25000)});
    if (!resposta.ok) throw new Error("Não foi possível consultar a atualização.");
    return resposta.json();
  }
  async function verificar() {
    if (ocupado || document.hidden) return;
    try {
      estado = await consultar();
      botao.hidden = !estado.disponivel;
      botao.classList.toggle("tem-atualizacao", !!estado.disponivel);
      botao.title = estado.local ? "Atualização disponível · atualizar Orquestra" : "Atualização disponível · abra localhost para instalar";
      botao.setAttribute("aria-label", botao.title);
    } catch (_) { /* Sem rede, o painel continua funcionando. */ }
  }
  botao.addEventListener("click", async function () {
    if (ocupado) return;
    // O clique consulta novamente: o resultado automático pode ter falhado ou mudado.
    try { estado = await consultar(); } catch (erro) { ui.avisar(erro.message, "erro"); return; }
    if (!estado.disponivel) { botao.hidden = true; ui.avisar("O Orquestra já está atualizado.", "info"); return; }
    if (!estado.local) { ui.avisar("Abra o painel em localhost no computador para atualizar.", "info"); return; }
    if (!await ui.confirmar({titulo:"Atualizar o Orquestra?", texto:"Salve as edições abertas antes de continuar. O aplicativo será atualizado e o painel reiniciado. Suas notas serão mantidas.", confirmar:"Atualizar e reiniciar"})) return;
    ocupado = true; botao.disabled = true; botao.classList.add("atualizando");
    try {
      var resposta = await fetch("/api/local/capacidade", {cache:"no-store", credentials:"same-origin"});
      var credencial = await resposta.json();
      if (!resposta.ok || !credencial.token) throw new Error("Abra localhost diretamente neste computador para atualizar.");
      resposta = await fetch("/api/atualizacao", {method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json", "X-Orquestra-Local":credencial.token, "X-Orquestra-Vault":document.body.dataset.vaultId}, body:"{}"});
      var dados = await resposta.json();
      if (!resposta.ok) throw new Error(dados.erro || "Não foi possível iniciar a atualização.");
      estado.revisao = dados.revisao || estado.revisao;
      ui.avisar("Atualizando o Orquestra. Aguarde a retomada do painel…", "info");
      var prazo = Date.now() + 360000, pid = estado.pid;
      while (Date.now() < prazo) {
        await new Promise(function (resolve) { setTimeout(resolve, 2000); });
        var novo;
        try { novo = await consultar(); } catch (_) { continue; }
        if (novo.pid !== pid && novo.instalada === estado.revisao) { location.reload(); return; }
        if (novo.estado === "falhou") throw new Error(novo.mensagem);
      }
      throw new Error("A retomada ainda não foi confirmada. Confira se o Orquestra está rodando antes de atualizar esta página.");
    } catch (erro) { ui.avisar(erro.message, "erro"); }
    finally { ocupado = false; botao.disabled = false; botao.classList.remove("atualizando"); }
  });
  setTimeout(verificar, 3000);
  setInterval(verificar, 1800000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) verificar(); });
})();
