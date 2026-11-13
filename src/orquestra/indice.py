"""Índice em memória do vault.

O índice é só um espelho rápido dos arquivos: a verdade está sempre no disco.
Ele é montado ao iniciar e atualizado arquivo por arquivo quando o vigia avisa
que algo mudou. Se for apagado, basta reconstruir.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from orquestra.caminhos import CaminhoInseguro, arquivos_do_vault, caminho_no_vault, ignorar
from orquestra.modulos import NOTAS_DE_CONTRATO, ZONAS, Modulo, descobrir
from orquestra.notas import Nota, ler_nota

EXT_MIDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif", ".bmp", ".ico", ".mp4", ".webm"}


def deve_ignorar(rel: str) -> bool:
    """Arquivos que o painel não indexa nem registra no diário."""
    # Em minúsculas: no Windows e no macOS "Diario/Registro" e "diario/registro" são a
    # mesma pasta, e o registro não pode nunca ser tratado como uma mudança a registrar.
    return ignorar(rel)


@dataclass
class Mudanca:
    tipo: str  # criado | editado | removido
    rel: str
    antes: Nota | None
    depois: Nota | None


@dataclass
class Resumo:
    total: int = 0
    abertos: int = 0  # ainda não concluídos
    hoje: int = 0  # com data de hoje ou atrasados
    decidir: int = 0  # esperando decisão humana


class Indice:
    def __init__(self, vault: Path):
        self.vault = vault.resolve()
        self.modulos: dict[str, Modulo] = {}
        self.notas: dict[str, Nota] = {}
        self.midias: dict[str, str] = {}  # nome do arquivo em minúsculas -> caminho relativo
        self.arquivos: set[str] = set()  # existência de anexos, inclusive sem prévia
        self.revisao = 0
        self._assinaturas: dict[str, tuple[int, int, int]] = {}
        self._links: dict[str, set[str]] = {}
        self._zonas: dict[tuple[str, str], dict[str, Nota]] = {}
        self._schemas: dict[str, tuple[int, int, int]] | None = None

    # ------------------------------------------------------------ carga

    def carregar(self) -> None:
        self._schemas = None
        self.recarregar_modulos()
        self.notas = {}
        self.midias = {}
        self.arquivos = set()
        self._referencias_vinculos = {}
        self._ancoras_vinculos = {}
        self._assinaturas = {}
        for rel, caminho, info in arquivos_do_vault(self.vault):
            self.arquivos.add(rel)
            if caminho.suffix.lower() == ".md":
                try:
                    self.notas[rel] = ler_nota(caminho, self.vault, somente_indice=True)
                    self._assinaturas[rel] = (info.st_mtime_ns, info.st_size, info.st_ctime_ns)
                except (OSError, CaminhoInseguro):
                    continue
            elif caminho.suffix.lower() in EXT_MIDIA:
                self.midias[caminho.name.lower()] = rel
        self._reindexar()
        self.revisao += 1

    def recarregar_modulos(self) -> None:
        novos = descobrir(self.vault)
        for chave, modulo in novos.items():
            anterior = self.modulos.get(chave)
            if modulo.invalido and anterior is not None and not anterior.invalido:
                anterior.avisos = modulo.avisos + ["Usando a última configuração válida até você corrigir o arquivo."]
                novos[chave] = anterior
        self.modulos = novos
        self.ordenar_modulos(getattr(self, "ordem_modulos", []))
        self._reindexar()

    def ordenar_modulos(self, ordem: list[str]) -> None:
        """Aplica preferências sem reler schemas nem reindexar todas as notas."""
        self.ordem_modulos = list(ordem)
        posicoes = {nome: i for i, nome in enumerate(ordem)}
        self.modulos = dict(sorted(self.modulos.items(), key=lambda par: posicoes.get(par[0], len(ordem))))

    def _reindexar(self) -> None:
        self._links = {}
        self._zonas = {}
        for rel, nota in self.notas.items():
            self._adicionar_consultas(rel, nota)

    def _adicionar_consultas(self, rel: str, nota: Nota) -> None:
        for chave in {rel.lower().removesuffix(".md"), nota.caminho.stem.lower()}:
            self._links.setdefault(chave, set()).add(rel)
        chave_zona = (rel.split("/", 1)[0], self.zona_de(rel))
        self._zonas.setdefault(chave_zona, {})[rel] = nota

    def _remover_consultas(self, rel: str, nota: Nota) -> None:
        for chave in {rel.lower().removesuffix(".md"), nota.caminho.stem.lower()}:
            encontrados = self._links.get(chave)
            if encontrados:
                encontrados.discard(rel)
                if not encontrados:
                    self._links.pop(chave, None)
        for zona in ("itens", "humano", "maquina", "arquivo", ""):
            grupo = self._zonas.get((rel.split("/", 1)[0], zona))
            if grupo is not None:
                grupo.pop(rel, None)

    def sincronizar(self) -> None:
        """Atualiza o índice comparando datas de modificação, sem reler tudo.

        Usado por quem não tem o vigia de arquivos ligado (o servidor MCP, por
        exemplo): antes de responder, confere o que mudou no disco desde a última vez.
        """
        schemas = {}
        for pasta in self.vault.iterdir():
            if pasta.name.startswith((".", "_")):
                continue
            try:
                arquivo = caminho_no_vault(self.vault, pasta / "_modulo.yaml")
                info = arquivo.stat()
                schemas[arquivo.relative_to(self.vault).as_posix()] = (info.st_mtime_ns, info.st_size, info.st_ctime_ns)
            except (CaminhoInseguro, OSError):
                continue
        if schemas != self._schemas:
            self.recarregar_modulos()
            self._schemas = schemas
        vistos: set[str] = set()
        arquivos: set[str] = set()
        self.midias = {}
        for rel, caminho, info in arquivos_do_vault(self.vault):
            arquivos.add(rel)
            if caminho.suffix.lower() in EXT_MIDIA:
                self.midias[caminho.name.lower()] = rel
            if caminho.suffix.lower() != ".md":
                continue
            vistos.add(rel)
            assinatura = (info.st_mtime_ns, info.st_size, info.st_ctime_ns)
            if rel not in self.notas or self._assinaturas.get(rel) != assinatura:
                self.atualizar(caminho)
        for rel in [r for r in self.notas if r not in vistos]:
            self._remover_consultas(rel, self.notas.pop(rel))
            self._assinaturas.pop(rel, None)
            self.revisao += 1
        if arquivos != self.arquivos:
            self.arquivos = arquivos
            self.revisao += 1

    def atualizar(self, caminho: Path) -> Mudanca | None:
        """Relê um arquivo que mudou no disco. Devolve o que mudou (ou None)."""
        try:
            caminho = caminho_no_vault(self.vault, caminho)
            rel = caminho.relative_to(self.vault).as_posix()
        except (ValueError, OSError):
            return None
        if deve_ignorar(rel):
            return None
        existia = rel in self.arquivos
        if caminho.is_file():
            self.arquivos.add(rel)
        else:
            self.arquivos.discard(rel)
        if existia != (rel in self.arquivos):
            self.revisao += 1
        sufixo = caminho.suffix.lower()
        if sufixo in EXT_MIDIA:
            if caminho.is_file():
                self.midias[caminho.name.lower()] = rel
            else:
                self.midias.pop(caminho.name.lower(), None)
            return None
        if sufixo != ".md":
            return None

        antes = self.notas.get(rel)
        if not caminho.is_file():
            if antes is None:
                return None
            del self.notas[rel]
            self._remover_consultas(rel, antes)
            self._assinaturas.pop(rel, None)
            self.revisao += 1
            getattr(self, "_referencias_vinculos", {}).pop(rel, None)
            getattr(self, "_ancoras_vinculos", {}).pop(rel, None)
            return Mudanca("removido", rel, antes, None)
        try:
            for _tentativa in range(3):
                antes_info = caminho.stat()
                depois = ler_nota(caminho, self.vault, somente_indice=True)
                info = caminho.stat()
                assinatura_antes = (antes_info.st_mtime_ns, antes_info.st_size, antes_info.st_ctime_ns)
                assinatura_depois = (info.st_mtime_ns, info.st_size, info.st_ctime_ns)
                if assinatura_antes == assinatura_depois:
                    break
            else:
                self._assinaturas.pop(rel, None)
                return None  # escritor ainda ativo: a próxima sincronização tenta de novo
        except (OSError, CaminhoInseguro):
            return None
        self._assinaturas[rel] = (info.st_mtime_ns, info.st_size, info.st_ctime_ns)
        if antes is not None and antes.versao == depois.versao:
            return None  # o arquivo foi tocado, mas o conteúdo é o mesmo
        if antes:
            self._remover_consultas(rel, antes)
        self.notas[rel] = depois
        self.revisao += 1
        self._adicionar_consultas(rel, depois)
        return Mudanca("editado" if antes else "criado", rel, antes, depois)

    # ------------------------------------------------------------ consultas

    def modulo_de(self, rel: str) -> Modulo | None:
        return self.modulos.get(rel.split("/", 1)[0])

    def zona_de(self, rel: str) -> str:
        """Papel da nota dentro do módulo: itens, humano, maquina, arquivo (ou "").

        Num módulo comum é a segunda parte do caminho. Num módulo montado em cima de
        uma pasta que já existia (`itens: .`), tudo que não está em humano/, maquina/
        ou arquivo/ é item, inclusive o que está em subpastas.
        """
        partes = rel.split("/")
        modulo = self.modulos.get(partes[0])
        if modulo is None or len(partes) < 2:
            return ""
        if len(partes) > 2 and partes[1] in ZONAS:
            return partes[1]
        if modulo.itens_na_raiz:
            return "" if partes[-1].lower() in NOTAS_DE_CONTRATO else "itens"
        if len(partes) > 2 and partes[1] == modulo.itens_em:
            return "itens"
        return partes[1] if len(partes) > 2 else ""

    def notas_em(self, modulo_id: str, zona: str, *, ordenar: bool = True) -> list[Nota]:
        achadas = list(self._zonas.get((modulo_id, zona), {}).values())
        if ordenar:
            achadas.sort(key=lambda n: n.titulo.lower())
        return achadas

    def registros_em(self, modulo_id: str, zona: str = "itens"):
        """Iteração sem ordenar para contagens e visões que já têm sua própria ordem."""
        return self._zonas.get((modulo_id, zona), {}).values()

    # ------------------------------------------------------------ pastas

    def pastas_da_raiz(self) -> list[tuple[str, int]]:
        """Pastas da raiz que têm notas, com a contagem (inclui subpastas)."""
        contagem: dict[str, int] = {}
        for rel in self.notas:
            if "/" in rel:
                raiz = rel.split("/", 1)[0]
                contagem[raiz] = contagem.get(raiz, 0) + 1
        return sorted(contagem.items(), key=lambda par: par[0].lower())

    def conteudo_da_pasta(self, pasta: str) -> tuple[list[tuple[str, int]], list[Nota]]:
        """O que há dentro de uma pasta: (subpastas com contagem, notas diretas)."""
        prefixo = pasta.strip("/") + "/" if pasta.strip("/") else ""
        subpastas: dict[str, int] = {}
        notas: list[Nota] = []
        for rel, nota in self.notas.items():
            if not rel.startswith(prefixo):
                continue
            resto = rel[len(prefixo):]
            if "/" in resto:
                nome = resto.split("/", 1)[0]
                subpastas[nome] = subpastas.get(nome, 0) + 1
            else:
                notas.append(nota)
        notas.sort(key=lambda n: n.titulo.lower())
        return sorted(subpastas.items(), key=lambda par: par[0].lower()), notas

    def fora_dos_modulos(self) -> int:
        """Quantas notas vivem em pastas que não são módulo (nem o diário)."""
        return sum(
            1 for rel in self.notas if "/" in rel and rel.split("/", 1)[0] not in self.modulos and not rel.startswith("diario/")
        )

    def itens(self, modulo_id: str) -> list[Nota]:
        """Registros do módulo (pasta itens/), ordenados por data e depois por título."""
        modulo = self.modulos.get(modulo_id)
        notas = self.notas_em(modulo_id, "itens")
        if modulo and modulo.campo_data:
            notas.sort(key=lambda n: (data_de(n, modulo) or dt.date.max, n.titulo.lower()))
        return notas

    def ids_externos(self, modulo_id: str) -> set[str]:
        """IDs já coletados neste módulo (inclusive arquivados), para não duplicar."""
        prefixo = modulo_id + "/"
        return {
            str(n.meta["id_externo"])
            for rel, n in self.notas.items()
            if rel.startswith(prefixo) and n.meta.get("id_externo")
        }

    def resumo(self, modulo: Modulo, hoje: dt.date | None = None) -> Resumo:
        hoje = hoje or dt.date.today()
        r = Resumo()
        if not modulo.tem_status:
            # Sem status não há "em aberto" nem "para hoje": é só uma coleção de notas.
            notas = self.registros_em(modulo.id)
            r.total = len(notas)
            r.decidir = sum(1 for n in notas if espera_decisao(n, modulo))
            return r
        for nota in self.registros_em(modulo.id):
            r.total += 1
            status = str(nota.campo(modulo.campo_status) or "")
            if espera_decisao(nota, modulo):
                r.decidir += 1
            if status in modulo.concluidos:
                continue
            r.abertos += 1
            data = data_de(nota, modulo)
            if data and data <= hoje:
                r.hoje += 1
        return r

    def buscar(self, termo: str, limite: int | None = 60) -> list[Nota]:
        termo = termo.lower().strip()
        if not termo:
            return []
        no_titulo, no_corpo = [], []
        for nota in self.notas.values():
            if termo in nota.titulo.lower():
                no_titulo.append(nota)
            elif termo in nota.corpo.lower():
                no_corpo.append(nota)
        return (no_titulo + no_corpo)[:limite]

    def referencias_de(self, rel: str):
        from orquestra.vinculos import referencias_da_nota
        return referencias_da_nota(self, rel)

    def resolver_referencia(self, referencia, origem: str = "", *, tipo: str = "wiki"):
        from orquestra.vinculos import resolver_referencia
        return resolver_referencia(self, referencia, origem, tipo=tipo)

    def resolver_link(self, nome: str, origem: str = "") -> str | None:
        """Resolve um [[wikilink]] do Obsidian para o caminho relativo da nota."""
        resolucao = self.resolver_referencia(nome, origem)
        return resolucao.rel if resolucao.estado in {"valido", "ancora_ausente"} and resolucao.rel in self.notas else None


def espera_decisao(nota: Nota, modulo: Modulo) -> bool:
    """Uma nota entra na fila Decidir por dois caminhos:

    - o status dela está na lista `decidir` do módulo (ex.: item recém-coletado);
    - um agente deixou uma `pergunta` no frontmatter, esperando resposta humana.
    """
    if str(nota.campo(modulo.campo_status) or "") in modulo.concluidos:
        return False
    if str(nota.meta.get("pergunta") or "").strip():
        return True
    return str(nota.campo(modulo.campo_status) or "") in modulo.decidir


def data_de(nota: Nota, modulo: Modulo) -> dt.date | None:
    """Data principal da nota (o campo indicado em `campo_data` do módulo)."""
    if not modulo.campo_data:
        return None
    valor = nota.meta.get(modulo.campo_data)
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    if valor:
        try:
            return dt.date.fromisoformat(str(valor)[:10])
        except ValueError:
            return None
    return None
