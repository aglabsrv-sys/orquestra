"""Servidor MCP: o vault como um conector para agentes de IA.

Um agente com acesso à pasta (Claude Code, Codex) trabalha direto nos arquivos e
segue o AGENTS.md por conta própria. Já um aplicativo de conversa não enxerga a
pasta: para ele, o Orquestra se apresenta como um conector MCP, com ferramentas
como "criar tarefa", "capturar" e "o que espera uma decisão".

A diferença importante é que aqui as regras do contrato são aplicadas pelo código,
não pela boa vontade do agente: por estas ferramentas não dá para reescrever o
texto de uma nota da pessoa, apagar um arquivo, nem criar algo sem `origem: agente`.

    orquestra mcp            (fala MCP pela entrada e saída padrão)

O servidor não precisa do painel aberto. Se o painel estiver aberto, ele percebe as
mudanças na hora, porque os dois trabalham nos mesmos arquivos.
"""

from __future__ import annotations

import datetime as dt
from functools import wraps
from pathlib import Path, PureWindowsPath
from typing import Any

from orquestra import diario
from orquestra.caminhos import CaminhoInseguro, caminho_no_vault, ignorar
from orquestra.indice import data_de, espera_decisao
from orquestra.modulos import ValorInvalido, validar
from orquestra.notas import Conflito, FrontmatterInvalido, Nota
from orquestra.painel import NaoEncontrado, Painel, Recusado

AUTOR = "agente:mcp"
INSTRUCOES = (
    "Este é o vault de trabalho de uma pessoa (notas markdown organizadas em áreas). "
    "Antes de qualquer outra coisa, chame `regras` e siga o que estiver lá. "
    "Tudo que você criar fica marcado como feito por agente. O texto que a pessoa escreveu "
    "nunca é reescrito: você só acrescenta. Em caso de dúvida, use `perguntar` em vez de supor. "
    "Ao terminar, chame `registrar_sessao`."
)


try:  # mcp 2.x só repassa ao agente a mensagem de erros deste tipo; os outros são mascarados
    from mcp.server.mcpserver.exceptions import ToolError as _ErroBase
except ImportError:
    try:
        from mcp.server.fastmcp.exceptions import ToolError as _ErroBase  # mcp 1.x
    except ImportError:
        _ErroBase = ValueError


class ErroDeFerramenta(_ErroBase):
    """Erro com uma mensagem em português, para o agente ler e corrigir o pedido."""


def _sincronizado(funcao):
    @wraps(funcao)
    def executar(self, *args, **kwargs):
        with self.painel._trava:
            return funcao(self, *args, **kwargs)
    return executar


class Ferramentas:
    """As operações oferecidas aos agentes. São métodos comuns, fáceis de testar."""

    def __init__(self, vault: Path):
        self.painel = Painel(vault)

    # ------------------------------------------------------------ apoio

    def _em_dia(self) -> None:
        # Sem vigia de arquivos neste processo: conferimos o disco antes de cada operação.
        self.painel.indice.sincronizar()
        self.painel.recarregar_config(modulos=False)

    def _area(self, area: str):
        try:
            modulo = self.painel.modulo(area)
            caminho_no_vault(self.painel.vault, modulo.pasta / "_modulo.yaml")
            return modulo
        except CaminhoInseguro:
            raise ErroDeFerramenta("A área usa um caminho vinculado ou fora do vault e não pode ser acessada.") from None
        except NaoEncontrado:
            existentes = ", ".join(self.painel.indice.modulos) or "nenhuma"
            raise ErroDeFerramenta(f"A área '{area}' não existe. Áreas deste vault: {existentes}.") from None

    def _nota(self, caminho: str) -> Nota:
        caminho = caminho.strip().replace("\\", "/")
        if PureWindowsPath(caminho).drive or caminho.startswith("/") or ".." in caminho.split("/"):
            raise ErroDeFerramenta("Use um caminho relativo dentro do vault, sem '..'.")
        nota = self.painel.indice.notas.get(caminho)
        if nota is None:
            achado = self.painel.indice.resolver_link(caminho)
            nota = self.painel.indice.notas.get(achado) if achado else None
        if nota is None:
            raise ErroDeFerramenta(f"Não encontrei a nota '{caminho}'. Use `buscar` ou `listar_itens` para achar o caminho certo.")
        self._conferir_nota(nota)
        return nota

    def _conferir_nota(self, nota: Nota) -> None:
        if not self._visivel(nota):
            raise ErroDeFerramenta("Este caminho é reservado ao painel. Use `regras` para ler as instruções dos agentes.")
        try:
            caminho_no_vault(self.painel.vault, nota.caminho)
        except CaminhoInseguro:
            raise ErroDeFerramenta("A nota usa um caminho vinculado ou fora do vault e não pode ser acessada.") from None

    @staticmethod
    def _visivel(nota: Nota) -> bool:
        return not ignorar(nota.rel) and Path(nota.rel).name.lower() not in {"agents.md", "agents.orquestra.md", "claude.md", "gemini.md"}

    def _resumo(self, nota: Nota) -> dict[str, Any]:
        self._conferir_nota(nota)
        modulo = self.painel.indice.modulo_de(nota.rel)
        campos = {k: v for k, v in nota.campos().items() if k not in ("criado_em",)}
        return {"caminho": nota.rel, "titulo": nota.titulo, "area": modulo.id if modulo else "", "campos": campos}

    @staticmethod
    def _e_da_pessoa(nota: Nota) -> bool:
        """Sem `origem`, a nota é da pessoa: foi escrita antes de existir o contrato."""
        return str(nota.meta.get("origem") or "humano") == "humano"

    # ------------------------------------------------------------ leitura

    @_sincronizado
    def regras(self) -> str:
        """Leia primeiro. Devolve o contrato do vault (AGENTS.md) e as áreas que existem, com os campos de cada uma."""
        self._em_dia()
        vault = self.painel.vault
        partes = []
        for nome in ("AGENTS.md", "AGENTS.orquestra.md"):
            try:
                arquivo = caminho_no_vault(vault, nome)
            except CaminhoInseguro:
                raise ErroDeFerramenta("O contrato do vault não pode ser um link ou junction.") from None
            if arquivo.is_file():
                partes.append(arquivo.read_text(encoding="utf-8-sig", errors="replace"))
        partes.append("# Áreas deste vault\n")
        for area in self.listar_areas(_ja_em_dia=True):
            campos = "; ".join(
                f"{c['nome']} ({c['tipo']}" + (": " + ", ".join(c["opcoes"]) if c["opcoes"] else "") + ")" for c in area["campos"]
            )
            partes.append(f"- **{area['id']}** ({area['nome']}): {area['descricao']} Campos: {campos or 'nenhum'}.")
        partes.append(
            "\nPor este conector, use as ferramentas em vez de editar arquivos: elas já aplicam as regras acima "
            "(origem, texto da pessoa intocado, nada apagado)."
        )
        return "\n".join(partes)

    @_sincronizado
    def listar_areas(self, _ja_em_dia: bool = False) -> list[dict[str, Any]]:
        """Lista as áreas (módulos) do vault, com campos, opções de status e quantos itens estão em aberto."""
        if not _ja_em_dia:
            self._em_dia()
        areas = []
        for m in self.painel.indice.modulos.values():
            resumo = self.painel.indice.resumo(m)
            areas.append(
                {
                    "id": m.id,
                    "nome": m.nome,
                    "descricao": m.descricao,
                    "campos": [{"nome": c.nome, "tipo": c.tipo, "opcoes": c.opcoes} for c in m.campos.values()],
                    "campo_status": m.campo_status if m.tem_status else "",
                    "concluidos": m.concluidos,
                    "total": resumo.total,
                    "em_aberto": resumo.abertos,
                    "para_decidir": resumo.decidir,
                }
            )
        return areas

    @_sincronizado
    def listar_itens(self, area: str, status: str = "", limite: int = 50) -> list[dict[str, Any]]:
        """Lista os itens de uma área. `status` filtra por um valor do campo de status (vazio = todos)."""
        self._em_dia()
        modulo = self._area(area)
        itens = self.painel.indice.itens(modulo.id)
        if status:
            itens = [n for n in itens if str(n.campo(modulo.campo_status) or "") == status]
        return [self._resumo(n) for n in itens[: max(1, min(int(limite), 200))]]

    @_sincronizado
    def ler_nota(self, caminho: str) -> dict[str, Any]:
        """Lê uma nota inteira: campos e texto. `caminho` é relativo ao vault (ex.: tarefas/itens/Nome.md) ou o nome da nota."""
        self._em_dia()
        nota = self._nota(caminho)
        return {**self._resumo(nota), "texto": nota.corpo, "e_da_pessoa": self._e_da_pessoa(nota)}

    @_sincronizado
    def buscar(self, termo: str, limite: int = 20) -> list[dict[str, Any]]:
        """Procura um termo no título e no texto de todas as notas do vault."""
        self._em_dia()
        return [self._resumo(n) for n in self.painel.indice.buscar(termo, max(1, min(int(limite), 60))) if self._visivel(n)]

    @_sincronizado
    def agenda(self, dia: str = "") -> list[dict[str, Any]]:
        """O que está marcado para um dia (AAAA-MM-DD; vazio = hoje). Em "hoje" entram também os atrasados."""
        self._em_dia()
        hoje = dt.date.today()
        try:
            alvo = dt.date.fromisoformat(dia) if dia else hoje
        except ValueError:
            raise ErroDeFerramenta("Use a data no formato AAAA-MM-DD.") from None
        achados = []
        for modulo in self.painel.indice.modulos.values():
            if not modulo.campo_data:
                continue
            for nota in self.painel.indice.itens(modulo.id):
                quando = data_de(nota, modulo)
                if quando is None or str(nota.campo(modulo.campo_status) or "") in modulo.concluidos:
                    continue
                if quando == alvo or (alvo == hoje and quando < hoje and modulo.tem_status):
                    achados.append({**self._resumo(nota), "atrasado": quando < hoje})
        return achados

    @_sincronizado
    def fila_de_decisoes(self) -> list[dict[str, Any]]:
        """Itens que esperam uma decisão da pessoa (perguntas de agentes e status de espera)."""
        self._em_dia()
        fila = []
        for modulo in self.painel.indice.modulos.values():
            for nota in self.painel.indice.itens(modulo.id):
                if espera_decisao(nota, modulo):
                    fila.append(self._resumo(nota))
        return fila

    @_sincronizado
    def respostas(self) -> list[dict[str, Any]]:
        """Itens em que a pessoa já respondeu uma pergunta (campo `resposta`). Aja e depois limpe com `atualizar_item`."""
        self._em_dia()
        return [self._resumo(n) for n in self.painel.indice.notas.values() if self._visivel(n) and str(n.meta.get("resposta") or "").strip()]

    # ------------------------------------------------------------ escrita

    def _executar(self, operacao):
        try:
            return operacao()
        except (Recusado, NaoEncontrado, ValorInvalido, FrontmatterInvalido, CaminhoInseguro) as e:
            raise ErroDeFerramenta(str(e)) from None
        except Conflito:
            raise ErroDeFerramenta("A nota mudou no disco enquanto você trabalhava. Leia de novo e repita.") from None
        except FileExistsError:
            raise ErroDeFerramenta("Já existe uma nota com esse nome.") from None

    @_sincronizado
    def criar_item(self, area: str, titulo: str, campos: dict[str, Any] | None = None, texto: str = "") -> dict[str, Any]:
        """Cria um item numa área. Fica marcado com `origem: agente`. Em campos de escolha, use só as opções da área."""
        self._em_dia()
        modulo = self._area(area)
        campos = {k: v for k, v in (campos or {}).items() if k != "origem"}
        desconhecidos = [k for k in campos if k not in modulo.campos]
        nota = self._executar(lambda: self.painel.criar_nota(modulo.id, titulo, campos, texto, origem="agente", autor=AUTOR))
        resposta = self._resumo(nota)
        if desconhecidos:
            resposta["ignorados"] = f"Campos que não existem nesta área e foram ignorados: {', '.join(desconhecidos)}."
        return resposta

    @_sincronizado
    def atualizar_item(
        self, caminho: str, campos: dict[str, Any] | None = None, acrescentar: str = "", novo_texto: str = ""
    ) -> dict[str, Any]:
        """Altera campos de um item e/ou acrescenta texto ao final.

        - `campos`: valores a mudar (status, data, tags...). Valor vazio remove o campo.
        - `acrescentar`: texto novo, colocado ao final. Em nota da pessoa, entra sob "## Notas do agente".
        - `novo_texto`: substitui o texto inteiro. Só é aceito em notas que um agente criou.
        """
        self._em_dia()
        nota = self._nota(caminho)
        zona = self.painel.indice.zona_de(nota.rel)
        modulo = self.painel.indice.modulo_de(nota.rel)
        campos = dict(campos or {})
        da_pessoa = self._e_da_pessoa(nota)

        if zona in ("maquina", "arquivo"):
            raise ErroDeFerramenta("Esta nota fica em maquina/ ou arquivo/ e não é alterada por aqui. Para registrar o que aprendeu, use `registrar_aprendizado`.")
        fora_de_area = modulo is None or zona != "itens"
        if fora_de_area and campos:
            raise ErroDeFerramenta("Esta nota é da pessoa (está em humano/ ou numa pasta dela). Você pode só acrescentar texto, com `acrescentar`.")
        if "origem" in campos:
            raise ErroDeFerramenta("O campo `origem` diz quem escreveu a nota e não pode ser alterado.")
        if str(campos.get("resposta") or "").strip():
            raise ErroDeFerramenta("`resposta` é escrita pela pessoa. Você só pode limpá-la (valor vazio) depois de agir.")
        if novo_texto and (da_pessoa or fora_de_area or str(nota.meta.get("origem") or "") != "agente"):
            raise ErroDeFerramenta("O texto desta nota não pode ser substituído por um agente. Use `acrescentar`.")

        corpo = None
        if novo_texto:
            corpo = "\n" + novo_texto.strip() + "\n"
        elif acrescentar.strip():
            atual = nota.corpo
            hoje = dt.date.today().isoformat()
            if fora_de_area:
                bloco = f"> Acrescentado por agente em {hoje}:\n" + "\n".join("> " + linha for linha in acrescentar.strip().splitlines())
            elif da_pessoa and "## Notas do agente" not in atual:
                bloco = f"## Notas do agente\n\n{acrescentar.strip()}"
            else:
                bloco = acrescentar.strip()
            # Acrescentar não dá licença para remover espaços ou linhas vazias
            # que a pessoa já escreveu no final da nota.
            separador = "" if atual.endswith("\n\n") else "\n" if atual.endswith("\n") or not atual else "\n\n"
            corpo = atual + separador + bloco + "\n"
        if corpo is None and not campos:
            raise ErroDeFerramenta("Nada para alterar: informe `campos`, `acrescentar` ou `novo_texto`.")

        atualizada = self._executar(lambda: self.painel.editar_nota(nota.rel, nota.versao, campos=campos or None, corpo=corpo, autor=AUTOR))
        resposta = self._resumo(atualizada)
        avisos = validar(modulo, atualizada.meta) if modulo and zona == "itens" else []
        if avisos:
            resposta["avisos"] = avisos
        return resposta

    @_sincronizado
    def perguntar(self, caminho: str, pergunta: str) -> dict[str, Any]:
        """Deixa uma pergunta para a pessoa num item. Ele aparece na fila Decidir do painel; a resposta volta em `resposta`."""
        if not pergunta.strip():
            raise ErroDeFerramenta("Escreva a pergunta.")
        return self.atualizar_item(caminho, campos={"pergunta": " ".join(pergunta.split())})

    @_sincronizado
    def capturar(self, texto: str, palavras_da_pessoa: bool = False) -> dict[str, Any]:
        """Guarda uma anotação rápida na área de captura (a "entrada"), para ser organizada depois.

        Marque `palavras_da_pessoa` só quando o texto for exatamente o que ela disse ou
        escreveu. Se você resumiu ou reescreveu, deixe falso: um resumo seu não é fala dela.
        """
        self._em_dia()
        texto = texto.strip()
        if not texto:
            raise ErroDeFerramenta("Escreva o que deve ser guardado.")
        destino = self.painel.config.captura
        if destino not in self.painel.indice.modulos:
            raise ErroDeFerramenta("Este vault não tem uma área de captura. Use `criar_item` numa das áreas (veja `listar_areas`).")
        primeira = texto.splitlines()[0].strip()
        titulo = primeira if len(primeira) <= 70 else primeira[:67].rstrip() + "..."
        origem = "humano" if palavras_da_pessoa else "agente"
        nota = self._executar(lambda: self.painel.criar_nota(destino, titulo, {}, texto, origem=origem, autor=AUTOR))
        return self._resumo(nota)

    @_sincronizado
    def registrar_numeros(self, valores: dict[str, float], dia: str = "", area: str = "numeros") -> dict[str, Any]:
        """Grava os números de um dia (uma nota por dia). Só números lidos de uma fonte: nunca estime nem complete."""
        self._em_dia()
        modulo = self._area(area)
        try:
            quando = dt.date.fromisoformat(dia) if dia else None
        except ValueError:
            raise ErroDeFerramenta("Use a data no formato AAAA-MM-DD.") from None
        if quando and quando > dt.date.today():
            raise ErroDeFerramenta("Não dá para registrar números de um dia que ainda não chegou.")
        fora = [k for k in valores if k not in modulo.campos_numericos]
        if fora:
            raise ErroDeFerramenta(
                f"Campos que não existem em '{area}': {', '.join(fora)}. Campos de número disponíveis: {', '.join(modulo.campos_numericos) or 'nenhum'}."
            )
        nota = self._executar(lambda: self.painel.registrar_numeros(modulo.id, valores, quando, origem="agente", autor=AUTOR))
        return self._resumo(nota)

    @_sincronizado
    def registrar_aprendizado(self, area: str, aprendizado: str) -> str:
        """Anota, numa linha, algo que vale para a próxima vez nesta área: uma correção da pessoa, o que funcionou, o que evitar."""
        self._em_dia()
        modulo = self._area(area)
        caminho = self._executar(lambda: self.painel.registrar_aprendizado(modulo.id, aprendizado, AUTOR))
        return f"Anotado em {caminho.relative_to(self.painel.vault).as_posix()}."

    @_sincronizado
    def aprendizados(self, area: str) -> str:
        """O que os agentes já aprenderam trabalhando nesta área. Leia antes de começar um trabalho nela."""
        self._em_dia()
        modulo = self._area(area)
        try:
            arquivo = caminho_no_vault(self.painel.vault, modulo.pasta / "maquina" / "aprendizados.md")
        except CaminhoInseguro:
            raise ErroDeFerramenta("Os aprendizados não podem usar links ou caminhos fora do vault.") from None
        return arquivo.read_text(encoding="utf-8-sig", errors="replace") if arquivo.is_file() else "Ainda não há aprendizados nesta área."

    @_sincronizado
    def registrar_sessao(self, agente: str, pedido: str, feito: str, pendente: str = "") -> str:
        """Ao terminar, registra no diário o que foi pedido, o que foi feito e o que ficou pendente. Uma linha cada."""
        caminho = self._executar(lambda: self.painel.registrar_sessao(agente, pedido, feito, pendente))
        return f"Sessão registrada em {caminho.relative_to(self.painel.vault).as_posix()}."

    @_sincronizado
    def sessoes_recentes(self, dias: int = 3) -> str:
        """O relato das últimas sessões de trabalho dos agentes. É a memória entre uma conversa e outra."""
        hoje = dt.date.today()
        datas = [hoje - dt.timedelta(days=i) for i in range(max(1, min(int(dias), 14)))]
        try:
            for dia in datas:
                caminho_no_vault(self.painel.vault, self.painel.vault / diario.PASTA_SESSOES / f"{dia.isoformat()}.md")
        except CaminhoInseguro:
            raise ErroDeFerramenta("As sessões não podem usar links ou caminhos fora do vault.") from None
        textos = [diario.ler_sessoes(self.painel.vault, dia) for dia in datas]
        return "\n\n".join(t.strip() for t in textos if t.strip()) or "Nenhuma sessão registrada nos últimos dias."


FERRAMENTAS = [
    "regras", "listar_areas", "listar_itens", "ler_nota", "buscar", "agenda", "fila_de_decisoes", "respostas",
    "criar_item", "atualizar_item", "perguntar", "capturar", "registrar_numeros",
    "aprendizados", "registrar_aprendizado", "sessoes_recentes", "registrar_sessao",
]


def criar_servidor(vault: Path):
    """Monta o servidor MCP com as ferramentas acima."""
    try:
        try:
            from mcp.server.mcpserver import MCPServer as Servidor  # mcp 2.x
        except ModuleNotFoundError as erro:  # mcp 1.x usa o nome antigo
            if erro.name != "mcp.server.mcpserver":
                raise
            from mcp.server.fastmcp import FastMCP as Servidor
    except ImportError:
        raise RuntimeError(
            "Não consegui carregar o SDK MCP. No projeto, execute `uv sync --frozen` "
            "para restaurar as versões compatíveis. Se instalou um pacote, reinstale "
            "o Orquestra e suas dependências no mesmo ambiente Python."
        ) from None

    ferramentas = Ferramentas(vault)
    servidor = Servidor("orquestra", instructions=INSTRUCOES)
    for nome in FERRAMENTAS:
        metodo = getattr(ferramentas, nome)
        if nome == "listar_areas":
            # O parâmetro interno não é para o agente: expomos uma versão sem ele.
            def listar_areas() -> list[dict[str, Any]]:
                return ferramentas.listar_areas()

            listar_areas.__doc__ = metodo.__doc__
            metodo = listar_areas
        servidor.tool(name=nome)(metodo)
    return servidor


def executar(vault: Path) -> None:
    """Roda o servidor pela entrada e saída padrão, como os clientes MCP locais esperam."""
    criar_servidor(vault).run()
