"""Automações do catálogo com destino independente dos módulos.

As definições vêm da instalação; somente configuração e destino ficam no cofre.
O aceite do código/configuração é local, cobre também os campos escritos e nunca
é tratado como isolamento das permissões do processo Python.
"""

from __future__ import annotations

import asyncio
import copy
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import tomllib
import uuid
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from orquestra import armazenamento, coletores, confianca
from orquestra.caminhos import caminho_no_vault, ignorar
from orquestra.config import carregar_env, gravar_yaml, ler_yaml
from orquestra.modulos import Campo, ColetorDef, Modulo, carregar_modulo
from orquestra.notas import simples

if TYPE_CHECKING:
    from orquestra.painel import Painel

class ErroAutomacao(ValueError):
    """Configuração inválida apresentada de forma segura na interface."""


ARQUIVO = "_orquestra/automacoes.json"
LIMITE_INSTANCIAS = 200
LIMITE_CONFIGURACAO_BYTES = 32 * 1024 * 1024
_CAMPO = re.compile(r"^[^\W\d][\w-]{0,99}$", re.UNICODE)
_HELPER_DISTRIBUIDO_ANTERIOR = "bca7d7d4a1600bc082feeafb4c25f0b5157ab3e8c6796b7d24bb6b9708140d1e"
_DESCRICOES = {
    "youtube_rss.py": "Guarda vídeos novos dos canais que você acompanha.",
    "rss.py": "Reúne publicações de feeds RSS e Atom na pasta escolhida.",
    "google_trends.py": "Guarda os assuntos em alta no Google.",
    "youtube_api.py": "Busca vídeos por assunto usando sua chave do YouTube.",
    "recorrentes.py": "Cria a tarefa do dia quando uma regra de recorrência coincide.",
    "agenda_ics.py": "Importa compromissos iCal; alterações e cancelamentos não são sincronizados.",
    "youtube_canal.py": "Preenche os números públicos de um canal na nota do dia.",
    "cotacoes.py": "Preenche cotações na nota do dia.",
    "github_repo.py": "Preenche estrelas e forks de repositórios na nota do dia.",
}
_ROTULOS = {
    "canais": "Canais", "feeds": "Endereços dos feeds", "pais": "País", "idioma": "Idioma",
    "maximo": "Máximo de itens", "maximo_por_canal": "Vídeos por canal", "maximo_por_feed": "Itens por feed",
    "maximo_por_termo": "Vídeos por busca", "termos": "Assuntos da busca", "tarefas": "Regras das tarefas",
    "agendas": "Agendas iCal", "dias_a_frente": "Dias à frente", "canal": "Canal",
    "campo_inscritos": "Campo para inscritos", "campo_visualizacoes": "Campo para visualizações",
    "moedas": "Campos e pares de moedas", "repositorios": "Repositórios e campos",
}
_AJUDAS = {
    "rss.py": "Acompanha blogs, newsletters e podcasts por RSS ou Atom. Troque os endereços dos feeds para escolher suas fontes; um endereço de página comum pode não ser um feed.",
    "youtube_rss.py": "Acompanha vídeos novos de canais específicos. Informe os canais por @nome, link ou ID. Não precisa de chave do YouTube.",
    "youtube_api.py": "Descobre vídeos por palavras ou assuntos, mesmo de canais que você não acompanha. Personalize os termos, país e idioma. Usa a chave da API do YouTube.",
    "google_trends.py": "Guarda os assuntos em alta no Google. Você pode escolher o país e a quantidade de assuntos; os temas vêm das tendências do momento.",
    "recorrentes.py": "Cria tarefas nas datas das suas regras, como todo dia, sexta ou dia 5. Cada tarefa é criada uma vez por data.",
    "agenda_ics.py": "Lê uma agenda iCal e guarda os próximos compromissos. Escolha a agenda e quantos dias consultar. Alterações e cancelamentos ainda não são sincronizados.",
    "youtube_canal.py": "Registra inscritos e visualizações de um canal na nota do dia. Escolha o canal e os campos que quer acompanhar. Usa a chave da API do YouTube.",
    "cotacoes.py": "Registra cotações na nota do dia. Escolha os pares de moedas, como USD-BRL, e o nome de cada indicador.",
    "github_repo.py": "Registra estrelas e forks de repositórios públicos na nota do dia. Escolha os repositórios e o nome de cada indicador.",
}


@lru_cache(maxsize=1)
def _definicoes() -> dict[str, tuple[Modulo, ColetorDef]]:
    base = Path(__file__).parent / "catalogo"
    encontrados = {}
    for pasta in sorted(base.iterdir()):
        if not pasta.is_dir() or not (pasta / "_modulo.yaml").is_file():
            continue
        modulo = carregar_modulo(pasta)
        for coletor in modulo.coletores:
            encontrados[f"{modulo.id}/{coletor.script}"] = (modulo, coletor)
    return encontrados


def _definicao(identificador: str) -> tuple[Modulo, ColetorDef]:
    encontrado = _definicoes().get(identificador)
    if encontrado is None:
        raise ErroAutomacao("Esta automação não está no catálogo desta instalação.")
    return encontrado


def ajuda_coletor(script: str) -> str:
    return _AJUDAS.get(script, "Executa uma rotina definida nesta pasta. As opções dependem da configuração da automação.")


def catalogo() -> list[dict[str, Any]]:
    saida = []
    for identificador, (modulo, coletor) in _definicoes().items():
        config = simples(coletor.config)
        parametros = []
        for nome, valor in config.items():
            tipo = "booleano" if isinstance(valor, bool) else "numero" if isinstance(valor, (int, float)) else (
                "mapa" if isinstance(valor, dict) else "registros" if isinstance(valor, list) and valor and isinstance(valor[0], dict)
                else "lista" if isinstance(valor, list) else "texto"
            )
            parametros.append({"nome": nome, "rotulo": _ROTULOS.get(nome, nome.replace("_", " ").capitalize()), "tipo": tipo, "padrao": valor})
        saida.append({
            "id": identificador, "nome": coletor.nome, "descricao": _DESCRICOES.get(coletor.script, ""),
            "icone": modulo.icone, "config": config, "parametros": parametros,
            "ajuda": _AJUDAS.get(coletor.script, ""),
            "requer": list(coletor.requer), "rede": coletor.script != "recorrentes.py",
            "tipo": "nota_diaria" if modulo.id == "numeros" else "itens",
            "a_cada": coletor.a_cada, "diario_as": coletor.diario_as,
        })
    return saida


def _arquivo(painel: Painel) -> Path:
    return caminho_no_vault(painel.vault, ARQUIVO)


def _ler_arquivo(painel: Painel) -> bytes:
    with _arquivo(painel).open("rb") as entrada:
        dados = entrada.read(LIMITE_CONFIGURACAO_BYTES + 1)
    if len(dados) > LIMITE_CONFIGURACAO_BYTES:
        raise ErroAutomacao("A configuração de automações excede o limite de 32 MB.")
    return dados


def _ler(painel: Painel) -> list[dict[str, Any]]:
    try:
        dados = _ler_arquivo(painel)
        bruto = json.loads(dados.decode("utf-8"))
    except FileNotFoundError:
        return []
    except ErroAutomacao:
        raise
    except (ValueError, OSError):
        raise ErroAutomacao("Não consegui ler as automações salvas. Preserve o arquivo e confira sua configuração.") from None
    if not isinstance(bruto, dict) or bruto.get("versao") != 1 or not isinstance(bruto.get("instancias"), list):
        raise ErroAutomacao("O arquivo de automações tem um formato desconhecido.")
    if len(bruto["instancias"]) > LIMITE_INSTANCIAS or any(not isinstance(i, dict) for i in bruto["instancias"]):
        raise ErroAutomacao("O arquivo de automações excede o limite ou contém registros inválidos.")
    return bruto["instancias"]


def _alterar(painel: Painel, operacao) -> None:
    # Mesma ordem da importação: uma edição/remoção só termina depois de uma
    # gravação já iniciada, inclusive entre instâncias cooperantes do painel.
    with painel._trava, armazenamento.trava(_arquivo(painel)):
        try:
            anterior = _ler_arquivo(painel)
        except FileNotFoundError:
            anterior = None
        instancias = _ler(painel)
        operacao(instancias)
        dados = json.dumps({"versao": 1, "instancias": instancias}, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
        armazenamento.gravar_bytes(_arquivo(painel), dados, esperado=anterior, validar=lambda: _arquivo(painel))
    painel.mudou_desde_o_backup = True
    painel.eventos.publicar({"tipo": "automacao"})


def _encontrar(painel: Painel, identificador: str) -> dict[str, Any]:
    encontrada = next((i for i in _ler(painel) if i.get("id") == identificador), None)
    if encontrada is None:
        raise ErroAutomacao("Esta automação não está mais instalada.")
    return encontrada


def _destino(painel: Painel, relativo: str) -> tuple[Path, str]:
    if not isinstance(relativo, str):
        raise ErroAutomacao("Escolha uma pasta do cofre.")
    caminho = caminho_no_vault(painel.vault, relativo or ".")
    rel = caminho.relative_to(painel.vault).as_posix()
    if rel != "." and (ignorar(rel) or any(p.startswith((".", "_")) for p in Path(rel).parts)):
        raise ErroAutomacao("Escolha uma pasta de notas visível do cofre.")
    if not caminho.is_dir():
        raise ErroAutomacao("A pasta de destino não existe. Crie-a em Pastas antes de continuar.")
    return caminho, "" if rel == "." else rel


def _config(definicao: str, config: dict | None) -> dict:
    _, coletor = _definicao(definicao)
    if config is not None and not isinstance(config, dict):
        raise ErroAutomacao("A configuração precisa ser um objeto.")
    resultado = {**simples(coletor.config), **(config or {})}
    if set(resultado) - set(coletor.config):
        raise ErroAutomacao("A configuração contém opções que não pertencem a esta automação.")
    for chave, padrao in simples(coletor.config).items():
        valor = resultado[chave]
        if isinstance(padrao, (dict, list)) and not isinstance(valor, type(padrao)):
            raise ErroAutomacao(f"Confira o formato de {chave.replace('_', ' ')}.")
        if isinstance(padrao, str) and not isinstance(valor, str):
            raise ErroAutomacao(f"{chave.replace('_', ' ').capitalize()} precisa ser texto.")
        if isinstance(padrao, int) and (isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= 10000):
            raise ErroAutomacao(f"{chave.replace('_', ' ').capitalize()} precisa ser um inteiro positivo, até 10000.")
    for chave in ("canais", "feeds", "termos"):
        if chave in resultado and any(not isinstance(v, str) for v in resultado[chave]):
            raise ErroAutomacao(f"Cada item de {chave} precisa ser texto.")
    for chave in ("tarefas", "repositorios"):
        if chave in resultado and any(not isinstance(v, dict) for v in resultado[chave]):
            raise ErroAutomacao(f"Cada item de {chave} precisa ser um registro de configuração.")
    if "agendas" in resultado and any(not isinstance(v, (str, dict)) for v in resultado["agendas"]):
        raise ErroAutomacao("Cada agenda precisa ser um endereço ou um registro de configuração.")
    if "moedas" in resultado and any(not isinstance(v, str) for v in resultado["moedas"].values()):
        raise ErroAutomacao("Cada cotação precisa informar seu par de moedas.")
    try:
        tamanho = len(json.dumps(resultado, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError, RecursionError):
        raise ErroAutomacao("A configuração contém um valor inválido.") from None
    if tamanho > 100_000:
        raise ErroAutomacao("A configuração está muito grande.")
    return resultado


def _requer(definicao: str, config: dict) -> list[str]:
    _, coletor = _definicao(definicao)
    requer = set(coletor.requer)
    if definicao.endswith("agenda_ics.py"):
        for agenda in config.get("agendas", []):
            if isinstance(agenda, dict) and agenda.get("variavel"):
                chave = agenda["variavel"]
                if not isinstance(chave, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", chave):
                    raise ErroAutomacao("Use um nome de segredo válido para o endereço iCal.")
                requer.add(chave)
    return sorted(requer)


def _mapeamento(mapeamento: dict | None) -> dict[str, str]:
    if mapeamento is not None and not isinstance(mapeamento, dict):
        raise ErroAutomacao("O mapeamento precisa ser um objeto.")
    resultado = dict(mapeamento or {})
    for origem, destino in resultado.items():
        if not isinstance(origem, str) or not isinstance(destino, str) or not _CAMPO.fullmatch(origem) or not _CAMPO.fullmatch(destino):
            raise ErroAutomacao("Use nomes de campos simples no mapeamento.")
        if origem in coletores.CAMPOS_DE_CONTROLE or destino in coletores.CAMPOS_DE_CONTROLE:
            raise ErroAutomacao("Campos internos de coleta não podem ser mapeados.")
    if len(set(resultado.values())) != len(resultado):
        raise ErroAutomacao("Cada campo precisa ter um destino diferente.")
    return resultado


def _campos(definicao: str, config: dict) -> dict[str, Campo]:
    modulo, _ = _definicao(definicao)
    if modulo.id != "numeros":
        campos = {nome: copy.copy(c) for nome, c in modulo.campos.items() if nome not in {"status", "origem"}}
        if modulo.id == "tarefas":
            # Prioridade é dado da regra, sem impor os estados do módulo pronto.
            campos["prioridade"] = Campo("prioridade")
            for tarefa in config.get("tarefas", []):
                if isinstance(tarefa, dict):
                    for nome, valor in tarefa.items():
                        if nome not in {"titulo", "quando", "corpo"} and _CAMPO.fullmatch(str(nome)):
                            tipo = ("lista" if isinstance(valor, list) else "booleano" if isinstance(valor, bool)
                                    else "numero" if isinstance(valor, (int, float)) else "texto")
                            campos.setdefault(nome, Campo(nome, tipo))
        for campo in campos.values():
            campo.padrao = None
        return campos
    campos = {"dia": Campo("dia", "data")}
    nomes = []
    if definicao.endswith("cotacoes.py"):
        nomes.extend(config.get("moedas", {}))
    elif definicao.endswith("youtube_canal.py"):
        nomes.extend(config.get(c) for c in ("campo_inscritos", "campo_visualizacoes"))
    else:
        for repo in config.get("repositorios", []):
            if isinstance(repo, dict):
                nomes.extend(repo.get(c) for c in ("campo_estrelas", "campo_forks"))
    for nome in nomes:
        if not nome:
            continue
        if not isinstance(nome, str) or not _CAMPO.fullmatch(nome) or nome in coletores.CAMPOS_DE_CONTROLE or nome == "dia":
            raise ErroAutomacao("Escolha um nome de campo numérico válido e diferente de dia.")
        if nome in campos:
            raise ErroAutomacao("Dois números desta automação usam o mesmo campo. Escolha um nome diferente para cada valor.")
        campos[nome] = Campo(nome, "numero")
    return campos


def _modulo_destino(painel: Painel, instancia: dict) -> Modulo:
    caminho, _ = _destino(painel, instancia["destino"])
    base = _campos(instancia["definicao"], instancia["config"])
    mapeamento = _mapeamento(instancia.get("mapeamento"))
    if set(mapeamento) - set(base):
        raise ErroAutomacao("O mapeamento contém um campo que esta automação não produz.")
    nomes = [mapeamento.get(nome, nome) for nome in base]
    if len(set(nomes)) != len(nomes):
        raise ErroAutomacao("O mapeamento faria dois valores ocuparem o mesmo campo. Escolha nomes diferentes.")
    campos = {mapeamento.get(nome, nome): Campo(**{**asdict(campo), "nome": mapeamento.get(nome, nome)}) for nome, campo in base.items()}
    donos = [m for m in painel.indice.modulos.values() if caminho.is_relative_to(m.pasta_itens)]
    dono = max(donos, key=lambda m: len(m.pasta.parts), default=None)
    if dono:
        for nome, campo in campos.items():
            existente = dono.campos.get(nome)
            if existente and existente.tipo != campo.tipo and not (existente.tipo == "escolha" and campo.tipo == "texto"):
                raise ErroAutomacao(f"O campo {nome} usa outro tipo nesta pasta. Escolha outro nome no mapeamento.")
        campos.update(dono.campos)
    return Modulo(
        id=f"@automacao:{instancia.get('id', 'previa')}", pasta=caminho,
        nome=instancia.get("nome", "Automação"), itens_em=".", campos=campos,
        campo_status=dono.campo_status if dono else "status",
    )


def _colisoes(painel: Painel, instancia: dict) -> None:
    if not instancia["definicao"].startswith("numeros/"):
        return
    campos = {c.nome for c in _modulo_destino(painel, instancia).campos.values() if c.tipo == "numero"}
    # Só os campos declarados pela instância são reivindicados, não todo o schema.
    mapa = instancia.get("mapeamento", {})
    campos &= {mapa.get(n, n) for n in _campos(instancia["definicao"], instancia["config"]) if n != "dia"}
    for outra in _ler(painel):
        if outra.get("id") == instancia.get("id") or outra.get("destino", "").casefold() != instancia["destino"].casefold() or not str(outra.get("definicao", "")).startswith("numeros/"):
            continue
        outro_mapa = outra.get("mapeamento", {})
        outros = {outro_mapa.get(n, n) for n in _campos(outra["definicao"], outra["config"]) if n != "dia"}
        conflito = campos & outros
        if conflito:
            raise ErroAutomacao("Outra automação já preenche estes campos nesta pasta: " + ", ".join(sorted(conflito)) + ". Escolha outros nomes ou outro destino.")
    destino, _ = _destino(painel, instancia["destino"])
    for modulo in painel.indice.modulos.values():
        if modulo.pasta_itens != destino:
            continue
        for coletor in modulo.coletores:
            definicao = "numeros/" + coletor.script
            if not coletor.ativo or definicao not in _definicoes():
                continue
            outros = {n for n in _campos(definicao, coletor.config) if n != "dia"}
            if campos & outros:
                raise ErroAutomacao("Uma automação ativa da pasta já preenche estes campos. Pause-a antes de usar o novo catálogo ou escolha outros nomes.")


def prever(painel: Painel, definicao: str, destino: str, config: dict | None = None, mapeamento: dict | None = None, *, ignorar_id: str | None = None) -> dict[str, Any]:
    _, relativo = _destino(painel, destino)
    instancia = {"definicao": definicao, "destino": relativo, "config": _config(definicao, config), "mapeamento": _mapeamento(mapeamento)}
    if ignorar_id:
        _encontrar(painel, ignorar_id)
        instancia["id"] = ignorar_id
    _requer(definicao, instancia["config"])
    modulo = _modulo_destino(painel, instancia)
    _colisoes(painel, instancia)
    produzidos = _campos(definicao, instancia["config"])
    campos = [{"nome": nome, "destino": instancia["mapeamento"].get(nome, nome), "tipo": c.tipo} for nome, c in produzidos.items()]
    avisos = ["A execução usa as permissões da sua conta. O destino selecionado organiza as notas produzidas."]
    if definicao.endswith("agenda_ics.py"):
        avisos.append("Importação iCal: recorrências RRULE, alterações e cancelamentos ainda não são sincronizados.")
        avisos.append("Endereços privados de agenda dão acesso aos seus eventos. Prefira informar uma variável de Segredos em vez de salvar o endereço no cofre.")
    return {**instancia, "campos": campos, "avisos": avisos,
            "politica": "Uma nota por dia; campos preenchidos manualmente são preservados." if definicao.startswith("numeros/") else "Uma nota por item; itens já presentes no destino são reconhecidos.",
            "exemplo": {"titulo": dt.date.today().isoformat() if definicao.startswith("numeros/") else "Exemplo de nota", "campos": {c["destino"]: (123 if c["tipo"] == "numero" else dt.date.today().isoformat() if c["tipo"] == "data" else ["exemplo"] if c["tipo"] == "lista" else "exemplo") for c in campos}},
            "pasta": str(modulo.pasta.relative_to(painel.vault))}


def _regra(a_cada: str | None, diario_as: str | None) -> tuple[str | None, str | None]:
    intervalo, hora = a_cada or None, diario_as or None
    if intervalo and (not coletores.intervalo_em_segundos(intervalo) or coletores.intervalo_em_segundos(intervalo) < 60):
        raise ErroAutomacao("Use um intervalo como 30m, 6h ou 1d.")
    if hora:
        try:
            if not re.fullmatch(r"\d{2}:\d{2}", hora):
                raise ValueError
            dt.time.fromisoformat(hora)
        except ValueError:
            raise ErroAutomacao("Use um horário válido, como 08:00.") from None
    if intervalo and hora:
        raise ErroAutomacao("Escolha um intervalo ou um horário diário.")
    return intervalo, hora


def criar(painel: Painel, definicao: str, destino: str, config: dict | None = None, *, nome: str = "", a_cada: str | None = None, diario_as: str | None = None, mapeamento: dict | None = None) -> dict[str, Any]:
    previa = prever(painel, definicao, destino, config, mapeamento)
    _, coletor = _definicao(definicao)
    if a_cada is None and diario_as is None:
        a_cada, diario_as = coletor.a_cada, coletor.diario_as
    intervalo, hora = _regra(a_cada, diario_as)
    instancia = {k: previa[k] for k in ("definicao", "destino", "config", "mapeamento")}
    instancia.update({"id": uuid.uuid4().hex, "nome": str(nome or coletor.nome).strip()[:120], "a_cada": intervalo, "diario_as": hora, "ativo": False})
    def adicionar(instancias):
        if len(instancias) >= LIMITE_INSTANCIAS:
            raise ErroAutomacao("O limite é de 200 automações por cofre.")
        _colisoes(painel, instancia)
        instancias.append(instancia)
    _alterar(painel, adicionar)
    return _publica(painel, instancia)


def atualizar(painel: Painel, identificador: str, definicao: str, destino: str, config: dict | None = None, *, nome: str = "", a_cada: str | None = None, diario_as: str | None = None, mapeamento: dict | None = None) -> dict[str, Any]:
    _encontrar(painel, identificador)
    previa = prever(painel, definicao, destino, config, mapeamento, ignorar_id=identificador)
    _, coletor = _definicao(definicao)
    if a_cada is None and diario_as is None:
        a_cada, diario_as = coletor.a_cada, coletor.diario_as
    intervalo, hora = _regra(a_cada, diario_as)
    instancia = {k: previa[k] for k in ("definicao", "destino", "config", "mapeamento")}
    instancia.update({"id": identificador, "nome": str(nome or coletor.nome).strip()[:120], "a_cada": intervalo, "diario_as": hora, "ativo": False})
    def alterar(instancias):
        posicao = next((n for n, i in enumerate(instancias) if i.get("id") == identificador), None)
        if posicao is None:
            raise ErroAutomacao("Esta automação não está mais instalada.")
        _colisoes(painel, instancia)
        instancias[posicao] = instancia
    _alterar(painel, alterar)
    return _publica(painel, instancia)


def _preparar(painel: Painel, instancia: dict) -> tuple[dict[str, Any], dict[str, bytes]]:
    modulo, coletor = _definicao(instancia["definicao"])
    _destino(painel, instancia["destino"])
    config = _config(instancia["definicao"], instancia["config"])
    _modulo_destino(painel, instancia)
    base = modulo.pasta / "maquina" / "coletores"
    arquivos = {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}}
    requer = _requer(instancia["definicao"], config)
    manifesto = {"definicao": instancia["definicao"], "arquivos": {n: hashlib.sha256(b).hexdigest() for n, b in arquivos.items()},
                 "config": config, "requer": requer, "destino": instancia["destino"], "mapeamento": _mapeamento(instancia.get("mapeamento")),
                 "a_cada": instancia.get("a_cada"), "diario_as": instancia.get("diario_as")}
    assinatura = hashlib.sha256(json.dumps(manifesto, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    chave = _chave(painel, instancia)
    aceite = confianca._ler(painel.vault).get(chave, "")
    return {"assinatura": assinatura, "confiavel": secrets.compare_digest(aceite, assinatura), "requer": requer, "arquivos": list(arquivos), "script": coletor.script, "config": config}, arquivos


def _chave(painel: Painel, instancia: dict) -> str:
    return hashlib.sha256((os.path.normcase(str(painel.vault.resolve())) + "\0automacao\0" + str(instancia["id"])).encode()).hexdigest()


def _publica(painel: Painel, instancia: dict) -> dict[str, Any]:
    try:
        estado, _ = _preparar(painel, instancia)
    except (ValueError, KeyError, OSError, TypeError) as erro:
        estado = {"confiavel": False, "assinatura": "", "requer": [], "erro": str(erro)}
    ultima = painel.ler_estado().get("automacoes", {}).get(str(instancia.get("id")), {})
    return {**instancia, "confianca": estado, "ultima": ultima, "rodando": "automacao:" + str(instancia.get("id")) in painel.rodando}


def listar(painel: Painel) -> list[dict[str, Any]]:
    return [_publica(painel, i) for i in _ler(painel)]


def _definicao_legada(painel: Painel, modulo_id: str, script: str):
    dono = painel.modulo(modulo_id)
    modulo = carregar_modulo(dono.pasta)
    if modulo.invalido:
        raise ErroAutomacao("A configuração desta pasta está inválida. Confira-a antes de configurar a automação.")
    coletor = next((c for c in modulo.coletores if c.script == script), None)
    if coletor is None:
        raise ErroAutomacao("Esta automação não está mais na pasta. Atualize a página.")
    definicao = next((identificador for identificador, (_, c) in _definicoes().items() if c.script == script), None)
    if definicao is None:
        raise ErroAutomacao("Esta automação personalizada usa uma configuração própria.")
    return modulo, coletor, definicao


def _atualizacoes_codigo(painel: Painel, modulo, definicao: str, *, arquivos_locais=None):
    """Reconhece somente árvores distribuídas conhecidas; nunca adota código próprio."""
    fonte, _ = _definicao(definicao)
    base_nativa = fonte.pasta / "maquina" / "coletores"
    base_local = caminho_no_vault(painel.vault, modulo.pasta / "maquina" / "coletores")
    desejados = {p.relative_to(base_nativa).as_posix(): p.read_bytes() for p in base_nativa.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}}
    atuais = arquivos_locais
    if atuais is None:
        atuais = {}
        for arquivo in base_local.rglob("*"):
            caminho = caminho_no_vault(painel.vault, arquivo)
            if caminho.is_file() and "__pycache__" not in caminho.parts and caminho.suffix not in {".pyc", ".pyo"}:
                atuais[caminho.relative_to(base_local).as_posix()] = caminho.read_bytes()
    if set(atuais) != set(desejados):
        return None
    mudancas = []
    for nome, atual in atuais.items():
        novo = desejados[nome]
        if atual == novo:
            continue
        if nome != "_comum.py" or hashlib.sha256(atual.replace(b"\r\n", b"\n")).hexdigest() != _HELPER_DISTRIBUIDO_ANTERIOR:
            return None
        mudancas.append((base_local / nome, atual, novo))
    return mudancas


def legado_desatualizado(painel: Painel, modulo: str, script: str) -> bool:
    try:
        dono, _, definicao = _definicao_legada(painel, modulo, script)
        return bool(_atualizacoes_codigo(painel, dono, definicao))
    except (ValueError, OSError):
        return False


def atualizar_codigo_legado(painel: Painel, modulo: str, script: str, *, versao: str, assinatura: str) -> dict[str, Any]:
    """Atualização explícita do código nativo, com recuperação e compare-and-swap."""
    with painel._trava:
        atual = _publica_legada(painel, modulo, script)
        if not versao or not secrets.compare_digest(versao, atual["versao"]) or not assinatura or not secrets.compare_digest(assinatura, atual["confianca"].get("assinatura", "")):
            raise ErroAutomacao("Esta automação mudou. Atualize a página antes de continuar.")
        if f"{modulo}/{script}" in painel.rodando:
            raise ErroAutomacao("Aguarde a execução terminar para atualizar.")
        dono, _, definicao = _definicao_legada(painel, modulo, script)
        mudancas = _atualizacoes_codigo(painel, dono, definicao)
        if mudancas is None:
            raise ErroAutomacao("Esta automação contém código próprio. Suas personalizações foram preservadas.")
        for caminho, anterior, novo in mudancas:
            armazenamento.gravar_bytes(caminho, novo, esperado=anterior,
                                       validar=lambda alvo=caminho: caminho_no_vault(painel.vault, alvo))
        painel.mudou_desde_o_backup = bool(mudancas) or painel.mudou_desde_o_backup
        painel.eventos.publicar({"tipo": "coletor", "modulo": modulo})
        return _publica_legada(painel, modulo, script)


def _publica_legada(painel: Painel, modulo_id: str, script: str) -> dict[str, Any]:
    dono = painel.modulo(modulo_id)
    caminho = caminho_no_vault(painel.vault, dono.pasta / "_modulo.yaml")
    with painel._trava, armazenamento.trava(caminho):
        for _ in range(3):
            antes = caminho.read_bytes()
            modulo, coletor, definicao = _definicao_legada(painel, modulo_id, script)
            try:
                estado, arquivos = confianca.preparar(painel.vault, modulo, coletor)
                atualizacoes = _atualizacoes_codigo(painel, modulo, definicao, arquivos_locais=arquivos)
            except (ValueError, OSError):
                estado = {"confiavel": False, "assinatura": ""}
                atualizacoes = None
            if antes == caminho.read_bytes():
                return {"id": "legado:" + modulo.id + ":" + script, "legado": {"modulo": modulo.id, "script": script},
                        "definicao": definicao, "nome": coletor.nome, "config": simples(coletor.config),
                        "destino": modulo.pasta_itens.relative_to(painel.vault).as_posix(),
                        "a_cada": coletor.a_cada, "diario_as": coletor.diario_as, "ativo": coletor.ativo,
                        "mapeamento": {}, "confianca": estado, "codigo_nativo": atualizacoes is not None,
                        "atualizacao_disponivel": bool(atualizacoes),
                        "versao": hashlib.sha256(antes).hexdigest(),
                        "ultima": painel.ultima_coleta(modulo.id, script)}
    raise ErroAutomacao("A configuração da pasta está mudando. Aguarde e atualize a página antes de configurar.")


def legadas(painel: Painel) -> list[dict[str, Any]]:
    """Formulários das automações já presentes nas áreas, sem migrar suas notas."""
    saida = []
    for modulo in painel.indice.modulos.values():
        for coletor in modulo.coletores:
            try:
                saida.append(_publica_legada(painel, modulo.id, coletor.script))
            except (ErroAutomacao, OSError):
                continue
    return saida


def prever_legada(painel: Painel, modulo: str, script: str, config: dict | None = None, *, nome: str = "", a_cada: str = "", diario_as: str = "", versao: str = "") -> dict[str, Any]:
    atual = _publica_legada(painel, modulo, script)
    if not atual["codigo_nativo"]:
        raise ErroAutomacao("Esta automação contém código personalizado. Revise-a na área de origem antes de executar.")
    if versao and not secrets.compare_digest(versao, atual["versao"]):
        raise ErroAutomacao("As configurações desta pasta mudaram. Atualize a página antes de salvar.")
    intervalo, hora = _regra(a_cada, diario_as)
    _, original = _definicao(atual["definicao"])
    recebido = config if config is not None else atual["config"]
    if not isinstance(recebido, dict):
        raise ErroAutomacao("Confira as opções da automação.")
    extras = {k: v for k, v in recebido.items() if k not in original.config}
    if any(k not in atual["config"] or atual["config"][k] != v for k, v in extras.items()):
        raise ErroAutomacao("Esta opção personalizada precisa ser ajustada na configuração da pasta.")
    configuracao = {**{k: v for k, v in atual["config"].items() if k not in original.config},
                    **_config(atual["definicao"], {k: v for k, v in recebido.items() if k in original.config})}
    _requer(atual["definicao"], configuracao)
    # Reutiliza o contrato real da pasta, mas não converte a automação em instância.
    instancia = {"definicao": atual["definicao"], "config": configuracao,
                 "destino": atual["destino"], "mapeamento": {}}
    _modulo_destino(painel, instancia)
    if atual["definicao"].startswith("numeros/"):
        campos = set(_campos(atual["definicao"], configuracao)) - {"dia"}
        for outra in _ler(painel):
            if outra.get("destino", "").casefold() == atual["destino"].casefold() and str(outra.get("definicao", "")).startswith("numeros/"):
                mapa = outra.get("mapeamento", {})
                if campos & {mapa.get(n, n) for n in _campos(outra["definicao"], outra["config"]) if n != "dia"}:
                    raise ErroAutomacao("Outra automação já preenche estes indicadores nesta pasta. Escolha nomes diferentes.")
    return {**atual, "nome": nome.strip() or atual["nome"], "config": configuracao,
            "a_cada": intervalo, "diario_as": hora,
            "politica": "Mantém as notas e a pasta desta automação.",
            "avisos": [], "exemplo": {"titulo": "Configuração da automação", "campos": {}}}


def atualizar_legada(painel: Painel, modulo: str, script: str, config: dict | None = None, *, nome: str = "", a_cada: str = "", diario_as: str = "", versao: str) -> dict[str, Any]:
    with painel._trava:
        dono, _, _ = _definicao_legada(painel, modulo, script)
        if f"{modulo}/{script}" in painel.rodando:
            raise ErroAutomacao("Aguarde a execução desta automação terminar para configurar.")
        caminho = caminho_no_vault(painel.vault, dono.pasta / "_modulo.yaml")
        with armazenamento.trava(caminho):
            if not versao or not secrets.compare_digest(versao, hashlib.sha256(caminho.read_bytes()).hexdigest()):
                raise ErroAutomacao("As configurações desta pasta mudaram. Atualize a página antes de salvar.")
            previa = prever_legada(painel, modulo, script, config, nome=nome, a_cada=a_cada, diario_as=diario_as, versao=versao)
            dados = ler_yaml(caminho)
            for definicao in dados.get("coletores") or []:
                if isinstance(definicao, dict) and str(definicao.get("script")) == script:
                    definicao.update(nome=previa["nome"], config=previa["config"], ativo=False)
                    for chave in ("a_cada", "diario_as"):
                        if previa[chave]:
                            definicao[chave] = previa[chave]
                        else:
                            definicao.pop(chave, None)
                    _, coletor = _definicao(previa["definicao"])
                    definicao["requer"] = sorted(set(definicao.get("requer", [])) | set(coletor.requer) | set(_requer(previa["definicao"], previa["config"])))
                    break
            else:
                raise ErroAutomacao("Esta automação não está mais na pasta.")
            # CAS preserva alterações externas e comentários do YAML.
            gravar_yaml(caminho, dados)
        painel.indice.recarregar_modulos()
        painel.mudou_desde_o_backup = True
        painel.eventos.publicar({"tipo": "coletor", "modulo": modulo})
        return _publica_legada(painel, modulo, script)


def destinos_tarefas(painel: Painel) -> list[dict[str, Any]]:
    """Contratos de leitura para resumo/agenda, sem avaliar confiança ou executar.

    O consumidor deve exigir também origem/coletor nas notas e o caminho direto;
    a existência de uma automação não transforma as demais notas em tarefas.
    """
    saida = []
    try:
        instancias = _ler(painel)
    except (ValueError, OSError):
        return saida
    for instancia in instancias:
        if instancia.get("definicao") not in {"tarefas/recorrentes.py", "tarefas/agenda_ics.py"}:
            continue
        try:
            modulo = _modulo_destino(painel, instancia)
            modulo.campo_data = instancia.get("mapeamento", {}).get("data", "data")
            saida.append({"id": instancia["id"], "destino": instancia["destino"], "modulo": modulo,
                          "coletor": Path(instancia["definicao"]).stem})
        except (ValueError, OSError, TypeError, KeyError):
            continue
    return saida


def autorizar(painel: Painel, identificador: str, assinatura: str) -> dict[str, Any]:
    instancia = _encontrar(painel, identificador)
    with confianca._transacao(painel.vault):
        estado, _ = _preparar(painel, instancia)
        if not assinatura or not secrets.compare_digest(assinatura, estado["assinatura"]):
            raise ErroAutomacao("A configuração ou o código mudou. Confira a nova versão antes de autorizar.")
        aceites = confianca._ler(painel.vault)
        aceites[_chave(painel, instancia)] = assinatura
        confianca._gravar(painel.vault, aceites)
    return _publica(painel, instancia)


def ativar(painel: Painel, identificador: str, ativo: bool) -> dict[str, Any]:
    def alterar(instancias):
        encontrado = next((i for i in instancias if i.get("id") == identificador), None)
        if encontrado is None:
            raise ErroAutomacao("Esta automação não está mais instalada.")
        if ativo and not _preparar(painel, encontrado)[0]["confiavel"]:
            raise ErroAutomacao("Autorize esta versão no próprio computador antes de ativar.")
        encontrado["ativo"] = bool(ativo)
    _alterar(painel, alterar)
    return _publica(painel, _encontrar(painel, identificador))


def remover(painel: Painel, identificador: str) -> None:
    _encontrar(painel, identificador)
    _alterar(painel, lambda instancias: instancias.__setitem__(slice(None), [i for i in instancias if i.get("id") != identificador]))


def _comando_catalogo(script: Path) -> list[str]:
    """Scripts nativos sem dependências usam o Python já instalado do painel."""
    fonte = script.read_text(encoding="utf-8-sig")
    bloco = re.search(r"(?m)^# /// script\r?\n((?:#.*\r?\n)*?)# ///(?:\r?\n|$)", fonte)
    if bloco:
        try:
            metadados = tomllib.loads("\n".join(linha[2:] if linha.startswith("# ") else linha[1:]
                                               for linha in bloco.group(1).splitlines()))
        except tomllib.TOMLDecodeError:
            raise ErroAutomacao("Os requisitos desta automação estão inválidos. Atualize a instalação.") from None
        if metadados.get("dependencies") == [] and metadados.get("requires-python") in (None, ">=3.11"):
            return [sys.executable, str(script)]
    uv = shutil.which("uv")
    if not uv:
        raise ErroAutomacao("Esta automação precisa do uv para preparar seus requisitos. Instale-o e tente novamente.")
    return [uv, "run", "--quiet", "--no-project", "--script", str(script)]


def _executar(painel: Painel, instancia: dict, estado: dict, arquivos: dict[str, bytes]) -> tuple[list[dict], str]:
    if not estado["confiavel"]:
        return [], "Autorize esta versão no próprio computador antes de executar."
    disponiveis = {**carregar_env(), **os.environ}
    faltam = [k for k in estado["requer"] if not disponiveis.get(k)]
    if faltam:
        return [], "Faltam os segredos: " + ", ".join(faltam) + ". Configure-os em Ajustes > Segredos."
    segredos = {k: v for k, v in disponiveis.items() if k in estado["requer"] or re.search(r"key|token|secret|password|credential", k, re.I)}
    if instancia["definicao"].endswith("agenda_ics.py"):
        for numero, agenda in enumerate(estado["config"].get("agendas", [])):
            endereco = agenda.get("url") if isinstance(agenda, dict) else agenda
            if isinstance(endereco, str) and endereco:
                segredos[f"endereco_ical_{numero}"] = endereco
    ambiente = {k: v for k, v in os.environ.items() if k.upper() in coletores._AMBIENTE_BASICO}
    ambiente.update({k: disponiveis[k] for k in estado["requer"]})
    ambiente.update({"ORQUESTRA_CONFIG": json.dumps(estado["config"], ensure_ascii=False), "ORQUESTRA_VAULT": str(painel.vault),
                     "ORQUESTRA_MODULO": str(_destino(painel, instancia["destino"])[0]), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    evento = threading.Event()
    chave = os.path.normcase(os.path.abspath(painel.vault))
    with coletores._trava_execucoes:
        coletores._execucoes.setdefault(chave, set()).add(evento)
    try:
        with coletores._pasta_temporaria() as temporaria:
            pasta = Path(temporaria)
            for nome, dados in arquivos.items():
                destino = pasta / nome
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(dados)
            script = pasta / estado["script"]
            comando = _comando_catalogo(script)
            stdout, stderr, codigo, erro = coletores._executar_limitado(comando, pasta, ambiente, evento)
        if erro or evento.is_set():
            return [], erro or "A execução foi interrompida porque o cofre foi fechado."
        if codigo:
            linhas = coletores._ocultar(stderr.decode("utf-8", errors="replace"), segredos).strip().splitlines()
            return [], linhas[-1][:1000] if linhas else "A automação terminou com erro."
        itens = []
        for linha in coletores._ocultar(stdout.decode("utf-8", errors="replace"), segredos).splitlines():
            try:
                item = json.loads(linha)
            except (ValueError, RecursionError):
                continue
            if isinstance(item, dict) and item.get("id") and item.get("titulo"):
                if len(itens) >= coletores.LIMITE_ITENS:
                    return [], "A automação excedeu 2.000 itens. Reduza a quantidade por execução."
                itens.append(item)
        return itens, coletores._falha_sem_itens(stderr) if not itens else ""
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as erro:
        return [], coletores._ocultar(str(erro), segredos)[:1000]
    finally:
        with coletores._trava_execucoes:
            coletores._execucoes.get(chave, set()).discard(evento)
            if not coletores._execucoes.get(chave):
                coletores._execucoes.pop(chave, None)


def _mapear(instancia: dict, itens: list[dict]) -> list[dict]:
    saida = []
    mapeamento = instancia.get("mapeamento", {})
    for original in itens:
        item = {k: v for k, v in original.items() if k in coletores.CHAVES_RESERVADAS and k != "campos"}
        campos = coletores._campos_do_item(original)
        destinos = [mapeamento.get(k, k) for k in campos]
        if len(destinos) != len(set(destinos)):
            raise ErroAutomacao("O mapeamento faria dois valores ocuparem o mesmo campo. Escolha nomes diferentes.")
        item["campos"] = {mapeamento.get(k, k): v for k, v in campos.items()}
        saida.append(item)
    return saida


def _sincronizar_destino(painel: Painel, pasta: Path) -> None:
    """Atualiza só o destino antes de deduplicar resultados de outro processo."""
    conhecidos = {n.caminho for n in list(painel.indice.notas.values()) if n.caminho.parent == pasta}
    caminhos = conhecidos | {p for p in pasta.iterdir() if p.suffix.lower() == ".md"}
    for caminho in caminhos:
        try:
            seguro = caminho_no_vault(painel.vault, caminho)
            info = seguro.stat()
        except FileNotFoundError:
            if caminho in conhecidos:
                painel.apos_escrita(caminho, "externo")
            continue
        except (OSError, ValueError):
            continue
        rel = seguro.relative_to(painel.vault).as_posix()
        assinatura = (info.st_mtime_ns, info.st_size, info.st_ctime_ns)
        if painel.indice._assinaturas.get(rel) != assinatura:
            painel.apos_escrita(seguro, "externo")


def _concluir(painel: Painel, instancia: dict, assinatura: str, itens: list[dict], erro: str) -> dict:
    with painel._trava, armazenamento.trava(_arquivo(painel)):
        atual = _encontrar(painel, instancia["id"])
        estado, _ = _preparar(painel, atual)
        if not secrets.compare_digest(estado["assinatura"], assinatura) or not estado["confiavel"]:
            erro = "A configuração ou autorização mudou durante a execução; nenhuma nota foi importada."
        novos, repetidos = 0, 0
        if not erro:
            _colisoes(painel, atual)
            modulo = _modulo_destino(painel, atual)
            _sincronizar_destino(painel, modulo.pasta_itens)
            _, coletor = _definicao(atual["definicao"])
            fonte = hashlib.sha256(json.dumps({k: atual[k] for k in ("definicao", "config", "mapeamento")}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            criadas, repetidos = coletores.importar(painel.indice, modulo, coletor, _mapear(atual, itens), escopo_pasta=True, rastreio_fonte=fonte)
            for nota in criadas:
                painel.apos_escrita(nota.caminho, f"coletor:{Path(coletor.script).stem}")
            novos = len(criadas)
        resultado = {"ok": not bool(erro), "novos": novos, "repetidos": repetidos, "erro": erro, "ultima": dt.datetime.now().isoformat(timespec="seconds")}
        painel.gravar_estado("automacoes", instancia["id"], resultado)
        painel.eventos.publicar({"tipo": "automacao", "id": instancia["id"]})
        return resultado


async def rodar(painel: Painel, identificador: str, previa: bool = False) -> dict:
    chave = "automacao:" + identificador
    if chave in painel.rodando:
        return {"ok": False, "erro": "Esta automação já está rodando."}
    painel.rodando.add(chave)
    try:
        instancia = _encontrar(painel, identificador)
        estado, arquivos = await asyncio.to_thread(_preparar, painel, instancia)
        itens, erro = await asyncio.to_thread(_executar, painel, instancia, estado, arquivos)
        if previa:
            return {"ok": not bool(erro), "erro": erro, "previa": True, "total": len(itens), "amostra": _mapear(instancia, itens[:5])}
        return await asyncio.to_thread(_concluir, painel, instancia, estado["assinatura"], itens, erro)
    except (OSError, ValueError, KeyError, TypeError) as erro:
        return {"ok": False, "erro": str(erro)[:1000]}
    finally:
        painel.rodando.discard(chave)


async def verificar(painel: Painel, agora: dt.datetime) -> None:
    for instancia in listar(painel):
        if not instancia.get("ativo") or not instancia["confianca"].get("confiavel"):
            continue
        try:
            ultima = dt.datetime.fromisoformat(instancia["ultima"]["ultima"]) if instancia["ultima"].get("ultima") else None
        except (ValueError, TypeError):
            ultima = None
        regra = ColetorDef(script="", nome="", a_cada=instancia.get("a_cada"), diario_as=instancia.get("diario_as"))
        if ultima is None and regra.diario_as:
            try:
                hora = dt.time.fromisoformat(regra.diario_as)
            except ValueError:
                continue
            if agora.time() < hora:
                continue
        if coletores.devido(regra, ultima, agora):
            await rodar(painel, instancia["id"])
