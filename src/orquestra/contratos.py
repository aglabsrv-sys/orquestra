"""Contratos JSON estritos das operações públicas do painel."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Pedido(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class CriarNota(Pedido):
    modulo: str = ""
    titulo: str = Field(default="", max_length=500)
    campos: dict[str, Any] = Field(default_factory=dict, max_length=200)
    corpo: str = Field(default="", max_length=1_000_000)
    zona: Literal["itens", "humano"] = "itens"
    subpasta: str = Field(default="", max_length=1000)


class EditarNota(Pedido):
    versao: str = Field(min_length=1, max_length=128)
    titulo: str | None = Field(default=None, max_length=500)
    campos: dict[str, Any] | None = Field(default=None, max_length=200)
    corpo: str | None = Field(default=None, max_length=1_000_000)


class Versao(Pedido):
    versao: str = Field(min_length=1, max_length=128)


class CopiaNota(Pedido):
    titulo: str = Field(default="", max_length=500)
    corpo: str = Field(max_length=1_000_000)
    campos: dict[str, Any] = Field(default_factory=dict, max_length=200)


class CopiaRecuperacao(Pedido):
    id: str = Field(min_length=20, max_length=100)
    tipo: Literal["antes", "proposta"] = "antes"
    titulo: str = Field(default="", max_length=500)


class Captura(Pedido):
    texto: str = Field(default="", max_length=1_000_000)


class SalvarSegredo(Pedido):
    nome: str = Field(min_length=2, max_length=80)
    valor: str | None = Field(max_length=8192)


class Coletor(Pedido):
    modulo: str
    script: str


class AtivarColetor(Coletor):
    ativo: bool


class ConfiarColetor(Coletor):
    acao: Literal["confiar", "revogar"] = "confiar"
    assinatura: str = ""


class ConfigurarColetor(Coletor):
    config: dict[str, Any] | None = Field(default=None, max_length=100)
    nome: str = Field(default="", max_length=120)
    a_cada: str = Field(default="", max_length=20)
    diario_as: str = Field(default="", max_length=5)
    versao: str = Field(default="", max_length=128)


class AtualizarColetor(Coletor):
    versao: str = Field(min_length=1, max_length=128)
    assinatura: str = Field(min_length=1, max_length=128)


class PedidoAutomacao(Pedido):
    definicao: str = Field(min_length=1, max_length=100)
    destino: str = Field(default="", max_length=1000)
    nome: str = Field(default="", max_length=120)
    config: dict[str, Any] = Field(default_factory=dict, max_length=100)
    mapeamento: dict[str, str] = Field(default_factory=dict, max_length=100)
    a_cada: str | None = Field(default=None, max_length=20)
    diario_as: str | None = Field(default=None, max_length=5)


class IdAutomacao(Pedido):
    id: str = Field(min_length=1, max_length=64)


class EditarAutomacao(PedidoAutomacao):
    id: str = Field(min_length=1, max_length=64)


class PreviaAutomacao(PedidoAutomacao):
    id: str | None = Field(default=None, min_length=1, max_length=64)


class AtivarAutomacao(IdAutomacao):
    ativo: bool


class ConfiarAutomacao(IdAutomacao):
    assinatura: str = Field(min_length=1, max_length=128)


class ExecutarAutomacao(IdAutomacao):
    previa: bool = False


class Tema(Pedido):
    tema: str


class Backup(Pedido):
    enviar: bool = False
    assinatura: str = ""


class ConfiarBackup(Pedido):
    acao: Literal["confiar", "revogar"] = "confiar"
    assinatura: str = ""


class Configuracao(Pedido):
    ordem_pastas: list[str] | None = Field(default=None, max_length=500)
    nome: str | None = Field(default=None, max_length=60)
    captura: str | None = None
    auto_commit: bool | None = None
    aparencia: dict[str, Any] | None = None


class CriarModulo(Pedido):
    pronto: str = ""
    nome: str = Field(default="", max_length=60)
    icone: str = "nota"
    exemplos: bool = False
    quadro: bool = True


class DefinicaoCampo(Pedido):
    nome: str = Field(max_length=100)
    tipo: str = "texto"
    opcoes: list[str] | str = Field(default_factory=list)


class Personalizacao(Pedido):
    versao: str | None = Field(default=None, min_length=1, max_length=128)
    nome: str | None = Field(default=None, max_length=60)
    descricao: str | None = Field(default=None, max_length=160)
    icone: str | None = None
    cena: str | None = None
    capa: str | None = Field(default=None, max_length=300)
    campos: list[DefinicaoCampo] = Field(default_factory=list, max_length=200)
    remover: list[str] = Field(default_factory=list, max_length=200)
    concluidos: list[str] | str | None = None
    quadro: bool | None = None
    grafico: bool | None = None


class AdotarPasta(Pedido):
    pasta: str
    quadro: bool = False


class NotaPasta(Pedido):
    pasta: str = ""
    titulo: str = Field(default="", max_length=500)
    corpo: str = Field(default="", max_length=1_000_000)


class Numeros(Pedido):
    modulo: str
    dia: str = ""
    valores: dict[str, str | int | float] = Field(default_factory=dict, max_length=200)


class EventoAgenda(Pedido):
    rel: str = Field(default="", max_length=2000)
    versao: str = Field(default="", max_length=128)
    titulo: str = Field(min_length=1, max_length=500)
    corpo: str = Field(default="", max_length=1_000_000)
    data: str = Field(max_length=10)
    data_fim: str = Field(default="", max_length=10)
    hora: str = Field(default="", max_length=5)
    hora_fim: str = Field(default="", max_length=5)
    dia_inteiro: bool = False
    categoria: str = Field(default="Compromisso", max_length=60)
    cor: Literal["azul", "verde", "lilas", "laranja", "rosa", "vermelho"] = "azul"
    tags: list[str] = Field(default_factory=list, max_length=20)


class MoverEventoAgenda(Pedido):
    rel: str = Field(min_length=1, max_length=2000)
    versao: str = Field(min_length=1, max_length=128)
    data: str = Field(max_length=10)
    hora: str | None = Field(default=None, max_length=5)


class Habito(Pedido):
    rel: str = Field(default="", max_length=2000)
    versao: str = Field(default="", max_length=128)
    titulo: str = Field(min_length=1, max_length=120)
    meta_semanal: int = Field(default=3, ge=1, le=7)
    tags: list[str] = Field(default_factory=list, max_length=12)


class MarcarHabito(Pedido):
    rel: str = Field(min_length=1, max_length=2000)
    versao: str = Field(min_length=1, max_length=128)
