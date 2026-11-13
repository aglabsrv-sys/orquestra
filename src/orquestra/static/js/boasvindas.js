/* Orquestra: tela de boas-vindas (escolher um vault que já existe ou criar um novo).
   JavaScript puro, como o resto do painel. Todo texto que vem do disco (nomes de
   pastas, campos encontrados) entra na página com textContent, nunca como HTML. */
(function () {
  "use strict";

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var raiz = $("#boas-vindas");
  if (!raiz) return;

  var modo = "";      // "existente" ou "novo"
  var analise = null; // resposta de /api/boas-vindas/analisar
  var capacidade = null;
  var numeroAnalise = 0, numeroProcura = 0, preparando = false;
  var reduzirMovimento = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function el(tag, classe, texto) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  function avisar(texto, tipo) {
    if (tipo === "erro") {
      var erro = $("#bv-erro");
      erro.textContent = texto;
      erro.hidden = false;
      erro.scrollIntoView({ behavior: reduzirMovimento ? "auto" : "smooth", block: "nearest" });
      return;
    }
    window.OrquestraInterface.avisar(texto, tipo);
  }

  function limparErro() {
    $("#bv-erro").hidden = true;
    $("#bv-erro").textContent = "";
  }

  function estado(texto) { $("#bv-estado").textContent = texto || ""; }

  function erroCampo(id, mensagem) {
    var campo = $("#" + id), detalhe = $("#erro-" + id);
    if (!campo || !detalhe) return;
    detalhe.textContent = mensagem || "";
    detalhe.hidden = !mensagem;
    if (mensagem) campo.setAttribute("aria-invalid", "true");
    else campo.removeAttribute("aria-invalid");
  }

  function etapa(numero) {
    $$("[data-etapa]").forEach(function (item) {
      if (Number(item.dataset.etapa) === numero) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
  }

  function invalidarAnalise() {
    numeroAnalise += 1;
    analise = null;
    $("#analisar").disabled = false;
    $("#analisar").textContent = "Olhar a pasta";
    $("#bloco-existente").removeAttribute("aria-busy");
    $("#analise").hidden = true;
    $("#bloco-comum").hidden = true;
    estado("");
  }

  function api(url, corpo) {
    if (!capacidade) capacidade = fetch("/api/local/capacidade", { cache: "no-store", credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (r) { return r.token || r.capacidade || ""; })
      .catch(function () { capacidade = null; return ""; });
    return capacidade.then(function (token) {
      if (!token) { capacidade = null; throw new Error("Escolher ou criar um vault exige acesso direto: abra localhost no computador onde o Orquestra está rodando."); }
      return fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Orquestra-Local": token }, credentials: "same-origin", body: JSON.stringify(corpo || {}) });
    })
      .then(function (resp) {
        return resp.json().catch(function () { return {}; }).then(function (dados) {
          if (!resp.ok) throw new Error(dados.erro || window.OrquestraInterface.mensagemErro(null, resp.status));
          return dados;
        });
      }).catch(function (erro) { if (erro instanceof TypeError) throw new Error("Sem conexão com o Orquestra. Ele está rodando?"); throw erro; });
  }

  function focar(seletor) {
    var alvo = $(seletor);
    if (!alvo) return;
    if (!/^(INPUT|BUTTON|SELECT|TEXTAREA|A)$/.test(alvo.tagName)) alvo.setAttribute("tabindex", "-1");
    requestAnimationFrame(function () { alvo.focus({ preventScroll: true }); });
  }

  function plural(n, um, varios) { return n + " " + (n === 1 ? um : varios); }

  // ---------------------------------------------------------------- passos

  function mostrar(qual) {
    if (preparando) return;
    invalidarAnalise();
    numeroProcura += 1;
    limparErro();
    ["caminho-existente", "caminho-novo", "nome"].forEach(function (id) { erroCampo(id, ""); });
    modo = qual;
    etapa(qual ? 2 : 1);
    $("#passo-escolha").hidden = !!qual;
    $("#bloco-existente").hidden = qual !== "existente";
    $("#bloco-novo").hidden = qual !== "novo";
    $("#bloco-comum").hidden = qual !== "novo"; // no "já tenho", só depois de olhar a pasta
    if ($("#passo-pronto").open) $("#passo-pronto").close();
    if (qual === "novo") {
      $("#titulo-prontos").textContent = "Áreas do painel";
      $("#texto-prontos").textContent = "Vêm do ponto de partida que você escolheu. Marque e desmarque à vontade: dá para mudar depois, em Ajustes.";
      $("#exemplos").checked = true;
      $("#backup").checked = true;
      $("#concluir").textContent = "Criar e abrir o painel";
      aplicarPerfil();
    } else if (qual === "existente") {
      $("#analise").hidden = true;
      analise = null;
      $$('input[name="modulo"]').forEach(function (c) { c.checked = false; c.disabled = false; });
      $("#exemplos").checked = false;
      $("#backup").checked = false;
      $("#concluir").textContent = "Abrir o painel";
    }
    iniciarPassos();
    resumir();
    window.scrollTo({ top: 0, behavior: reduzirMovimento ? "auto" : "smooth" });
    focar(qual === "novo" ? "#caminho-novo" : qual === "existente" ? "#caminho-existente" : "[data-modo]");
  }

  function aplicarPerfil() {
    var escolhido = $('input[name="perfil"]:checked');
    var lista = escolhido ? escolhido.dataset.modulos.split(",") : [];
    $$('input[name="modulo"]').forEach(function (c) { c.disabled = false; c.checked = lista.indexOf(c.value) >= 0; });
    resumir();
  }

  // ---------------------------------------------------------------- análise de uma pasta que já existe

  function analisar() {
    if (preparando || modo !== "existente") return;
    var caminho = $("#caminho-existente").value.trim(), botao = $("#analisar");
    limparErro();
    if (!caminho) { erroCampo("caminho-existente", "Informe o caminho da pasta ou use Procurar."); $("#caminho-existente").focus(); return; }
    erroCampo("caminho-existente", "");
    invalidarAnalise();
    var numero = numeroAnalise;
    botao.disabled = true;
    botao.textContent = "Lendo a pasta…";
    $("#bloco-existente").setAttribute("aria-busy", "true");
    estado("Lendo suas pastas e notas. Nenhum arquivo está sendo alterado.");
    api("/api/boas-vindas/analisar", { caminho: caminho })
      .then(function (dados) {
        if (numero !== numeroAnalise || modo !== "existente" || $("#caminho-existente").value.trim() !== caminho) return;
        if (!dados.existe) throw new Error("Essa pasta não existe. Confira o caminho, ou volte e escolha “Criar um vault novo”.");
        analise = dados;
        $("#caminho-existente").value = dados.caminho;
        desenharAnalise();
      })
      .catch(function (erro) {
        if (numero !== numeroAnalise || modo !== "existente") return;
        erroCampo("caminho-existente", erro.message);
        avisar(erro.message, "erro");
        estado("Não foi possível ler a pasta. Confira o caminho e tente novamente.");
      })
      .finally(function () {
        if (numero !== numeroAnalise) return;
        botao.disabled = false; botao.textContent = "Olhar a pasta";
        $("#bloco-existente").removeAttribute("aria-busy");
      });
  }

  function desenharAnalise() {
    var a = analise, resumo = $("#analise-resumo"), lista = $("#analise-pastas");
    resumo.textContent = "";
    lista.textContent = "";

    var titulo = el("p");
    titulo.appendChild(el("b", "", a.nome));
    titulo.appendChild(document.createTextNode(" · " + plural(a.notas, "nota", "notas") + (a.obsidian ? " · cofre do Obsidian" : "")));
    resumo.appendChild(titulo);
    if (a.ja_e_vault) {
      resumo.appendChild(el("p", "", "Esta pasta já está preparada para o painel" + (a.modulos.length ? " (" + a.modulos.map(function (m) { return m.nome; }).join(", ") + ")" : "") + ". Você pode abrir agora, ou aproveitar para acrescentar áreas."));
    } else if (a.notas) {
      var estilo = el("p", "suave");
      estilo.appendChild(document.createTextNode("Jeito de organizar: "));
      estilo.appendChild(el("b", "", a.estilo.nome));
      estilo.appendChild(document.createTextNode(". " + a.estilo.descricao));
      resumo.appendChild(estilo);
    } else {
      resumo.appendChild(el("p", "suave", "A pasta está vazia. Marque abaixo as áreas com que quer começar."));
    }
    if (a.truncado) resumo.appendChild(el("p", "suave", "A pasta é muito grande: contei só uma parte dela."));

    var adotaveis = a.pastas.filter(function (p) { return !p.modulo; });
    $("#analise-pastas-bloco").hidden = !adotaveis.length;
    adotaveis.forEach(function (p) {
      var linha = el("div", "bv-pasta");
      var marca = el("label", "bv-pasta-marca");
      var caixa = el("input");
      caixa.type = "checkbox"; caixa.dataset.pasta = p.pasta;
      marca.appendChild(caixa);
      var texto = el("span");
      texto.appendChild(el("b", "", p.pasta));
      var detalhe = plural(p.notas, "nota", "notas");
      var campos = (p.campos || []).map(function (c) { return c.nome; });
      if (campos.length) detalhe += " · campos: " + campos.slice(0, 5).join(", ") + (campos.length > 5 ? "…" : "");
      else detalhe += " · sem campos no topo das notas";
      texto.appendChild(el("small", "", detalhe));
      marca.appendChild(texto);
      linha.appendChild(marca);

      var lado = el("span", "bv-pasta-lado");
      if (p.tem_status) lado.appendChild(el("em", "et", "vira quadro"));
      else {
        var q = el("label", "bv-quadro");
        var cq = el("input"); cq.type = "checkbox"; cq.dataset.quadro = p.pasta;
        cq.setAttribute("aria-label", "Incluir quadro em " + p.pasta);
        cq.disabled = true;
        caixa.addEventListener("change", function () { cq.disabled = !caixa.checked; if (!caixa.checked) cq.checked = false; });
        q.appendChild(cq); q.appendChild(el("span", "", "com quadro"));
        q.title = "Acrescenta um campo de status (a fazer, fazendo, feito). As notas atuais ficam numa coluna “sem status”.";
        lado.appendChild(q);
      }
      linha.appendChild(lado);
      lista.appendChild(linha);
    });

    // Áreas prontas: as que já existem como pasta não podem ser acrescentadas por cima.
    var nomes = a.pastas.map(function (p) { return p.pasta.toLowerCase(); });
    $$('input[name="modulo"]').forEach(function (c) {
      var existe = nomes.indexOf(c.value) >= 0;
      c.disabled = existe; if (existe) c.checked = false;
      c.closest("label").title = existe ? "Já existe uma pasta com esse nome no seu vault." : "";
    });
    $("#titulo-prontos").textContent = "Quer acrescentar alguma área pronta?";
    $("#texto-prontos").textContent = "Opcional. Cada uma é uma pasta nova no vault, com campos e instruções para agentes. Suas pastas não são tocadas.";
    var avisoGit = $("#aviso-backup");
    avisoGit.hidden = !a.tem_git;
    avisoGit.textContent = a.tem_git ? "Esta pasta já usa Git. O histórico do Orquestra é separado da sua branch. Configurações existentes precisam ser revisadas e autorizadas em Ajustes antes do backup." : "";

    $("#analise").hidden = false;
    $("#bloco-comum").hidden = false;
    $("#concluir").textContent = "Abrir o painel";
    estado("Pasta lida. Confira as áreas e as opções antes de abrir o painel.");
    resumir();
    iniciarPassos();
    $("#analise").scrollIntoView({ behavior: reduzirMovimento ? "auto" : "smooth", block: "start" });
    focar("#analise-resumo");
  }

  // ---------------------------------------------------------------- o que vai ser criado

  function escolhas() {
    var pastas = $$("[data-pasta]:checked").map(function (c) {
      var q = $('[data-quadro="' + CSS.escape(c.dataset.pasta) + '"]');
      return { pasta: c.dataset.pasta, quadro: !!(q && q.checked) };
    });
    var tema = $('input[name="tema"]:checked');
    return {
      modo: modo,
      caminho: (modo === "novo" ? $("#caminho-novo") : $("#caminho-existente")).value.trim(),
      nome: $("#nome").value.trim(),
      tema: tema ? tema.value : "",
      aparencia: {modo:$('#bv-modo').value,cena:$('#bv-cena').value,fonte:$('#bv-fonte').value,cantos:$('#bv-cantos').value,tamanho:$('#bv-tamanho').value,destaque:$('#bv-destaque').dataset.editado ? $('#bv-destaque').value : ''},
      modulos: $$('input[name="modulo"]:checked').map(function (c) { return c.value; }),
      pastas: pastas,
      exemplos: $("#exemplos").checked,
      backup: $("#backup").checked
    };
  }

  function resumir() {
    var lista = $("#vai-criar");
    if (!lista) return;
    var e = escolhas(), itens = [];
    $("#resumo-caminho").textContent = e.caminho || "Escolha uma pasta acima";
    var jaVault = analise && analise.ja_e_vault && modo === "existente";
    if (!jaVault) {
      itens.push("orquestra.yaml e a pasta _orquestra/ (configuração e temas do painel)");
      if (modo === "existente" && analise && analise.tem_agents) itens.push("AGENTS.orquestra.md (o seu AGENTS.md fica como está)");
      else itens.push("AGENTS.md e CLAUDE.md (as regras que os agentes de IA leem)");
    }
    e.pastas.forEach(function (p) { itens.push(p.pasta + "/_modulo.yaml (para a sua pasta aparecer como área)"); });
    if (e.modulos.length) itens.push(plural(e.modulos.length, "pasta nova do catálogo", "pastas novas do catálogo") + (e.exemplos ? ", com notas de exemplo" : ", sem exemplos"));
    itens.push("diario/ (o registro do que muda, criado conforme você usa)");
    if (e.backup) itens.push(".git/ (histórico de versões, só neste computador)");
    lista.textContent = "";
    itens.forEach(function (t) { lista.appendChild(el("li", "", t)); });
    $("#nao-toco").hidden = modo !== "existente";
  }

  // ---------------------------------------------------------------- concluir

  function concluir() {
    if (preparando) return;
    var e = escolhas(), botao = $("#concluir");
    limparErro();
    var idCaminho = modo === "novo" ? "caminho-novo" : "caminho-existente";
    if (!e.caminho) { erroCampo(idCaminho, "Informe a pasta onde o vault vai ficar."); focar("#" + idCaminho); return; }
    if (!e.nome) { erroCampo("nome", "Dê um nome para o painel."); focar("#nome"); return; }
    erroCampo(idCaminho, ""); erroCampo("nome", "");
    if (modo === "existente" && !analise) { analisar(); return; }
    numeroProcura += 1;
    preparando = true;
    var controles = $$("input, select, button", raiz).filter(function (c) { return !c.disabled; });
    controles.forEach(function (c) { c.disabled = true; });
    raiz.setAttribute("aria-busy", "true");
    estado("Preparando o vault. Aguarde nesta tela para acompanhar o resultado.");
    botao.disabled = true;
    var antes = botao.textContent;
    botao.textContent = "Preparando…";
    api("/api/boas-vindas/concluir", e)
      .then(function (r) {
        var avisos = (r.avisos || []).slice();
        if (r.pediu_git && !r.com_git) avisos.push("Não liguei o histórico porque o git não está instalado. Instale em git-scm.com e ligue depois, em Ajustes.");
        $("#bv-navegacao").hidden = true;
        ["#bloco-existente", "#bloco-novo", "#bloco-comum"].forEach(function (s) { $(s).hidden = true; });
        $("#pronto-texto").textContent = "Seu cofre foi preparado. Suas notas e áreas já estão disponíveis.";
        var lista = $("#pronto-avisos");
        lista.textContent = "";
        avisos.forEach(function (a) { lista.appendChild(el("li", "", a)); });
        $("#passo-pronto").showModal();
        etapa(3); estado("Seu vault está pronto. Confira os avisos antes de continuar.");
        raiz.removeAttribute("aria-busy");
        window.scrollTo({ top: 0, behavior: reduzirMovimento ? "auto" : "smooth" });
        focar("#passo-pronto a");
      })
      .catch(function (erro) {
        preparando = false;
        controles.forEach(function (c) { c.disabled = false; });
        raiz.removeAttribute("aria-busy");
        avisar(erro.message, "erro");
        estado("A preparação não terminou. Confira o aviso e tente novamente.");
        botao.textContent = antes;
      });
  }

  $("#passo-pronto").addEventListener("cancel", function (e) { e.preventDefault(); location.href = "/"; });

  var paginas = [], paginaAtual = 0;
  function iniciarPassos() {
    paginas = ["pasta", "areas", "visual"];
    paginaAtual = modo === 'existente' && analise && paginas.length > 1 ? 1 : 0; pintarPasso();
  }
  function pintarPasso() {
    var atual = paginas[paginaAtual];
    $("#bv-navegacao").hidden = !modo || (modo === "existente" && !analise);
    $("#bloco-novo").hidden = modo !== "novo" || atual !== "pasta";
    $("#bloco-existente").hidden = modo !== "existente" || (atual !== 'pasta' && atual !== 'areas');
    if (modo === 'existente') {
      Array.from($('#bloco-existente').children).forEach(function (p) { if (p.id !== 'analise') p.hidden = atual !== 'pasta'; });
      $('#analise').hidden = atual !== 'areas';
      $$('.bv-pasta').forEach(function (p) { p.hidden = false; });
    }
    $("#bloco-comum").hidden = atual === "pasta";
    $("#bv-perfis-bloco").hidden = modo !== "novo";
    $$("[data-bv-pagina]").forEach(function (p) { p.hidden = p.dataset.bvPagina !== atual.split('-')[0]; });
    // No primeiro passo do vault novo, apenas o caminho fica visível.
    if (modo === "novo") {
      Array.from($("#bloco-novo").children).forEach(function (p) { if (!p.dataset.bvPagina) p.hidden = atual !== "pasta"; });
    }
    $("#bv-passo").textContent = (paginaAtual + 1) + " de " + paginas.length;
    $("#bv-proximo").hidden = atual === "visual";
    $("#bv-anterior").disabled = paginaAtual === 0;
    etapa(atual === "visual" ? 3 : 2);
  }
  $("#bv-proximo").onclick = function () {
    var campo = modo === "novo" ? $("#caminho-novo") : $("#caminho-existente");
    if (!campo.value.trim()) { campo.reportValidity(); return; }
    if (modo === 'existente' && !analise) { analisar(); return; }
    if (paginas[paginaAtual] === "visual" && !$("#nome").reportValidity()) return;
    paginaAtual = Math.min(paginaAtual + 1, paginas.length - 1); pintarPasso();
  };
  $("#bv-anterior").onclick = function () { paginaAtual = Math.max(0, paginaAtual - 1); pintarPasso(); };

  // ---------------------------------------------------------------- ligações

  $$("[data-modo]").forEach(function (b) { b.onclick = function () { mostrar(b.dataset.modo); }; });
  $$("[data-recomecar]").forEach(function (b) { b.onclick = function () { mostrar(""); }; });
  $$(".bv-cofre").forEach(function (b) {
    b.onclick = function () { $("#caminho-existente").value = b.dataset.caminho; analisar(); };
  });
  $$("[data-procurar]").forEach(function (b) {
    b.onclick = function () {
      if (preparando) return;
      var numero = ++numeroProcura, modoInicial = modo;
      var campo = $("#" + b.dataset.procurar), valorInicial = campo.value;
      b.disabled = true;
      api("/api/boas-vindas/procurar", {})
        .then(function (r) {
          if (!r.caminho || numero !== numeroProcura || modo !== modoInicial || campo.value !== valorInicial) return;
          campo.value = r.caminho;
          erroCampo(campo.id, ""); limparErro(); resumir();
          if (b.dataset.procurar === "caminho-existente") analisar();
          else campo.focus();
        })
        .catch(function (erro) { if (numero === numeroProcura && modo === modoInicial) avisar(erro.message, "erro"); })
        .then(function () { if (!preparando) b.disabled = false; });
    };
  });
  $("#analisar").onclick = analisar;
  $("#caminho-existente").addEventListener("keydown", function (e) { if (e.key === "Enter") analisar(); });
  $("#caminho-existente").addEventListener("input", invalidarAnalise);
  ["caminho-existente", "caminho-novo", "nome"].forEach(function (id) {
    $("#" + id).addEventListener("input", function () { erroCampo(id, ""); limparErro(); resumir(); });
  });
  $$('input[name="perfil"]').forEach(function (r) { r.onchange = aplicarPerfil; });
  $("#concluir").onclick = concluir;
  raiz.addEventListener("change", resumir);

  var previaSequencia=0;
  async function atualizarVisual(){
    var escolhido=$('input[name="tema"]:checked');if(!escolhido)return;
    var numero=++previaSequencia,capa=JSON.parse(escolhido.dataset.capa||'{}');
    if($('#bv-cena').value)capa.cena=$('#bv-cena').value;
    document.querySelectorAll('.bv-capa canvas,.bv-previa-visual canvas').forEach(function(c){window.Orquestra.atualizarCena(c,capa);});
    try{var r=await fetch('/api/boas-vindas/visual?tema='+encodeURIComponent(escolhido.value)+'&modo='+$('#bv-modo').value+'&destaque='+encodeURIComponent($('#bv-destaque').dataset.editado?$('#bv-destaque').value:''));if(!r.ok)return;var d=await r.json();if(numero!==previaSequencia)return;
      var estilo=$('#bv-estilo-previa');if(!estilo){estilo=document.createElement('style');estilo.id='bv-estilo-previa';document.head.appendChild(estilo);}estilo.textContent=d.estilo;
      var root=document.documentElement;root.style.setProperty('--fonte',$('#bv-fonte').selectedOptions[0].dataset.fonte);root.style.setProperty('--cantos',({reto:0,discreto:.45,medio:1,redondo:1.45})[$('#bv-cantos').value]);root.style.setProperty('--tamanho-fonte',({pequena:'14px',padrao:'16px',grande:'18px'})[$('#bv-tamanho').value]);
      if(!$('#bv-destaque').dataset.editado)$('#bv-destaque').value=JSON.parse(escolhido.dataset.cores).destaque;
    }catch(e){/* A seleção continua disponível sem a prévia. */}
  }
  $$('input[name="tema"],.bv-visual-compacto select').forEach(function(r){r.addEventListener('change',atualizarVisual);});
  if($('#bv-destaque'))$('#bv-destaque').addEventListener('input',function(){this.dataset.editado='1';atualizarVisual();});
  var inicio = typeof URLSearchParams !== "undefined" && typeof location !== "undefined" ? new URLSearchParams(location.search).get("modo") : "";
  if (inicio === "novo" || inicio === "existente") mostrar(inicio);
})();
