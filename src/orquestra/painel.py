"""O núcleo do painel: junta vault, índice, eventos e as operações sobre notas.

Tudo que altera o vault passa por aqui, seja pelo navegador, pela linha de comando
ou pelo agendador. Assim as regras (checagem de versão, registro no diário, aviso
às abas abertas) valem para todo mundo.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import threading
from copy import deepcopy
from functools import wraps
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap

from orquestra import adocao, aparencia, backup, coletores, diario, preparo, temas
from orquestra import armazenamento
from orquestra.caminhos import CaminhoInseguro, caminho_no_vault
from orquestra.config import ConfigPainel, gravar_yaml, ler_config_painel, ler_yaml
from orquestra.eventos import Eventos
from orquestra.indice import Indice, Mudanca, deve_ignorar
from orquestra.modulos import ARQUIVO_MODULO, TIPOS_DE_CAMPO, ColetorDef, Modulo, carregar_modulo, converter, padroes
from orquestra.notas import Conflito, Nota, caminho_livre, gravar_nota, ler_nota, nome_de_arquivo

ARQUIVOS_DE_CONFIG = {"orquestra.yaml", ARQUIVO_MODULO, "tema.yaml"}
ZONAS_DE_ESCRITA = {"itens", "humano"}
registro = logging.getLogger(__name__)


def _sincronizado(funcao):
    @wraps(funcao)
    def executar(self, *args, **kwargs):
        with self._trava:
            return funcao(self, *args, **kwargs)
    return executar


class NaoEncontrado(Exception):
    pass


class Recusado(Exception):
    """Operação recusada, com uma explicação para mostrar ao usuário."""


class Painel:
    def __init__(self, vault: Path):
        self._trava = threading.RLock()
        self.vault = vault.resolve()
        self.indice = Indice(self.vault)
        self.indice.carregar()
        self.eventos = Eventos()
        self.avisos: list[str] = []
        self.config: ConfigPainel = ConfigPainel()
        self.config.backup.auto_commit = False
        try:
            caminho_no_vault(self.vault, "orquestra.yaml")
            self.config = ler_config_painel(self.vault)
        except (ValueError, OSError) as erro:
            self.avisos = [f"Não consegui ler orquestra.yaml: {str(erro).splitlines()[0]}. Corrija no Obsidian para voltar a salvar configurações."]
        self.tema: dict[str, Any] = temas.carregar(self.vault, self.config.tema)
        self.indice.ordenar_modulos(self.config.ordem_pastas)
        self.rodando: set[str] = set()  # coletores em execução agora
        # Há algo que ainda não entrou no histórico? Ao abrir não sabemos, então conferimos uma vez.
        self.mudou_desde_o_backup = True

    # ------------------------------------------------------------ recargas

    @_sincronizado
    def recarregar_config(self, *, modulos: bool = True) -> None:
        try:
            caminho_no_vault(self.vault, "orquestra.yaml")
            config = ler_config_painel(self.vault)
            tema = temas.carregar(self.vault, config.tema)
        except (ValueError, OSError) as erro:
            self.avisos = [f"Não consegui ler orquestra.yaml: {str(erro).splitlines()[0]}. Usando a última configuração válida."]
            return
        self.config, self.tema, self.avisos = config, tema, []
        self.indice.ordenar_modulos(config.ordem_pastas)
        if modulos:
            self.indice.recarregar_modulos()

    @_sincronizado
    def recarregar_tudo(self) -> None:
        """Usado quando uma pasta inteira é renomeada ou apagada."""
        self.indice.carregar()
        self.recarregar_config()
        self.eventos.publicar({"tipo": "config"})

    # ------------------------------------------------------------ caminhos

    def caminho_seguro(self, rel: str) -> Path:
        """Converte um caminho relativo em absoluto, garantindo que fica dentro do vault."""
        try:
            return caminho_no_vault(self.vault, rel)
        except CaminhoInseguro:
            raise NaoEncontrado("Caminho fora do vault ou link não permitido.") from None

    def modulo(self, modulo_id: str) -> Modulo:
        modulo = self.indice.modulos.get(modulo_id)
        if modulo is None:
            raise NaoEncontrado(f"Módulo '{modulo_id}' não existe.")
        caminho_no_vault(self.vault, modulo.pasta / ARQUIVO_MODULO)
        return modulo

    def nota(self, rel: str) -> Nota:
        self.caminho_seguro(rel)
        nota = self.indice.notas.get(rel)
        if nota is None:
            raise NaoEncontrado(rel)
        return nota

    def _modulo_para_escrita(self, modulo: Modulo) -> Modulo:
        caminho_no_vault(self.vault, modulo.pasta / ARQUIVO_MODULO)
        atual = carregar_modulo(modulo.pasta)
        if atual.invalido:
            raise Recusado("A configuração desta área está inválida. Corrija o _modulo.yaml no editor antes de gravar nesta área.")
        return atual

    # ------------------------------------------------------------ mudanças

    @_sincronizado
    def apos_escrita(self, caminho: Path, autor: str) -> Mudanca | None:
        """Atualiza o índice, registra no diário e avisa as abas abertas.

        É chamado tanto depois de uma gravação feita pelo painel quanto pelo vigia,
        quando o arquivo muda por fora (Obsidian, agente). Como o índice compara o
        conteúdo, a mesma mudança nunca é registrada duas vezes.
        """
        mudanca = self.indice.atualizar(caminho)
        if mudanca is None:
            return None
        self.mudou_desde_o_backup = True
        detalhe = diario.resumir(mudanca.antes, mudanca.depois) if mudanca.tipo == "editado" else ""
        try:
            diario.registrar(self.vault, mudanca.tipo, mudanca.rel, detalhe, autor)
        except (OSError, ValueError):
            registro.warning("Não foi possível acrescentar esta mudança ao diário.", exc_info=True)
        self.eventos.publicar(
            {
                "tipo": "nota",
                "acao": mudanca.tipo,
                "rel": mudanca.rel,
                "modulo": mudanca.rel.split("/", 1)[0],
                "versao": mudanca.depois.versao if mudanca.depois else "",
            }
        )
        return mudanca

    @_sincronizado
    def ao_mudar_arquivos(self, caminhos: set[Path]) -> None:
        """Chamado pelo vigia com os arquivos que mudaram no disco."""
        mudou_config = False
        for caminho in caminhos:
            try:
                rel = caminho_no_vault(self.vault, caminho).relative_to(self.vault).as_posix()
            except (CaminhoInseguro, OSError):
                continue
            if deve_ignorar(rel) and caminho.name not in ARQUIVOS_DE_CONFIG:
                continue
            self.mudou_desde_o_backup = True
            if caminho.name in ARQUIVOS_DE_CONFIG:
                mudou_config = True
            else:
                self.apos_escrita(caminho, "externo")
        if mudou_config:
            self.recarregar_config()
            self.eventos.publicar({"tipo": "config"})

    # ------------------------------------------------------------ notas

    @_sincronizado
    def evento_agenda(self, rel: str) -> dict:
        from orquestra import calendario
        nota = self.nota(rel)
        modulo = self.indice.modulo_de(rel)
        if not modulo or self.indice.zona_de(rel) != "itens" or not modulo.campo_data:
            raise Recusado("Este arquivo não é um item com data da agenda.")
        evento = calendario.evento(nota, modulo)
        if evento is None:
            raise Recusado("Esta nota não tem uma data válida.")
        return {**evento, "corpo": nota.corpo}

    @_sincronizado
    def salvar_evento_agenda(self, dados: dict) -> Nota:
        from orquestra import calendario
        try:
            campos = calendario.validar_evento(dados)
        except ValueError as erro:
            raise Recusado(str(erro)) from None
        if not dados["titulo"].strip():
            raise Recusado("Dê um título para o compromisso.")
        if dados.get("rel"):
            self.evento_agenda(dados["rel"])
            modulo = self.indice.modulo_de(dados["rel"])
            campos[modulo.campo_data] = campos.pop("data")
            return self.editar_nota(dados["rel"], dados.get("versao"), titulo=dados["titulo"], corpo=dados.get("corpo", ""), campos=campos)
        if "agenda" not in self.indice.modulos:
            self.adicionar_modulo("agenda")
        modulo = self.modulo("agenda")
        if not set(campos).issubset(modulo.campos):
            raise Recusado("A pasta agenda existente tem outro formato. Configure os campos da Agenda pessoal antes de criar compromissos.")
        return self.criar_nota("agenda", dados["titulo"], campos, dados.get("corpo", ""))

    @_sincronizado
    def mover_evento_agenda(self, dados: dict) -> Nota:
        from orquestra import calendario
        evento = self.evento_agenda(dados["rel"])
        novo_dia = calendario.data(dados["data"])
        if not novo_dia or not 2 <= novo_dia.year <= 9998:
            raise Recusado("Escolha uma data válida.")
        inicio = dt.datetime.fromisoformat(evento["data"] + "T" + (evento["hora"] or "00:00"))
        fim = dt.datetime.fromisoformat(evento["data_fim"] + "T" + (evento["hora_fim"] or "00:00"))
        nova_hora = calendario.hora(dados.get("hora")) if dados.get("hora") is not None else evento["hora"]
        if dados.get("hora") is not None and not nova_hora:
            raise Recusado("Horário inválido.")
        novo_inicio = dt.datetime.combine(novo_dia, dt.time.fromisoformat(nova_hora or "00:00"))
        try:
            novo_fim = novo_inicio + (fim - inicio)
        except OverflowError:
            raise Recusado("O término fica fora do intervalo de datas permitido.") from None
        pedido = {**evento, "versao": dados["versao"], "data": novo_dia.isoformat(), "data_fim": novo_fim.date().isoformat(),
                  "hora": nova_hora, "hora_fim": novo_fim.strftime("%H:%M") if nova_hora else "", "dia_inteiro": not nova_hora}
        # Ao atribuir horário a um item de dia inteiro, use uma hora de duração.
        if evento["dia_inteiro"] and nova_hora:
            fim_horario = novo_inicio + dt.timedelta(hours=1)
            pedido.update(data_fim=fim_horario.date().isoformat(), hora_fim=fim_horario.strftime("%H:%M"))
        return self.salvar_evento_agenda(pedido)

    @_sincronizado
    def criar_nota(
        self,
        modulo_id: str,
        titulo: str,
        campos: dict[str, Any] | None = None,
        corpo: str = "",
        zona: str = "itens",
        origem: str = "humano",
        autor: str = "painel",
    ) -> Nota:
        modulo = self._modulo_para_escrita(self.modulo(modulo_id))
        titulo = (titulo or "").strip()
        if not titulo:
            raise Recusado("Dê um título para a nota.")
        if zona not in ZONAS_DE_ESCRITA:
            raise Recusado("Pelo painel só é possível criar notas em 'itens' ou 'humano'.")

        meta = CommentedMap()
        if nome_de_arquivo(titulo) != titulo:
            meta["titulo"] = titulo
        if zona == "itens":
            meta.update(padroes(modulo))
            for nome, valor in (campos or {}).items():
                campo = modulo.campos.get(nome)
                if campo is None:
                    continue
                convertido = converter(campo, valor)
                if convertido is None:
                    meta.pop(nome, None)
                else:
                    meta[nome] = convertido
        if origem != "humano" or "origem" in modulo.campos or zona == "humano":
            meta["origem"] = origem
        meta["criado_em"] = dt.date.today()

        corpo = (corpo or "").replace("\r\n", "\n").strip()
        pasta = caminho_no_vault(self.vault, modulo.pasta_itens if zona == "itens" else modulo.pasta / zona)
        caminho = caminho_no_vault(self.vault, caminho_livre(pasta, titulo))
        nota = Nota(
            caminho=caminho,
            rel=caminho.relative_to(self.vault).as_posix(),
            meta=meta,
            corpo=("\n" + corpo + "\n") if corpo else "",
            vault=self.vault,
        )
        gravar_nota(nota, criar=True)
        self.apos_escrita(caminho, autor)
        return self.indice.notas.get(nota.rel, nota)

    @_sincronizado
    def criar_nota_em_pasta(self, pasta: str, titulo: str, corpo: str = "", origem: str = "humano", autor: str = "painel") -> Nota:
        """Cria uma nota numa pasta qualquer do vault (não precisa ser módulo)."""
        pasta = pasta.strip().strip("/")
        titulo = (titulo or "").strip()
        if not titulo:
            raise Recusado("Dê um título para a nota.")
        destino = self.caminho_seguro(pasta) if pasta else self.vault
        if not destino.is_dir() or (pasta and deve_ignorar(pasta + "/x.md")):
            raise NaoEncontrado(pasta or "/")
        partes = pasta.split("/") if pasta else []
        modulo = self.indice.modulos.get(partes[0]) if partes else None
        if modulo and len(partes) > 1 and partes[1] == "maquina":
            raise Recusado("A pasta maquina/ é dos agentes e dos coletores. Crie a nota em outro lugar.")
        meta = CommentedMap()
        if nome_de_arquivo(titulo) != titulo:
            meta["titulo"] = titulo
        # Dentro de um módulo montado sobre a pasta, a nota nova já nasce com os campos dele.
        if modulo and self.indice.zona_de(pasta + "/x.md") == "itens":
            meta.update(padroes(modulo))
        if origem != "humano" or (modulo and "origem" in modulo.campos):
            meta["origem"] = origem
        corpo = (corpo or "").replace("\r\n", "\n").strip()
        caminho = caminho_livre(destino, titulo)
        nota = Nota(
            caminho=caminho,
            rel=caminho.relative_to(self.vault).as_posix(),
            meta=meta,
            corpo=("\n" + corpo + "\n") if meta and corpo else (corpo + "\n" if corpo else ""),
            vault=self.vault,
        )
        gravar_nota(nota, criar=True)
        self.apos_escrita(caminho, autor)
        return self.indice.notas.get(nota.rel, nota)

    @_sincronizado
    def editar_nota(
        self,
        rel: str,
        versao: str | None,
        titulo: str | None = None,
        campos: dict[str, Any] | None = None,
        corpo: str | None = None,
        autor: str = "painel",
    ) -> Nota:
        caminho = self.caminho_seguro(rel)
        if deve_ignorar(rel):
            raise NaoEncontrado(rel)
        if not caminho.is_file() or caminho.suffix.lower() != ".md":
            if versao and caminho.suffix.lower() == ".md":
                raise Conflito("A nota foi removida ou movida. Preserve o rascunho como uma nova nota.")
            raise NaoEncontrado(rel)
        # Relemos do disco: o índice pode estar uma fração de segundo atrasado.
        nota = ler_nota(caminho, self.vault)
        if not versao:
            raise Recusado("Informe a versão da nota antes de editar. Reabra a nota e tente novamente.")
        if nota.versao != versao:
            raise Conflito("Esta nota mudou no disco depois que você abriu. Preserve o rascunho antes de recarregar.")
        if nota.erro:
            raise Recusado("O frontmatter desta nota está com erro. Corrija no Obsidian antes de editar aqui.")

        modulo = self.indice.modulo_de(rel)
        if modulo:
            modulo = self._modulo_para_escrita(modulo)
        if titulo is not None and titulo.strip() and titulo.strip() != nota.titulo:
            nota.meta["titulo"] = titulo.strip()
        for nome, valor in (campos or {}).items():
            campo = modulo.campos.get(nome) if modulo else None
            if campo is not None:
                convertido = converter(campo, valor)
            elif isinstance(valor, str):
                convertido = valor.strip() or None  # campo livre (ex.: pergunta)
            else:
                convertido = valor
            if convertido is None:
                nota.meta.pop(nome, None)
            else:
                nota.meta[nome] = convertido
        if corpo is not None:
            nota.corpo = corpo.replace("\r\n", "\n")

        gravar_nota(nota, versao_esperada=nota.versao)
        self.apos_escrita(caminho, autor)
        return self.indice.notas.get(rel, nota)

    @_sincronizado
    def arquivar(self, rel: str, autor: str = "painel", versao: str | None = None) -> str:
        """Move a nota para a pasta arquivo/ do módulo. Nada é apagado."""
        caminho = self.caminho_seguro(rel)
        modulo = self.indice.modulo_de(rel)
        if not caminho.is_file() or modulo is None:
            raise NaoEncontrado(rel)
        if self.indice.zona_de(rel) == "arquivo":
            raise Recusado("Esta nota já está arquivada.")
        nota = ler_nota(caminho, self.vault)
        if versao is not None and versao != nota.versao:
            raise Conflito("A nota mudou no disco. Reabra a versão atual antes de arquivar.")
        pasta = caminho_no_vault(self.vault, modulo.pasta / "arquivo")
        destino = caminho_no_vault(self.vault, caminho_livre(pasta, caminho.stem))
        armazenamento.mover_seguro(caminho, destino, esperado=nota.versao,
                                   validar=lambda: (caminho_no_vault(self.vault, caminho), caminho_no_vault(self.vault, destino)))
        self.indice.atualizar(caminho)  # some do índice
        self.indice.atualizar(destino)  # reaparece em arquivo/
        novo_rel = destino.relative_to(self.vault).as_posix()
        try:
            diario.registrar(self.vault, "arquivado", rel, f"movido para {novo_rel}", autor)
        except (OSError, ValueError):
            registro.warning("Nota arquivada, mas não foi possível registrar no diário.")
        self.eventos.publicar({"tipo": "nota", "acao": "removido", "rel": rel, "modulo": modulo.id, "versao": ""})
        self.mudou_desde_o_backup = True
        return novo_rel

    @_sincronizado
    def copiar_nota(self, rel: str, titulo: str, corpo: str, campos: dict[str, Any] | None = None) -> Nota:
        """Preserva o arquivo atual e salva um rascunho recuperado ao lado dele."""
        caminho = self.caminho_seguro(rel)
        if caminho.suffix.lower() != ".md" or deve_ignorar(rel):
            raise NaoEncontrado(rel)
        try:
            original = ler_nota(caminho, self.vault)
        except FileNotFoundError:
            original = self.indice.notas.get(rel) or Nota(caminho, rel, vault=self.vault)
        if original.erro:
            raise Recusado("Corrija o formato da nota original antes de copiar suas propriedades.")
        if self.indice.zona_de(rel) in ("maquina", "arquivo"):
            raise Recusado("Salve a cópia em uma pasta de notas ou itens.")
        modulo = self.indice.modulo_de(rel)
        if modulo:
            modulo = self._modulo_para_escrita(modulo)
        meta = deepcopy(original.meta)
        for nome, valor in (campos or {}).items():
            campo = modulo.campos.get(nome) if modulo else None
            convertido = converter(campo, valor) if campo else valor
            if convertido is None:
                meta.pop(nome, None)
            else:
                meta[nome] = convertido
        titulo = titulo.strip() or original.titulo + " - rascunho"
        meta["titulo"] = titulo
        destino = caminho_no_vault(self.vault, caminho_livre(original.caminho.parent, titulo))
        nota = Nota(destino, destino.relative_to(self.vault).as_posix(), meta=meta, corpo=corpo, vault=self.vault)
        gravar_nota(nota, criar=True)
        self.apos_escrita(destino, "painel")
        return nota

    @_sincronizado
    def recuperar_como_copia(self, rel: str, identificador: str, tipo: str, titulo: str = "") -> Nota:
        caminho = self.caminho_seguro(rel)
        if caminho.suffix.lower() != ".md" or deve_ignorar(rel) or self.indice.zona_de(rel) in ("maquina", "arquivo"):
            raise Recusado("Escolha uma nota em uma pasta de notas ou itens para recuperar uma cópia.")
        try:
            bruto = armazenamento.ler_recuperacao(caminho, identificador, tipo=tipo)
        except (FileNotFoundError, ValueError):
            raise NaoEncontrado("Essa versão de recuperação não está disponível.") from None
        destino = caminho_no_vault(self.vault, caminho_livre(caminho.parent, titulo.strip() or caminho.stem + " - recuperada"))
        armazenamento.gravar_bytes(destino, bruto, criar=True, validar=lambda: caminho_no_vault(self.vault, destino))
        self.apos_escrita(destino, "painel")
        return ler_nota(destino, self.vault)

    # ------------------------------------------------------------ estado

    @property
    def _arquivo_estado(self) -> Path:
        return caminho_no_vault(self.vault, "_orquestra/estado.json")

    def ler_estado(self) -> dict[str, Any]:
        try:
            estado = json.loads(self._arquivo_estado.read_text(encoding="utf-8"))
            return estado if isinstance(estado, dict) else {}
        except (OSError, ValueError):
            return {}

    @_sincronizado
    def gravar_estado(self, secao: str, chave: str, valor: Any) -> None:
        def alterar(bruto: bytes) -> bytes:
            try:
                estado = json.loads(bruto) if bruto else {}
            except ValueError:
                estado = {}
            if not isinstance(estado, dict):
                estado = {}
            if not isinstance(estado.get(secao), dict):
                estado[secao] = {}
            estado[secao][chave] = valor
            return json.dumps(estado, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            armazenamento.atualizar_bytes(self._arquivo_estado, alterar, backup=False,
                                         validar=lambda: caminho_no_vault(self.vault, "_orquestra/estado.json"))
        except (OSError, ValueError):
            registro.warning("Não foi possível salvar o estado do painel.", exc_info=True)

    # ------------------------------------------------------------ coletores

    def coletor(self, modulo_id: str, script: str) -> tuple[Modulo, ColetorDef]:
        modulo = self.modulo(modulo_id)
        for coletor in modulo.coletores:
            if coletor.script == script:
                return modulo, coletor
        raise NaoEncontrado(f"Coletor '{script}' não existe em {modulo_id}.")

    @_sincronizado
    def _concluir_coleta(self, modulo: Modulo, coletor: ColetorDef, itens: list, erro: str) -> coletores.Resultado:
        if erro:
            resultado = coletores.Resultado(False, erro=erro)
        else:
            criadas, repetidos = coletores.importar(self.indice, modulo, coletor, itens)
            for nota in criadas:
                self.apos_escrita(nota.caminho, f"coletor:{Path(coletor.script).stem}")
            resultado = coletores.Resultado(True, len(criadas), repetidos)
        self.gravar_estado(
            "coletores",
            f"{modulo.id}/{coletor.script}",
            {
                "ultima": dt.datetime.now().isoformat(timespec="seconds"),
                "ok": resultado.ok,
                "novos": resultado.novos,
                "repetidos": resultado.repetidos,
                "erro": resultado.erro,
            },
        )
        self.eventos.publicar({"tipo": "coletor", "modulo": modulo.id})
        return resultado

    def rodar_coletor_agora(self, modulo: Modulo, coletor: ColetorDef) -> coletores.Resultado:
        """Versão síncrona, usada pela linha de comando."""
        itens, erro = coletores.rodar_script(self.vault, modulo, coletor)
        return self._concluir_coleta(modulo, coletor, itens, erro)

    async def rodar_coletor(self, modulo: Modulo, coletor: ColetorDef) -> coletores.Resultado:
        """Versão assíncrona: o script roda em outra thread para não travar o painel."""
        chave = f"{modulo.id}/{coletor.script}"
        if chave in self.rodando:
            return coletores.Resultado(False, erro="Este coletor já está rodando.")
        self.rodando.add(chave)
        try:
            itens, erro = await asyncio.to_thread(coletores.rodar_script, self.vault, modulo, coletor)
            return await asyncio.to_thread(self._concluir_coleta, modulo, coletor, itens, erro)
        finally:
            self.rodando.discard(chave)

    def ultima_coleta(self, modulo_id: str, script: str) -> dict[str, Any]:
        return self.ler_estado().get("coletores", {}).get(f"{modulo_id}/{script}", {})

    @_sincronizado
    def definir_coletor_ativo(self, modulo_id: str, script: str, ativo: bool) -> None:
        """Liga ou desliga um coletor alterando só essa chave no _modulo.yaml."""
        modulo, _ = self.coletor(modulo_id, script)
        caminho = caminho_no_vault(self.vault, modulo.pasta / ARQUIVO_MODULO)
        dados = ler_yaml(caminho)
        for definicao in dados.get("coletores") or []:
            if isinstance(definicao, dict) and str(definicao.get("script")) == script:
                definicao["ativo"] = bool(ativo)
        gravar_yaml(caminho, dados)
        self.indice.recarregar_modulos()

    # ------------------------------------------------------------ tema e backup

    @_sincronizado
    def definir_tema(self, tema_id: str) -> None:
        if tema_id not in {t["id"] for t in temas.listar(self.vault)}:
            raise NaoEncontrado(f"Tema '{tema_id}' não existe.")
        caminho = caminho_no_vault(self.vault, "orquestra.yaml")
        dados = ler_yaml(caminho)
        dados["tema"] = tema_id
        gravar_yaml(caminho, dados)
        self.recarregar_config()

    def fazer_backup(self, enviar: bool = False) -> dict[str, str]:
        with self._trava:
            self.mudou_desde_o_backup = False
        resultado = {"commit": backup.commit(self.vault)}
        if resultado["commit"] not in ("feito", "nada"):
            self.mudou_desde_o_backup = True  # não deu: tenta de novo na próxima volta
        agora = dt.datetime.now().isoformat(timespec="seconds")
        self.gravar_estado("backup", "tentativa_commit", agora)
        self.gravar_estado("backup", "resultado_commit", resultado["commit"])
        if resultado["commit"] in ("feito", "nada"):
            self.gravar_estado("backup", "ultimo_commit", agora)
        if enviar:
            resultado["push"] = backup.push(self.vault) if resultado["commit"] in ("feito", "nada") else "erro: corrija o histórico local antes de enviar"
            self.gravar_estado("backup", "tentativa_push", agora)
            if resultado["push"] == "feito":
                self.gravar_estado("backup", "ultimo_push", agora)
            self.gravar_estado("backup", "resultado_push", resultado["push"])
        return resultado

    def iniciar_backup(self) -> bool:
        """Liga o histórico em git neste vault e o commit automático."""
        if not backup.iniciar(self.vault):
            raise Recusado("O git não está instalado. Instale em https://git-scm.com e tente de novo.")
        self.definir_config(auto_commit=True)
        return True

    # ------------------------------------------------------------ personalização

    @_sincronizado
    def definir_config(
        self,
        nome: str | None = None,
        captura: str | None = None,
        auto_commit: bool | None = None,
        visual: dict[str, Any] | None = None,
        ordem_pastas: list[str] | None = None,
    ) -> None:
        """Altera o orquestra.yaml preservando os comentários do arquivo."""
        caminho = caminho_no_vault(self.vault, "orquestra.yaml")
        dados = ler_yaml(caminho)
        if nome is not None:
            nome = nome.strip()
            if not nome:
                raise Recusado("O painel precisa de um nome.")
            dados["nome"] = nome[:60]
        if captura is not None:
            if captura and captura not in self.indice.modulos:
                raise NaoEncontrado(f"Módulo '{captura}' não existe.")
            dados["captura"] = captura
        if auto_commit is not None:
            if not isinstance(dados.get("backup"), dict):
                dados["backup"] = CommentedMap()
            dados["backup"]["auto_commit"] = bool(auto_commit)
        if ordem_pastas is not None:
            if len(set(ordem_pastas)) != len(ordem_pastas) or set(ordem_pastas) != set(self.indice.modulos):
                raise Recusado("A lista de pastas mudou. Recarregue antes de reordenar.")
            dados["ordem_pastas"] = ordem_pastas
        if visual:
            try:
                escolhas = aparencia.validar(visual)
            except ValueError as e:
                raise Recusado(str(e)) from None
            if not isinstance(dados.get("aparencia"), dict):
                dados["aparencia"] = CommentedMap()
            for chave, valor in escolhas.items():
                dados["aparencia"][chave] = valor
        gravar_yaml(caminho, dados)
        self.recarregar_config()
        self.eventos.publicar({"tipo": "config"})

    def adicionar_modulo(self, modulo_id: str, exemplos: bool = False) -> Modulo:
        """Copia um módulo pronto do catálogo para o vault."""
        try:
            relatorio = preparo.Relatorio(self.vault)
            if not preparo.adicionar_modulo(self.vault, modulo_id, exemplos, relatorio):
                raise Recusado(relatorio.avisos[-1])
        except preparo.PastaRecusada as e:
            raise Recusado(str(e)) from None
        self.recarregar_tudo()
        return self.modulo(modulo_id)

    @_sincronizado
    def criar_modulo(self, nome: str, icone: str = "nota", com_quadro: bool = True) -> Modulo:
        """Cria um módulo em branco: a pasta, um _modulo.yaml simples e as subpastas."""
        nome = (nome or "").strip()
        if not nome:
            raise Recusado("Dê um nome para a área.")
        pasta_id = adocao.sem_acento(nome_de_arquivo(nome)).replace(" ", "-")[:40].strip("-.")
        if not pasta_id or pasta_id.startswith(("_", ".")) or pasta_id == "diario":
            raise Recusado("Esse nome não serve para uma pasta. Tente outro.")
        pasta = caminho_no_vault(self.vault, pasta_id)
        if pasta.exists():
            raise Recusado(f"Já existe uma pasta '{pasta_id}'. Para vê-la no painel, use “Mostrar no painel” em Pastas.")
        campos: dict[str, Any] = {}
        definicao: dict[str, Any] = {"nome": nome[:60], "descricao": "", "icone": icone or "nota", "campos": campos}
        if com_quadro:
            campos["status"] = {"tipo": "escolha", "opcoes": ["a_fazer", "fazendo", "feito"], "padrao": "a_fazer", "obrigatorio": True}
            campos["data"] = {"tipo": "data"}
            definicao["status"] = {"concluidos": ["feito"], "decidir": []}
        campos["origem"] = {"tipo": "escolha", "opcoes": ["humano", "agente", "coletor"], "padrao": "humano"}
        campos["tags"] = {"tipo": "lista"}
        definicao["visoes"] = ([{"tipo": "kanban", "nome": "Quadro", "agrupar_por": "status"}] if com_quadro else []) + [
            {"tipo": "tabela", "nome": "Lista"}
        ]
        for zona in ("itens", "humano", "maquina"):
            caminho_no_vault(self.vault, pasta / zona).mkdir(parents=True, exist_ok=True)
        gravar_yaml(caminho_no_vault(self.vault, pasta / ARQUIVO_MODULO), definicao)
        instrucoes = caminho_no_vault(self.vault, pasta / "maquina" / "instrucoes.md")
        texto = (
            f"# Instruções para agentes: {nome}\n\n"
            f"Leia antes `{pasta_id}/_modulo.yaml`, `{pasta_id}/humano/` e `{pasta_id}/maquina/aprendizados.md`.\n\n"
            "Este módulo foi criado pela pessoa no painel e ainda não tem regras próprias.\n"
            "Valem as regras gerais do AGENTS.md. Em caso de dúvida sobre o que fazer aqui, use `pergunta`.\n"
        )
        armazenamento.gravar_bytes(instrucoes, texto.encode("utf-8"), criar=True,
                                   validar=lambda: caminho_no_vault(self.vault, instrucoes))
        preparo.garantir_aprendizados(pasta, nome)
        self.recarregar_tudo()
        return self.modulo(pasta_id)

    def adotar_pasta(self, pasta: str, com_quadro: bool = False) -> Modulo:
        """Faz uma pasta que já existia aparecer como área do painel. As notas não são alteradas."""
        try:
            adocao.adotar(self.vault, pasta, com_quadro)
        except adocao.NaoPodeAdotar as e:
            raise Recusado(str(e)) from None
        self.recarregar_tudo()
        return self.modulo(pasta.strip().strip("/"))

    def desligar_modulo(self, modulo_id: str) -> None:
        """Tira a área do painel. A pasta e as notas continuam onde estão."""
        self.modulo(modulo_id)
        try:
            adocao.desligar(self.vault, modulo_id)
        except adocao.NaoPodeAdotar as e:
            raise Recusado(str(e)) from None
        self.recarregar_tudo()

    @_sincronizado
    def personalizar_modulo(self, modulo_id: str, dados: dict[str, Any]) -> Modulo:
        """Aplica ao _modulo.yaml o que a pessoa mudou na tela "Personalizar".

        Só mexe nas chaves que a tela oferece; comentários e o resto do arquivo ficam.
        """
        modulo = self._modulo_para_escrita(self.modulo(modulo_id))
        caminho = caminho_no_vault(self.vault, modulo.pasta / ARQUIVO_MODULO)
        yaml = ler_yaml(caminho)

        if dados.get("versao") and dados["versao"] != armazenamento.versao(yaml._orq_original or b""):
            raise Conflito("A configuração desta área mudou no disco. Suas escolhas continuam nesta tela; copie-as e reabra Personalizar para revisar a versão atual antes de salvar.")

        nome = str(dados.get("nome") or "").strip()
        if nome:
            yaml["nome"] = nome[:60]
        if "descricao" in dados:
            yaml["descricao"] = str(dados.get("descricao") or "").strip()[:160]
        if dados.get("icone"):
            yaml["icone"] = str(dados["icone"])
        cena = str(dados.get("cena") or "")
        if dados.get("capa"):
            if dados["capa"] in temas.CAPAS_CATALOGO:
                yaml["capa"] = dados["capa"]
            else:
                midia = caminho_no_vault(self.vault, str(dados["capa"]))
                if not midia.is_file() or midia.suffix.lower() not in {".png", ".jpg", ".webp", ".mp4", ".webm"}:
                    raise Recusado("Escolha uma imagem ou vídeo enviado ao vault.")
                yaml["capa"] = midia.relative_to(self.vault).as_posix()
            cena = ""
        if cena:
            if cena not in temas.CENAS:
                raise Recusado(f"A cena '{cena}' não existe.")
            capa = yaml.get("capa")
            if isinstance(capa, dict):
                capa["cena"] = cena
            else:
                yaml["capa"] = CommentedMap(cena=cena)

        campos = yaml.get("campos")
        if not isinstance(campos, dict):
            campos = yaml["campos"] = CommentedMap()
        for nome_campo in dados.get("remover") or []:
            campos.pop(str(nome_campo), None)
        for pedido in dados.get("campos") or []:
            if not isinstance(pedido, dict):
                continue
            nome_campo = str(pedido.get("nome") or "").strip()
            if not nome_campo:
                continue
            if nome_campo.lower() == "titulo" or any(c in nome_campo for c in ":#[]{}\n\r\t,"):
                raise Recusado(f"'{nome_campo}' não serve como nome de campo. Use letras, números e _.")
            tipo = str(pedido.get("tipo") or "texto")
            if tipo not in TIPOS_DE_CAMPO:
                raise Recusado(f"O tipo '{tipo}' não existe.")
            opcoes = pedido.get("opcoes") or []
            if isinstance(opcoes, str):
                opcoes = opcoes.split(",")
            opcoes = list(dict.fromkeys(str(o).strip() for o in opcoes if str(o).strip()))
            if tipo == "escolha" and not opcoes:
                raise Recusado(f"O campo '{nome_campo}' é de escolha: diga quais são as opções, separadas por vírgula.")
            atual = campos.get(nome_campo)
            if not isinstance(atual, dict):
                atual = campos[nome_campo] = CommentedMap()
            atual["tipo"] = tipo
            if tipo == "escolha":
                atual["opcoes"] = opcoes
                if atual.get("padrao") is not None and str(atual["padrao"]) not in opcoes:
                    del atual["padrao"]
            else:
                atual.pop("opcoes", None)

        regras = yaml.get("status")
        campo_status = str(regras.get("campo") or "status") if isinstance(regras, dict) else "status"
        opcoes_status = campos.get(campo_status, {}).get("opcoes", []) if isinstance(campos.get(campo_status), dict) else []
        if "concluidos" in dados and opcoes_status:
            if not isinstance(regras, dict):
                regras = yaml["status"] = CommentedMap()
            pedidos = dados.get("concluidos") or []
            if isinstance(pedidos, str):
                pedidos = pedidos.split(",")
            regras["concluidos"] = [o for o in (str(x).strip() for x in pedidos) if o in opcoes_status]

        # Visões: a pessoa liga e desliga o quadro e o gráfico; a lista sempre fica.
        if "quadro" in dados or "grafico" in dados:
            visoes = yaml.get("visoes")
            if not isinstance(visoes, list):
                visoes = [{"tipo": v.tipo, "nome": v.nome, **({"agrupar_por": v.agrupar_por} if v.tipo == "kanban" else {})} for v in modulo.visoes]
            tem = lambda tipo: any(isinstance(v, dict) and v.get("tipo") == tipo for v in visoes)  # noqa: E731
            if "quadro" in dados:
                if dados["quadro"] and not tem("kanban") and opcoes_status:
                    visoes.insert(0, {"tipo": "kanban", "nome": "Quadro", "agrupar_por": campo_status})
                elif not dados["quadro"]:
                    visoes = [v for v in visoes if not (isinstance(v, dict) and v.get("tipo") == "kanban")]
            if "grafico" in dados:
                if dados["grafico"] and not tem("grafico"):
                    visoes.append({"tipo": "grafico", "nome": "Evolução"})
                elif not dados["grafico"]:
                    visoes = [v for v in visoes if not (isinstance(v, dict) and v.get("tipo") == "grafico")]
            if not tem("tabela") and not any(isinstance(v, dict) and v.get("tipo") == "tabela" for v in visoes):
                visoes.append({"tipo": "tabela", "nome": "Lista"})
            yaml["visoes"] = visoes

        gravar_yaml(caminho, yaml)
        self.recarregar_tudo()
        return self.modulo(modulo_id)

    # ------------------------------------------------------------ números, aprendizados e sessões

    @_sincronizado
    def registrar_numeros(
        self, modulo_id: str, valores: dict[str, Any], dia: dt.date | None = None, origem: str = "humano", autor: str = "painel"
    ) -> Nota:
        """Grava os números de um dia: uma nota por dia, um campo por número."""
        modulo = self.modulo(modulo_id)
        numericos = set(modulo.campos_numericos)
        if not numericos:
            raise Recusado("Este módulo não tem campos do tipo número.")
        dia = dia or dt.date.today()
        limpos = {k: v for k, v in (valores or {}).items() if k in numericos and str(v).strip() != ""}
        if not limpos:
            raise Recusado("Preencha pelo menos um número.")
        caminho = caminho_no_vault(self.vault, modulo.pasta_itens / f"{dia.isoformat()}.md")
        if caminho.is_file():
            rel = caminho.relative_to(self.vault).as_posix()
            return self.editar_nota(rel, ler_nota(caminho, self.vault).versao, campos=limpos, autor=autor)
        campo_dia = modulo.campo_data or next((c.nome for c in modulo.campos.values() if c.tipo == "data"), None)
        campos = dict(limpos)
        if campo_dia:
            campos[campo_dia] = dia
        return self.criar_nota(modulo.id, dia.isoformat(), campos, origem=origem, autor=autor)

    @_sincronizado
    def registrar_aprendizado(self, modulo_id: str, texto: str, autor: str = "agente") -> Path:
        """Acrescenta uma linha datada ao maquina/aprendizados.md do módulo."""
        modulo = self.modulo(modulo_id)
        texto = " ".join(str(texto or "").split())
        if not texto:
            raise Recusado("Escreva o que foi aprendido.")
        caminho = caminho_no_vault(self.vault, preparo.garantir_aprendizados(modulo.pasta, modulo.nome))
        linha = f"- {dt.date.today().isoformat()}: {texto}\n".encode("utf-8")
        armazenamento.atualizar_bytes(caminho, lambda atual: atual + (b"" if atual.endswith(b"\n") else b"\n") + linha,
                                     validar=lambda: caminho_no_vault(self.vault, caminho))
        self.apos_escrita(caminho, autor)
        return caminho

    @_sincronizado
    def registrar_sessao(self, agente: str, pedido: str, feito: str, pendente: str = "") -> Path:
        """Acrescenta o relato de uma sessão de trabalho ao diário de hoje."""
        agora = dt.datetime.now()
        caminho = caminho_no_vault(self.vault, Path(diario.PASTA_SESSOES) / f"{agora:%Y-%m-%d}.md")
        uma_linha = lambda t: " ".join(str(t or "").split())  # noqa: E731
        bloco = f"## {agora:%H:%M} · {uma_linha(agente) or 'agente'}\n\n**Pedido:** {uma_linha(pedido)}\n**Feito:** {uma_linha(feito)}\n"
        if uma_linha(pendente):
            bloco += f"**Pendente:** {uma_linha(pendente)}\n"
        armazenamento.atualizar_bytes(
            caminho,
            lambda atual: atual + ((f"# Sessões de {agora:%Y-%m-%d}\n" if not atual else "") + "\n" + bloco).encode("utf-8"),
            validar=lambda: caminho_no_vault(self.vault, caminho),
        )
        self.apos_escrita(caminho, f"agente:{uma_linha(agente) or 'agente'}")
        return caminho
