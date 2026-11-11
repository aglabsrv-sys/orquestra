/* Cenas: as capas em pixel art do painel, desenhadas por código.

   Cada capa é um <canvas> pequeno (320x180) ampliado sem suavização, o que dá o
   aspecto de pixel art. Nada aqui é imagem pronta: cada cena é uma função que
   desenha com as cores da paleta do tema, então trocar o tema recolore tudo.

   Para criar uma cena nova: escreva uma função em CENAS que recebe (paleta, R),
   prepara as camadas fixas uma vez e devolve `function (g, t)` que desenha um
   quadro no instante t (em segundos). R é um gerador de números aleatórios com
   semente, para a cena sair sempre igual para o mesmo módulo.

   Papéis das cores da paleta:
     ceu[4]   do alto até o horizonte      astro   sol ou lua
     nuvem    nuvens e névoa               longe / meio / perto   planos de profundidade
     sombra   o tom mais escuro            luz     janelas e pontos de luz
     brilho   estrelas e reflexos          noite   true desenha mais estrelas
*/
(function () {
  "use strict";

  var W = 320, H = 180, QPS = 12;
  var BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
  var PADRAO = {
    ceu: ["#2b1a3a", "#7a2e4a", "#d9603f", "#f7b267"], astro: "#ffe3a3", nuvem: "#f29a6b",
    longe: "#8a3f4d", meio: "#5a2a3c", perto: "#33182a", sombra: "#1a0d18",
    luz: "#ffd27a", brilho: "#fff3d1", noite: false
  };

  // ---------------------------------------------------------------- utilidades

  function gerador(semente) { // mulberry32: aleatório com semente
    var a = semente >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function rgb(cor) {
    var h = String(cor || "#000").replace("#", "");
    if (h.length === 3) h = h.replace(/./g, "$&$&");
    var n = parseInt(h.slice(0, 6), 16) || 0;
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function mix(a, b, t) {
    var A = rgb(a), B = rgb(b), s = "#";
    for (var i = 0; i < 3; i++) {
      var v = Math.max(0, Math.min(255, Math.round(A[i] + (B[i] - A[i]) * t)));
      s += (v < 16 ? "0" : "") + v.toString(16);
    }
    return s;
  }
  function limiar(x, y) { return (BAYER[(y & 3) * 4 + (x & 3)] + 0.5) / 16; }
  function inteiro(R, a, b) { return a + Math.floor(R() * (b - a + 1)); }
  function camada(desenhar, w, h) {
    var c = document.createElement("canvas");
    c.width = w || W; c.height = h || H;
    desenhar(c.getContext("2d"));
    return c;
  }

  // Degradê vertical em faixas, com transição pontilhada (dithering) entre elas.
  function degrade(g, cores, x0, y0, w, h) {
    var C = cores.map(rgb), n = C.length - 1;
    var img = g.createImageData(w, h), d = img.data;
    for (var y = 0; y < h; y++) {
      var t = h > 1 ? (y / (h - 1)) * n : 0;
      var i = Math.min(n - 1, Math.floor(t));
      var f = Math.max(0, Math.min(1, (t - i - 0.28) / 0.44)); // meio de cada faixa fica chapado
      for (var x = 0; x < w; x++) {
        var c = f > limiar(x + x0, y + y0) ? C[i + 1] : C[i], p = (y * w + x) * 4;
        d[p] = c[0]; d[p + 1] = c[1]; d[p + 2] = c[2]; d[p + 3] = 255;
      }
    }
    g.putImageData(img, x0, y0);
  }
  function disco(g, cx, cy, r, cor) {
    g.fillStyle = cor;
    for (var y = -r; y <= r; y++) {
      var w = Math.floor(Math.sqrt(r * r - y * y));
      g.fillRect(cx - w, cy + y, w * 2 + 1, 1);
    }
  }
  function pontilhado(g, cx, cy, r, cor, densidade) { // disco "transparente" em pixel art
    g.fillStyle = cor;
    for (var y = -r; y <= r; y++)
      for (var x = -r; x <= r; x++)
        if (x * x + y * y <= r * r && limiar(cx + x, cy + y) < densidade) g.fillRect(cx + x, cy + y, 1, 1);
  }
  function halo(g, cx, cy, r, cor) {
    pontilhado(g, cx, cy, r + 15, cor, 0.16);
    pontilhado(g, cx, cy, r + 9, cor, 0.36);
    pontilhado(g, cx, cy, r + 4, cor, 0.66);
  }

  function estrelas(R, n, yMax) {
    var s = [];
    for (var i = 0; i < n; i++) s.push({ x: inteiro(R, 0, W - 1), y: inteiro(R, 0, yMax), f: R() * 6.28, v: 0.5 + R() * 2, g: R() < 0.12 });
    return s;
  }
  function desenharEstrelas(g, s, t, cor, dx) {
    g.fillStyle = cor;
    for (var i = 0; i < s.length; i++) {
      var e = s[i], b = Math.sin(t * e.v + e.f);
      if (b < -0.55) continue;
      var x = dx ? (((e.x - dx * (e.g ? 2 : 1)) % W) + W) % W | 0 : e.x;
      g.fillRect(x, e.y, 1, 1);
      if (e.g && b > 0.45) { g.fillRect(x - 1, e.y, 3, 1); g.fillRect(x, e.y - 1, 1, 3); }
    }
  }

  function fazerNuvem(R, cor, sombra) {
    var w = inteiro(R, 26, 68), h = inteiro(R, 9, 15);
    return camada(function (g) {
      // Vários "gomos" lado a lado, maiores no meio, formam o corpo da nuvem.
      var n = 3 + Math.floor(w / 11), esq = w, dir = 0;
      for (var i = 0; i < n; i++) {
        var cx = Math.round(((i + 0.5) / n) * (w - 10)) + 5 + inteiro(R, -2, 2);
        var meio = 1 - Math.abs((i + 0.5) / n - 0.5) * 1.5;
        var r = Math.max(2, Math.min(Math.floor(h / 2), Math.round(2 + meio * (h / 2) * (0.6 + R() * 0.5))));
        cx = Math.max(r, Math.min(w - r - 1, cx));
        disco(g, cx, h - r, r, cor);
        esq = Math.min(esq, cx - r); dir = Math.max(dir, cx + r);
      }
      g.fillStyle = cor;
      g.fillRect(esq + 2, h - 3, Math.max(0, dir - esq - 3), 3);
      g.clearRect(0, h, w, 4); // base reta
      g.globalCompositeOperation = "source-atop";
      g.fillStyle = sombra;
      g.fillRect(0, h - 2, w, 2);
      for (var x = 0; x < w; x++) if (limiar(x, 1) < 0.5) g.fillRect(x, h - 3, 1, 1);
    }, w, h + 2);
  }
  function nuvens(R, n, yMin, yMax, cor, sombra, vMin, vMax) {
    var lista = [];
    for (var i = 0; i < n; i++)
      lista.push({ sp: fazerNuvem(R, cor, sombra), x: R() * (W + 80), y: inteiro(R, yMin, yMax), v: vMin + R() * (vMax - vMin) });
    return lista;
  }
  function desenharNuvens(g, lista, t) {
    for (var i = 0; i < lista.length; i++) {
      var n = lista[i], larg = W + n.sp.width;
      var x = ((((n.x + t * n.v) % larg) + larg) % larg) - n.sp.width;
      g.drawImage(n.sp, Math.round(x), n.y);
    }
  }

  // Perfil de serra: soma de ruídos com interpolação linear (picos angulosos).
  function relevo(R, base, amp, rug) {
    var oitavas = [], a = new Float32Array(W + 2);
    for (var k = 0; k < 5; k++) {
      var passo = 80 >> k, pts = [];
      for (var i = 0; i <= Math.ceil(W / passo) + 2; i++) pts.push(R() * 2 - 1);
      oitavas.push({ passo: passo, pts: pts, peso: Math.pow(rug, k) });
    }
    for (var x = 0; x < W + 2; x++) {
      var v = 0, soma = 0;
      for (var o = 0; o < oitavas.length; o++) {
        var q = oitavas[o], j = Math.floor(x / q.passo), f = x / q.passo - j;
        v += (q.pts[j] + (q.pts[j + 1] - q.pts[j]) * f) * q.peso; soma += q.peso;
      }
      a[x] = base - (v / soma) * amp;
    }
    return a;
  }
  function serra(g, a, cor, corLuz, dir, prof) {
    var x, y;
    g.fillStyle = cor;
    for (x = 0; x < W; x++) { y = Math.round(a[x]); g.fillRect(x, y, 1, H - y); }
    g.fillStyle = corLuz; // encostas viradas para o astro recebem luz
    for (x = 0; x < W; x++) {
      y = Math.round(a[x]);
      if (Math.round(a[Math.max(0, Math.min(W, x + dir))]) > y)
        for (var k = 0; k < prof + 3; k++) if (limiar(x, y + k) > k / (prof + 3)) g.fillRect(x, y + k, 1, 1);
    }
  }
  function pinheiro(g, x, base, h, cor) {
    g.fillStyle = cor;
    var tronco = Math.max(1, Math.round(h * 0.12)), copa = h - tronco, largura = Math.max(2, Math.round(h * 0.2));
    g.fillRect(x, base - tronco, h > 30 ? 2 : 1, tronco);
    for (var i = 0; i < copa; i++) {
      var w = Math.round((1 - i / copa) * largura), dente = i % 5;
      w += dente < 2 ? 1 : dente === 4 ? -1 : 0;
      g.fillRect(x - Math.max(0, w), base - tronco - 1 - i, Math.max(0, w) * 2 + 1, 1);
    }
  }
  function nevoa(g, t, y, altura, cor, v) { // faixa de névoa que desliza
    g.fillStyle = cor;
    for (var yy = 0; yy < altura; yy++) {
      var dens = (1 - Math.abs(yy - altura / 2) / (altura / 2)) * 0.62;
      for (var x = 0; x < W; x++) {
        var onda = 0.5 + 0.5 * Math.sin((x + t * v) * 0.045 + yy * 0.35) * Math.sin((x - t * v * 0.6) * 0.014 + 1.3);
        if (limiar(x, y + yy) < dens * onda) g.fillRect(x, y + yy, 1, 1);
      }
    }
  }
  function passaros(R, n, yMin, yMax) {
    var p = [];
    for (var i = 0; i < n; i++) p.push({ x: R() * W, y: inteiro(R, yMin, yMax), v: 3 + R() * 4, f: R() * 6 });
    return p;
  }
  function desenharPassaros(g, p, t, cor) {
    g.fillStyle = cor;
    for (var i = 0; i < p.length; i++) {
      var b = p[i], x = Math.round((((b.x + t * b.v) % (W + 20)) + W + 20) % (W + 20)) - 10;
      var y = b.y + Math.round(Math.sin(t * 0.7 + b.f) * 2), asa = Math.sin(t * 5 + b.f) > 0 ? -1 : 0;
      g.fillRect(x - 2, y + asa, 2, 1); g.fillRect(x, y + 1, 1, 1); g.fillRect(x + 1, y + asa, 2, 1);
    }
  }

  var CENAS = {};

  // ---------------------------------------------------------------- montanhas

  CENAS.montanhas = function (pal, R) {
    var chao = pal.ceu[pal.ceu.length - 1];
    var sol = { x: inteiro(R, 70, 250), y: inteiro(R, 78, 92), r: 13 };
    var dir = sol.x > W / 2 ? 1 : -1;
    var ceu = camada(function (g) {
      degrade(g, pal.ceu, 0, 0, W, 140);
      g.fillStyle = chao; g.fillRect(0, 140, W, 40);
      halo(g, sol.x, sol.y, sol.r, mix(pal.astro, chao, 0.3));
      disco(g, sol.x, sol.y, sol.r, pal.astro);
    });
    var est = estrelas(R, pal.noite ? 70 : 16, pal.noite ? 70 : 40);
    var nv = nuvens(R, 4, 14, 64, mix(pal.nuvem, pal.brilho, 0.3), pal.nuvem, 1.1, 2.6);
    var s1 = camada(function (g) { serra(g, relevo(R, 106, 34, 0.55), pal.longe, mix(pal.longe, pal.astro, 0.4), dir, 3); });
    var s2 = camada(function (g) { serra(g, relevo(R, 130, 28, 0.6), pal.meio, mix(pal.meio, pal.astro, 0.25), dir, 2); });
    var s3 = camada(function (g) {
      var a = relevo(R, 156, 18, 0.5);
      serra(g, a, pal.perto, mix(pal.perto, pal.astro, 0.14), dir, 1);
      for (var i = 0; i < 30; i++) { var x = inteiro(R, 2, W - 3); pinheiro(g, x, Math.round(a[x]) + 2, inteiro(R, 6, 15), pal.sombra); }
      var frente = relevo(R, 174, 5, 0.4);
      g.fillStyle = pal.sombra;
      for (var k = 0; k < W; k++) g.fillRect(k, Math.round(frente[k]), 1, H);
    });
    var aves = passaros(R, 3, 40, 70), corNevoa = mix(pal.nuvem, chao, 0.5);
    return function (g, t) {
      g.drawImage(ceu, 0, 0);
      desenharEstrelas(g, est, t, pal.brilho);
      desenharNuvens(g, nv, t);
      g.drawImage(s1, 0, 0);
      nevoa(g, t, 112, 13, corNevoa, 5);
      g.drawImage(s2, 0, 0);
      nevoa(g, t, 139, 11, corNevoa, -7);
      g.drawImage(s3, 0, 0);
      desenharPassaros(g, aves, t, pal.sombra);
    };
  };

  // ---------------------------------------------------------------- cidade

  CENAS.cidade = function (pal, R) {
    var chao = 166;
    var lua = { x: inteiro(R, 50, 270), y: inteiro(R, 34, 56), r: 17 };
    var ceu = camada(function (g) {
      degrade(g, pal.ceu, 0, 0, W, chao);
      halo(g, lua.x, lua.y, lua.r, mix(pal.astro, pal.ceu[1], 0.45));
      disco(g, lua.x, lua.y, lua.r, pal.astro);
      var cratera = mix(pal.astro, pal.ceu[1], 0.22);
      disco(g, lua.x - 6, lua.y - 4, 3, cratera); disco(g, lua.x + 5, lua.y + 6, 4, cratera); disco(g, lua.x + 7, lua.y - 7, 2, cratera);
    });
    var est = estrelas(R, pal.noite ? 80 : 26, 90);
    var nv = nuvens(R, 3, 18, 84, mix(pal.nuvem, pal.ceu[1], 0.35), mix(pal.nuvem, pal.ceu[0], 0.6), 0.8, 1.8);

    function fileira(largMin, largMax, altMin, altMax) {
      var lista = [], x = -inteiro(R, 0, 8);
      while (x < W) {
        var w = inteiro(R, largMin, largMax);
        lista.push({ x: x, w: w, h: inteiro(R, altMin, altMax), topo: R() });
        x += w + (R() < 0.25 ? inteiro(R, 1, 4) : 0);
      }
      return lista;
    }
    var fundo = camada(function (g) {
      var luzFraca = mix(pal.luz, pal.longe, 0.5);
      fileira(9, 22, 30, 78).forEach(function (p) {
        g.fillStyle = pal.longe; g.fillRect(p.x, chao - p.h, p.w, p.h);
        g.fillStyle = luzFraca;
        for (var y = chao - p.h + 3; y < chao - 3; y += 4)
          for (var x = p.x + 2; x < p.x + p.w - 2; x += 3) if (R() < 0.24) g.fillRect(x, y, 1, 2);
      });
    });
    var janelas = [], antenas = [];
    var frente = camada(function (g) {
      var apagada = mix(pal.perto, pal.luz, 0.1);
      fileira(15, 34, 38, 112).forEach(function (p) {
        var y0 = chao - p.h;
        g.fillStyle = pal.perto; g.fillRect(p.x, y0, p.w, p.h);
        if (p.topo < 0.35 && p.w > 18) { g.fillRect(p.x + 4, y0 - 6, p.w - 8, 6); y0 -= 6; }   // topo em degrau
        else if (p.topo < 0.5) { g.fillRect(p.x + 3, y0 - 5, 6, 5); g.fillRect(p.x + 2, y0 - 6, 8, 1); } // caixa d'água
        if (p.h > 78) { g.fillRect(p.x + (p.w >> 1), y0 - 10, 1, 10); antenas.push({ x: p.x + (p.w >> 1), y: y0 - 11, f: R() * 6 }); }
        g.fillStyle = mix(pal.perto, pal.astro, 0.16); g.fillRect(p.x, chao - p.h, 1, p.h); // aresta iluminada
        g.fillStyle = apagada;
        for (var y = chao - p.h + 5; y < chao - 5; y += 6)
          for (var x = p.x + 3; x < p.x + p.w - 3; x += 4) {
            g.fillRect(x, y, 2, 3);
            if (R() < 0.38) janelas.push({ x: x, y: y, per: 5 + R() * 22, f: R() * 6.28, quente: R() < 0.2 });
          }
      });
      g.fillStyle = pal.sombra; g.fillRect(0, chao, W, H - chao);
      g.fillStyle = mix(pal.sombra, pal.luz, 0.25); // faixa da rua
      for (var k = 0; k < W; k += 9) g.fillRect(k, chao + 8, 4, 1);
      for (var p2 = 12; p2 < W; p2 += 44) { // postes
        g.fillStyle = pal.perto; g.fillRect(p2, chao - 7, 1, 7);
        pontilhado(g, p2, chao - 8, 5, pal.luz, 0.25);
        g.fillStyle = pal.brilho; g.fillRect(p2 - 1, chao - 8, 3, 1);
      }
    });
    var luzQuente = mix(pal.luz, pal.brilho, 0.45), vermelho = mix(pal.luz, "#ff3b30", 0.75);
    return function (g, t) {
      g.drawImage(ceu, 0, 0);
      desenharEstrelas(g, est, t, pal.brilho);
      var ax = ((t * 7) % (W + 240)) - 60; // avião distante
      if (ax < W + 4) { g.fillStyle = pal.brilho; g.fillRect(ax | 0, 26 - ((ax * 0.03) | 0), 2, 1); if ((t * 2 | 0) % 2) { g.fillStyle = vermelho; g.fillRect((ax | 0) - 1, 26 - ((ax * 0.03) | 0), 1, 1); } }
      desenharNuvens(g, nv, t);
      g.drawImage(fundo, 0, 0);
      g.drawImage(frente, 0, 0);
      for (var i = 0; i < janelas.length; i++) {
        var j = janelas[i];
        if (Math.sin(t / j.per + j.f) < -0.9) continue; // de vez em quando alguém apaga a luz
        g.fillStyle = j.quente ? luzQuente : pal.luz; g.fillRect(j.x, j.y, 2, 3);
      }
      g.fillStyle = vermelho;
      for (var a = 0; a < antenas.length; a++) if (Math.sin(t * 2.4 + antenas[a].f) > 0.2) g.fillRect(antenas[a].x, antenas[a].y, 1, 1);
      var cx = ((t * 22) % (W + 80)) - 40, vx = W + 40 - ((t * 17 + 90) % (W + 120)); // carros
      g.fillStyle = pal.brilho; g.fillRect(cx | 0, chao + 5, 2, 1);
      g.fillStyle = vermelho; g.fillRect(vx | 0, chao + 11, 2, 1);
    };
  };

  // ---------------------------------------------------------------- janela (estúdio)

  CENAS.janela = function (pal, R) {
    var X0 = 64, Y0 = 18, LW = 192, LH = 104, PE = Y0 + LH; // vão da janela e o peitoril
    var parede = mix(pal.sombra, pal.perto, 0.55), moldura = mix(pal.sombra, pal.perto, 0.25);
    var solX = X0 + inteiro(R, 110, 160), horizonte = pal.ceu[pal.ceu.length - 1];

    var fora = camada(function (g) {
      degrade(g, pal.ceu, X0, Y0, LW, LH);
      halo(g, solX, PE - 32, 11, mix(pal.astro, horizonte, 0.3));
      disco(g, solX, PE - 32, 11, pal.astro);
    });
    var nv = nuvens(R, 4, Y0 + 6, Y0 + 52, mix(pal.nuvem, pal.brilho, 0.3), pal.nuvem, 1.4, 3);
    var est = pal.noite ? estrelas(R, 50, 70) : [];

    var telaX = 193, telaY = 103, telaW = 48, telaH = 27;
    var sala = camada(function (g) {
      var x, y, i;
      degrade(g, [pal.sombra, parede, parede], 0, 0, W, H);
      // claridade da janela na parede
      g.fillStyle = mix(parede, pal.nuvem, 0.3);
      for (y = Y0 - 12; y < PE + 12; y++)
        for (x = X0 - 12; x < X0 + LW + 12; x++) {
          var d = Math.max(X0 - x, x - (X0 + LW - 1), Y0 - y, y - (PE - 1));
          if (d > 0 && limiar(x, y) < (1 - d / 12) * 0.5) g.fillRect(x, y, 1, 1);
        }
      g.clearRect(X0, Y0, LW, LH);
      // prédios lá fora, na base do vão
      x = X0;
      while (x < X0 + LW) { var w = inteiro(R, 7, 18), h = inteiro(R, 8, 30); g.fillStyle = pal.longe; g.fillRect(x, PE - h, Math.min(w, X0 + LW - x), h); x += w; }
      x = X0;
      while (x < X0 + LW) {
        var w2 = inteiro(R, 10, 24), h2 = inteiro(R, 4, 17), lim = Math.min(w2, X0 + LW - x);
        g.fillStyle = pal.meio; g.fillRect(x, PE - h2, lim, h2);
        g.fillStyle = pal.luz;
        for (i = 0; i < 3; i++) if (R() < 0.5 && h2 > 7 && lim > 6) g.fillRect(x + inteiro(R, 2, lim - 3), PE - h2 + inteiro(R, 2, h2 - 4), 1, 2);
        x += w2;
      }
      // moldura e travessas
      g.fillStyle = moldura;
      g.fillRect(X0 - 3, Y0 - 3, LW + 6, 3); g.fillRect(X0 - 3, Y0, 3, LH); g.fillRect(X0 + LW, Y0, 3, LH);
      g.fillRect(X0 + 63, Y0, 2, LH); g.fillRect(X0 + 127, Y0, 2, LH); g.fillRect(X0, Y0 + 42, LW, 2);
      g.fillStyle = mix(moldura, pal.nuvem, 0.4);
      g.fillRect(X0 - 3, Y0 - 3, LW + 6, 1); g.fillRect(X0 - 3, Y0 - 3, 1, LH + 3);
      g.fillStyle = mix(pal.perto, pal.nuvem, 0.35); g.fillRect(X0 - 7, PE, LW + 14, 4); // peitoril
      g.fillStyle = pal.sombra; g.fillRect(X0 - 5, PE + 4, LW + 10, 1);

      // estante com livros (parede esquerda)
      g.fillStyle = mix(pal.perto, pal.nuvem, 0.2); g.fillRect(6, 62, 46, 2);
      var lombadas = [pal.longe, pal.meio, mix(pal.astro, pal.sombra, 0.45), mix(pal.nuvem, pal.sombra, 0.4), pal.perto];
      for (x = 9; x < 44;) { var lw = inteiro(R, 2, 4), lh = inteiro(R, 8, 13); g.fillStyle = lombadas[inteiro(R, 0, 4)]; g.fillRect(x, 62 - lh, lw, lh); x += lw + (R() < 0.2 ? 2 : 0); }
      g.fillStyle = mix(pal.perto, pal.nuvem, 0.2); g.fillRect(10, 96, 38, 2);
      g.fillStyle = mix(pal.meio, pal.nuvem, 0.3); g.fillRect(16, 89, 7, 7);          // vaso
      g.fillStyle = mix(pal.sombra, pal.meio, 0.6);
      for (i = 0; i < 6; i++) g.fillRect(15 + i * 2 - (i % 2), 84 - (i % 3) * 2, 2, 6); // folhas
      g.fillStyle = mix(pal.astro, pal.sombra, 0.4); g.fillRect(32, 88, 10, 8);
      g.fillStyle = pal.sombra; g.fillRect(34, 90, 6, 4);                              // porta-retrato
      // quadro (parede direita)
      g.fillStyle = mix(pal.perto, pal.nuvem, 0.25); g.fillRect(272, 46, 34, 44);
      degrade(g, [pal.ceu[1], pal.ceu[2], pal.ceu[3]], 274, 48, 30, 40);
      g.fillStyle = pal.perto;
      for (x = 0; x < 30; x++) { var mh = 8 + Math.round(Math.abs(Math.sin(x * 0.28)) * 9 + Math.sin(x * 0.9) * 2); g.fillRect(274 + x, 88 - mh, 1, mh); }
      disco(g, 296, 58, 3, pal.astro);

      // vaso no peitoril
      g.fillStyle = mix(pal.longe, pal.sombra, 0.35); g.fillRect(77, PE - 8, 9, 8); g.fillRect(76, PE - 9, 11, 2);
      g.fillStyle = mix(pal.sombra, pal.meio, 0.45);
      [[-5, 9], [-3, 13], [-1, 17], [1, 15], [3, 11], [5, 8]].forEach(function (f) { for (var k = 0; k < f[1]; k++) g.fillRect(81 + Math.round(f[0] * (0.3 + k / f[1])), PE - 10 - k, 2, 1); });

      // gato no peitoril, olhando para fora
      g.fillStyle = pal.sombra;
      for (y = 0; y < 11; y++) { var gw = y < 2 ? 5 : y < 4 ? 7 : 8; g.fillRect(128 - gw, PE - 11 + y, gw * 2, 1); }
      disco(g, 136, PE - 14, 4, pal.sombra);
      g.fillRect(132, PE - 20, 2, 3); g.fillRect(138, PE - 20, 2, 3);

      // mesa
      var tampo = mix(pal.perto, pal.meio, 0.55);
      g.fillStyle = tampo; g.fillRect(28, 140, 264, 5);
      g.fillStyle = mix(tampo, pal.nuvem, 0.35); g.fillRect(28, 140, 264, 1);
      g.fillStyle = mix(pal.sombra, pal.perto, 0.4);
      g.fillRect(36, 145, 4, 35); g.fillRect(280, 145, 4, 35); g.fillRect(232, 145, 48, 26);
      g.fillStyle = tampo; g.fillRect(250, 156, 12, 2);
      g.fillStyle = pal.sombra; g.fillRect(0, 174, W, 6); // rodapé
      // cadeira (de costas)
      g.fillStyle = mix(pal.sombra, pal.perto, 0.2);
      g.fillRect(118, 150, 40, 30); g.fillRect(122, 146, 32, 5); g.fillRect(136, 176, 4, 4);

      // luminária de mesa
      g.fillStyle = pal.sombra; g.fillRect(50, 137, 13, 3); g.fillRect(56, 113, 1, 24);
      for (i = 0; i < 9; i++) g.fillRect(56 + i, 113 - i, 1, 2);
      g.fillStyle = mix(pal.luz, pal.sombra, 0.25);
      for (i = 0; i < 6; i++) g.fillRect(63 - i, 102 + i, 8 + i * 2, 1);
      g.fillStyle = pal.brilho; g.fillRect(64, 108, 6, 1);
      g.fillStyle = pal.luz;
      for (y = 109; y < 140; y++) { var mw = 4 + Math.round((y - 109) * 0.55); for (x = 67 - mw; x <= 67 + mw; x++) if (limiar(x, y) < 0.3 * (1 - (y - 109) / 36)) g.fillRect(x, y, 1, 1); }
      // livros, caneca, teclado
      g.fillStyle = pal.longe; g.fillRect(86, 136, 20, 4);
      g.fillStyle = mix(pal.astro, pal.sombra, 0.4); g.fillRect(88, 133, 16, 3);
      g.fillStyle = pal.meio; g.fillRect(87, 130, 18, 3);
      g.fillStyle = mix(pal.nuvem, pal.sombra, 0.25); g.fillRect(162, 133, 6, 7); g.fillRect(168, 135, 2, 3);
      g.fillStyle = mix(pal.sombra, pal.perto, 0.2); g.fillRect(184, 137, 28, 3);
      // monitor (a tela é desenhada a cada quadro)
      g.fillStyle = pal.sombra;
      g.fillRect(telaX - 3, telaY - 3, telaW + 6, telaH + 6); g.fillRect(214, 133, 6, 6); g.fillRect(206, 138, 22, 2);
      g.clearRect(telaX, telaY, telaW, telaH);
    });

    var fios = [];
    for (var i = 0; i < 6; i++) fios.push({ x: 222 + i * 4 + inteiro(R, -1, 1), n: inteiro(R, 9, 30), f: R() * 6 });
    var poeira = [];
    for (var p = 0; p < 16; p++) poeira.push({ x: inteiro(R, X0, X0 + LW), y: R() * 120, v: 1 + R() * 2.5, f: R() * 6 });
    var planta = mix(pal.sombra, pal.meio, 0.4), fundoTela = mix(pal.sombra, pal.luz, 0.14), vapor = mix(pal.brilho, parede, 0.45);
    var coresCodigo = [pal.luz, pal.astro, pal.nuvem, pal.brilho];

    return function (g, t) {
      g.drawImage(fora, 0, 0);
      g.save(); g.beginPath(); g.rect(X0, Y0, LW, LH); g.clip();
      desenharEstrelas(g, est, t, pal.brilho);
      desenharNuvens(g, nv, t);
      g.restore();

      // tela: linhas de "código" subindo
      g.fillStyle = fundoTela; g.fillRect(telaX, telaY, telaW, telaH);
      var rolagem = Math.floor(t * 1.4);
      for (var l = 0; l < 8; l++) {
        var n = l + rolagem, recuo = 2 + ((n * 7) % 4) * 3, x = telaX + recuo;
        for (var s = 0; s < 3; s++) {
          var larg = 3 + ((n * 13 + s * 5) % 9);
          if (x + larg > telaX + telaW - 2 || (n + s) % 5 === 4) break;
          g.fillStyle = coresCodigo[(n + s * 3) % 4]; g.fillRect(x, telaY + 2 + l * 3, larg, 1);
          x += larg + 2;
        }
      }
      if ((t * 2 | 0) % 2) { g.fillStyle = pal.brilho; g.fillRect(telaX + 2, telaY + telaH - 3, 2, 1); }

      g.drawImage(sala, 0, 0);

      // rabo do gato
      g.fillStyle = pal.sombra;
      var rabo = Math.sin(t * 1.3) > 0.55 ? 1 : 0;
      for (var k = 0; k < 9; k++) g.fillRect(119 - k, PE - 2 - (k > 5 ? (k - 5) * (1 + rabo) : 0), 2, 2);
      // planta pendente balançando
      g.fillStyle = planta; g.fillRect(220, Y0 - 1, 26, 5);
      for (var f = 0; f < fios.length; f++) {
        var fio = fios[f];
        for (var q = 0; q < fio.n; q++) {
          var fx = fio.x + Math.round(Math.sin(t * 0.9 + q * 0.22 + fio.f) * q * 0.07);
          g.fillRect(fx, Y0 + 4 + q, 1, 1);
          if (q % 4 === 2) g.fillRect(fx + ((q >> 2) % 2 ? 1 : -2), Y0 + 4 + q, 2, 1);
        }
      }
      // vapor da caneca
      g.fillStyle = vapor;
      for (var v = 0; v < 5; v++) if ((v + (t * 3 | 0)) % 3) g.fillRect(165 + Math.round(Math.sin(t * 2 + v * 0.9) * 1.5), 130 - v * 2, 1, 1);
      // poeira na luz
      g.fillStyle = pal.brilho;
      for (var d = 0; d < poeira.length; d++) {
        var m = poeira[d];
        if (Math.sin(t * 1.2 + m.f) < 0.25) continue;
        g.fillRect(m.x + Math.round(Math.sin(t * 0.25 + m.f) * 7), 22 + ((m.y + t * m.v) % 120 | 0), 1, 1);
      }
    };
  };

  // ---------------------------------------------------------------- mar

  CENAS.mar = function (pal, R) {
    var hz = 98, sol = { x: inteiro(R, 90, 200), r: 21 }, horizonte = pal.ceu[pal.ceu.length - 1];
    var fundo = camada(function (g) {
      degrade(g, pal.ceu, 0, 0, W, hz);
      halo(g, sol.x, hz - 3, sol.r, mix(pal.astro, horizonte, 0.3));
      disco(g, sol.x, hz - 3, sol.r, pal.astro);
      degrade(g, [mix(horizonte, pal.meio, 0.5), pal.meio, pal.perto, pal.sombra], 0, hz, W, H - hz);
    });
    var est = pal.noite ? estrelas(R, 60, 60) : estrelas(R, 10, 30);
    var nv = nuvens(R, 4, 12, 62, mix(pal.nuvem, pal.brilho, 0.3), pal.nuvem, 1, 2.4);
    var fx = sol.x < 150 ? 258 : 60; // o farol fica do lado oposto ao sol
    var farol = camada(function (g) {
      g.fillStyle = pal.sombra;
      for (var y = 0; y < 16; y++) { var w = Math.round(8 + y * 1.6 + Math.sin(y * 1.7) * 2); g.fillRect(fx - w, hz - 7 + y, w * 2, 1); }
      for (var k = 0; k < 28; k++) { g.fillStyle = (k / 7 | 0) % 2 ? mix(pal.perto, pal.nuvem, 0.45) : mix(pal.sombra, pal.perto, 0.5); g.fillRect(fx - 3 - (k > 20 ? 1 : 0), hz - 35 + k, 6 + (k > 20 ? 2 : 0), 1); }
      g.fillStyle = pal.sombra; g.fillRect(fx - 4, hz - 41, 8, 6); g.fillRect(fx - 5, hz - 36, 10, 1);
      g.fillRect(fx - 3, hz - 43, 6, 2); g.fillRect(fx - 1, hz - 45, 2, 2);
    });
    var ondas = [];
    for (var i = 0; i < 70; i++) ondas.push({ x: R() * W, y: inteiro(R, hz + 3, H - 2), n: inteiro(R, 2, 7), v: 2 + R() * 5, f: R() * 6 });
    var aves = passaros(R, 3, 30, 60), corOnda = mix(pal.meio, pal.nuvem, 0.4), vela = mix(pal.brilho, pal.nuvem, 0.35);
    return function (g, t) {
      g.drawImage(fundo, 0, 0);
      desenharEstrelas(g, est, t, pal.brilho);
      desenharNuvens(g, nv, t);
      // reflexo do astro na água
      for (var y = hz + 1; y < H; y++) {
        var prof = (y - hz) / (H - hz), meia = 4 + prof * 30;
        for (var k = 0; k < 3; k++) {
          if ((y + k + (t * 4 | 0)) % 3 === 0) continue;
          var desvio = Math.sin(t * (1.1 + k * 0.4) + y * 0.9 + k * 2) * meia * 0.6, larg = 2 + ((y * 7 + k * 13) % 5) + prof * 7;
          g.fillStyle = k ? pal.astro : pal.brilho;
          g.fillRect(Math.round(sol.x + desvio - larg / 2), y, Math.round(larg), 1);
        }
      }
      g.fillStyle = corOnda;
      for (var i = 0; i < ondas.length; i++) {
        var o = ondas[i];
        if (Math.sin(t * 1.4 + o.f) < 0) continue;
        g.fillRect((((o.x + t * o.v) % W) + W) % W | 0, o.y, o.n, 1);
      }
      // veleiro
      var bx = Math.round(((t * 1.6 + 40) % (W + 40)) - 20), by = hz + 5 + Math.round(Math.sin(t * 1.1));
      g.fillStyle = pal.sombra; g.fillRect(bx - 5, by, 11, 2); g.fillRect(bx - 4, by + 2, 9, 1); g.fillRect(bx, by - 10, 1, 10);
      g.fillStyle = vela; for (var s = 0; s < 8; s++) g.fillRect(bx + 1, by - 9 + s, 1 + (s >> 1), 1);
      g.drawImage(farol, 0, 0);
      // facho do farol
      var fase = (t * 0.3) % 1, lado = fase < 0.25 ? -1 : fase > 0.5 && fase < 0.75 ? 1 : 0;
      g.fillStyle = lado ? pal.brilho : mix(pal.luz, pal.sombra, 0.4); g.fillRect(fx - 2, hz - 40, 4, 3);
      if (lado) {
        pontilhado(g, fx, hz - 39, 7, pal.brilho, 0.35);
        g.fillStyle = pal.brilho;
        for (var d = 4; d < 90; d++) { var ab = d * 0.13; for (var yy = -ab; yy <= ab; yy++) { var px = fx + lado * d, py = Math.round(hz - 39 + yy + d * 0.05); if (limiar(px, py) < 0.26 * (1 - d / 90)) g.fillRect(px, py, 1, 1); } }
      }
      desenharPassaros(g, aves, t, pal.sombra);
    };
  };

  // ---------------------------------------------------------------- floresta

  CENAS.floresta = function (pal, R) {
    var lua = { x: inteiro(R, 50, 270), y: inteiro(R, 30, 48), r: 14 };
    var ceu = camada(function (g) {
      degrade(g, pal.ceu, 0, 0, W, H);
      halo(g, lua.x, lua.y, lua.r, mix(pal.astro, pal.ceu[1], 0.5));
      disco(g, lua.x, lua.y, lua.r, pal.astro);
      var c = mix(pal.astro, pal.ceu[1], 0.22);
      disco(g, lua.x - 4, lua.y - 3, 3, c); disco(g, lua.x + 5, lua.y + 4, 2, c);
    });
    var est = estrelas(R, pal.noite ? 90 : 34, 96);
    function mata(base, cor, hMin, hMax, passo) {
      return camada(function (g) {
        g.fillStyle = cor; g.fillRect(0, base - 2, W, H);
        for (var x = -4; x < W + 6; x += inteiro(R, Math.max(2, passo - 3), passo + 3)) pinheiro(g, x, base, inteiro(R, hMin, hMax), cor);
      });
    }
    var m1 = mata(120, pal.longe, 16, 34, 7), m2 = mata(142, pal.meio, 26, 50, 11);
    var cx = inteiro(R, 60, 240); // cabana
    var cabana = camada(function (g) {
      g.fillStyle = pal.sombra;
      g.fillRect(cx, 131, 22, 12);
      for (var i = 0; i < 9; i++) g.fillRect(cx - 3 + i, 130 - i, 28 - i * 2, 1);
      g.fillRect(cx + 16, 118, 3, 8);
      g.fillStyle = mix(pal.sombra, pal.luz, 0.3); g.fillRect(cx + 14, 135, 5, 8);
    });
    var m3 = mata(170, pal.perto, 44, 92, 21);
    var frente = camada(function (g) { g.fillStyle = pal.sombra; var a = relevo(R, 175, 4, 0.5); for (var x = 0; x < W; x++) g.fillRect(x, Math.round(a[x]), 1, H); });
    var vaga = [];
    for (var i = 0; i < 18; i++) vaga.push({ x: inteiro(R, 10, W - 10), y: inteiro(R, 118, 172), a: R() * 6, b: R() * 6, c: R() * 6 });
    var corNevoa = mix(pal.nuvem, pal.ceu[2], 0.45), fumaca = mix(pal.nuvem, pal.ceu[1], 0.4), brilhoLuz = mix(pal.luz, pal.brilho, 0.5);
    return function (g, t) {
      g.drawImage(ceu, 0, 0);
      desenharEstrelas(g, est, t, pal.brilho);
      g.drawImage(m1, 0, 0);
      nevoa(g, t, 108, 15, corNevoa, 4);
      g.drawImage(m2, 0, 0);
      g.drawImage(cabana, 0, 0);
      g.fillStyle = Math.sin(t * 9) * Math.sin(t * 2.3) > 0.82 ? brilhoLuz : pal.luz; // janela acesa, tremulando
      g.fillRect(cx + 4, 134, 5, 5);
      g.fillStyle = pal.sombra; g.fillRect(cx + 6, 134, 1, 5); g.fillRect(cx + 4, 136, 5, 1);
      pontilhado(g, cx + 6, 145, 6, pal.luz, 0.14);
      g.fillStyle = fumaca; // fumaça da chaminé
      for (var k = 0; k < 7; k++) {
        var sobe = (t * 5 + k * 5) % 34;
        if (limiar(k, sobe | 0) < 1 - sobe / 34) g.fillRect(cx + 17 + Math.round(Math.sin(sobe * 0.3 + k) * (1 + sobe * 0.08)), 116 - (sobe | 0), sobe > 14 ? 2 : 1, 1);
      }
      nevoa(g, t, 136, 13, corNevoa, -6);
      g.drawImage(m3, 0, 0);
      g.drawImage(frente, 0, 0);
      for (var i = 0; i < vaga.length; i++) { // vaga-lumes
        var v = vaga[i], b = Math.sin(t * 1.8 + v.c);
        if (b < 0.1) continue;
        var x = v.x + Math.round(Math.sin(t * 0.32 + v.a) * 16), y = v.y + Math.round(Math.cos(t * 0.24 + v.b) * 8);
        g.fillStyle = pal.luz; g.fillRect(x, y, 1, 1);
        if (b > 0.75) { g.fillStyle = brilhoLuz; g.fillRect(x - 1, y, 3, 1); g.fillRect(x, y - 1, 1, 3); }
      }
    };
  };

  // ---------------------------------------------------------------- espaço

  CENAS.espaco = function (pal, R) {
    var fundo = camada(function (g) {
      degrade(g, [pal.sombra, pal.ceu[0], pal.ceu[1], pal.ceu[0]], 0, 0, W, H);
      // nebulosa: ruído suave pontilhado
      var gw = 9, gh = 6, grade = [];
      for (var i = 0; i < (gw + 1) * (gh + 1); i++) grade.push(R());
      var claro = mix(pal.meio, pal.nuvem, 0.45);
      for (var y = 0; y < H; y++)
        for (var x = 0; x < W; x++) {
          var u = (x / W) * gw, v = (y / H) * gh, iu = u | 0, iv = v | 0, fu = u - iu, fv = v - iv;
          fu = fu * fu * (3 - 2 * fu); fv = fv * fv * (3 - 2 * fv);
          var a = grade[iv * (gw + 1) + iu], b = grade[iv * (gw + 1) + iu + 1], c = grade[(iv + 1) * (gw + 1) + iu], d = grade[(iv + 1) * (gw + 1) + iu + 1];
          var n = a + (b - a) * fu + (c - a) * fv + (a - b - c + d) * fu * fv, l = limiar(x, y);
          if (n > 0.72 && l < (n - 0.72) * 3.2) { g.fillStyle = claro; g.fillRect(x, y, 1, 1); }
          else if (n > 0.54 && l < (n - 0.54) * 2.4) { g.fillStyle = pal.longe; g.fillRect(x, y, 1, 1); }
        }
    });
    var est1 = estrelas(R, 70, H - 1), est2 = estrelas(R, 34, H - 1);
    var P = { x: inteiro(R, 200, 250), y: inteiro(R, 66, 92), r: inteiro(R, 30, 38) };
    var A = P.r * 1.85, B = P.r * 0.4, INC = 0.2; // elipse do anel e sua inclinação
    function anel(g, deFrente) {
      for (var y = -Math.ceil(B + A * INC); y <= Math.ceil(B + A * INC); y++)
        for (var x = -Math.ceil(A); x <= Math.ceil(A); x++) {
          var v = (y - x * INC) / B, d = Math.sqrt((x / A) * (x / A) + v * v);
          if (d < 0.66 || d > 1 || (d > 0.84 && d < 0.875) || v >= 0 !== deFrente) continue;
          if (limiar(P.x + x, P.y + y) > 0.86) continue;
          g.fillStyle = mix(pal.brilho, pal.nuvem, (d - 0.66) / 0.34);
          g.fillRect(P.x + x, P.y + y, 1, 1);
        }
    }
    var planeta = camada(function (g) {
      anel(g, false);
      var faixa = mix(pal.astro, pal.nuvem, 0.55);
      for (var y = -P.r; y <= P.r; y++)
        for (var x = -P.r; x <= P.r; x++) {
          if (x * x + y * y > P.r * P.r) continue;
          var nx = x / P.r, ny = y / P.r, nz = Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny));
          var luz = nx * -0.62 + ny * -0.48 + nz * 0.62 + (limiar(P.x + x, P.y + y) - 0.5) * 0.3;
          var base = Math.sin(y * 0.42 + Math.sin(nx * 3) * 0.7) > 0.25 ? faixa : pal.astro;
          g.fillStyle = luz > 0.42 ? base : luz > 0.08 ? mix(base, pal.sombra, 0.5) : mix(base, pal.sombra, 0.84);
          g.fillRect(P.x + x, P.y + y, 1, 1);
        }
      anel(g, true);
    });
    var corLua = mix(pal.brilho, pal.nuvem, 0.3), vermelho = mix(pal.luz, "#ff3b30", 0.75);
    return function (g, t) {
      g.drawImage(fundo, 0, 0);
      desenharEstrelas(g, est1, t, mix(pal.brilho, pal.ceu[1], 0.35), t * 0.5);
      desenharEstrelas(g, est2, t, pal.brilho, t * 1.4);
      var fase = t % 11; // estrela cadente
      if (fase < 0.7) {
        var p = fase / 0.7, sx = 30 + ((Math.floor(t / 11) * 97) % 140) + p * 90, sy = 12 + p * 44;
        for (var k = 0; k < 12; k++) { g.fillStyle = k < 3 ? pal.brilho : mix(pal.brilho, pal.ceu[0], k / 12); g.fillRect((sx - k * 2) | 0, (sy - k) | 0, 2, 1); }
      }
      var ang = t * 0.22, lx = P.x + Math.cos(ang) * A * 1.22, ly = P.y + Math.sin(ang) * B * 1.7 + (lx - P.x) * INC;
      var atras = Math.sin(ang) < 0;
      if (atras) disco(g, Math.round(lx), Math.round(ly), 3, corLua);
      g.drawImage(planeta, 0, 0);
      if (!atras) disco(g, Math.round(lx), Math.round(ly), 3, corLua);
      var tx = ((t * 5) % (W + 80)) - 40, ty = 34 + tx * 0.1; // satélite
      g.fillStyle = pal.brilho; g.fillRect(tx | 0, ty | 0, 3, 2);
      g.fillStyle = pal.luz; g.fillRect((tx | 0) - 3, ty | 0, 2, 1); g.fillRect((tx | 0) + 4, ty | 0, 2, 1);
      if ((t * 1.5 | 0) % 2) { g.fillStyle = vermelho; g.fillRect((tx | 0) + 1, (ty | 0) - 1, 1, 1); }
    };
  };

  // ---------------------------------------------------------------- execução

  var ativas = [], parado = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function preparar(canvas) {
    if (canvas._cena) return canvas._cena;
    var pal = {};
    try { pal = JSON.parse(canvas.dataset.paleta || "{}"); } catch (e) { pal = {}; }
    for (var chave in PADRAO) if (pal[chave] === undefined || pal[chave] === null || pal[chave] === "") pal[chave] = PADRAO[chave];
    if (!Array.isArray(pal.ceu) || pal.ceu.length < 2) pal.ceu = PADRAO.ceu;
    while (pal.ceu.length < 4) pal.ceu = pal.ceu.concat(pal.ceu[pal.ceu.length - 1]);
    canvas.width = W; canvas.height = H;
    var g = canvas.getContext("2d");
    g.imageSmoothingEnabled = false;
    var semente = Number(canvas.dataset.semente) || 1;
    var desenhar = (CENAS[canvas.dataset.cena] || CENAS.montanhas)(pal, gerador(semente));
    var cena = { canvas: canvas, visivel: false, quadro: function (t) { desenhar(g, t + (semente % 50)); } };
    canvas._cena = cena;
    cena.quadro(3);
    return cena;
  }

  // Uma cena só é animada se estiver na tela e, dentro do carrossel, se for o slide ativo.
  function deveAnimar(cena) {
    if (!cena.visivel || document.hidden) return false;
    var slide = cena.canvas.closest(".slide");
    return !slide || slide.classList.contains("ativo");
  }

  function iniciar(raiz) {
    var observador = "IntersectionObserver" in window
      ? new IntersectionObserver(function (itens) { itens.forEach(function (i) { if (i.target._cena) i.target._cena.visivel = i.isIntersecting; }); })
      : null;
    (raiz || document).querySelectorAll("canvas[data-cena]").forEach(function (canvas) {
      if (canvas._cena) return;
      try {
        var cena = preparar(canvas);
        ativas.push(cena);
        if (observador) observador.observe(canvas); else cena.visivel = true;
      } catch (e) { if (window.console) console.error("Cena não pôde ser desenhada:", e); }
    });
  }

  var ultimo = 0, fonteAmbiente = null;
  function laco(agora) {
    requestAnimationFrame(laco);
    if (agora - ultimo < 1000 / QPS) return;
    ultimo = agora;
    if (!parado) for (var i = 0; i < ativas.length; i++) if (deveAnimar(ativas[i])) ativas[i].quadro(agora / 1000);
    pintarAmbiente();
  }

  // O fundo da página copia a capa ativa em baixíssima resolução; o CSS desfoca.
  function pintarAmbiente() {
    var alvo = document.getElementById("ambiente");
    if (!alvo || !fonteAmbiente) return;
    try {
      if (fonteAmbiente.tagName === "IMG" && !fonteAmbiente.complete) return;
      alvo.getContext("2d").drawImage(fonteAmbiente, 0, 0, alvo.width, alvo.height);
      alvo.classList.add("visivel");
    } catch (e) { /* imagem de outro site ou ainda carregando */ }
  }
  function ambiente(elemento) { fonteAmbiente = elemento || null; pintarAmbiente(); }

  window.Orquestra = { iniciarCenas: iniciar, ambiente: ambiente, cenas: Object.keys(CENAS) };
  document.addEventListener("DOMContentLoaded", function () {
    iniciar(document);
    var capa = document.querySelector(".cab-modulo .capa");
    if (capa) ambiente(capa);
    requestAnimationFrame(laco);
  });
})();
