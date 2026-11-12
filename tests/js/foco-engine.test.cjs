'use strict';
const {test}=require('node:test'); const assert=require('node:assert/strict');
const {Motor}=require('../../src/orquestra/static/js/foco-engine.js');
const agora=new Date(2026,10,12,12).getTime();
test('o prazo preserva o tempo ao navegar, pausar e reabrir',()=>{
  let m=new Motor(null,agora); m.alternar(agora); m.atualizar(agora+90000);
  assert.equal(m.s.restante,1410); m=new Motor(m.exportar(),agora+150000); assert.equal(m.s.restante,1350);
  m.alternar(agora+150000); assert.equal(m.s.fim,0); m.atualizar(agora+900000); assert.equal(m.s.restante,1350);
  m.alternar(agora+900000); assert.equal(m.s.fim,agora+2250000);
});
test('suspensão conclui uma única vez e não inicia outra etapa sozinha',()=>{
  const m=new Motor(null,agora); m.alternar(agora); assert.equal(m.atualizar(agora+1800000),true);
  assert.equal(m.s.ciclos,1); assert.equal(m.s.hoje,1); assert.equal(m.s.fim,0); assert.equal(m.proximo(),'curta');
  m.atualizar(agora+3600000); assert.equal(m.s.ciclos,1);
  const novo=new Motor(m.exportar(),agora+3600000); assert.equal(novo.s.ciclos,1); assert.equal(novo.s.hoje,1);
});
test('quatro focos liberam pausa longa e pausas não contam como foco',()=>{
  const m=new Motor(null,agora); for(let i=0;i<4;i++){m.mudar('foco');m.alternar(agora);m.atualizar(agora+1500000);}
  assert.equal(m.proximo(),'longa'); m.alternar(agora+1600000); assert.equal(m.s.modo,'longa');
  m.atualizar(agora+2600000); assert.equal(m.s.ciclos,4); assert.equal(m.proximo(),'foco');
});
test('valores estranhos no armazenamento não quebram o relógio',()=>{
  const m=new Motor({duracoes:{foco:NaN,curta:-1,longa:Infinity},restante:-50,fim:Infinity,modo:'<script>',ciclos:-10},agora);
  assert.equal(m.s.modo,'foco'); assert.equal(m.s.restante,1500); assert.equal(m.s.fim,0); assert.equal(m.s.ciclos,0);
  assert.throws(()=>m.configurar({foco:0,curta:5,longa:15},false));
});
test('configurar duração exige minutos válidos e reinicia só ao aplicar',()=>{
  const m=new Motor(null,agora); m.alternar(agora); m.configurar({foco:50,curta:10,longa:20},true);
  assert.equal(m.s.fim,0); assert.equal(m.s.restante,3000); assert.equal(m.s.som,true); assert.equal(m.s.ciclos,0);
});
test('reabrir no dia seguinte não conta ontem como foco de hoje',()=>{
 const m=new Motor(null,agora);m.alternar(agora);
 const novo=new Motor(m.exportar(),agora+24*3600000);
 assert.equal(novo.s.ciclos,1);assert.equal(novo.s.hoje,0);
});
