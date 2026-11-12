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

  function el(tag, classe, texto) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  function avisar(texto, tipo) {
    var caixa = $("#avisos"), a = el("div", "aviso" + (tipo ? " " + tipo : ""), texto);
    caixa.appendChild(a);
    setTimeout(function () { a.remove(); }, tipo === "erro" ? 7000 : 2600);
  }

  function api(url, corpo) {
    if (!capacidade) capacidade = fetch("/api/local/capacidade", { cache: "no-store", credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (r) { return r.token || r.capacidade || ""; })
      .catch(function () { capacidade = null; return ""; });
    return capacidade.then(function (token) {
      if (!token) throw new Error("Escolher ou criar um vault exige acesso direto: abra localhost no computador onde o Orquestra está rodando.");
      return fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Orquestra-Local": token }, credentials: "same-origin", body: JSON.stringify(corpo || {}) });
    })
      .then(function (resp) {
        return resp.json().catch(function () { return {}; }).then(function (dados) {
          if (!resp.ok) throw new Error(dados.erro || "Erro " + resp.status);
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
    modo = qual;
    $("#passo-escolha").hidden = !!qual;
    $("#bloco-existente").hidden = qual !== "existente";
    $("#bloco-novo").hidden = qual !== "novo";
    $("#bloco-comum").hidden = qual !== "novo"; // no "já tenho", só depois de olhar a pasta
    $("#passo-pronto").hidden = true;
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
    resumir();
    window.scrollTo({ top: 0, behavior: "smooth" });
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
    var caminho = $("#caminho-existente").value.trim(), botao = $("#analisar");
    if (!caminho) { $("#caminho-existente").focus(); return; }
    botao.disabled = true;
    api("/api/boas-vindas/analisar", { caminho: caminho })
      .then(function (dados) {
        if (!dados.existe) throw new Error("Essa pasta não existe. Confira o caminho, ou volte e escolha “Criar um vault novo”.");
        analise = dados;
        $("#caminho-existente").value = dados.caminho;
        desenharAnalise();
      })
      .catch(function (erro) { avisar(erro.message, "erro"); })
      .then(function () { botao.disabled = false; });
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
    avisoGit.textContent = a.tem_git ? "Esta pasta já é um repositório git. Se você marcar a opção acima, o painel passa a fazer commits automáticos nele." : "";

    $("#analise").hidden = false;
    $("#bloco-comum").hidden = false;
    $("#concluir").textContent = "Abrir o painel";
    resumir();
    $("#analise").scrollIntoView({ behavior: "smooth", block: "start" });
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
    var jaVault = analise && analise.ja_e_vault && modo === "existente";
    if (!jaVault) {
      itens.push("orquestra.yaml e a pasta _orquestra/ (configuração e temas do painel)");
      if (modo === "existente" && analise && analise.tem_agents) itens.push("AGENTS.orquestra.md (o seu AGENTS.md fica como está)");
      else itens.push("AGENTS.md e CLAUDE.md (as regras que os agentes de IA leem)");
    }
    e.pastas.forEach(function (p) { itens.push(p.pasta + "/_modulo.yaml (para a sua pasta aparecer como área)"); });
    e.modulos.forEach(function (m) {
      var caixa = $('input[name="modulo"][value="' + m + '"]');
      itens.push(m + "/ (área " + $("b", caixa.closest("label")).textContent + (e.exemplos ? ", com exemplos" : "") + ")");
    });
    itens.push("diario/ (o registro do que muda, criado conforme você usa)");
    if (e.backup) itens.push(".git/ (histórico de versões, só neste computador)");
    lista.textContent = "";
    itens.forEach(function (t) { lista.appendChild(el("li", "", t)); });
    $("#nao-toco").hidden = modo !== "existente";
  }

  // ---------------------------------------------------------------- concluir

  function concluir() {
    var e = escolhas(), botao = $("#concluir");
    if (!e.caminho) { avisar("Diga qual é a pasta.", "erro"); return; }
    if (modo === "existente" && !analise) { analisar(); return; }
    botao.disabled = true;
    var antes = botao.textContent;
    botao.textContent = "Preparando…";
    api("/api/boas-vindas/concluir", e)
      .then(function (r) {
        var avisos = (r.avisos || []).slice();
        if (r.pediu_git && !r.com_git) avisos.push("Não liguei o histórico porque o git não está instalado. Instale em git-scm.com e ligue depois, em Ajustes.");
        if (!avisos.length) { location.href = "/"; return; }
        ["#bloco-existente", "#bloco-novo", "#bloco-comum"].forEach(function (s) { $(s).hidden = true; });
        $("#pronto-texto").textContent = "O vault está pronto em " + r.vault + ". Antes de abrir, vale ler:";
        var lista = $("#pronto-avisos");
        lista.textContent = "";
        avisos.forEach(function (a) { lista.appendChild(el("li", "", a)); });
        $("#passo-pronto").hidden = false;
        window.scrollTo({ top: 0, behavior: "smooth" });
        focar("#passo-pronto h2");
      })
      .catch(function (erro) { avisar(erro.message, "erro"); botao.disabled = false; botao.textContent = antes; });
  }

  // ---------------------------------------------------------------- ligações

  $$("[data-modo]").forEach(function (b) { b.onclick = function () { mostrar(b.dataset.modo); }; });
  $$("[data-recomecar]").forEach(function (b) { b.onclick = function () { mostrar(""); }; });
  $$(".bv-cofre").forEach(function (b) {
    b.onclick = function () { $("#caminho-existente").value = b.dataset.caminho; analisar(); };
  });
  $$("[data-procurar]").forEach(function (b) {
    b.onclick = function () {
      b.disabled = true;
      api("/api/boas-vindas/procurar", {})
        .then(function (r) {
          if (!r.caminho) return;
          $("#" + b.dataset.procurar).value = r.caminho;
          if (b.dataset.procurar === "caminho-existente") analisar();
        })
        .catch(function (erro) { avisar(erro.message, "erro"); })
        .then(function () { b.disabled = false; });
    };
  });
  $("#analisar").onclick = analisar;
  $("#caminho-existente").addEventListener("keydown", function (e) { if (e.key === "Enter") analisar(); });
  $("#caminho-existente").addEventListener("input", function () { analise = null; $("#analise").hidden = true; $("#bloco-comum").hidden = true; });
  $$('input[name="perfil"]').forEach(function (r) { r.onchange = aplicarPerfil; });
  $("#concluir").onclick = concluir;
  raiz.addEventListener("change", resumir);

  // O tema escolhido já pinta a própria tela, para a pessoa ver antes de decidir.
  $$('input[name="tema"]').forEach(function (r) {
    r.addEventListener("change", function () {
      var cores = JSON.parse(r.dataset.cores || "{}");
      Object.keys(cores).forEach(function (nome) { document.documentElement.style.setProperty("--" + nome.replace(/_/g, "-"), cores[nome]); });
    });
  });
})();
