/* Mantém wikilinks no leitor, preservando a árvore da janela principal. */
(function(){
  'use strict';
  document.addEventListener('click',function(e){
    var a=e.target.closest('a');if(!a||e.defaultPrevented||e.button||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;
    var u=new URL(a.href,location.href);if(u.origin!==location.origin)return;
    if(/^\/(n|documento)\//.test(u.pathname)||/^\/pastas(?:\/|$)/.test(u.pathname)){
      e.preventDefault();parent.postMessage({tipo:'orquestra:leitor',url:u.href,titulo:a.textContent},location.origin);
    }
  });
})();
