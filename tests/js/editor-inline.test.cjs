'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {intervalo,substituir}=require('../../src/orquestra/static/js/editor-inline.js');

test('editar um parágrafo conserva tabelas, código, wikilinks e espaços fora dele',()=>{
  const antes='# Título\n\n[[Referência|Nome visível]] e **ênfase**.\n\n';
  const bloco='Um parágrafo.\n';
  const depois='\n- [x] Item\n- Outro\n\n| Chave | Valor |\n| --- | --- |\n| a | b |\n\n```js\nconst a = "[[literal]]";\n```\n';
  const fonte=antes+bloco+depois,trecho=intervalo(fonte,4,5);
  assert.equal(trecho.conteudo,'Um parágrafo.');
  assert.equal(substituir(fonte,trecho,'Parágrafo revisado.'),antes+'Parágrafo revisado.\n'+depois);
  assert.equal(substituir(fonte,trecho,trecho.conteudo),fonte);
});

test('a quebra separadora do próximo bloco não desaparece ao substituir o texto',()=>{
  const fonte='Primeiro.\n\nSegundo.';
  assert.equal(substituir(fonte,intervalo(fonte,0,1),'Novo primeiro.'),'Novo primeiro.\n\nSegundo.');
  assert.equal(substituir(fonte,intervalo(fonte,2,3),'Novo segundo.'),'Primeiro.\n\nNovo segundo.');
  const lista='- Um\n- Dois\n\nDepois.';
  assert.equal(substituir(lista,intervalo(lista,0,3),'- Revisto'),'- Revisto\n\nDepois.');
});

test('trechos multilinha preservam indentação e não acrescentam newline ao fim do arquivo',()=>{
  const fonte='Antes.\n\n- Um\n  - Aninhado\n- Dois\n\nFim sem newline';
  const trecho=intervalo(fonte,2,5);
  assert.equal(trecho.conteudo,'- Um\n  - Aninhado\n- Dois');
  assert.equal(substituir(fonte,trecho,trecho.conteudo),fonte);
  const fim=intervalo(fonte,6,7);
  assert.equal(fim.quebra,'');
  assert.equal(substituir(fonte,fim,'Fim alterado'),'Antes.\n\n- Um\n  - Aninhado\n- Dois\n\nFim alterado');
});
