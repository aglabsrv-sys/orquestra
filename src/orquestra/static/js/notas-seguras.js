/* Fila por nota e rascunhos do navegador. Sem acesso ao DOM: testável com node:test. */
(function (raiz) {
  "use strict";

  function criarFila(enviar, observar) {
    var itens = [], ativa = false, erro = null;
    function estado() {
      var valor = { ativa: ativa, pendentes: itens.length, erro: erro };
      if (observar) observar(valor);
      return valor;
    }
    function processar() {
      if (ativa || erro || !itens.length) return;
      ativa = true;
      estado();
      var item = itens[0];
      Promise.resolve().then(function () { return enviar(item.dados); }).then(function (resposta) {
        itens.shift();
        if (item.salvo) item.salvo(resposta, item.dados);
        item.resolver(resposta);
      }, function (falha) {
        erro = falha;
        item.rejeitar(falha);
      }).finally(function () {
        ativa = false;
        estado();
        processar();
      });
    }
    return {
      adicionar: function (dados, salvo) {
        // Captura o valor no momento da ação, antes da próxima edição da tela.
        var copia = JSON.parse(JSON.stringify(dados));
        var promessa = new Promise(function (resolver, rejeitar) {
          itens.push({ dados: copia, salvo: salvo, resolver: resolver, rejeitar: rejeitar });
        });
        processar();
        return promessa;
      },
      repetir: function () { erro = null; processar(); },
      descartar: function () {
        if (ativa) return false;
        var cancelado = new Error("Gravação descartada pela pessoa.");
        cancelado.cancelado = true;
        itens.splice(0).forEach(function (item) { item.rejeitar(cancelado); });
        erro = null;
        estado();
        return true;
      },
      estado: estado
    };
  }

  function criarRascunhos(armazenamento, vault, caminho, sessao) {
    if (!vault || !caminho) throw new Error("Identidade do vault e da nota são obrigatórias.");
    var prefixo = "orquestra:rascunho:v1:" + encodeURIComponent(vault) + ":" + encodeURIComponent(caminho) + ":";
    var chave = prefixo + sessao;
    return {
      guardar: function (dados) {
        armazenamento.setItem(chave, JSON.stringify({ dados: dados, quando: Date.now() }));
      },
      listar: function () {
        var encontrados = [];
        for (var i = 0; i < armazenamento.length; i++) {
          var nome = armazenamento.key(i);
          if (!nome || nome.indexOf(prefixo) !== 0) continue;
          try {
            var valor = JSON.parse(armazenamento.getItem(nome));
            if (valor && valor.dados && typeof valor.dados.corpo === "string") encontrados.push({ chave: nome, dados: valor.dados, quando: valor.quando });
          } catch (e) { /* Uma entrada inválida não impede recuperar as demais. */ }
        }
        return encontrados.sort(function (a, b) { return b.quando - a.quando; });
      },
      remover: function (nome) {
        if (nome && nome.indexOf(prefixo) === 0) armazenamento.removeItem(nome);
      },
      limpar: function () { armazenamento.removeItem(chave); }
    };
  }

  function camposParaCopia(original, editados) {
    // Sem prototype: frontmatter arbitrário não pode alterar Object.prototype.
    var copia = Object.create(null);
    [original, editados].forEach(function (origem) {
      if (!origem || typeof origem !== "object" || Array.isArray(origem)) return;
      Object.keys(origem).forEach(function (nome) { copia[nome] = origem[nome]; });
    });
    return copia;
  }

  var api = { criarFila: criarFila, criarRascunhos: criarRascunhos, camposParaCopia: camposParaCopia };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else raiz.OrquestraNotas = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
