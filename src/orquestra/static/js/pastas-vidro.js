/* Pastas de vidro dos Projetos.
   A arte do fundo é gerada, não baixada: um campo de ruído dobrado sobre si
   mesmo e iluminado como líquido, pintado aos poucos (alguns ms por quadro)
   para uma fileira de pastas não travar a página. Imagem do projeto, quando
   existe, substitui a arte. O + abre a captura rápida já ligada ao projeto. */
(function () {
  "use strict";
  // Quatro artes nativas: Aurora e Brasa vêm da referência; Ametista e Oceano
  // seguem o mesmo desenho em outras cores. Os ids batem com ARTES_DE_PASTA.
  var ARTES = {
    aurora: { style: "streak", colors: ["#f4efe9", "#e9c2b8", "#c2433f", "#2a1e2a", "#22395e", "#6f97c2", "#e5edf4"], scale: 0.7, warp: 1.4, angle: -0.62, gloss: 0.18, veins: 0 },
    brasa: { style: "marble", colors: ["#07090c", "#16252c", "#3d5f68", "#1a1416", "#a3201a", "#ef4a2b", "#ff8a5c"], scale: 0.62, warp: 3.2, angle: -0.5, gloss: 0.55, veins: 0.6 },
    ametista: { style: "marble", colors: ["#0b0814", "#231a3d", "#5b3f8f", "#1a1226", "#7d5bd6", "#c9a9f2", "#f3e9ff"], scale: 0.72, warp: 3.3, angle: 1.4, gloss: 0.5, veins: 0.45 },
    oceano: { style: "streak", colors: ["#eef6f4", "#bfe3dc", "#2f8f8a", "#0f2a33", "#123f5c", "#7fb8c9", "#f2e6cf"], scale: 0.7, warp: 1.5, angle: 0.5, gloss: 0.22, veins: 0 }
  };

  function hexToRgb(hex) {
    var h = String(hex).trim().replace(/^#/, "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = /^[0-9a-f]{6}$/i.test(h) ? parseInt(h, 16) : 0x808080;
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0; var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function hashString(s) {
    var h = 2166136261;
    for (var i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
    return h >>> 0;
  }
  function makeFbm(seed) {
    var r = rng(seed), perm = new Uint8Array(512), grad = new Float32Array(512), p = [], i;
    for (i = 0; i < 256; i++) p.push(i);
    for (i = 255; i > 0; i--) { var j = Math.floor(r() * (i + 1)), t = p[i]; p[i] = p[j]; p[j] = t; }
    for (i = 0; i < 512; i++) perm[i] = p[i & 255];
    for (i = 0; i < 256; i++) { var a = r() * Math.PI * 2; grad[i * 2] = Math.cos(a); grad[i * 2 + 1] = Math.sin(a); }
    function noise(x, y) {
      var xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi, X = xi & 255, Y = yi & 255;
      var h00 = perm[X + perm[Y]] * 2, h10 = perm[X + 1 + perm[Y]] * 2, h01 = perm[X + perm[Y + 1]] * 2, h11 = perm[X + 1 + perm[Y + 1]] * 2;
      var d00 = grad[h00] * xf + grad[h00 + 1] * yf, d10 = grad[h10] * (xf - 1) + grad[h10 + 1] * yf;
      var d01 = grad[h01] * xf + grad[h01 + 1] * (yf - 1), d11 = grad[h11] * (xf - 1) + grad[h11 + 1] * (yf - 1);
      var u = xf * xf * xf * (xf * (xf * 6 - 15) + 10), v = yf * yf * yf * (yf * (yf * 6 - 15) + 10);
      return d00 + u * (d10 - d00) + v * (d01 - d00 + u * (d11 - d01 - d10 + d00));
    }
    return function (x, y, octaves) {
      var sum = 0, amp = 0.5;
      for (var k = 0; k < octaves; k++) { sum += amp * noise(x, y); var nx = 1.6 * x + 1.2 * y + 7.1; y = -1.2 * x + 1.6 * y + 3.3; x = nx; amp *= 0.5; }
      return sum;
    };
  }

  // Campo dobrado duas vezes, normalizado por percentis e iluminado como
  // superfície líquida. Amostrado em meia resolução e ampliado (Catmull-Rom).
  function createArtJob(width, height, recipe, seed) {
    var w = Math.max(1, Math.round(width)), h = Math.max(1, Math.round(height));
    var stops = recipe.colors.map(function (c, i) { return { t: i / (recipe.colors.length - 1), c: hexToRgb(c) }; });
    var scale = recipe.scale, warp = recipe.warp, gloss = recipe.gloss, veins = recipe.veins, streak = recipe.style === "streak";
    var fbm = makeFbm(seed * 977 + 13), r = rng(seed + 1), ox = r() * 50, oy = r() * 50;
    var angle = recipe.angle + (r() - 0.5) * 0.5, ca = Math.cos(angle), sa = Math.sin(angle), m = Math.min(w, h);
    var gw = Math.ceil(w / 2) + 3, gh = Math.ceil(h / 2) + 3;
    var G = new Float32Array(gw * gh), GQ = new Float32Array(gw * gh), F = new Float32Array(w * h), Q = new Float32Array(w * h);
    var pixels = new Uint8ClampedArray(w * h * 4), row = 0;
    function field(gy) {
      for (var gx = 0; gx < gw; gx++) {
        var u = ((gx - 1) * 2 - w / 2) / m, v = ((gy - 1) * 2 - h / 2) / m;
        var px = (u * ca - v * sa) * scale, py = (u * sa + v * ca) * scale;
        if (streak) { px *= 0.14; py *= 2.2; }
        px += ox; py += oy;
        var qx = fbm(px, py, 3), qy = fbm(px + 5.2, py + 1.3, 3);
        var rx = fbm(px + warp * qx + 1.7, py + warp * qy + 9.2, 3), ry = fbm(px + warp * qx + 8.3, py + warp * qy + 2.8, 3);
        G[gy * gw + gx] = fbm(px + warp * rx, py + warp * ry, 4);
        GQ[gy * gw + gx] = Math.sqrt(qx * qx + qy * qy);
      }
    }
    function upsample() {
      var cr = function (a, b, c, d) { return (-a + 9 * b + 9 * c - d) / 16; };
      var T = new Float32Array(w * gh), x, y, c;
      for (var gy = 0; gy < gh; gy++) {
        var base = gy * gw;
        for (x = 0; x < w; x++) { c = (x >> 1) + 1; T[gy * w + x] = x & 1 ? cr(G[base + c - 1], G[base + c], G[base + c + 1], G[base + c + 2]) : G[base + c]; }
      }
      for (y = 0; y < h; y++) {
        c = (y >> 1) + 1;
        for (x = 0; x < w; x++) {
          F[y * w + x] = y & 1 ? cr(T[(c - 1) * w + x], T[c * w + x], T[(c + 1) * w + x], T[(c + 2) * w + x]) : T[c * w + x];
          var gx = (x >> 1) + 1, q0 = GQ[c * gw + gx];
          var qxx = x & 1 ? (q0 + GQ[c * gw + gx + 1]) / 2 : q0;
          var q1 = y & 1 ? (x & 1 ? (GQ[(c + 1) * gw + gx] + GQ[(c + 1) * gw + gx + 1]) / 2 : GQ[(c + 1) * gw + gx]) : qxx;
          Q[y * w + x] = (qxx + q1) / 2;
        }
      }
    }
    function colorize() {
      var sample = [], stride = Math.max(1, Math.floor(F.length / 4096));
      for (var s = 0; s < F.length; s += stride) sample.push(F[s]);
      sample.sort(function (a, b) { return a - b; });
      var lo = sample[Math.floor(sample.length * 0.02)], hi = sample[Math.floor(sample.length * 0.98)], k = 1 / (hi - lo || 1);
      var lx = -0.55, ly = -0.65, lz = 0.52, slope = k * m * 0.012;
      for (var y = 0; y < h; y++) {
        for (var x = 0; x < w; x++) {
          var i = y * w + x, t = (F[i] - lo) * k; t = t < 0 ? 0 : t > 1 ? 1 : t;
          var j = 1; while (j < stops.length - 1 && stops[j].t < t) j++;
          var a = stops[j - 1], b = stops[j], f = (t - a.t) / (b.t - a.t || 1);
          f = f < 0 ? 0 : f > 1 ? 1 : f; f = f * f * (3 - 2 * f);
          var gx = (F[x < w - 1 ? i + 1 : i] - F[x > 0 ? i - 1 : i]) * slope, gy = (F[y < h - 1 ? i + w : i] - F[y > 0 ? i - w : i]) * slope;
          var nd = (-gx * lx - gy * ly + lz) / Math.sqrt(gx * gx + gy * gy + 1);
          var spec = Math.pow(nd > 0 ? nd : 0, 24) * gloss * 255;
          var silk = 1 + 0.035 * Math.sin(t * 150 + Q[i] * 24);
          var vein = veins * Math.max(0, 1 - Math.abs(Q[i] - 0.42) * 14) * 0.6;
          var lit = (0.82 + 0.28 * nd) * silk * (1 - vein);
          pixels[i * 4] = (a.c[0] + (b.c[0] - a.c[0]) * f) * lit + spec;
          pixels[i * 4 + 1] = (a.c[1] + (b.c[1] - a.c[1]) * f) * lit + spec;
          pixels[i * 4 + 2] = (a.c[2] + (b.c[2] - a.c[2]) * f) * lit + spec;
          pixels[i * 4 + 3] = 255;
        }
      }
    }
    return {
      width: w, height: h, pixels: pixels,
      step: function (rows) {
        if (row >= gh) return true;
        var end = Math.min(gh, row + Math.max(1, rows));
        while (row < end) field(row++);
        if (row < gh) return false;
        upsample(); colorize(); return true;
      }
    };
  }

  // Uma fila para todas as pastas: poucos milissegundos por quadro.
  var fila = [], bombeando = false;
  function bombear() {
    if (bombeando) return;
    bombeando = true;
    requestAnimationFrame(function tique() {
      var ate = performance.now() + 7;
      while (fila.length && performance.now() < ate) {
        var item = fila[0];
        if (item.job.step(4)) { fila.shift(); item.pronto(); }
      }
      if (fila.length) requestAnimationFrame(tique); else bombeando = false;
    });
  }
  function pintar(canvas, arte, semente, largura, altura) {
    var receita = ARTES[arte];
    if (!receita) return;
    var densidade = Math.min(1.25, Math.max(1, window.devicePixelRatio || 1));
    var job = createArtJob((largura || 364) * densidade, (altura || 296) * densidade, receita, hashString(semente) % 997);
    fila.push({ job: job, pronto: function () {
      canvas.width = job.width; canvas.height = job.height;
      var ctx = canvas.getContext("2d");
      if (ctx) ctx.putImageData(new ImageData(job.pixels, job.width, job.height), 0, 0);
      canvas.setAttribute("data-ready", "");
    } });
    bombear();
  }

  // Reprepara os controles quando o painel troca de visão sem recarregar a página.
  var medir, pintarAoVer;
  function preparar() {
    if (medir) medir.disconnect();
    if (pintarAoVer) pintarAoVer.disconnect();
    // Dentro de uma pasta: Nota captura já ligada ao item; Ajustes escolhe capa e entrada rápida.
    var dentro = document.querySelector(".pasta-dentro");
    prepararDentro(dentro);
    var grades = document.querySelectorAll(".pastas-vidro");
    if (!grades.length) return;
    var pastas = Array.from(grades).flatMap(function (grade) { return Array.from(grade.querySelectorAll(".gf-root")); });

    var claro = getComputedStyle(document.documentElement).getPropertyValue("--modo-claro").trim() === "1";
    // A pasta é desenhada em 340 px e escalada para a coluna da grade.
    // Só a largura importa; a altura muda com a escala e não deve realimentar o observador.
    medir = new ResizeObserver(function (entradas) {
      entradas.forEach(function (e) {
        var k = (e.contentRect.width / 340).toFixed(4);
        if (e.target.dataset.k === k) return;
        e.target.dataset.k = k;
        requestAnimationFrame(function () { e.target.style.setProperty("--gf-k", k); });
      });
    });

    // Sem montagem na entrada: a pasta aparece pronta e a arte é pintada só
    // quando fica visível. O hover segue no CSS; o clique entra direto.
    pintarAoVer = "IntersectionObserver" in window ? new IntersectionObserver(function (entradas) {
      entradas.forEach(function (e) {
        if (!e.isIntersecting) return;
        pintarAoVer.unobserve(e.target);
        var canvas = e.target.querySelector("canvas.gf-art");
        if (canvas) pintar(canvas, e.target.dataset.arte, e.target.dataset.titulo);
      });
    }, { rootMargin: "200px" }) : null;

    pastas.forEach(function (pasta) {
      if (pasta.hasAttribute("data-entered")) {
        medir.observe(pasta);
        if (pintarAoVer && !pasta.querySelector("canvas[data-ready]")) pintarAoVer.observe(pasta);
        return;
      }
      pasta.dataset.tone = claro ? "light" : "dark";
      pasta.setAttribute("data-entered", "");
      medir.observe(pasta);
      if (pintarAoVer) pintarAoVer.observe(pasta);
      else { var c = pasta.querySelector("canvas.gf-art"); if (c) pintar(c, pasta.dataset.arte, pasta.dataset.titulo); }

      var mais = pasta.querySelector(".gf-key--add");
      if (mais) mais.addEventListener("click", function () {
        if (!window.Orquestra || !window.Orquestra.capturar) { location.href = pasta.querySelector(".gf-hit").href; return; }
        window.Orquestra.capturar({ vinculo: pasta.dataset.vinculo, nome: pasta.dataset.titulo, aoGuardar: function (r) { soltar(pasta, r); } });
      });
    });
  }

  // A nota recém-capturada cai dentro da pasta e a contagem gira.
  function soltar(pasta, nota) {
    var lista = pasta.querySelector(".gf-files"), slots = lista.querySelectorAll(".gf-sheet-slot");
    if (slots.length >= 4) slots[0].remove();
    var slot = document.createElement("div"), folha = document.createElement("span"), cabeca = document.createElement("span"), nome = document.createElement("span"), linhas = document.createElement("span");
    slot.className = "gf-sheet-slot";
    folha.className = "gf-sheet gf-sheet--drop";
    linhas.className = "gf-lines"; linhas.setAttribute("aria-hidden", "true"); linhas.innerHTML = "<i></i><i></i><i></i><i></i><i></i>";
    cabeca.className = "gf-sheet-head"; nome.className = "gf-sheet-name"; nome.textContent = nota.titulo || "Nova nota";
    cabeca.appendChild(nome); folha.append(linhas, cabeca); slot.appendChild(folha); lista.appendChild(slot);
    folha.addEventListener("animationend", function () { folha.classList.remove("gf-sheet--drop"); }, { once: true });
    var folhas = lista.querySelectorAll(".gf-sheet"), n = folhas.length;
    folhas.forEach(function (f, i) {
      f.style.setProperty("--gf-slot", n > 1 ? String((i / (n - 1)) * 2 - 1) : "0");
      f.style.setProperty("--gf-depth", String(n - 1 - i));
      if (!f.style.getPropertyValue("--gf-jx")) { f.style.setProperty("--gf-jx", ((i * 37 % 10) - 5) + "px"); f.style.setProperty("--gf-jr", ((i * 53 % 32) / 10 - 1.6).toFixed(1) + "deg"); }
      f.style.zIndex = String(i + 1);
    });
    var total = parseInt(pasta.dataset.total, 10) + 1, contador = pasta.querySelector("[data-gf-total]"), novo = contador.cloneNode();
    pasta.dataset.total = String(total); novo.textContent = String(total); novo.classList.add("gf-rola"); contador.replaceWith(novo);
    var frente = pasta.querySelector(".gf-front");
    frente.classList.remove("gf-front--bump"); void frente.offsetWidth; frente.classList.add("gf-front--bump");
    var glifo = pasta.querySelector(".gf-glyph");
    if (glifo) { glifo.classList.remove("gf-glyph--gira"); void glifo.getBoundingClientRect(); glifo.classList.add("gf-glyph--gira"); }
  }


  var preparadas = new WeakSet();
  function prepararDentro(secao) {
    var nova = document.querySelector("[data-pasta-nova]");
    if (nova && secao && !preparadas.has(nova)) {
      preparadas.add(nova);
      nova.addEventListener("click", function () {
        if (!window.Orquestra || !window.Orquestra.capturar) return;
        window.Orquestra.capturar({ vinculo: secao.dataset.vinculo, pasta: secao.dataset.diretorio, nome: secao.dataset.titulo, aoGuardar: function () { location.reload(); } });
      });
    }
    var abrir = document.querySelector("[data-pasta-ajustes]");
    if (!abrir || preparadas.has(abrir)) return;
    var dialogo = document.getElementById("pasta-ajustes");
    if (!dialogo) return;
    preparadas.add(abrir);
    var estado = document.getElementById("pasta-ajustes-estado"), arquivo = document.getElementById("pasta-ajustes-arquivo");
    var imagem = document.getElementById("pasta-ajustes-imagem"), rapida = document.getElementById("pasta-ajustes-rapida");
    var salvar = document.getElementById("pasta-ajustes-salvar"), form = dialogo.querySelector("form");
    var capas = dialogo.querySelector("#pasta-ajustes-capas"), trocar = dialogo.querySelector("#pasta-ajustes-trocar-imagem");
    var principal = dialogo.querySelector("#pasta-ajustes-principal"), abrirCapas = dialogo.querySelector("[data-abrir-capas]");
    var opcaoImagem = dialogo.querySelector('input[value="imagem"]'), quadroImagem = dialogo.querySelector(".pasta-capa-imagem");
    var cor = document.getElementById("pasta-cor"), cores = dialogo.querySelector(".pasta-cores");
    var opcaoCor = dialogo.querySelector('input[value="cor"]'), previaCor = dialogo.querySelector("[data-previa-cor]");
    var imagemInicial = imagem && imagem.value, fundoInicial = quadroImagem && quadroImagem.style.backgroundImage;
    var previasProntas = false;
    function refletirCapa() {
      var selecionada = capas.querySelector('input[name="capa"]:checked');
      cores.hidden = !opcaoCor.checked;
      trocar.hidden = !opcaoImagem.checked || !imagem.value;
      abrirCapas.querySelector("[data-capa-rotulo]").textContent = selecionada.closest("label").lastElementChild.textContent;
      previaCor.style.background = cor.value;
      cor.parentElement.style.setProperty("--c", cor.value);
      dialogo.querySelectorAll("[data-pasta-cor]").forEach(function (b) { b.setAttribute("aria-checked", String(opcaoCor.checked && b.dataset.pastaCor === cor.value)); });
    }
    function mostrarCapas(ativa, animar) {
      if (!capas) return;
      principal.hidden = ativa;
      capas.hidden = !ativa;
      dialogo.dataset.tela = animar ? (ativa ? "capas" : "ajustes") : "";
      var titulo = ativa ? "pasta-ajustes-capas-titulo" : "pasta-ajustes-titulo";
      dialogo.setAttribute("aria-labelledby", titulo);
      if (animar) (ativa ? document.getElementById(titulo) : abrirCapas).focus({ preventScroll: true });
      dialogo.scrollTop = 0;
      if (ativa && !previasProntas) {
        previasProntas = true;
        capas.querySelectorAll("canvas[data-arte-previa]").forEach(function (c) { pintar(c, c.dataset.artePrevia, "previa", 180, 120); });
      }
    }
    function escolherCapa() {
      if (opcaoImagem.checked && !imagem.value) { arquivo.click(); return; }
      mostrarCapas(false, true);
    }
    function atualizarCor() {
      opcaoCor.checked = true;
      refletirCapa();
    }
    if (cor) {
      cor.addEventListener("input", atualizarCor);
      dialogo.querySelectorAll("[data-pasta-cor]").forEach(function (b) {
        b.addEventListener("click", function () { cor.value = b.dataset.pastaCor; atualizarCor(); });
      });
      form.addEventListener("change", function (e) {
        if (e.target.name === "capa") refletirCapa();
      });
      abrirCapas.addEventListener("click", function () { mostrarCapas(true, true); });
      capas.querySelector("[data-voltar-capas]").addEventListener("click", function () { mostrarCapas(false, true); });
      capas.querySelector("[data-usar-capa]").addEventListener("click", escolherCapa);
    }
    abrir.addEventListener("click", function () {
      form.reset();
      if (capas) {
        imagem.value = imagemInicial;
        quadroImagem.style.backgroundImage = fundoInicial;
        refletirCapa();
        mostrarCapas(false, false);
      }
      estado.textContent = "";
      dialogo.showModal();
    });
    dialogo.querySelectorAll("[data-fechar]").forEach(function (b) { b.addEventListener("click", function () { dialogo.close(); }); });
    dialogo.querySelectorAll("[data-acao-pasta]").forEach(function (botao) {
      botao.addEventListener("click", async function () {
        var acao = botao.dataset.acaoPasta, excluir = acao === "excluir";
        if (salvar.disabled || botao.disabled) return;
        var confirmacao = await window.OrquestraInterface.confirmar({
          titulo: excluir ? "Mover esta pasta para a lixeira?" : "Arquivar esta pasta?",
          texto: dialogo.dataset.tipoAcao === "diretorio"
            ? "A pasta inteira, com notas, subpastas e anexos, será movida " + (excluir ? "para a lixeira." : "para Arquivo nesta área.")
            : "A nota principal e as notas exclusivas " + (excluir ? "irão para a lixeira." : "irão para Arquivo nesta área.") + " Anexos e notas compartilhadas ficam onde estão.",
          confirmar: excluir ? "Mover para a lixeira" : "Arquivar pasta", perigoso: excluir
        });
        if (!confirmacao) return;
        var botoes = Array.from(dialogo.querySelectorAll("[data-acao-pasta], #pasta-ajustes-salvar"));
        botoes.forEach(function (b) { b.disabled = true; });
        estado.textContent = excluir ? "Movendo para a lixeira…" : "Arquivando…";
        try {
          var resultado = await window.Orquestra.api("POST", "/api/modulos/" + encodeURIComponent(dialogo.dataset.modulo) + "/pastas/acao",
            { chave: dialogo.dataset.chaveAcao, acao: acao, versao: dialogo.dataset.versao });
          if (resultado.parcial) {
            estado.textContent = resultado.movidas + " nota(s) movida(s). Reabra a pasta para conferir o restante.";
          } else location.replace(dialogo.dataset.voltar);
        } catch (erro) { estado.textContent = erro.message; botoes.forEach(function (b) { b.disabled = false; }); }
      });
    });
    // Escolher "Imagem própria" sem imagem enviada abre o seletor de arquivo.
    if (opcaoImagem) {
      trocar.addEventListener("click", function () { arquivo.click(); });
      opcaoImagem.addEventListener("change", function () { if (!imagem.value) arquivo.click(); });
      arquivo.addEventListener("change", async function () {
        var f = arquivo.files[0]; if (!f) return;
        if (!/^image[/](png|jpeg|webp)$/.test(f.type) || f.size > 2 * 1024 * 1024) { estado.textContent = "Use uma imagem PNG, JPEG ou WebP de até 2 MB."; arquivo.value = ""; return; }
        estado.textContent = "Enviando imagem…"; salvar.disabled = true;
        try {
          var cap = await fetch("/api/local/capacidade", { cache: "no-store" });
          if (!cap.ok) throw new Error("Envie imagens pelo localhost deste computador.");
          var token = (await cap.json()).token;
          var r = await fetch("/api/capas", { method: "POST", body: f, headers: { "Content-Type": "application/octet-stream", "X-Orquestra-Vault": document.body.dataset.vaultId || "", "X-Orquestra-Local": token } });
          var dados = await r.json(); if (!r.ok) throw new Error(dados.erro || "Não foi possível enviar a imagem.");
          imagem.value = dados.caminho; opcaoImagem.checked = true;
          refletirCapa();
          quadroImagem.style.backgroundImage = "url('/arquivo/" + dados.caminho.split("/").map(encodeURIComponent).join("/") + "')";
          estado.textContent = "Imagem pronta. Salve para aplicar.";
        } catch (erro) { estado.textContent = erro.message; }
        finally { salvar.disabled = false; arquivo.value = ""; }
      });
    }
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (salvar.disabled) return;
      if (capas && !capas.hidden) { escolherCapa(); return; }
      var escolha = (dialogo.querySelector('input[name="capa"]:checked') || {}).value || "";
      if (escolha === "imagem" && !imagem.value) { mostrarCapas(true, true); arquivo.click(); return; }
      var corpo = { chave: dialogo.dataset.chave, titulo: document.getElementById("pasta-ajustes-nome").value.trim(), entrada_rapida: !!(rapida && rapida.checked), subpastas: window.Orquestra.estiloEscolhido(form.querySelector("#pasta-ajustes-subpastas")) };
      if (escolha === "imagem") corpo.imagem = imagem.value;
      else if (escolha === "cor") corpo.cor = cor.value;
      else if (escolha.indexOf("arte:") === 0) corpo.arte = escolha.slice(5);
      salvar.disabled = true; estado.textContent = "Salvando…";
      try {
        await window.Orquestra.api("POST", "/api/modulos/" + encodeURIComponent(dialogo.dataset.modulo) + "/pastas", corpo);
        location.reload();
      } catch (erro) { estado.textContent = erro.message; salvar.disabled = false; }
    });
  }
  window.Orquestra = window.Orquestra || {};
  window.Orquestra.prepararPastasModulo = preparar;
  preparar();
})();
