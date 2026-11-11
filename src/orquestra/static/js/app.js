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
  var minhas = {};
  var arrastando = null;

  function caminho(rel) { return rel.split("/").map(encodeURIComponent).join("/"); }

  // ---------------------------------------------------------------- avisos

  function avisar(texto, tipo, acao) {
    var caixa = $("#avisos");
    if (!caixa) return;
    var el = document.createElement("div");
    el.className = "aviso" + (tipo ? " " + tipo : "");
    el.textContent = texto;
    if (acao) {
      var botao = document.createElement("button");
      botao.textContent = acao.rotulo;
      botao.onclick = acao.fazer;
      el.appendChild(botao);
    }
    caixa.appendChild(el);
    setTimeout(function () { el.remove(); }, acao ? 12000 : tipo === "erro" ? 6000 : 2600);
  }

  // ---------------------------------------------------------------- API

  function api(metodo, url, corpo) {
    return fetch(url, { method: metodo, headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo || {}) })
      .catch(function () { throw new Error("Sem conexão com o painel. Ele está rodando?"); })
      .then(function (resp) {
        return resp.json().catch(function () { return {}; }).then(function (dados) {
          if (!resp.ok) {
            var erro = new Error(dados.erro || "Erro " + resp.status);
            erro.conflito = !!dados.conflito;
            throw erro;
          }
          if (dados.versao) minhas[dados.versao] = true;
          return dados;
        });
      });
  }
  function mostrarErro(erro) {
    if (erro.conflito) avisar(erro.message, "erro", { rotulo: "Recarregar", fazer: function () { location.reload(); } });
    else avisar(erro.message, "erro");
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
      slides.forEach(function (s, k) { s.classList.toggle("ativo", k === i); });
      pontos.forEach(function (p, k) { p.classList.toggle("ativo", k === i); });
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
    setaEsq.onclick = function () { ir(atual - 1); };
    setaDir.onclick = function () { ir(atual + 1); };
    pontos.forEach(function (p, k) { p.onclick = function () { ir(k); }; });
    slides.forEach(function (s, k) {
      // Clicar num slide que está ao lado traz ele para o centro em vez de abrir.
      s.addEventListener("click", function (e) { if (k !== atual) { e.preventDefault(); ir(k); } });
    });
    document.addEventListener("keydown", function (e) {
      if (digitando(e) || $("dialog[open]")) return;
      if (e.key === "ArrowLeft") ir(atual - 1);
      else if (e.key === "ArrowRight") ir(atual + 1);
      else if (e.key === "Enter" && atual >= 0) slides[atual].click();
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

  function dialogos() {
    $$("[data-fechar]").forEach(function (b) { b.onclick = function () { b.closest("dialog").close(); }; });
    $$("dialog").forEach(function (d) {
      d.addEventListener("click", function (e) { if (e.target === d) d.close(); }); // clique fora fecha
    });
  }

  function captura() {
    var dialogo = $("#captura"), abrir = $("#abrir-captura");
    if (!dialogo || !abrir) return;
    var texto = $("#captura-texto"), salvar = $("#captura-salvar");
    function mostrar() { dialogo.showModal(); texto.focus(); }
    function guardar() {
      if (!texto.value.trim()) { texto.focus(); return; }
      salvar.disabled = true;
      api("POST", "/api/captura", { texto: texto.value })
        .then(function () { texto.value = ""; dialogo.close(); avisar("Guardado na entrada."); })
        .catch(mostrarErro)
        .then(function () { salvar.disabled = false; });
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
    abrir.onclick = function () { dialogo.showModal(); titulo.focus(); };
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var campos = {};
      $$("[data-novo]", form).forEach(function (el) { campos[el.name] = el.type === "checkbox" ? el.checked : el.value; });
      salvar.disabled = true;
      api("POST", "/api/notas", { modulo: dialogo.dataset.modulo, zona: dialogo.dataset.zona, titulo: titulo.value, campos: campos, corpo: $("#novo-corpo").value })
        .then(function () { location.reload(); })
        .catch(function (erro) { salvar.disabled = false; mostrarErro(erro); });
    });
  }

  // ---------------------------------------------------------------- quadro

  function contar(quadro) {
    $$(".coluna", quadro).forEach(function (col) { $(".conta", col).textContent = $$(".cartao", col).length; });
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
      if (origem === coluna) return;
      $(".cartoes", coluna).prepend(cartao);
      contar(q);
      mudarCampo(cartao, campo, coluna.dataset.valor)
        .then(function () { if (seletor) seletor.value = coluna.dataset.valor; })
        .catch(function (erro) { // não deu: volta o cartão para onde estava
          $(".cartoes", origem).prepend(cartao);
          if (seletor) seletor.value = origem.dataset.valor;
          contar(q);
          mostrarErro(erro);
        });
    }

    q.addEventListener("dragstart", function (e) {
      var cartao = e.target.closest && e.target.closest(".cartao");
      if (!cartao) return;
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
      api("PUT", "/api/notas/" + caminho(item.dataset.rel), { versao: item.dataset.versao, campos: campos })
        .then(function () {
          item.classList.add("saindo");
          setTimeout(function () { item.remove(); atualizarSelos(); if (!$(".fila-item")) location.reload(); }, 260);
        })
        .catch(function (erro) { $$("button", item).forEach(function (b) { b.disabled = false; }); mostrarErro(erro); });
    }
    $$("[data-acao]").forEach(function (botao) {
      botao.onclick = function () { resolver(botao.closest(".fila-item"), JSON.parse(botao.dataset.acao)); };
    });
    // Pergunta de um agente: a resposta fica no frontmatter (campo `resposta`) e a pergunta sai da fila.
    $$("[data-responder]").forEach(function (botao) {
      botao.onclick = function () {
        var item = botao.closest(".fila-item"), pergunta = $(".cartao-pergunta", item);
        var resposta = prompt(pergunta ? pergunta.textContent.trim() : "Sua resposta:");
        if (resposta && resposta.trim()) resolver(item, { resposta: resposta.trim(), pergunta: "" });
      };
    });
  }

  // ---------------------------------------------------------------- nota

  var notaSuja = false;

  function nota() {
    var raiz = $(".nota");
    if (!raiz) return;
    var rel = raiz.dataset.rel, versao = raiz.dataset.versao, url = "/api/notas/" + caminho(rel);
    var ver = $("#ver"), editor = $("#editor"), bEditar = $("#editar"), bSalvar = $("#salvar"), bCancelar = $("#cancelar");
    var estado = $("#estado-salvo"), original = editor ? editor.value : "";

    function gravar(dados) {
      dados.versao = versao;
      return api("PUT", url, dados).then(function (r) {
        versao = r.versao;
        if (estado) estado.textContent = "Salvo às " + new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) + ".";
        return r;
      });
    }
    function falhou(erro) {
      if (erro.conflito) $("#faixa-conflito").hidden = false;
      mostrarErro(erro);
    }

    // Propriedades: cada campo é salvo assim que muda.
    $$("[data-campo]", raiz).forEach(function (el) {
      el.addEventListener("change", function () {
        var campos = {};
        campos[el.name] = el.type === "checkbox" ? el.checked : el.value;
        gravar({ campos: campos })
          .then(function () { el.classList.add("salvo-ok"); setTimeout(function () { el.classList.remove("salvo-ok"); }, 900); })
          .catch(falhou);
      });
    });

    var titulo = $("#nota-titulo");
    if (titulo) {
      titulo.addEventListener("change", function () {
        if (!titulo.value.trim()) { titulo.value = document.title.split(" · ")[0]; return; }
        gravar({ titulo: titulo.value }).catch(falhou);
      });
      titulo.addEventListener("keydown", function (e) { if (e.key === "Enter") titulo.blur(); });
    }

    function modoEdicao(ligado) {
      ver.hidden = ligado; editor.hidden = !ligado;
      bEditar.hidden = ligado; bSalvar.hidden = !ligado; bCancelar.hidden = !ligado;
      if (ligado) editor.focus();
    }
    function salvarTexto() {
      bSalvar.disabled = true;
      gravar({ corpo: editor.value })
        .then(function (r) {
          original = editor.value; notaSuja = false;
          ver.innerHTML = r.html || '<p class="suave">Sem texto.</p>'; // HTML gerado pelo servidor, com HTML cru desativado
          modoEdicao(false);
          avisar("Salvo.");
        })
        .catch(falhou)
        .then(function () { bSalvar.disabled = false; });
    }
    if (bEditar) {
      bEditar.onclick = function () { modoEdicao(true); };
      bSalvar.onclick = salvarTexto;
      bCancelar.onclick = function () { editor.value = original; notaSuja = false; modoEdicao(false); };
      editor.addEventListener("input", function () { notaSuja = editor.value !== original; });
      document.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && !editor.hidden) { e.preventDefault(); salvarTexto(); }
      });
      window.addEventListener("beforeunload", function (e) { if (notaSuja) { e.preventDefault(); e.returnValue = ""; } });
    }

    var bArquivar = $("#arquivar");
    if (bArquivar) {
      bArquivar.onclick = function () {
        if (!confirm("Arquivar esta nota? Ela vai para a pasta arquivo/ do módulo e pode ser trazida de volta.")) return;
        api("POST", "/api/arquivar/" + caminho(rel), {})
          .then(function () { notaSuja = false; location.href = raiz.dataset.voltar || "/"; })
          .catch(mostrarErro);
      };
    }
  }

  // ---------------------------------------------------------------- máquina e ajustes

  function maquina() {
    $$(".coletor").forEach(function (linha) {
      var dados = { modulo: linha.dataset.modulo, script: linha.dataset.script };
      var rodar = $("[data-rodar]", linha), ativar = $("[data-ativar]", linha);
      rodar.onclick = function () {
        rodar.disabled = true;
        var texto = $("span", rodar), antes = texto.textContent;
        texto.textContent = "Rodando...";
        api("POST", "/api/coletores/rodar", dados)
          .then(function (r) { avisar(r.novos + " novos, " + r.repetidos + " já conhecidos."); setTimeout(function () { location.reload(); }, 900); })
          .catch(function (erro) { mostrarErro(erro); setTimeout(function () { location.reload(); }, 1800); })
          .then(function () { texto.textContent = antes; rodar.disabled = false; });
      };
      ativar.onchange = function () {
        api("POST", "/api/coletores/ativo", { modulo: dados.modulo, script: dados.script, ativo: ativar.checked })
          .then(function () { avisar(ativar.checked ? "Coletor automático ligado." : "Coletor automático desligado."); })
          .catch(function (erro) { ativar.checked = !ativar.checked; mostrarErro(erro); });
      };
    });
  }

  function ajustes() {
    $$("[data-tema]").forEach(function (b) {
      b.onclick = function () { api("POST", "/api/tema", { tema: b.dataset.tema }).then(function () { location.reload(); }).catch(mostrarErro); };
    });
    $$("[data-backup]").forEach(function (b) {
      b.onclick = function () {
        b.disabled = true;
        api("POST", "/api/backup", { enviar: b.dataset.backup === "enviar" })
          .then(function (r) {
            var frases = { feito: "Commit feito.", nada: "Nada mudou desde o último commit." };
            var texto = frases[r.commit] || r.commit;
            if (r.push) texto += r.push === "feito" ? " Enviado." : " Envio: " + r.push;
            avisar(texto, /erro/.test(texto) ? "erro" : "");
          })
          .catch(mostrarErro)
          .then(function () { b.disabled = false; });
      };
    });
  }

  function tabela() {
    $$(".tabela th[data-ordenar]").forEach(function (th, coluna) {
      var crescente = true;
      th.onclick = function () {
        var corpo = $("tbody", th.closest("table")), linhas = $$("tr", corpo);
        var chave = function (tr) { var td = tr.children[coluna]; return (td.dataset.ordem || td.textContent).trim().toLowerCase(); };
        linhas.sort(function (a, b) { return chave(a).localeCompare(chave(b), "pt-BR", { numeric: true }) * (crescente ? 1 : -1); });
        linhas.forEach(function (tr) { corpo.appendChild(tr); });
        crescente = !crescente;
      };
    });
  }

  // ---------------------------------------------------------------- ao vivo

  function atualizarSelos() {
    fetch("/api/resumo").then(function (r) { return r.json(); }).then(function (dados) {
      Object.keys(dados.selos || {}).forEach(function (id) {
        var selo = $('[data-selo-de="' + id + '"] .selo');
        if (selo) { selo.textContent = dados.selos[id]; selo.hidden = !dados.selos[id]; }
      });
      $$('[data-conta="decidir"]').forEach(function (el) { el.textContent = dados.decidir; });
      $$('[data-conta="hoje"]').forEach(function (el) { el.textContent = dados.hoje; });
    }).catch(function () { /* o painel pode estar reiniciando */ });
  }

  var temporizador = 0, avisouNovidade = false;
  function ocupado() { return notaSuja || !!arrastando || !!$("dialog[open]") || (document.activeElement && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)); }
  function recarregarLogo() {
    clearTimeout(temporizador);
    temporizador = setTimeout(function () {
      if (!ocupado()) { location.reload(); return; }
      // A pessoa está no meio de algo: não tiramos a tela debaixo dela.
      if (notaSuja && $("#faixa-conflito")) { $("#faixa-conflito").hidden = false; return; }
      if (!avisouNovidade) { avisouNovidade = true; avisar("Há novidades nesta página.", "", { rotulo: "Atualizar", fazer: function () { location.reload(); } }); }
    }, 450);
  }

  function aoVivo() {
    if (!window.EventSource) return;
    var fonte = new EventSource("/eventos");
    fonte.onmessage = function (mensagem) {
      var ev;
      try { ev = JSON.parse(mensagem.data); } catch (e) { return; }
      // Pequena espera: a resposta da nossa própria gravação pode chegar depois do evento.
      setTimeout(function () {
        if (ev.tipo === "config") { recarregarLogo(); return; }
        atualizarSelos();
        if (ev.versao && minhas[ev.versao]) return;
        var observa = document.body.dataset.observa || "", corte = observa.indexOf(":");
        var tipo = corte < 0 ? observa : observa.slice(0, corte), alvo = corte < 0 ? "" : observa.slice(corte + 1);
        var afeta = tipo === "tudo" || (tipo === "modulo" && (ev.modulo === alvo || ev.tipo === "coletor")) || (tipo === "nota" && ev.rel === alvo);
        if (afeta) recarregarLogo();
      }, 350);
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    relogio(); carrossel(); dialogos(); captura(); novoItem(); quadro(); seletoresSoltos();
    decidir(); nota(); maquina(); ajustes(); tabela(); aoVivo();
  });
})();
