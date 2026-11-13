"""Prévia de HTML com recursos locais resolvidos a partir do próprio arquivo."""
from html import escape
from html.parser import HTMLParser
from pathlib import PurePosixPath
import posixpath
import re
from urllib.parse import quote, unquote, urlsplit


def preparar_html(texto: str, origem: str) -> str:
    def recurso(valor: str) -> str:
        url = urlsplit(valor)
        if url.scheme or url.netloc or valor.startswith(('#', '/arquivo/')):
            return valor
        caminho = posixpath.normpath(str(PurePosixPath(origem).parent / unquote(url.path)))
        if valor.startswith('/'):
            caminho = unquote(url.path).lstrip('/')
        return '/arquivo/' + quote(caminho)

    def estilo(valor: str) -> str:
        return re.sub(r'url\(\s*[\'"]?([^\)\'"\s]+)[\'"]?\s*\)', lambda m: 'url("' + recurso(m.group(1)) + '")', valor, flags=re.I)

    class Documento(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.partes = []
            self.em_estilo = False

        def handle_starttag(self, tag, attrs):
            if tag == 'base':
                return
            self.em_estilo = tag == 'style' or self.em_estilo
            pares = []
            for chave, valor in attrs:
                if valor is not None:
                    if chave in {'src', 'poster', 'background'}:
                        valor = recurso(valor)
                    elif chave == 'style':
                        valor = estilo(valor)
                pares.append(chave if valor is None else chave + '="' + escape(valor, quote=True) + '"')
            self.partes.append('<' + tag + (' ' + ' '.join(pares) if pares else '') + '>')

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)

        def handle_endtag(self, tag):
            if tag == 'style':
                self.em_estilo = False
            self.partes.append('</' + tag + '>')

        def handle_data(self, data):
            self.partes.append(estilo(data) if self.em_estilo else data)

        def handle_entityref(self, name):
            self.partes.append('&' + name + ';')

        def handle_charref(self, name):
            self.partes.append('&#' + name + ';')

        def handle_decl(self, decl):
            self.partes.append('<!' + decl + '>')

        def handle_comment(self, data):
            self.partes.append('<!--' + data + '-->')

    parser = Documento()
    parser.feed(texto)
    parser.close()
    return ''.join(parser.partes)
