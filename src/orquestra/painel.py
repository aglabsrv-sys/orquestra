"""O núcleo do painel: junta vault, índice, eventos e as operações sobre notas.

Tudo que altera o vault passa por aqui, seja pelo navegador, pela linha de comando
ou pelo agendador. Assim as regras (checagem de versão, registro no diário, aviso
às abas abertas) valem para todo mundo.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap

from orquestra import backup, coletores, diario, temas
from orquestra.config import ConfigPainel, gravar_yaml, ler_config_painel, ler_yaml
from orquestra.eventos import Eventos
from orquestra.indice import Indice, Mudanca
from orquestra.modulos import ARQUIVO_MODULO, ColetorDef, Modulo, converter, padroes
from orquestra.notas import Conflito, Nota, caminho_livre, gravar_nota, ler_nota, nome_de_arquivo

ARQUIVOS_DE_CONFIG = {"orquestra.yaml", ARQUIVO_MODULO, "tema.yaml"}
ZONAS_DE_ESCRITA = {"itens", "humano"}


class NaoEncontrado(Exception):
    pass


class Recusado(Exception):
    """Operação recusada, com uma explicação para mostrar ao usuário."""


class Painel:
    def __init__(self, vault: Path):
        self.vault = vault.resolve()
        self.indice = Indice(self.vault)
        self.indice.carregar()
        self.eventos = Eventos()
        self.config: ConfigPainel = ler_config_painel(self.vault)
        self.tema: dict[str, Any] = temas.carregar(self.vault, self.config.tema)
        self.rodando: set[str] = set()  # coletores em execução agora

    # ------------------------------------------------------------ recargas

    def recarregar_config(self) -> None:
        self.config = ler_config_painel(self.vault)
        self.tema = temas.carregar(self.vault, self.config.tema)
        self.indice.recarregar_modulos()

    def recarregar_tudo(self) -> None:
        """Usado quando uma pasta inteira é renomeada ou apagada."""
        self.indice.carregar()
        self.recarregar_config()
        self.eventos.publicar({"tipo": "config"})

    # ------------------------------------------------------------ caminhos

    def caminho_seguro(self, rel: str) -> Path:
        """Converte um caminho relativo em absoluto, garantindo que fica dentro do vault."""
        caminho = (self.vault / rel).resolve()
        if caminho != self.vault and self.vault not in caminho.parents:
            raise NaoEncontrado(rel)
        return caminho

    def modulo(self, modulo_id: str) -> Modulo:
        modulo = self.indice.modulos.get(modulo_id)
        if modulo is None:
            raise NaoEncontrado(f"Módulo '{modulo_id}' não existe.")
        return modulo

    def nota(self, rel: str) -> Nota:
        nota = self.indice.notas.get(rel)
        if nota is None:
            raise NaoEncontrado(rel)
        return nota

    # ------------------------------------------------------------ mudanças

    def apos_escrita(self, caminho: Path, autor: str) -> Mudanca | None:
        """Atualiza o índice, registra no diário e avisa as abas abertas.

        É chamado tanto depois de uma gravação feita pelo painel quanto pelo vigia,
        quando o arquivo muda por fora (Obsidian, agente). Como o índice compara o
        conteúdo, a mesma mudança nunca é registrada duas vezes.
        """
        mudanca = self.indice.atualizar(caminho)
        if mudanca is None:
            return None
        detalhe = diario.resumir(mudanca.antes, mudanca.depois) if mudanca.tipo == "editado" else ""
        try:
            diario.registrar(self.vault, mudanca.tipo, mudanca.rel, detalhe, autor)
        except OSError:
            pass  # o diário é útil, mas nunca pode impedir o trabalho
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

    def ao_mudar_arquivos(self, caminhos: set[Path]) -> None:
        """Chamado pelo vigia com os arquivos que mudaram no disco."""
        mudou_config = False
        for caminho in caminhos:
            if caminho.name in ARQUIVOS_DE_CONFIG:
                mudou_config = True
            else:
                self.apos_escrita(caminho, "externo")
        if mudou_config:
            self.recarregar_config()
            self.eventos.publicar({"tipo": "config"})

    # ------------------------------------------------------------ notas

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
        modulo = self.modulo(modulo_id)
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
        if "origem" in modulo.campos or zona == "humano":
            meta["origem"] = origem
        meta["criado_em"] = dt.date.today()

        corpo = (corpo or "").replace("\r\n", "\n").strip()
        caminho = caminho_livre(modulo.pasta / zona, titulo)
        nota = Nota(
            caminho=caminho,
            rel=caminho.relative_to(self.vault).as_posix(),
            meta=meta,
            corpo=("\n" + corpo + "\n") if corpo else "",
        )
        gravar_nota(nota, criar=True)
        self.apos_escrita(caminho, autor)
        return self.indice.notas.get(nota.rel, nota)

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
        if not caminho.is_file() or caminho.suffix.lower() != ".md":
            raise NaoEncontrado(rel)
        # Relemos do disco: o índice pode estar uma fração de segundo atrasado.
        nota = ler_nota(caminho, self.vault)
        if versao and nota.versao != versao:
            raise Conflito(rel)
        if nota.erro:
            raise Recusado("O frontmatter desta nota está com erro. Corrija no Obsidian antes de editar aqui.")

        modulo = self.indice.modulo_de(rel)
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

    def arquivar(self, rel: str, autor: str = "painel") -> str:
        """Move a nota para a pasta arquivo/ do módulo. Nada é apagado."""
        caminho = self.caminho_seguro(rel)
        modulo = self.indice.modulo_de(rel)
        if not caminho.is_file() or modulo is None:
            raise NaoEncontrado(rel)
        if self.indice.zona_de(rel) == "arquivo":
            raise Recusado("Esta nota já está arquivada.")
        destino = caminho_livre(modulo.pasta / "arquivo", caminho.stem)
        destino.parent.mkdir(parents=True, exist_ok=True)
        os.replace(caminho, destino)
        self.indice.atualizar(caminho)  # some do índice
        self.indice.atualizar(destino)  # reaparece em arquivo/
        novo_rel = destino.relative_to(self.vault).as_posix()
        try:
            diario.registrar(self.vault, "arquivado", rel, f"movido para {novo_rel}", autor)
        except OSError:
            pass
        self.eventos.publicar({"tipo": "nota", "acao": "removido", "rel": rel, "modulo": modulo.id, "versao": ""})
        return novo_rel

    # ------------------------------------------------------------ estado

    @property
    def _arquivo_estado(self) -> Path:
        return self.vault / "_orquestra" / "estado.json"

    def ler_estado(self) -> dict[str, Any]:
        try:
            return json.loads(self._arquivo_estado.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def gravar_estado(self, secao: str, chave: str, valor: Any) -> None:
        estado = self.ler_estado()
        estado.setdefault(secao, {})[chave] = valor
        try:
            self._arquivo_estado.parent.mkdir(parents=True, exist_ok=True)
            temporario = self._arquivo_estado.with_name("estado.json.orq-tmp")
            temporario.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporario, self._arquivo_estado)
        except OSError:
            pass

    # ------------------------------------------------------------ coletores

    def coletor(self, modulo_id: str, script: str) -> tuple[Modulo, ColetorDef]:
        modulo = self.modulo(modulo_id)
        for coletor in modulo.coletores:
            if coletor.script == script:
                return modulo, coletor
        raise NaoEncontrado(f"Coletor '{script}' não existe em {modulo_id}.")

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
            return self._concluir_coleta(modulo, coletor, itens, erro)
        finally:
            self.rodando.discard(chave)

    def ultima_coleta(self, modulo_id: str, script: str) -> dict[str, Any]:
        return self.ler_estado().get("coletores", {}).get(f"{modulo_id}/{script}", {})

    def definir_coletor_ativo(self, modulo_id: str, script: str, ativo: bool) -> None:
        """Liga ou desliga um coletor alterando só essa chave no _modulo.yaml."""
        modulo, _ = self.coletor(modulo_id, script)
        caminho = modulo.pasta / ARQUIVO_MODULO
        dados = ler_yaml(caminho)
        for definicao in dados.get("coletores") or []:
            if isinstance(definicao, dict) and str(definicao.get("script")) == script:
                definicao["ativo"] = bool(ativo)
        gravar_yaml(caminho, dados)
        self.indice.recarregar_modulos()

    # ------------------------------------------------------------ tema e backup

    def definir_tema(self, tema_id: str) -> None:
        if tema_id not in {t["id"] for t in temas.listar(self.vault)}:
            raise NaoEncontrado(f"Tema '{tema_id}' não existe.")
        caminho = self.vault / "orquestra.yaml"
        dados = ler_yaml(caminho)
        dados["tema"] = tema_id
        gravar_yaml(caminho, dados)
        self.recarregar_config()

    def fazer_backup(self, enviar: bool = False) -> dict[str, str]:
        resultado = {"commit": backup.commit(self.vault)}
        agora = dt.datetime.now().isoformat(timespec="seconds")
        self.gravar_estado("backup", "ultimo_commit", agora)
        if enviar:
            resultado["push"] = backup.push(self.vault)
            self.gravar_estado("backup", "ultimo_push", agora)
            self.gravar_estado("backup", "resultado_push", resultado["push"])
        return resultado
