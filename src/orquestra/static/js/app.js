/* Orquestra: comportamento das páginas.
   JavaScript puro, sem bibliotecas e sem etapa de build: o que está aqui é o que
   roda no navegador. As páginas vêm prontas do servidor; este arquivo só cuida do
   que precisa de interação (arrastar, salvar, atualizar ao vivo). */
(function () {
  "use strict";

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // Versões de arquivos que esta aba acabou de gravar. Serve para não recarregar
  // a página por causa de uma mudança que ela mesma fez.
  var minhas = {}, minhasRemovidas = {}, configPropriaAte = 0;
  document.addEventListener("orquestra:nota-salva", function (e) {
    if (!e.detail) return;
    if (typeof e.detail.versao === "string") minhas[e.detail.versao] = true;
    if (e.detail.removido && typeof e.detail.rel === "string") minhasRemovidas[e.detail.rel] = Date.now() + 2000;
  });
  document.addEventListener("orquestra:config-salva", function () { configPropriaAte = Date.now() + 3000; });
  var arrastando = null;
  var personalizacaoPendente = function () { return false; };

  function caminho(rel) { return rel.split("/").map(encodeURIComponent).join("/"); }

  // ---------------------------------------------------------------- avisos

  function avisar(texto, tipo, acao) {
    return window.OrquestraInterface.avisar(texto, tipo, acao);
  }
  function confirmar(opcoes) { return window.OrquestraInterface.confirmar(opcoes); }

  // ---------------------------------------------------------------- API

  var capacidade = null;
  function capacidadeLocal() {
    if (!capacidade) capacidade = fetch("/api/local/capacidade", { cache: "no-store", credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (r) { return r.token || r.capacidade || ""; })
      .catch(function () { capacidade = null; return ""; });
    return capacidade;
  }
  function api(metodo, url, corpo) {
    if (url === "/api/config" || url === "/api/tema") configPropriaAte = Date.now() + 3000;
    return capacidadeLocal().then(function (token) {
      var headers = { "Content-Type": "application/json" };
      if (document.body.dataset.vaultId) headers["X-Orquestra-Vault"] = document.body.dataset.vaultId;
      if (token) headers["X-Orquestra-Local"] = token;
      return fetch(url, { method: metodo, headers: headers, credentials: "same-origin", body: JSON.stringify(corpo || {}) });
    })
      .catch(function () { throw new Error("Sem conexão com o painel. Confira se o Orquestra está aberto. Mantenha esta aba aberta para tentar novamente."); })
      .then(function (resp) {
        return resp.json().catch(function () {
          if (resp.ok) throw new Error("O painel respondeu em um formato inesperado. Mantenha esta aba aberta e confira o resultado antes de tentar novamente.");
          return {};
        }).then(function (dados) {
          if (!dados || typeof dados !== "object" || Array.isArray(dados)) throw new Error("O painel respondeu em um formato inesperado. Mantenha esta aba aberta e confira o resultado antes de tentar novamente.");
          if (!resp.ok) {
            var erro = new Error(window.OrquestraInterface.mensagemErro(typeof dados.erro === "string" ? { message: dados.erro } : null, resp.status));
            erro.conflito = !!dados.conflito;
            throw erro;
          }
          if (dados.versao) minhas[dados.versao] = true;
          return dados;
        });
      });
  }
  function mostrarErro(erro) {
    if (!erro || !erro.cancelado) avisar(window.OrquestraInterface.mensagemErro(erro), "erro");
  }

  // ---------------------------------------------------------------- relógio

  function relogio() {
    var el = $("#relogio");
    if (!el) return;
    function tique() { el.textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }); }
    tique();
    setInterval(tique, 10000);
  }

  // ---------------------------------------------------------------- carrossel

  function carrossel() {
    var raiz = $("#carrossel");
    if (!raiz) return;
    var trilho = $(".trilho", raiz), slides = $$(".slide", trilho), pontos = $$(".pontos button", raiz);
    var setaEsq = $(".seta.esq", raiz), setaDir = $(".seta.dir", raiz), atual = -1, quadro = 0;

    function ativar(i) {
      if (i === atual) return;
      atual = i;
      slides.forEach(function (s, k) {
        s.classList.toggle("ativo", k === i);
        s.tabIndex = k === i ? 0 : -1;
        s.setAttribute("aria-hidden", k === i ? "false" : "true");
      });
      pontos.forEach(function (p, k) { p.classList.toggle("ativo", k === i); p.setAttribute("aria-current", k === i ? "true" : "false"); });
      setaEsq.disabled = i === 0;
      setaDir.disabled = i === slides.length - 1;
      window.Orquestra.ambiente($(".capa", slides[i]));
      try { sessionStorage.setItem("orq-slide", String(i)); } catch (e) { /* modo privado */ }
    }
    function posicao(i) { return slides[i].offsetLeft - (trilho.clientWidth - slides[i].offsetWidth) / 2; }
    function ir(i, suave) {
      i = Math.max(0, Math.min(slides.length - 1, i));
      trilho.scrollTo({ left: posicao(i), behavior: suave === false ? "auto" : "smooth" });
    }
    function medir() {
      var meio = trilho.scrollLeft + trilho.clientWidth / 2, melhor = 0, menor = Infinity;
      slides.forEach(function (s, k) {
        var d = Math.abs(s.offsetLeft + s.offsetWidth / 2 - meio);
        if (d < menor) { menor = d; melhor = k; }
      });
      ativar(melhor);
    }

    trilho.addEventListener("scroll", function () { cancelAnimationFrame(quadro); quadro = requestAnimationFrame(medir); }, { passive: true });
    var arrasto = null, bloquearCliqueAte = 0;
    trilho.addEventListener("dragstart", function (e) { e.preventDefault(); });
    trilho.addEventListener("pointerdown", function (e) {
      if (e.pointerType !== "mouse" || e.button !== 0 || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
      arrasto = {id:e.pointerId, x:e.clientX, scroll:trilho.scrollLeft, moveu:false};
    });
    trilho.addEventListener("pointermove", function (e) {
      if (!arrasto || e.pointerId !== arrasto.id) return;
      var distancia = e.clientX - arrasto.x;
      if (!arrasto.moveu && Math.abs(distancia) < 8) return;
      if (!arrasto.moveu) { arrasto.moveu = true; trilho.classList.add("arrastando"); trilho.setPointerCapture(e.pointerId); }
      e.preventDefault(); trilho.scrollLeft = arrasto.scroll - distancia;
    });
    function terminarArrasto(e) {
      if (!arrasto || e.pointerId !== arrasto.id) return;
      var moveu = arrasto.moveu; arrasto = null;
      if (trilho.hasPointerCapture(e.pointerId)) trilho.releasePointerCapture(e.pointerId);
      trilho.classList.remove("arrastando");
      if (moveu) { bloquearCliqueAte = Date.now() + 300; medir(); ir(atual); }
    }
    trilho.addEventListener("pointerup", terminarArrasto);
    trilho.addEventListener("pointercancel", terminarArrasto);
    window.addEventListener("pointerup", terminarArrasto);
    trilho.addEventListener("click", function (e) { if (Date.now() < bloquearCliqueAte) { e.preventDefault(); e.stopImmediatePropagation(); } }, true);
    setaEsq.onclick = function () { ir(atual - 1); };
    setaDir.onclick = function () { ir(atual + 1); };
    pontos.forEach(function (p, k) { p.onclick = function () { ir(k); }; });
    slides.forEach(function (s, k) {
      // Clicar num slide que está ao lado traz ele para o centro em vez de abrir.
      s.addEventListener("click", function (e) { if (k !== atual) { e.preventDefault(); ir(k); } });
    });
    document.addEventListener("keydown", function (e) {
      var interativo = e.target && e.target.closest && e.target.closest("a, button, [role=button], [role=link], [role=tab], [role=radio], [role=slider]");
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || digitando(e) || interativo || $("dialog[open]")) return;
      if (e.key === "ArrowLeft") { e.preventDefault(); ir(atual - 1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); ir(atual + 1); }
      else if (e.key === "Enter" && atual >= 0) { e.preventDefault(); slides[atual].click(); }
    });

    var inicial = 0;
    try { inicial = Number(sessionStorage.getItem("orq-slide")) || 0; } catch (e) { /* modo privado */ }
    inicial = Math.min(inicial, slides.length - 1);
    ir(inicial, false);
    ativar(inicial);
    window.addEventListener("resize", function () { ir(atual, false); });
  }

  function digitando(e) {
    var alvo = e.target;
    return alvo && (alvo.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName));
  }

  // ---------------------------------------------------------------- diálogos

  function dialogos(raizDialogos) {
    function pedirFechamento(d) {
      // Escape, botão e backdrop passam pela mesma proteção de alterações pendentes.
      if (d && d.dispatchEvent(new Event("cancel", { cancelable: true }))) d.close();
    }
    $$("[data-fechar]", raizDialogos).forEach(function (b) { b.onclick = function () { pedirFechamento(b.closest("dialog")); }; });
    $$("dialog", raizDialogos).forEach(function (d) {
      d.addEventListener("click", function (e) {
        if (e.target !== d) return;
        var caixa = d.getBoundingClientRect();
        // Espaço interno do diálogo não é o backdrop.
        if (e.clientX >= caixa.left && e.clientX <= caixa.right && e.clientY >= caixa.top && e.clientY <= caixa.bottom) return;
        pedirFechamento(d);
      });
    });
  }

  function captura() {
    var dialogo = $("#captura"), abrir = $("#abrir-captura");
    if (!dialogo || !abrir) return;
    var texto = $("#captura-texto"), salvar = $("#captura-salvar");
    function mostrar() { dialogo.showModal(); texto.focus(); }
    function guardar() {
      if (salvar.disabled) return;
      if (!texto.value.trim()) { texto.focus(); return; }
      var concluir = window.OrquestraInterface.ocupado(salvar, "Guardando…");
      api("POST", "/api/captura", { texto: texto.value })
        .then(function () { texto.value = ""; dialogo.close(); avisar("Guardado na entrada."); })
        .catch(mostrarErro)
        .finally(concluir);
    }
    abrir.onclick = mostrar;
    salvar.onclick = guardar;
    texto.addEventListener("keydown", function (e) { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) guardar(); });
    document.addEventListener("keydown", function (e) {
      if (e.key.toLowerCase() === "c" && !e.ctrlKey && !e.metaKey && !e.altKey && !digitando(e) && !$("dialog[open]")) { e.preventDefault(); mostrar(); }
    });
  }

  function novoItem() {
    var dialogo = $("#dialogo-novo"), abrir = $("#abrir-novo");
    if (!dialogo || !abrir) return;
    var form = $("form", dialogo), titulo = $("#novo-titulo"), salvar = $("#novo-salvar");
    var adicionais = $("#novo-adicionar-campo", dialogo);
    $$("[data-extra-campo]", dialogo).forEach(function (grupo) { $$("input,select,textarea", grupo).forEach(function (el) { el.disabled = grupo.hidden; }); });
    if (adicionais) adicionais.onchange = function () {
      var grupo = $$("[data-extra-campo]", dialogo).find(function (g) { return g.dataset.extraCampo === adicionais.value; });
      if (!grupo) return;
      grupo.hidden = false;
      $$("input,select,textarea", grupo).forEach(function (el) { el.disabled = false; });
      adicionais.selectedOptions[0].disabled = true; adicionais.value = "";
      var campo = $("input,select,textarea", grupo); if (campo) campo.focus();
    };
    abrir.onclick = function () { dialogo.showModal(); titulo.focus(); };
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (salvar.disabled) return;
      var campos = {};
      $$("[data-novo]", form).filter(function (el) { return !el.disabled; }).forEach(function (el) { campos[el.name] = el.type === "checkbox" ? el.checked : el.value; });
      var concluir = window.OrquestraInterface.ocupado(salvar, "Criando…");
      api("POST", "/api/notas", { modulo: dialogo.dataset.modulo, subpasta: dialogo.dataset.subpasta || '', zona: dialogo.dataset.zona, titulo: titulo.value, campos: campos, corpo: $("#novo-corpo").disabled ? "" : $("#novo-corpo").value })
        .then(function () { location.reload(); })
        .catch(mostrarErro).finally(concluir);
    });
  }

  // ---------------------------------------------------------------- quadro

  function contar(quadro, origem, destino) {
    origem.dataset.total = Number(origem.dataset.total) - 1;
    destino.dataset.total = Number(destino.dataset.total) + 1;
    $$(".coluna", quadro).forEach(function (col) {
      var total = Number(col.dataset.total), restantes = Math.max(0, total - $$(".cartao", col).length), mais = $(".mais", col);
      $(".conta", col).textContent = total;
      if (mais) { mais.hidden = !restantes; mais.textContent = "+" + restantes + " na lista"; }
    });
  }

  function mudarCampo(cartao, campo, valor) {
    return api("PUT", "/api/notas/" + caminho(cartao.dataset.rel), { versao: cartao.dataset.versao, campos: (function () { var c = {}; c[campo] = valor; return c; })() })
      .then(function (r) { cartao.dataset.versao = r.versao; return r; });
  }

  function quadro() {
    var q = $(".quadro");
    if (!q) return;
    var campo = q.dataset.campo;

    function mover(cartao, coluna) {
      var origem = cartao.closest(".coluna"), seletor = $(".mudar-status", cartao);
      if (origem === coluna || cartao.getAttribute("aria-busy") === "true") return;
      cartao.setAttribute("aria-busy", "true");
      var arrastavel = cartao.draggable;
      cartao.draggable = false;
      if (seletor) seletor.disabled = true;
      $(".cartoes", coluna).prepend(cartao);
      contar(q, origem, coluna);
      mudarCampo(cartao, campo, coluna.dataset.valor)
        .then(function () { if (seletor) seletor.value = coluna.dataset.valor; })
        .catch(function (erro) { // não deu: volta o cartão para onde estava
          $(".cartoes", origem).prepend(cartao);
          if (seletor) seletor.value = origem.dataset.valor;
          contar(q, coluna, origem);
          mostrarErro(erro);
        }).finally(function () {
          cartao.removeAttribute("aria-busy"); cartao.draggable = arrastavel;
          if (seletor) seletor.disabled = false;
        });
    }

    q.addEventListener("dragstart", function (e) {
      var cartao = e.target.closest && e.target.closest(".cartao");
      if (!cartao || cartao.getAttribute("aria-busy") === "true") { e.preventDefault(); return; }
      arrastando = cartao;
      cartao.classList.add("arrastando");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", cartao.dataset.rel);
    });
    q.addEventListener("dragend", function () {
      if (arrastando) arrastando.classList.remove("arrastando");
      arrastando = null;
      $$(".coluna.alvo", q).forEach(function (c) { c.classList.remove("alvo"); });
    });
    $$(".coluna", q).forEach(function (coluna) {
      coluna.addEventListener("dragover", function (e) { if (arrastando) { e.preventDefault(); coluna.classList.add("alvo"); } });
      coluna.addEventListener("dragleave", function (e) { if (!coluna.contains(e.relatedTarget)) coluna.classList.remove("alvo"); });
      coluna.addEventListener("drop", function (e) {
        e.preventDefault();
        coluna.classList.remove("alvo");
        if (arrastando) mover(arrastando, coluna);
      });
    });
    // No celular não há arrastar: o seletor do cartão faz o mesmo trabalho.
    q.addEventListener("change", function (e) {
      if (!e.target.classList.contains("mudar-status")) return;
      var destino = $$(".coluna", q).filter(function (c) { return c.dataset.valor === e.target.value; })[0];
      if (destino) mover(e.target.closest(".cartao"), destino);
    });
  }

  // Seletores de status fora do quadro (agenda do dia).
  function seletoresSoltos() {
    document.addEventListener("change", function (e) {
      var s = e.target;
      if (!s.classList || !s.classList.contains("mudar-status") || s.closest(".quadro")) return;
      mudarCampo(s.closest(".cartao"), s.dataset.campo, s.value).then(function () { avisar("Atualizado."); recarregarLogo(); }).catch(mostrarErro);
    });
  }

  // ---------------------------------------------------------------- fila Decidir

  function decidir() {
    function resolver(item, campos) {
      $$("button", item).forEach(function (b) { b.disabled = true; });
      return api("PUT", "/api/notas/" + caminho(item.dataset.rel), { versao: item.dataset.versao, campos: campos })
        .then(function () {
          item.classList.add("saindo");
          setTimeout(function () { item.remove(); atualizarSelos(); if (!$(".fila-item")) location.reload(); }, 260);
          return true;
        })
        .catch(function (erro) { $$("button", item).forEach(function (b) { b.disabled = false; }); mostrarErro(erro); return false; });
    }
    $$("[data-acao]").forEach(function (botao) {
      botao.onclick = function () {
        var item=botao.closest('.fila-item'),campos=JSON.parse(botao.dataset.acao);
        if($('[data-responder]',item)&&!Object.prototype.hasOwnProperty.call(campos,'pergunta'))campos.pergunta='';
        resolver(item,campos);
      };
    });
    // Pergunta de um agente: a resposta fica no frontmatter (campo `resposta`) e a pergunta sai da fila.
    var dialogo = $("#dialogo-resposta"), texto = $("#resposta-texto"), itemAtual = null;
    if (!dialogo) return;
    $$("[data-responder]").forEach(function (botao) {
      botao.onclick = function () {
        var item = botao.closest(".fila-item"), pergunta = $(".cartao-pergunta", item);
        itemAtual = item;
        $("#resposta-pergunta").textContent = pergunta ? pergunta.textContent.trim() : "O que você gostaria de responder?";
        texto.value = ""; dialogo.showModal(); texto.focus();
      };
    });
    $("#form-resposta").addEventListener("submit", function (e) {
      e.preventDefault();
      if (!itemAtual || !texto.value.trim()) { texto.focus(); return; }
      var salvar = $("#resposta-salvar"); salvar.disabled = true;
      resolver(itemAtual, { resposta: texto.value.trim(), pergunta: "" }).then(function (ok) { if (ok) dialogo.close(); }).finally(function () { salvar.disabled = false; });
    });
  }

  // ---------------------------------------------------------------- nota

  var notaSuja = false;

  function nota() {
    var raiz = $(".nota");
    if (!raiz || !window.OrquestraNotas) return;
    var rel = raiz.dataset.rel, versao = raiz.dataset.versao, url = "/api/notas/" + caminho(rel);
    var ver = $("#ver"), editor = $("#editor"), titulo = $("#nota-titulo");
    var bEditar = $("#editar"), bSalvar = $("#salvar"), bCancelar = $("#cancelar");
    var estado = $("#estado-salvo"), faixa = $("#faixa-conflito"), falha = $("#falha-gravacao");
    var bRepetir = $("#repetir-gravacao"), bReverter = $("#reverter-gravacao");
    var campos = $$("[data-campo]", raiz), bloqueioExterno = false, recuperado = null, rascunhos = null;
    var metaOriginal = {};
    try { metaOriginal = JSON.parse(raiz.dataset.metaOriginal || "{}"); } catch (e) { /* Metadados ausentes não impedem preservar o texto. */ }
    var original = editor ? editor.value : "", tituloOriginal = titulo ? titulo.value : "";
    var camposOriginais = {}, estadoFila = { ativa: false, pendentes: 0, erro: null }, armazenamentoAvisado = false, emEdicao = false;

    function valor(el) { return el.type === "checkbox" ? el.checked : el.value; }
    campos.forEach(function (el) { camposOriginais[el.name] = valor(el); });
    function dadosAtuais() {
      var valores = {};
      campos.forEach(function (el) { valores[el.name] = valor(el); });
      return { titulo: titulo ? titulo.value : tituloOriginal, corpo: editor ? editor.value : original, campos: valores, versao: versao };
    }
    function diferentes() {
      return (editor && editor.value !== original) || (titulo && titulo.value !== tituloOriginal) || campos.some(function (el) { return valor(el) !== camposOriginais[el.name]; });
    }
    function avisarArmazenamento() {
      if (armazenamentoAvisado) return;
      armazenamentoAvisado = true;
      $("#aviso-rascunho").hidden = false;
    }
    function atualizarEstadoSalvo() {
      if (!estado) return;
      var mensagem = estadoFila.erro ? "Há alterações que não foram salvas." : estadoFila.ativa || estadoFila.pendentes ? "Salvando…" : diferentes() ? "Há alterações no rascunho." : "Tudo salvo no vault.";
      if (estado.textContent !== mensagem) estado.textContent = mensagem;
      estado.classList.toggle("erro-texto", !!estadoFila.erro);
    }
    function guardarRascunho() {
      notaSuja = !!diferentes() || !!estadoFila.pendentes;
      atualizarEstadoSalvo();
      if (!rascunhos) { if (notaSuja) avisarArmazenamento(); return; }
      try {
        if (notaSuja) rascunhos.guardar(Object.assign(dadosAtuais(), { metaOriginal: metaOriginal }));
        else {
          rascunhos.limpar();
          if (recuperado) { rascunhos.remover(recuperado.chave); recuperado = null; }
        }
      } catch (e) { avisarArmazenamento(); }
    }
    var edicaoInline = window.OrquestraEdicao ? window.OrquestraEdicao.criar(ver, editor, {aoMudar:guardarRascunho, aoConcluir:function(){salvarTexto(function(){ver.focus();});}}) : null;
    function modoEdicao(ligado, alvo) {
      if (!bEditar) return;
      emEdicao = !!ligado;
      if (edicaoInline) {
        ver.hidden = false; editor.hidden = true;
        if(ligado)edicaoInline.abrir(alvo);else edicaoInline.fechar();
      } else { ver.hidden = ligado; editor.hidden = !ligado; }
      bEditar.hidden = ligado; bSalvar.hidden = !ligado; bCancelar.hidden = !ligado;
      if (ligado && !edicaoInline) editor.focus();
    }
    var fila = window.OrquestraNotas.criarFila(function (dados) {
      if (bloqueioExterno) {
        var conflito = new Error("O arquivo mudou. Preserve seu rascunho e abra a versão do disco antes de continuar.");
        conflito.conflito = true;
        return Promise.reject(conflito);
      }
      var envio = Object.assign({}, dados, { versao: versao });
      return api("PUT", url, envio);
    }, function (e) {
      estadoFila = e;
      atualizarEstadoSalvo();
      falha.hidden = !e.erro;
      if (e.erro) {
        $("#falha-gravacao-texto").textContent = e.erro.message;
        if (e.erro.conflito) { bloqueioExterno = true; faixa.hidden = false; }
      }
      bRepetir.disabled = e.ativa || bloqueioExterno;
      bReverter.disabled = e.ativa;
      if (bSalvar) bSalvar.disabled = e.ativa;
      if (bCancelar) bCancelar.disabled = e.ativa;
      $("#salvar-copia").disabled = e.ativa;
      guardarRascunho();
    });
    function gravar(dados, aoSalvar) {
      return fila.adicionar(dados, function (r, salvo) {
        versao = r.versao;
        if (salvo.titulo !== undefined) tituloOriginal = salvo.titulo;
        if (salvo.corpo !== undefined) original = salvo.corpo;
        Object.keys(salvo.campos || {}).forEach(function (nome) { camposOriginais[nome] = salvo.campos[nome]; });
        if (aoSalvar) aoSalvar(r, salvo);
      }).catch(mostrarErro);
    }

    raiz.addEventListener("orquestra:anexo", function (e) {
      var campo = raiz.dataset.imagemCampo;
      if (!campo || bloqueioExterno) return;
      var valores = {}; valores[campo] = e.detail.caminho;
      var campoOculto = $("#nota-imagem-campo"); if (campoOculto) campoOculto.value = e.detail.caminho;
      guardarRascunho();
      gravar({campos: valores}, function () {
        var imagem = $(".nota-imagem", raiz);
        if (!imagem) { imagem = document.createElement("img"); imagem.className = "nota-imagem"; imagem.alt = "Criativo da nota"; ver.before(imagem); }
        imagem.src = "/arquivo/" + caminho(e.detail.caminho);
        raiz.dataset.versao = versao;
        var mensagem = $("#anexo-estado"); if (mensagem) mensagem.textContent = "Imagem adicionada.";
      });
    });

    // Os pedidos saem em sequência e usam a versão devolvida pela gravação anterior.
    campos.forEach(function (el) {
      el.addEventListener("input", guardarRascunho);
      el.addEventListener("change", function () {
        var valores = {}; valores[el.name] = valor(el);
        guardarRascunho();
        gravar({ campos: valores });
      });
    });
    if (titulo && !titulo.disabled) {
      titulo.addEventListener("input", guardarRascunho);
      titulo.addEventListener("change", function () {
        if (!titulo.value.trim()) { titulo.value = tituloOriginal; guardarRascunho(); return; }
        gravar({ titulo: titulo.value });
      });
      titulo.addEventListener("keydown", function (e) { if (e.key === "Enter") titulo.blur(); });
    }
    function salvarTexto(depois) {
      if (typeof depois !== "function") depois = null;
      if (editor.value === original && !estadoFila.pendentes) { modoEdicao(false); if (depois) depois(); return; }
      if (bloqueioExterno) { if (bloqueioExterno) faixa.hidden = false; return; }
      gravar({ corpo: editor.value }, function (r, salvo) {
        // Digitar durante a requisição não marca o texto posterior como salvo.
        if (editor.value === salvo.corpo) {
          modoEdicao(false); ver.innerHTML = r.html || '<p class="suave">Sem texto.</p>';
          if(edicaoInline)edicaoInline.atualizar(original);
          if (depois) depois();
        } else if(!edicaoInline)ver.innerHTML = r.html || '<p class="suave">Sem texto.</p>';

      });
    }
    if (bEditar) {
      bEditar.onclick = function () { modoEdicao(true); };
      ver.addEventListener("dblclick", function (e) { if (!e.target.closest("a")) modoEdicao(true,e.target); });
      ver.addEventListener("keydown", function (e) { if (e.key === "Enter" && e.target === ver && !emEdicao) { e.preventDefault(); modoEdicao(true); } });
      editor.addEventListener("keydown", function (e) { if (e.key === "Escape") { e.preventDefault(); salvarTexto(); ver.focus(); } });
      document.addEventListener("pointerdown", function (e) {
        if (!emEdicao || e.target === editor || edicaoInline && edicaoInline.contem(e.target) || e.target.closest(".nota-acoes, dialog, #falha-gravacao, #faixa-conflito")) return;
        salvarTexto();
      });
      document.addEventListener("click", function (e) {
        var link = e.target.closest("a[href]");
        function seguir() {
          var destino=new URL(link.href,location.href);
          if(window.parent!==window&&new URLSearchParams(location.search).get('explorador')==='1'&&destino.origin===location.origin&&/^\/(n|documento|pastas)(?:\/|$)/.test(destino.pathname))window.parent.postMessage({tipo:'orquestra:leitor',url:destino.href,titulo:link.textContent},location.origin);
          else location.href = link.href;
        }
        // Durante a edição no lugar, clicar num link só posiciona o cursor;
        // Ctrl+clique (Cmd no Mac) salva o texto e abre o link.
        if (link && emEdicao && edicaoInline && edicaoInline.contem(link)) {
          e.preventDefault();
          if ((e.ctrlKey || e.metaKey) && link.getAttribute("href") && link.getAttribute("href").charAt(0) !== "#") salvarTexto(seguir);
          return;
        }
        if (!link || !notaSuja || !emEdicao || e.ctrlKey || e.metaKey || e.shiftKey || link.target === "_blank" || link.getAttribute("href").charAt(0) === "#") return;
        e.preventDefault(); salvarTexto(seguir);
      }, true);
      bSalvar.onclick = salvarTexto;
      bCancelar.onclick = async function () {
        if (editor.value !== original && !await confirmar({ titulo: "Descartar alterações do texto?", texto: "O texto volta à última versão salva. As propriedades já salvas continuam como estão.", confirmar: "Descartar texto", perigoso: true })) return;
        editor.value = original; guardarRascunho(); modoEdicao(false);
      };
      editor.addEventListener("input", guardarRascunho);
      document.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && emEdicao) { e.preventDefault(); salvarTexto(); }
      });
    }
    window.addEventListener("beforeunload", function (e) {
      guardarRascunho();
      if (notaSuja) { e.preventDefault(); e.returnValue = ""; }
    });
    bRepetir.onclick = function () {
      if (bloqueioExterno || !fila.descartar()) return;
      gravar(dadosAtuais(), function (r) { if (typeof r.html === "string" && editor.value === original) { modoEdicao(false); ver.innerHTML = r.html; if(edicaoInline)edicaoInline.atualizar(original); } });
    };
    async function reverter() {
      if (!await confirmar({ titulo: "Descartar rascunho desta aba?", texto: "Suas alterações não salvas serão descartadas. A página abrirá novamente a versão atual do arquivo no vault.", confirmar: "Descartar e recarregar", perigoso: true })) return;
      if (!fila.descartar()) return;
      if (rascunhos) {
        try { rascunhos.limpar(); if (recuperado) rascunhos.remover(recuperado.chave); } catch (e) { avisarArmazenamento(); }
      }
      // Evita regravar o rascunho no evento beforeunload após o descarte explícito.
      editor.value = original; titulo.value = tituloOriginal;
      campos.forEach(function (el) { if (el.type === "checkbox") el.checked = camposOriginais[el.name]; else el.value = camposOriginais[el.name]; });
      notaSuja = false; location.reload();
    }
    bReverter.onclick = reverter;
    $("#recarregar-nota").onclick = reverter;

    $("#copiar-rascunho").onclick = function () {
      var texto = titulo.value + "\n\n" + editor.value;
      function selecionar(){modoEdicao(true);if(edicaoInline)edicaoInline.selecionar();else editor.select();avisar("Selecionei o texto. Use Ctrl+C ou Cmd+C.");}
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(texto).then(function () { avisar("Rascunho copiado."); }).catch(selecionar);
      else selecionar();
    };
    $("#salvar-copia").onclick = function () {
      var b = this;
      if (estadoFila.ativa) return;
      b.disabled = true;
      var copia = dadosAtuais(); copia.titulo += " — cópia recuperada";
      var camposEditados = copia.campos;
      copia.campos = window.OrquestraNotas.camposParaCopia(metaOriginal, camposEditados);
      delete copia.versao;
      api("POST", "/api/notas/copia/" + caminho(rel), copia).then(function (r) {
        var aindaIgual = editor.value === copia.corpo && titulo.value + " — cópia recuperada" === copia.titulo && JSON.stringify(dadosAtuais().campos) === JSON.stringify(camposEditados);
        if (!aindaIgual) { avisar("Cópia salva. Há novas alterações nesta aba.", "", { rotulo: "Abrir cópia", fazer: function () { window.open(r.url, "_blank", "noopener"); } }); return; }
        if (rascunhos) { try { rascunhos.limpar(); if (recuperado) rascunhos.remover(recuperado.chave); } catch (e) { /* A cópia já está salva no vault. */ } }
        fila.descartar();
        // A navegação só ocorre se nenhum envio ao arquivo original está em andamento.
        original = editor.value; tituloOriginal = titulo.value;
        campos.forEach(function (el) { camposOriginais[el.name] = valor(el); });
        notaSuja = false; location.href = r.url;
      }).catch(mostrarErro).finally(function () { b.disabled = false; });
    };

    // Cada sessão tem sua própria chave: abas diferentes não apagam rascunhos entre si.
    try {
      var sessao = window.crypto && crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random().toString(36).slice(2);
      rascunhos = window.OrquestraNotas.criarRascunhos(localStorage, raiz.dataset.vaultId, rel, sessao);
      var disponiveis = rascunhos.listar();
      if (disponiveis.length) {
        var recuperacao = $("#recuperar-rascunho");
        recuperacao.hidden = false;
        $("#rascunho-quando").textContent = new Date(disponiveis[0].quando).toLocaleString("pt-BR");
        $("#retomar-rascunho").onclick = function () {
          recuperado = disponiveis[0];
          var d = recuperado.dados;
          if (d.metaOriginal && typeof d.metaOriginal === "object" && !Array.isArray(d.metaOriginal)) metaOriginal = d.metaOriginal;
          titulo.value = d.titulo || tituloOriginal; editor.value = d.corpo;
          campos.forEach(function (el) { if (Object.prototype.hasOwnProperty.call(d.campos || {}, el.name)) { if (el.type === "checkbox") el.checked = !!d.campos[el.name]; else el.value = d.campos[el.name]; } });
          bloqueioExterno = d.versao !== versao;
          faixa.hidden = !bloqueioExterno;
          recuperacao.hidden = true; modoEdicao(true); guardarRascunho();
        };
        $("#descartar-rascunho").onclick = async function () {
          if (!await confirmar({ titulo: "Descartar rascunho anterior?", texto: "Apenas o rascunho desta nota, de " + new Date(disponiveis[0].quando).toLocaleString("pt-BR") + ", será removido deste navegador. O arquivo no vault será preservado.", confirmar: "Descartar rascunho", perigoso: true })) return;
          rascunhos.remover(disponiveis.shift().chave);
          recuperacao.hidden = !disponiveis.length;
          if (disponiveis.length) $("#rascunho-quando").textContent = new Date(disponiveis[0].quando).toLocaleString("pt-BR");
        };
      }
    } catch (e) { rascunhos = null; }

    ["excluir-nota", "vincular-cliente"].forEach(function (id) {
      var botao = $("#" + id);
      if (!botao) return;
      botao.onclick = async function () {
        if (notaSuja || estadoFila.pendentes) { avisar("Salve ou preserve seu rascunho antes de continuar.", "erro"); return; }
        var excluir = id === "excluir-nota";
        if (!await confirmar({ titulo: excluir ? "Excluir esta nota?" : "Acompanhar em Clientes?", texto: excluir ? "A nota vai para a lixeira e poderá ser restaurada em Pastas → Lixeira. Anexos e outras notas não serão excluídos." : "Cria um acompanhamento comercial ligado a este cadastro. Os dados de contato continuam em Contatos.", confirmar: excluir ? "Mover para a lixeira" : "Acompanhar em Clientes" })) return;
        if (notaSuja || estadoFila.pendentes) { avisar("Salve ou preserve seu rascunho antes de continuar.", "erro"); return; }
        botao.disabled = true;
        try {
          var resposta = await api("POST", (excluir ? "/api/excluir/" : "/api/contatos/cliente/") + caminho(rel), {versao: versao});
          location.href = resposta.url || "/lixeira";
        } catch (erro) { botao.disabled = false; mostrarErro(erro); }
      };
    });

    var bArquivar = $("#arquivar");
    if (bArquivar) bArquivar.onclick = async function () {
      if (notaSuja || estadoFila.pendentes) { avisar("Salve ou preserve seu rascunho antes de arquivar.", "erro"); return; }
      if (!await confirmar({ titulo: "Arquivar esta nota?", texto: "A nota será movida para a pasta arquivo/ desta área. Você pode consultá-la depois nas notas arquivadas.", confirmar: "Arquivar nota" })) return;
      if (notaSuja || estadoFila.pendentes) { avisar("Salve ou preserve seu rascunho antes de arquivar.", "erro"); return; }
      bArquivar.disabled = true;
      api("POST", "/api/arquivar/" + caminho(rel), { versao: versao }).then(function () { location.href = raiz.dataset.voltar || "/"; }).catch(function (erro) { bArquivar.disabled = false; mostrarErro(erro); });
    };

    var historico = $("#versoes-locais");
    if (historico) {
      var carregado = false, versoes = [], buscaVersao = 0;
      var escolha = $("#versoes-escolha"), tipo = $("#versoes-tipo"), mensagem = $("#versoes-mensagem"), textoVersao = $("#versao-texto");
      var copiarVersao = $("#copiar-versao"), salvarVersao = $("#salvar-versao-copia"), tituloVersao = $("#versao-titulo-copia");
      tituloVersao.value = tituloOriginal + " — versão recuperada";
      var urlHistorico = "/api/notas/recuperacao/" + caminho(rel);
      function consultar(urlConsulta) {
        return fetch(urlConsulta, { cache: "no-store", credentials: "same-origin" }).then(function (r) {
          return r.json().then(function (d) { if (!r.ok) throw new Error(d.erro || "Não consegui ler esta versão."); return d; });
        });
      }
      function lerVersao() {
        var numero = ++buscaVersao, entrada = versoes.filter(function (v) { return v.id === escolha.value; })[0];
        if (!entrada) return;
        $("option[value='antes']", tipo).disabled = !entrada.tem_anterior;
        if (!entrada.tem_anterior) tipo.value = "proposta";
        mensagem.textContent = "Lendo a versão preservada…";
        textoVersao.value = ""; copiarVersao.disabled = true; salvarVersao.disabled = true;
        consultar(urlHistorico + "?id=" + encodeURIComponent(escolha.value) + "&tipo=" + encodeURIComponent(tipo.value)).then(function (d) {
          if (numero !== buscaVersao) return;
          textoVersao.value = d.texto; mensagem.textContent = "Versão preservada. O arquivo atual continua como está.";
          copiarVersao.disabled = false; salvarVersao.disabled = false;
        }).catch(function (erro) { if (numero === buscaVersao) mensagem.textContent = erro.message; });
      }
      $("#consultar-versoes").onclick = function () {
        historico.hidden = false;
        if (carregado) return;
        mensagem.textContent = "Consultando versões locais…";
        consultar(urlHistorico).then(function (d) {
          carregado = true; versoes = d.versoes || [];
          if (!versoes.length) { mensagem.textContent = "Ainda não há versões preservadas desta nota neste computador."; return; }
          versoes.forEach(function (v) {
            var opcao = document.createElement("option"), id = v.id;
            var data = new Date(id.slice(0, 4) + "-" + id.slice(4, 6) + "-" + id.slice(6, 8) + "T" + id.slice(9, 11) + ":" + id.slice(11, 13) + ":" + id.slice(13, 15) + "Z");
            opcao.value = id; opcao.textContent = (isNaN(data.getTime()) ? id : data.toLocaleString("pt-BR")) + " · " + String(v.motivo || "gravação").replace(/_/g, " ");
            escolha.appendChild(opcao);
          });
          $("#versoes-conteudo").hidden = false; lerVersao();
        }).catch(function (erro) { mensagem.textContent = erro.message + " Clique em Consultar recuperação para tentar novamente."; });
      };
      escolha.onchange = lerVersao; tipo.onchange = lerVersao;
      copiarVersao.onclick = function () {
        if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(textoVersao.value).then(function () { avisar("Versão copiada."); }).catch(function () { textoVersao.focus(); textoVersao.select(); avisar("Selecionei a versão. Use Ctrl+C ou Cmd+C."); });
        else { textoVersao.focus(); textoVersao.select(); avisar("Selecionei a versão. Use Ctrl+C ou Cmd+C."); }
      };
      salvarVersao.onclick = function () {
        var nome = tituloVersao.value.trim();
        if (!nome) { mensagem.textContent = "Preencha o título da nova nota de recuperação."; tituloVersao.focus(); return; }
        salvarVersao.disabled = true;
        api("POST", "/api/notas/recuperacao/copia/" + caminho(rel), { id: escolha.value, tipo: tipo.value, titulo: nome.trim() }).then(function (r) {
          var link = $("#copia-recuperada"); link.href = r.url; link.hidden = false;
          mensagem.textContent = "Cópia criada no vault. Sua nota atual e seu rascunho foram preservados.";
          avisar("Versão salva como nova nota.");
        }).catch(function (erro) { mensagem.textContent = erro.message; mostrarErro(erro); }).finally(function () { salvarVersao.disabled = false; });
      };
    }
  }

  // ---------------------------------------------------------------- gaveta de áreas (dock compacto)

  var desligarGaveta = function () {};
  function gaveta() {
    desligarGaveta();
    var botao = $("#abrir-gaveta"), caixa = $("#gaveta");
    if (!botao || !caixa) return;
    function abrir(sim) {
      caixa.hidden = !sim;
      botao.setAttribute("aria-expanded", sim ? "true" : "false");
      if (sim) { var primeiro = $(".gaveta-item.ativo", caixa) || $(".gaveta-item", caixa); if (primeiro) primeiro.focus(); }
    }
    botao.onclick = function (e) { e.stopPropagation(); abrir(caixa.hidden); };
    function clicarFora(e) { if (!caixa.hidden && !caixa.contains(e.target)) abrir(false); }
    function teclaGaveta(e) {
      if (e.key === "Escape" && !caixa.hidden) { abrir(false); botao.focus(); }
      else if (e.key.toLowerCase() === "g" && !e.ctrlKey && !e.metaKey && !e.altKey && !digitando(e) && !$("dialog[open]") && botao.getClientRects().length) { e.preventDefault(); abrir(caixa.hidden); }
    }
    document.addEventListener("click", clicarFora);
    document.addEventListener("keydown", teclaGaveta);
    desligarGaveta = function () { document.removeEventListener("click", clicarFora); document.removeEventListener("keydown", teclaGaveta); };
  }

  // ---------------------------------------------------------------- pastas

  function pastas() {
    var dNota = $("#dialogo-nota-pasta"), abrirNota = $("#abrir-nota-pasta");
    if (dNota && abrirNota) {
      var titulo = $("#nota-pasta-titulo"), salvar = $("#nota-pasta-salvar");
      abrirNota.onclick = function () { dNota.showModal(); titulo.focus(); };
      $("form", dNota).addEventListener("submit", function (e) {
        e.preventDefault();
        salvar.disabled = true;
        api("POST", "/api/pastas/nota", { pasta: dNota.dataset.pasta, titulo: titulo.value, corpo: $("#nota-pasta-corpo").value })
          .then(function (r) { location.href = r.url; })
          .catch(function (erro) { salvar.disabled = false; mostrarErro(erro); });
      });
    }

    // "Mostrar no painel": antes de confirmar, conta o que o painel entendeu da pasta.
    var dAdotar = $("#dialogo-adotar");
    if (!dAdotar) return;
    var pasta = "", confirmar = $("#adotar-confirmar"), achados = $("#adotar-achados");
    $$("[data-adotar]").forEach(function (b) {
      b.onclick = function () {
        pasta = b.dataset.adotar;
        $("#adotar-nome").textContent = pasta;
        achados.textContent = "Olhando as notas…";
        $("#adotar-quadro").checked = false;
        $("#adotar-linha-quadro").hidden = true;
        dAdotar.showModal();
        fetch("/api/pastas/resumo?pasta=" + encodeURIComponent(pasta)).then(function (r) { return r.json(); }).then(function (d) {
          achados.textContent = "";
          if (d.erro) { achados.textContent = d.erro; return; }
          if (d.religar) { achados.textContent = "Esta pasta já foi uma área do painel. Ela volta do jeito que estava."; return; }
          var p1 = document.createElement("p");
          if (d.campos.length) {
            p1.textContent = "Campos que encontrei nas suas notas:";
            achados.appendChild(p1);
            var lista = document.createElement("ul");
            d.campos.forEach(function (c) {
              var li = document.createElement("li"), nome = document.createElement("b");
              nome.textContent = c.nome;
              li.appendChild(nome);
              li.appendChild(document.createTextNode(" · " + c.tipo + (c.opcoes.length ? " (" + c.opcoes.join(", ") + ")" : "")));
              lista.appendChild(li);
            });
            achados.appendChild(lista);
          } else {
            p1.textContent = "As notas desta pasta não têm campos no topo (frontmatter). Elas aparecem como uma lista simples, e você pode criar campos depois.";
            achados.appendChild(p1);
          }
          var p2 = document.createElement("p");
          p2.className = "suave";
          p2.textContent = d.tem_status ? "Como há um campo de status, a área já nasce com um quadro." : "";
          achados.appendChild(p2);
          $("#adotar-linha-quadro").hidden = !!d.tem_status;
        }).catch(function () { achados.textContent = "Não consegui olhar a pasta."; });
      };
    });
    confirmar.onclick = function () {
      confirmar.disabled = true;
      api("POST", "/api/pastas/adotar", { pasta: pasta, quadro: $("#adotar-quadro").checked })
        .then(function (r) { location.href = r.url; })
        .catch(function (erro) { confirmar.disabled = false; mostrarErro(erro); });
    };
  }

  // ---------------------------------------------------------------- personalizar uma área

  function personalizar() {
    var raiz = $("#personalizar");
    if (!raiz) return;
    var abas = $$('[role=tab]', raiz), paineis = $$('[role=tabpanel]', raiz);
    function mostrarAba(id, foco) {
      abas.forEach(function (aba) { var ativa = aba.getAttribute('aria-controls') === id; aba.setAttribute('aria-selected', String(ativa)); aba.tabIndex = ativa ? 0 : -1; if (ativa && foco) aba.focus(); });
      paineis.forEach(function (painel) { painel.hidden = painel.id !== id; });
    }
    abas.forEach(function (aba, i) {
      aba.onclick = function () { mostrarAba(aba.getAttribute('aria-controls')); };
      aba.onkeydown = function (e) {
        var indice = e.key === 'Home' ? 0 : e.key === 'End' ? abas.length - 1 : e.key === 'ArrowRight' ? (i + 1) % abas.length : e.key === 'ArrowLeft' ? (i + abas.length - 1) % abas.length : -1;
        if (indice >= 0) { e.preventDefault(); mostrarAba(abas[indice].getAttribute('aria-controls'), true); }
      };
    });
    var lista = $("#p-campos"), modelo = $("#p-modelo-campo");
    function retrato() {
      return JSON.stringify($$("input, select, textarea", raiz).map(function (el) {
        return el.type === "checkbox" ? el.checked : el.value;
      }));
    }
    var original = retrato(), estado = $("#p-estado");
    personalizacaoPendente = function () { return retrato() !== original; };
    function atualizarPendencia() {
      if (estado) estado.textContent = personalizacaoPendente() ? "Há alterações para salvar." : "As mudanças só entram em vigor ao salvar.";
    }
    raiz.addEventListener("input", atualizarPendencia);
    raiz.addEventListener("change", atualizarPendencia);
    window.addEventListener("beforeunload", function (e) {
      if (personalizacaoPendente()) { e.preventDefault(); e.returnValue = ""; }
    });

    function ligar(linha) {
      var tipo = $("[data-tipo]", linha), opcoes = $("[data-opcoes]", linha), tirar = $("[data-tirar]", linha);
      var grupoOpcoes = $(".campo-editor-opcoes", linha) || opcoes;
      function mostrarOpcoes() { grupoOpcoes.hidden = tipo.value !== "escolha"; opcoes.hidden = grupoOpcoes.hidden; opcoes.disabled = grupoOpcoes.hidden; }
      tipo.onchange = function () { mostrarOpcoes(); if (!grupoOpcoes.hidden) opcoes.focus(); };
      mostrarOpcoes();
      if (tirar) tirar.onclick = function () { linha.remove(); atualizarPendencia(); };
    }
    $$(".campo-editor", lista).forEach(ligar);
    $("#p-novo-campo").onclick = function () {
      var linha = modelo.content.firstElementChild.cloneNode(true);
      lista.appendChild(linha);
      ligar(linha);
      atualizarPendencia();
      $("[data-nome]", linha).focus();
    };

    $("#p-salvar").onclick = function () {
      if (this.disabled) return;
      var invalido = $$("input, select, textarea", raiz).filter(function (campo) {
        var linha = campo.closest(".campo-editor"), remover = linha && $("[data-remover]", linha);
        return !campo.disabled && !(remover && remover.checked) && !campo.checkValidity();
      })[0];
      if (invalido) { var painelCampo = invalido.closest('[role=tabpanel]'); if (painelCampo) mostrarAba(painelCampo.id); invalido.reportValidity(); invalido.focus(); return; }
      var campos = [], remover = [];
      $$(".campo-editor", lista).forEach(function (linha) {
        var nome = $("[data-nome]", linha).value.trim(), marcado = $("[data-remover]", linha);
        if (marcado && marcado.checked) { remover.push(linha.dataset.original); return; }
        if (!nome) return;
        campos.push({ nome: nome, tipo: $("[data-tipo]", linha).value, opcoes: $("[data-opcoes]", linha).value });
      });
      var dados = {
        versao: raiz.dataset.versao,
        nome: $("#p-nome").value, descricao: $("#p-descricao").value, icone: $("#p-icone").value, cena: $("#p-cena").value,
        capa: $("#p-capa").value || null,
        campos: campos, remover: remover, quadro: $("#p-quadro").checked, grafico: $("#p-grafico").checked
      };
      if ($("#p-concluidos")) dados.concluidos = $("#p-concluidos").value;
      var botao = $("#p-salvar");
      var enviado = retrato();
      var concluir = window.OrquestraInterface.ocupado(botao, "Salvando…");
      api("PUT", "/api/modulos/" + encodeURIComponent(raiz.dataset.modulo), dados)
        .then(function (r) {
          if (r.versao) raiz.dataset.versao = r.versao;
          original = enviado;
          atualizarPendencia();
          if (personalizacaoPendente()) { avisar("Área salva. Há novas alterações para salvar nesta tela."); return; }
          location.href = r.url;
        })
        .catch(mostrarErro).finally(concluir);
    };
  }

  // ---------------------------------------------------------------- números

  function numeros() {
    var dialogo = $("#dialogo-numeros"), abrir = $("#abrir-numeros");
    if (dialogo && abrir) {
      var salvar = $("#numeros-salvar");
      abrir.onclick = function () { dialogo.showModal(); var primeiro = $("[data-numero]", dialogo); if (primeiro) primeiro.focus(); };
      $("form", dialogo).addEventListener("submit", function (e) {
        e.preventDefault();
        var valores = {};
        $$("[data-numero]", dialogo).forEach(function (c) { if (c.value !== "") valores[c.name] = c.value; });
        salvar.disabled = true;
        api("POST", "/api/numeros", { modulo: dialogo.dataset.modulo, dia: $("#numeros-dia").value, valores: valores })
          .then(function () { location.reload(); })
          .catch(function (erro) { salvar.disabled = false; mostrarErro(erro); });
      });
    }

    // Linha-guia: o ponteiro escolhe o dia mais próximo; as setas fazem o mesmo pelo teclado.
    $$(".numero-grafico").forEach(function (g) {
      var pontos = [];
      try { pontos = JSON.parse(g.dataset.pontos || "[]"); } catch (e) { return; }
      if (!pontos.length) return;
      var guia = $(".g-guia", g), foco = $(".g-foco", g), dica = $(".g-dica", g), atual = -1;
      function mostrar(i) {
        atual = Math.max(0, Math.min(pontos.length - 1, i));
        var p = pontos[atual], esquerda = p.x / 3.2;
        guia.setAttribute("x1", p.x); guia.setAttribute("x2", p.x); guia.removeAttribute("hidden");
        foco.style.left = esquerda + "%"; foco.style.top = (p.y / 1.2) + "%"; foco.hidden = false;
        $("b", dica).textContent = p.valor;
        $("span", dica).textContent = p.dia;
        dica.hidden = false;
        dica.style.left = Math.max(12, Math.min(88, esquerda)) + "%";
      }
      function esconder() { atual = -1; guia.setAttribute("hidden", ""); foco.hidden = true; dica.hidden = true; }
      g.addEventListener("pointermove", function (e) {
        var caixa = g.getBoundingClientRect(), x = (e.clientX - caixa.left) / caixa.width * 320, melhor = 0, menor = Infinity;
        pontos.forEach(function (p, k) { var d = Math.abs(p.x - x); if (d < menor) { menor = d; melhor = k; } });
        mostrar(melhor);
      });
      g.addEventListener("pointerleave", function () { if (document.activeElement !== g) esconder(); });
      g.addEventListener("focus", function () { mostrar(atual < 0 ? pontos.length - 1 : atual); });
      g.addEventListener("blur", esconder);
      g.addEventListener("keydown", function (e) {
        if (e.key === "ArrowLeft") { e.preventDefault(); mostrar(atual - 1); }
        else if (e.key === "ArrowRight") { e.preventDefault(); mostrar(atual + 1); }
        else if (e.key === "Escape") g.blur();
      });
    });
  }

  // ---------------------------------------------------------------- máquina e ajustes

  function maquina() {
    $$(".coletor").forEach(function (linha) {
      var dados = { modulo: linha.dataset.modulo, script: linha.dataset.script };
      var rodar = $("[data-rodar]", linha), ativar = $("[data-ativar]", linha);
      var revisao = $("[data-confianca]", linha), confiar = $("[data-confiar]", linha);
      if (revisao && confiar) {
        capacidadeLocal().then(function (token) {
          confiar.hidden = !token;
          $("[data-confianca-remota]", linha).hidden = !!token;
        });
        confiar.onclick = async function () {
          var conf = JSON.parse(revisao.dataset.confianca || "{}");
          var acao = confiar.dataset.confiar;
          if (!await confirmar({
            titulo: acao === "revogar" ? "Revogar autorização da automação?" : "Autorizar a execução da automação?",
            texto: acao === "revogar" ? "“" + dados.script + "” deixará de ter autorização para rodar neste computador." : "“" + dados.script + "” poderá executar com as permissões da sua conta. Confira o código e a configuração antes de autorizar.",
            detalhes: acao === "revogar" ? "" : "Arquivos:\n" + (conf.arquivos || []).join("\n") + "\n\nChaves declaradas: " + ((conf.requer || []).join(", ") || "nenhuma") + "\n\nAssinatura: " + conf.assinatura,
            confirmar: acao === "revogar" ? "Revogar autorização" : "Autorizar automação", perigoso: acao !== "revogar"
          })) return;
          confiar.disabled = true;
          api("POST", "/api/coletores/confiar", { modulo: dados.modulo, script: dados.script, assinatura: conf.assinatura, acao: acao })
            .then(function () { location.reload(); })
            .catch(function (erro) { confiar.disabled = false; mostrarErro(erro); });
        };
      }
      rodar.onclick = function () {
        rodar.disabled = true;
        var texto = $("span", rodar), antes = texto.textContent;
        texto.textContent = "Rodando...";
        api("POST", "/api/coletores/rodar", dados)
          .then(function (r) { avisar(r.novos + " novos, " + r.repetidos + " já conhecidos."); setTimeout(function () { location.reload(); }, 900); })
          .catch(mostrarErro)
          .then(function () { texto.textContent = antes; rodar.disabled = false; });
      };
      ativar.onchange = function () {
        api("POST", "/api/coletores/ativo", { modulo: dados.modulo, script: dados.script, ativo: ativar.checked })
          .then(function () { avisar(ativar.checked ? "Execução automática ligada." : "Execução automática desligada."); })
          .catch(function (erro) { ativar.checked = !ativar.checked; mostrarErro(erro); });
      };
    });
  }

  function ajustes() {
    // Um único ponto de entrada no Tab; setas e Home/End seguem o padrão de rádio.
    $$("[role='radiogroup']").forEach(function (grupo) {
      var radios = $$("[role='radio']", grupo), escolhido = radios.filter(function (r) { return r.getAttribute("aria-checked") === "true"; })[0] || radios[0];
      radios.forEach(function (radio) {
        radio.tabIndex = radio === escolhido ? 0 : -1;
        radio.addEventListener("keydown", function (e) {
          var deslocamento = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
          if (!deslocamento && e.key !== "Home" && e.key !== "End") return;
          e.preventDefault();
          var destino = e.key === "Home" ? radios[0] : e.key === "End" ? radios[radios.length - 1] : radios[(radios.indexOf(radio) + deslocamento + radios.length) % radios.length];
          radios.forEach(function (r) { r.tabIndex = r === destino ? 0 : -1; });
          destino.focus(); destino.click();
        });
      });
    });
    $$("[data-tema]").forEach(function (b) {
      b.onclick = function () { api("POST", "/api/tema", { tema: b.dataset.tema }).then(function () { location.reload(); }).catch(mostrarErro); };
    });
    $$("[data-backup]").forEach(function (b) {
      b.onclick = function () {
        b.disabled = true;
        api("POST", "/api/backup", { enviar: b.dataset.backup === "enviar" })
          .then(function (r) {
            var frases = { feito: "Versão local guardada.", nada: "Nada mudou desde o último snapshot." };
            var texto = frases[r.commit] || r.commit;
            if (r.push) texto += r.push === "feito" ? " Enviado." : " Envio: " + r.push;
            avisar(texto, /erro/.test(texto) ? "erro" : "");
          })
          .catch(mostrarErro)
          .then(function () { b.disabled = false; });
      };
    });

    // Aparência: cada escolha é gravada e a página recarrega já com o novo visual.
    function visual(chave, valor, botao) {
      var dados = { aparencia: {} };
      dados.aparencia[chave] = valor;
      var grupo = botao && botao.closest("[role='radiogroup']"), opcoes = grupo ? $$("[role='radio']", grupo) : [];
      var anteriores = opcoes.map(function (opcao) { return opcao.getAttribute("aria-checked"); });
      if (grupo) grupo.setAttribute("aria-busy", "true");
      opcoes.forEach(function (opcao) { opcao.disabled = true; opcao.setAttribute("aria-checked", opcao === botao ? "true" : "false"); });
      api("POST", "/api/config", dados).then(function (r) {
        var estilo = $("#aparencia-dinamica");
        if (!estilo) { estilo = document.createElement("style"); estilo.id = "aparencia-dinamica"; document.head.appendChild(estilo); }
        if (r.estilo) estilo.textContent = r.estilo;
        if (chave === 'tamanho') document.documentElement.dataset.tamanho = valor;
        opcoes.forEach(function (opcao) { opcao.disabled = false; });
        if (grupo) grupo.removeAttribute("aria-busy");

      }).catch(function (erro) {
        opcoes.forEach(function (opcao, i) { opcao.disabled = false; opcao.setAttribute("aria-checked", anteriores[i]); });
        if (grupo) grupo.removeAttribute("aria-busy");
        if (botao) botao.focus(); mostrarErro(erro);
      });
    }
    $$("[data-visual]").forEach(function (b) { b.onclick = function () { if (!b.disabled && b.getAttribute("aria-checked") !== "true") visual(b.dataset.visual, b.dataset.valor, b); }; });
    var corLivre = $("#cor-livre");
    if (corLivre) corLivre.addEventListener("change", function () { visual("destaque", corLivre.value); });

    // Painel: nome e captura são gravados ao mudar, como as propriedades de uma nota.
    function config(dados, mensagem) {
      var estadoConfig = $("#estado-config");
      if (estadoConfig) { estadoConfig.textContent = "Salvando suas preferências…"; estadoConfig.classList.remove("erro-texto"); }
      return api("POST", "/api/config", dados).then(function () {
        if (estadoConfig) estadoConfig.textContent = mensagem || "Preferências salvas.";
        return true;
      }).catch(function (erro) {
        if (estadoConfig) { estadoConfig.textContent = window.OrquestraInterface.mensagemErro(erro); estadoConfig.classList.add("erro-texto"); }
        mostrarErro(erro); return false;
      });
    }
    var nome = $("#cfg-nome"), captura = $("#cfg-captura"), auto = $("#cfg-auto-commit"), ligar = $("#ligar-historico");
    var revisaoBackup = $("#revisao-backup"), confiarBackup = $("#confiar-backup");
    if (revisaoBackup) {
      capacidadeLocal().then(function (token) {
        if (confiarBackup) confiarBackup.hidden = !token;
        if (ligar) ligar.hidden = !token;
        $("[data-backup-remoto]", revisaoBackup).hidden = !!token;
      });
      if (confiarBackup) confiarBackup.onclick = async function () {
        var conf = JSON.parse(revisaoBackup.dataset.confiancaBackup || "{}");
        var acao = confiarBackup.dataset.acao;
        var destinos = (conf.remotos || []).map(function (r) { return r.nome + " (" + r.tipo + "): " + r.destino; }).join("\n") || "Nenhum destino remoto";
        if (!await confirmar({ titulo: acao === "revogar" ? "Revogar autorização de backup?" : "Autorizar configuração de backup?", texto: acao === "revogar" ? "O backup só poderá rodar novamente depois de uma nova autorização neste computador." : "Confira a configuração Git e os destinos abaixo antes de autorizar os backups deste vault.", detalhes: destinos + "\n\nArquivos: " + (conf.arquivos || []).join(", ") + "\nAssinatura: " + conf.assinatura, confirmar: acao === "revogar" ? "Revogar autorização" : "Autorizar backup" })) return;
        confiarBackup.disabled = true;
        api("POST", "/api/backup/confiar", { acao: acao, assinatura: conf.assinatura }).then(function () { location.reload(); }).catch(function (erro) { confiarBackup.disabled = false; mostrarErro(erro); });
      };
    }
    if (nome) nome.addEventListener("change", function () {
      var erroNome = $("#erro-cfg-nome"), valido = !!nome.value.trim() && nome.checkValidity();
      var mensagem = nome.value.trim() ? (nome.validationMessage || "Use um nome de até 60 caracteres.") : "Informe um nome para o painel.";
      nome.setAttribute("aria-invalid", valido ? "false" : "true");
      if (erroNome) { erroNome.textContent = valido ? "" : mensagem; erroNome.hidden = valido; }
      if (!valido) {
        var estadoConfig = $("#estado-config");
        if (estadoConfig) { estadoConfig.textContent = "O nome do painel não foi salvo. " + mensagem; estadoConfig.classList.add("erro-texto"); }
        return;
      }
      nome.disabled = true;
      config({ nome: nome.value }).then(function (ok) { nome.disabled = false; if (ok) document.title = nome.value + " · Orquestra"; });
    });
    if (captura) captura.addEventListener("change", function () {
      captura.disabled = true;
      config({ captura: captura.value }).then(function (ok) { captura.disabled = false; });
    });
    if (auto) auto.addEventListener("change", function () {
      var proximo = auto.checked; auto.disabled = true;
      config({ auto_commit: proximo }, proximo ? "Backup automático ligado." : "Backup automático desligado.").then(function (ok) { if (!ok) auto.checked = !proximo; auto.disabled = false; });
    });
    if (ligar) ligar.onclick = async function () {
      var conf = JSON.parse(revisaoBackup.dataset.confiancaBackup || "{}");
      if (!await confirmar({ titulo: "Preparar o histórico local?", texto: "Será criado um repositório Git neste vault. Depois, você revisará a configuração antes de autorizar o primeiro backup.", detalhes: conf.assinatura ? "Assinatura da preparação: " + conf.assinatura : "Esta etapa prepara o repositório. Nenhum destino remoto será autorizado agora.", confirmar: "Preparar histórico" })) return;
      ligar.disabled = true;
      api("POST", "/api/backup/iniciar", { assinatura: conf.assinatura }).then(function () { location.reload(); }).catch(function (erro) { ligar.disabled = false; mostrarErro(erro); });
    };

    // Áreas: acrescentar uma pronta, criar em branco, tirar do painel.
    function ligarRetirada(b) {
      b.onclick = async function () {
        var linha = b.closest(".area-linha");
        if (!await confirmar({ titulo: "Retirar esta área do painel?", texto: "“" + $("b", linha).textContent + "” deixará de aparecer na navegação. A pasta e as notas continuam no vault; você pode adicioná-la novamente aqui em Ajustes → Pastas.", confirmar: "Retirar do painel" })) return;
        b.disabled = true;
        api("POST", "/api/modulos/" + encodeURIComponent(linha.dataset.modulo) + "/desligar", {})
          .then(function () { location.reload(); })
          .catch(function (erro) { b.disabled = false; mostrarErro(erro); });
      };
    }
    async function atualizarAreas(r) {
      // Atualiza só a área criada e a navegação, preservando campos e posição.
      try {
        var resposta = await fetch('/ajustes/areas', { cache: 'no-store', credentials: 'same-origin' });
        if (!resposta.ok) throw new Error('Falha ao atualizar a lista de pastas.');
        var doc = new DOMParser().parseFromString(await resposta.text(), 'text/html');
        if (doc.body.dataset.vaultId !== document.body.dataset.vaultId) throw new Error('O cofre mudou.');
        var nova = $$('.area-linha', doc).find(function (l) { return l.dataset.modulo === r.id; });
        var lista = $('#areas-ordem');
        if (!nova || !lista || !$('.dock', doc)) throw new Error('Lista indisponível.');
        if (!$$('.area-linha', lista).some(function (l) { return l.dataset.modulo === r.id; })) {
          if (!$('.area-linha', lista)) { var vazio = $('p.suave', lista); if (vazio) vazio.remove(); }
          var linha = document.importNode(nova, true);
          lista.insertBefore(linha, lista.lastElementChild);
          ligarRetirada($('[data-desligar]', linha));
        }
        $$('.dock, #gaveta').forEach(function (atual) {
          var novo = $(atual.id ? '#' + atual.id : '.dock', doc);
          if (novo) atual.replaceWith(document.importNode(novo, true)); else atual.remove();
        });
        if ($('#gaveta', doc) && !$('#gaveta')) $('.dock').after(document.importNode($('#gaveta', doc), true));
        gaveta();
        document.dispatchEvent(new CustomEvent('orquestra:areas-atualizadas'));
        $('#estado-config').textContent = 'Área adicionada. Continue seus ajustes ou abra pelo dock.';
        avisar('Área adicionada ao painel.');
      } catch (erro) {
        avisar('A área foi adicionada. Não foi possível atualizar a navegação; recarregue a página quando terminar seus ajustes.', 'erro');
      }
    }
    $$("[data-pronto], [data-religar]").forEach(function (b) {
      b.onclick = async function () {
        b.disabled = true;
        configPropriaAte = Date.now() + 10000;
        try {
          var r = b.dataset.religar
            ? await api("POST", "/api/pastas/adotar", { pasta: b.dataset.religar })
            : await api("POST", "/api/modulos", { pronto: b.dataset.pronto, exemplos: $("#pronto-exemplos").checked });
          b.setAttribute('aria-label', 'Área adicionada');
          b.title = 'Área já adicionada ao painel';
          await atualizarAreas(r);
          if (b.dataset.religar) b.remove();
        } catch (erro) { b.disabled = false; mostrarErro(erro); }
      };
    });
    $$("[data-desligar]").forEach(ligarRetirada);
    var dArea = $("#dialogo-area"), abrirArea = $("#abrir-area-branco");
    if (dArea && abrirArea) {
      abrirArea.onclick = function () { dArea.showModal(); $("#area-nome").focus(); };
      $("form", dArea).addEventListener("submit", function (e) {
        e.preventDefault();
        var salvar = $("#area-salvar");
        salvar.disabled = true;
        configPropriaAte = Date.now() + 10000;
        api("POST", "/api/modulos", { nome: $("#area-nome").value, icone: $("#area-icone").value, quadro: $("#area-quadro").checked })
          .then(async function (r) {
            dArea.close();
            $("form", dArea).reset();
            salvar.disabled = false;
            await atualizarAreas(r);
            abrirArea.focus({ preventScroll: true });
          })
          .catch(function (erro) { salvar.disabled = false; mostrarErro(erro); });
      });
    }
  }

  function tabela() {
    $$("[data-lote]").forEach(function (raiz) {
      var todos = $("[data-lote-todos]", raiz);
      if (!todos || raiz.dataset.loteLigado) return;
      raiz.dataset.loteLigado = "1";
      var barra = $(".lote-barra", raiz), acao = $("[data-lote-acao]", raiz), status = $("[data-lote-status]", raiz), botao = $("[data-lote-executar]", raiz), resultado = $("[data-lote-resultado]", raiz), ocupado = false;
      function caixas() { return $$("[data-lote-item]", raiz); }
      function atualizar() {
        var itens = caixas(), selecionados = itens.filter(function (el) { return el.checked; });
        barra.hidden = !selecionados.length;
        $("[data-lote-contagem]", raiz).textContent = selecionados.length + " selecionados";
        todos.checked = itens.length > 0 && selecionados.length === itens.length;
        todos.indeterminate = selecionados.length > 0 && selecionados.length < itens.length;
        itens.forEach(function (el) { el.closest("tr").classList.toggle("selecionada", el.checked); });
      }
      todos.onchange = function () { caixas().forEach(function (el) { el.checked = todos.checked; }); atualizar(); };
      caixas().forEach(function (el) { el.onchange = atualizar; });
      acao.onchange = function () { if (status) status.hidden = acao.value !== "status"; };
      botao.onclick = async function () {
        if (ocupado) return;
        var selecionados = caixas().filter(function (el) { return el.checked; }), operacao = acao.value;
        if (!selecionados.length) return;
        if (operacao !== "status" && !await confirmar({titulo: (operacao === "excluir" ? "Excluir " : "Arquivar ") + selecionados.length + " notas?", texto: operacao === "excluir" ? "As notas irão para a lixeira. Anexos e outras notas serão mantidos." : "As notas irão para arquivo/ desta área.", confirmar: operacao === "excluir" ? "Mover para a lixeira" : "Arquivar"})) return;
        ocupado = true;
        $$("input,select,button", raiz).forEach(function (el) { el.disabled = true; });
        try {
          var resposta = await api("POST", "/api/lote", {acao:operacao, itens:selecionados.map(function (el) { return {rel:el.dataset.rel, versao:el.dataset.versao}; }), status:operacao === "status" ? status.value : ""});
          var falhas = [], salvos = 0;
          resposta.resultados.forEach(function (r) {
            var el = selecionados.find(function (c) { return c.dataset.rel === r.rel; });
            if (!el) return;
            if (!r.ok) { falhas.push(el.getAttribute("aria-label").replace(/^Selecionar /, "") + ": " + r.erro); return; }
            salvos++; el.checked = false;
            if (r.versao) {
              minhas[r.versao] = true; el.dataset.versao = r.versao;
              el.closest("tr").classList.toggle("concluido", !!r.concluido);
              var celula = $$("[data-coluna]", el.closest("tr")).find(function (c) { return c.dataset.coluna === raiz.dataset.campoStatus; });
              if (celula) { celula.textContent = status.selectedOptions[0].textContent; }
            } else {
              minhasRemovidas[r.rel] = Date.now() + 2000; el.closest("tr").remove();
            }
          });
          resultado.hidden = false; resultado.textContent = salvos + " notas atualizadas." + (falhas.length ? "\n" + falhas.join("\n") : "");
          if (salvos) fetch(location.href, {cache:"no-store", credentials:"same-origin"}).then(function (r) { if (!r.ok) return; return r.text(); }).then(function (html) {
            if (!html) return;
            var doc = new DOMParser().parseFromString(html, "text/html"), atual = $(".cab-numeros"), nova = $(".cab-numeros", doc);
            if (doc.body.dataset.vaultId === document.body.dataset.vaultId && atual && nova) atual.replaceWith(document.importNode(nova, true));
          }).catch(function () { /* O resultado da gravação já está visível. */ });
        } catch (erro) { mostrarErro(erro); }
        finally { ocupado = false; $$("input,select,button", raiz).forEach(function (el) { el.disabled = false; }); atualizar(); }
      };
    });
    $$(".tabela th[data-ordenar]").forEach(function (th) {
      var coluna = th.cellIndex;
      var crescente = true;
      var botao = $("button", th);
      if (!botao) return;
      botao.onclick = function () {
        var corpo = $("tbody", th.closest("table")), linhas = $$("tr", corpo);
        var chave = function (tr) { var td = tr.children[coluna]; return (td.dataset.ordem || td.textContent).trim().toLowerCase(); };
        linhas.sort(function (a, b) { return chave(a).localeCompare(chave(b), "pt-BR", { numeric: true }) * (crescente ? 1 : -1); });
        linhas.forEach(function (tr) { corpo.appendChild(tr); });
        $$("th[data-ordenar]", th.closest("table")).forEach(function (cabecalho) { cabecalho.setAttribute("aria-sort", "none"); });
        th.setAttribute("aria-sort", crescente ? "ascending" : "descending");
        crescente = !crescente;
      };
    });
  }

  // ---------------------------------------------------------------- ao vivo

  var resumoTemporizador = 0, resumoEmVoo = false, resumoPendente = false;
  function atualizarSelos() {
    // Uma rajada de mudanças precisa de uma leitura final, não uma por arquivo.
    resumoPendente = true;
    if (resumoEmVoo || resumoTemporizador) return;
    resumoTemporizador = setTimeout(buscarResumo, 180);
  }
  function buscarResumo() {
    resumoTemporizador = 0;
    if (resumoEmVoo || !resumoPendente) return;
    resumoPendente = false; resumoEmVoo = true;
    fetch("/api/resumo", { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("Não consegui atualizar os contadores.");
      return r.json();
    }).then(function (dados) {
      if (!dados || typeof dados !== "object" || Array.isArray(dados)) return;
      if (document.body.dataset.vaultId && dados.vault_id !== document.body.dataset.vaultId) { recarregarLogo(true, true); return; }
      // Nomes de pastas podem conter aspas: não os interpolar em seletores CSS.
      $$("[data-selo-de]").forEach(function (item) {
        var numero = Number((dados.selos || {})[item.dataset.seloDe] || 0), selo = $(".selo", item);
        numero = Number.isFinite(numero) ? Math.max(0, Math.floor(numero)) : 0;
        if (selo) { selo.textContent = numero > 99 ? '99+' : numero; selo.hidden = numero === 0; selo.title = numero + ' pendências'; }
      });
      $$('[data-conta="decidir"]').forEach(function (el) { el.textContent = dados.decidir; });
      $$('[data-conta="hoje"]').forEach(function (el) { el.textContent = dados.hoje; });
    }).catch(function () { /* preserva os contadores atuais se o painel reiniciar */ }).then(function () {
      resumoEmVoo = false;
      // Eventos recebidos durante o pedido invalidam o resultado: leia outra vez.
      if (resumoPendente) atualizarSelos();
    });
  }

  var temporizador = 0, avisouNovidade = false;
  function ocupado() { return notaSuja || personalizacaoPendente() || !!arrastando || !!$("dialog[open]") || (document.activeElement && (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable)); }
  function recarregarLogo(resumoJaSolicitado, reconexao) {
    if (!resumoJaSolicitado) atualizarSelos();
    clearTimeout(temporizador);
    temporizador = setTimeout(function () {
        if (reconexao && !ocupado() && !$('[data-lote-item]:checked')) { location.reload(); return; }
      if (personalizacaoPendente() && $("#p-novidades")) { $("#p-novidades").hidden = false; return; }
      // Atualização explícita preserva foco, rolagem e formulários.
      // A pessoa está no meio de algo: não tiramos a tela debaixo dela.
      if (notaSuja && $("#faixa-conflito")) { $("#faixa-conflito").hidden = false; return; }
      if (!avisouNovidade) { avisouNovidade = true; avisar("Há novidades nesta página.", "", { rotulo: "Atualizar", fazer: function () { location.reload(); } }); }
    }, 450);
  }

  var fonteAoVivo = null, cicloAoVivoLigado = false;
  function aoVivo() {
    if (!window.EventSource) return;
    if (fonteAoVivo) fonteAoVivo.close();
    var fonte = new EventSource("/eventos"), abriu = false, houveFalha = false;
    fonteAoVivo = fonte;
    var estado = $("#estado-conexao");
    fonte.onerror = function () {
      houveFalha = true;
      if (estado) { estado.hidden = false; estado.textContent = "Reconectando…"; }
    };
    fonte.onopen = function () {
      if (estado) { estado.hidden = true; estado.textContent = ""; }
      atualizarSelos();
      // Eventos não têm replay. Após qualquer interrupção, conferir a página
      // inteira, preservando editores, formulários e diálogos com trabalho pendente.
      if (abriu || houveFalha) recarregarLogo(true, true);
      abriu = true;
    };
    if (!cicloAoVivoLigado) {
      cicloAoVivoLigado = true;
      window.addEventListener("pagehide", function () { if (fonteAoVivo) fonteAoVivo.close(); });
      window.addEventListener("pageshow", function (e) { if (e.persisted) { aoVivo(); recarregarLogo(false, true); } });
    }
    fonte.onmessage = function (mensagem) {
      var ev;
      try { ev = JSON.parse(mensagem.data); } catch (e) { return; }
      if (!ev || typeof ev !== "object") return;
      // Pequena espera: a resposta da nossa própria gravação pode chegar depois do evento.
      setTimeout(function () {
        if (ev.tipo === "config") { if (Date.now() > configPropriaAte) recarregarLogo(); return; }
        atualizarSelos();
        if (ev.versao && minhas[ev.versao]) return;
        if (ev.acao === "removido" && minhasRemovidas[ev.rel]) {
          var propria = minhasRemovidas[ev.rel] > Date.now(); delete minhasRemovidas[ev.rel];
          if (propria) return;
        }
        var observa = document.body.dataset.observa || "", corte = observa.indexOf(":");
        var tipo = corte < 0 ? observa : observa.slice(0, corte), alvo = corte < 0 ? "" : observa.slice(corte + 1);
        var afeta = tipo === "tudo" || (tipo === "modulo" && (ev.modulo === alvo || ev.tipo === "coletor")) || (tipo === "nota" && ev.rel === alvo);
        if (afeta) recarregarLogo(true);
      }, 350);
    };
  }

  window.Orquestra = window.Orquestra || {};
  window.Orquestra.api = api;
  window.Orquestra.prepararPastas = function (novos) { dialogos(novos); pastas(); };
  window.Orquestra.prepararModulo = function (dialogosNovos) { dialogos(dialogosNovos); novoItem(); quadro(); maquina(); tabela(); numeros(); };

  document.addEventListener("DOMContentLoaded", function () {
    relogio(); carrossel(); dialogos(); gaveta(); captura(); novoItem(); quadro(); seletoresSoltos();
    decidir(); nota(); maquina(); ajustes(); tabela(); pastas(); personalizar(); numeros(); aoVivo();
  });
})();
