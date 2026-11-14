"""Preparo de um vault: criar um novo ou adaptar um que já existe.

Tudo aqui segue uma regra só: **nunca sobrescrever nem apagar o que já está na
pasta**. Por isso a mesma função serve para os dois casos. Numa pasta vazia ela
cria o vault inteiro; num vault do Obsidian que a pessoa já usa, ela só acrescenta
o que falta (o contrato dos agentes, a configuração do painel e os módulos que a
pessoa escolheu) e conta, num relatório, o que criou e o que deixou como estava.

- `modelo_vault/` tem o que todo vault recebe: AGENTS.md, orquestra.yaml, temas.
- `catalogo/` tem os módulos prontos. Cada pasta ali é copiada como está.
- `catalogo/perfis.yaml` agrupa os módulos em pontos de partida (perfis).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from orquestra import adocao, backup
from orquestra.config import gravar_yaml, ler_yaml, pasta_app
from orquestra.modulos import ARQUIVO_MODULO, descobrir
from orquestra import armazenamento
from orquestra.caminhos import arquivos_do_vault, caminho_no_vault

RAIZ = Path(__file__).parent
MODELO = RAIZ / "modelo_vault"
CATALOGO = RAIZ / "catalogo"
PERFIL_PADRAO = "criador"

MODELO_ENV = """\
# Chaves de API usadas pelos coletores. Este arquivo fica fora do vault de propósito:
# o vault vai para backup, e segredo não deve ir junto.
#
# YOUTUBE_API_KEY=
"""

ARQUIVO_APRENDIZADOS = "aprendizados.md"
MODELO_APRENDIZADOS = """# Aprendizados: {nome}

O que os agentes aprenderam trabalhando neste módulo: o que funcionou, o que a
pessoa corrigiu, o que ela não quer mais. Todo agente lê este arquivo antes de
começar e acrescenta uma linha ao terminar, quando aprendeu algo que vale para a
próxima vez. É assim que o trabalho melhora a cada rodada, e não só se repete.

Formato: uma linha por aprendizado, com a data. Só fatos e correções; nada de relato.

## Aprendizados

"""

_MARCADOR_DATA = re.compile(r"\{\{hoje(?:([+-])(\d+))?\}\}")
_NOME_COM_DATA = re.compile(r"^_HOJE(?:([+-])(\d+))?_$")
PASTAS_PULADAS = {".git", ".obsidian", ".trash", "__pycache__", "node_modules", ".venv"}
LIMITE_DE_ARQUIVOS = 30000  # ao analisar uma pasta, para não travar em pastas gigantes


class PastaRecusada(Exception):
    """A pasta escolhida não pode ser um vault; a mensagem explica por quê."""


@dataclass
class ModuloPronto:
    id: str
    nome: str
    descricao: str
    icone: str
    ordem: int


@dataclass
class Perfil:
    id: str
    nome: str
    descricao: str
    modulos: list[str]


@dataclass
class Relatorio:
    vault: Path
    novo: bool = False  # a pasta estava vazia (ou não existia)
    criados: list[str] = field(default_factory=list)
    mantidos: list[str] = field(default_factory=list)  # já existiam; não foram tocados
    avisos: list[str] = field(default_factory=list)
    com_git: bool = False


# ---------------------------------------------------------------- catálogo e perfis


def catalogo() -> dict[str, ModuloPronto]:
    """Módulos prontos que vêm com o Orquestra, na ordem em que aparecem no painel."""
    assinaturas = []
    for pasta in sorted(CATALOGO.iterdir()):
        arquivo = pasta / ARQUIVO_MODULO
        if arquivo.is_file():
            info = arquivo.stat()
            assinaturas.append((pasta.name, info.st_mtime_ns, info.st_ctime_ns, info.st_size))
    # Só metadados do catálogo distribuído. Configurações e notas dos cofres
    # continuam sendo relidas por seus próprios mecanismos de versão.
    prontos = _catalogo_distribuido(str(CATALOGO.resolve()), tuple(assinaturas))
    return {m.id: replace(m) for m in prontos}


@lru_cache(maxsize=4)
def _catalogo_distribuido(raiz: str, assinaturas: tuple) -> tuple[ModuloPronto, ...]:
    prontos = []
    for nome, *_ in assinaturas:
        pasta = Path(raiz) / nome
        bruto = ler_yaml(pasta / ARQUIVO_MODULO)
        prontos.append(
            ModuloPronto(
                id=pasta.name,
                nome=str(bruto.get("nome") or pasta.name),
                descricao=str(bruto.get("descricao") or ""),
                icone=str(bruto.get("icone") or "pasta"),
                ordem=int(bruto.get("ordem", 100)),
            )
        )
    prontos.sort(key=lambda m: (m.ordem, m.nome.lower()))
    return tuple(prontos)


def perfis() -> dict[str, Perfil]:
    """Pontos de partida: cada perfil é uma lista de módulos do catálogo."""
    disponiveis = catalogo()
    resultado: dict[str, Perfil] = {}
    for chave, dados in ler_yaml(CATALOGO / "perfis.yaml").items():
        if not isinstance(dados, dict):
            continue
        resultado[str(chave)] = Perfil(
            id=str(chave),
            nome=str(dados.get("nome") or chave),
            descricao=str(dados.get("descricao") or ""),
            modulos=[str(m) for m in dados.get("modulos") or [] if str(m) in disponiveis],
        )
    return resultado


def modulos_do_perfil(perfil: str | None) -> list[str]:
    todos = perfis()
    if perfil and perfil not in todos:
        raise PastaRecusada(f"Perfil '{perfil}' não existe. Opções: {', '.join(todos)}.")
    return list(todos[perfil or PERFIL_PADRAO].modulos)


# ---------------------------------------------------------------- cópia que nunca sobrescreve


def _datas_relativas(texto: str, hoje: dt.date) -> str:
    """Troca {{hoje}}, {{hoje+2}}, {{hoje-1}} por datas reais, para o exemplo nascer atual."""

    def trocar(m: re.Match) -> str:
        dias = int(m.group(2) or 0) * (-1 if m.group(1) == "-" else 1)
        return (hoje + dt.timedelta(days=dias)).isoformat()

    return _MARCADOR_DATA.sub(trocar, texto)


def _nome_final(nome: str, hoje: dt.date) -> str:
    """'_HOJE_.md' e '_HOJE-3_.md' viram a data correspondente."""
    achado = _NOME_COM_DATA.match(Path(nome).stem)
    if not achado:
        return nome
    dias = int(achado.group(2) or 0) * (-1 if achado.group(1) == "-" else 1)
    return (hoje + dt.timedelta(days=dias)).isoformat() + Path(nome).suffix


def _copiar(origem: Path, destino: Path, vault: Path, hoje: dt.date, relatorio: Relatorio, pular: tuple[str, ...] = ()) -> None:
    """Copia uma árvore do modelo para o vault. Arquivo que já existe fica como está."""
    for raiz, pastas, arquivos in os.walk(origem):
        pastas[:] = sorted(p for p in pastas if p != "__pycache__")
        rel_raiz = Path(raiz).relative_to(origem)
        if rel_raiz.parts and rel_raiz.parts[0] in pular:
            continue
        for nome in sorted(arquivos):
            alvo = caminho_no_vault(vault, destino / rel_raiz / _nome_final(nome, hoje))
            rel = alvo.relative_to(vault).as_posix()
            if alvo.exists():
                relatorio.mantidos.append(rel)
                continue
            fonte = Path(raiz) / nome
            if fonte.suffix.lower() == ".md":
                dados = _datas_relativas(fonte.read_text(encoding="utf-8"), hoje).encode("utf-8")
            else:
                dados = fonte.read_bytes()
            try:
                armazenamento.gravar_bytes(alvo, dados, criar=True, validar=lambda: caminho_no_vault(vault, alvo))
            except FileExistsError:
                relatorio.mantidos.append(rel)
                continue
            relatorio.criados.append(rel)


def _pasta_com_esse_nome(vault: Path, nome: str) -> Path | None:
    """Procura sem diferenciar maiúsculas: 'Tarefas' e 'tarefas' são a mesma pasta no Windows e no macOS."""
    try:
        return next((p for p in vault.iterdir() if p.is_dir() and p.name.lower() == nome.lower()), None)
    except OSError:
        return None


def adicionar_modulo(vault: Path, modulo_id: str, exemplos: bool = True, relatorio: Relatorio | None = None) -> bool:
    """Copia um módulo do catálogo para o vault. Devolve False se já havia uma pasta com esse nome."""
    relatorio = relatorio or Relatorio(vault)
    origem = CATALOGO / modulo_id
    if modulo_id not in catalogo():
        raise PastaRecusada(f"O módulo '{modulo_id}' não está no catálogo.")
    existente = _pasta_com_esse_nome(vault, modulo_id)
    if existente is not None:
        relatorio.mantidos.append(existente.name + "/")
        relatorio.avisos.append(
            f"Já existe uma pasta '{existente.name}'. Não mexi nela: se quiser vê-la no painel, "
            "use “Mostrar no painel” em Pastas."
        )
        return False
    destino = caminho_no_vault(vault, modulo_id)
    _copiar(origem, destino, vault, dt.date.today(), relatorio, pular=() if exemplos else ("itens", "midia"))
    for zona in ("itens", "humano", "maquina"):
        caminho_no_vault(vault, destino / zona).mkdir(parents=True, exist_ok=True)
    garantir_aprendizados(destino, catalogo()[modulo_id].nome)
    relatorio.criados.append(f"{modulo_id}/maquina/{ARQUIVO_APRENDIZADOS}")
    return True


def garantir_aprendizados(pasta_modulo: Path, nome: str) -> Path:
    """Cria o arquivo de aprendizados do módulo, se ainda não existir."""
    vault = pasta_modulo.parent
    caminho = caminho_no_vault(vault, pasta_modulo / "maquina" / ARQUIVO_APRENDIZADOS)
    if not caminho.exists():
        try:
            armazenamento.gravar_bytes(caminho, MODELO_APRENDIZADOS.format(nome=nome).encode("utf-8"), criar=True,
                                       validar=lambda: caminho_no_vault(vault, caminho))
        except FileExistsError:
            pass
    return caminho


# ---------------------------------------------------------------- preparar


def _definir(caminho: Path, **chaves: Any) -> None:
    """Altera chaves do orquestra.yaml preservando os comentários do arquivo."""
    dados = ler_yaml(caminho)
    for chave, valor in chaves.items():
        if valor is None:
            continue
        if chave.startswith("backup_"):
            if not isinstance(dados.get("backup"), dict):
                dados["backup"] = {}
            dados["backup"][chave.removeprefix("backup_")] = valor
        else:
            dados[chave] = valor
    gravar_yaml(caminho, dados)


def _comece_aqui(vault: Path) -> str:
    modelo = (MODELO / "Comece aqui.md").read_text(encoding="utf-8")
    linhas = [f"| `{m.id}/` | {m.descricao or m.nome} |" for m in descobrir(vault).values()]
    linhas.append("| `diario/` | O que mudou e o que os agentes fizeram. |")
    return modelo.replace("{{modulos}}", "\n".join(linhas))


def conferir_pasta(caminho: str | Path) -> Path:
    """Valida a pasta escolhida para ser um vault e devolve o caminho absoluto."""
    texto = str(caminho or "").strip().strip('"')
    if not texto:
        raise PastaRecusada("Diga em que pasta o vault fica.")
    pasta = Path(texto).expanduser()
    if not pasta.is_absolute():
        raise PastaRecusada("Use o caminho completo da pasta (por exemplo, o que aparece na barra do explorador de arquivos).")
    pasta = pasta.resolve()
    if pasta.parent == pasta:
        raise PastaRecusada("Escolha uma pasta, não a unidade inteira.")
    if pasta == Path.home().resolve():
        raise PastaRecusada("Sua pasta pessoal inteira é grande demais para ser um vault. Escolha (ou crie) uma pasta dentro dela.")
    if pasta.exists() and not pasta.is_dir():
        raise PastaRecusada("Isso é um arquivo, não uma pasta.")
    projeto = RAIZ.parent.parent
    if RAIZ == pasta or RAIZ in pasta.parents or (projeto / "pyproject.toml").is_file() and pasta.is_relative_to(projeto):
        raise PastaRecusada("Essa é a pasta do próprio programa. Escolha outra para os seus arquivos.")
    return pasta


def preparar(
    destino: str | Path,
    modulos: list[str] | None = None,
    exemplos: bool = True,
    nome: str | None = None,
    tema: str | None = None,
    com_backup: bool | None = None,
    pastas: list[dict[str, Any]] | None = None,
) -> Relatorio:
    """Deixa a pasta pronta para o painel. Vale para pasta vazia e para vault que já existe.

    - `modulos`: ids do catálogo a acrescentar (pastas que já existem não são tocadas);
    - `pastas`: pastas da raiz a mostrar no painel, como `{"pasta": "Projetos", "quadro": True}`;
    - `com_backup`: liga o histórico em git. Por padrão, só em vault novo: num vault que a
      pessoa já usa, mexer com git sem perguntar pode atrapalhar o que ela já tem.
    """
    vault = conferir_pasta(destino)
    vault.mkdir(parents=True, exist_ok=True)
    hoje = dt.date.today()
    relatorio = Relatorio(vault, novo=not any(vault.iterdir()))
    if com_backup is None:
        com_backup = relatorio.novo
    ja_era_vault = caminho_no_vault(vault, "orquestra.yaml").is_file()

    # ---- o que todo vault recebe
    _copiar(MODELO / "_orquestra", vault / "_orquestra", vault, hoje, relatorio)
    if not ja_era_vault:
        armazenamento.gravar_bytes(caminho_no_vault(vault, "orquestra.yaml"), (MODELO / "orquestra.yaml").read_bytes(), criar=True,
                                   validar=lambda: caminho_no_vault(vault, "orquestra.yaml"))
        relatorio.criados.append("orquestra.yaml")

    contrato = caminho_no_vault(vault, "AGENTS.md")
    if not contrato.exists():
        armazenamento.gravar_bytes(contrato, (MODELO / "AGENTS.md").read_bytes(), criar=True,
                                   validar=lambda: caminho_no_vault(vault, contrato))
        relatorio.criados.append("AGENTS.md")
    elif "Orquestra" not in contrato.read_text(encoding="utf-8", errors="replace"):
        # A pessoa já tem as próprias regras para agentes. Não misturamos: as nossas vão ao lado.
        ao_lado = caminho_no_vault(vault, "AGENTS.orquestra.md")
        if not ao_lado.exists():
            armazenamento.gravar_bytes(ao_lado, (MODELO / "AGENTS.md").read_bytes(), criar=True,
                                       validar=lambda: caminho_no_vault(vault, ao_lado))
            relatorio.criados.append(ao_lado.name)
        relatorio.avisos.append(
            "Você já tinha um AGENTS.md, então guardei as regras do painel em AGENTS.orquestra.md. "
            "Peça ao seu agente para ler os dois, ou junte os arquivos quando quiser."
        )
    # O Claude Code lê CLAUDE.md, que importa os contratos com @. Assim as mesmas regras
    # valem para todos os agentes, sem copiar o texto. Um CLAUDE.md da pessoa fica como está.
    claude = caminho_no_vault(vault, "CLAUDE.md")
    suplemento = caminho_no_vault(vault, "AGENTS.orquestra.md").is_file()
    if not claude.exists():
        conteudo = (MODELO / "CLAUDE.md").read_bytes()
        if suplemento:
            conteudo = conteudo.rstrip() + b"\n@AGENTS.orquestra.md\n"
        armazenamento.gravar_bytes(claude, conteudo, criar=True, validar=lambda: caminho_no_vault(vault, claude))
        relatorio.criados.append("CLAUDE.md")
    elif suplemento and "@AGENTS.orquestra.md" not in claude.read_text(encoding="utf-8", errors="replace"):
        relatorio.avisos.append(
            "Seu CLAUDE.md foi preservado. Para o Claude Code ler também as regras do painel, "
            "acrescente a linha @AGENTS.orquestra.md a ele."
        )

    # ---- módulos do catálogo e pastas adotadas
    escolhidos = [m for m in dict.fromkeys(modulos or [])]
    for modulo_id in escolhidos:
        adicionar_modulo(vault, modulo_id, exemplos, relatorio)
    for pedido in pastas or []:
        try:
            criado = adocao.adotar(vault, str(pedido.get("pasta") or ""), bool(pedido.get("quadro")))
            relatorio.criados.append(criado.relative_to(vault).as_posix())
        except adocao.NaoPodeAdotar as e:
            relatorio.avisos.append(str(e))

    if exemplos and relatorio.novo and {"conteudo", "radar"} <= set(escolhidos):
        _copiar(MODELO / "diario", vault / "diario", vault, hoje, relatorio)

    comeco = caminho_no_vault(vault, "Comece aqui.md" if relatorio.novo else "Orquestra - comece aqui.md")
    if not ja_era_vault and not comeco.exists():
        armazenamento.gravar_bytes(comeco, _comece_aqui(vault).encode("utf-8"), criar=True,
                                   validar=lambda: caminho_no_vault(vault, comeco))
        relatorio.criados.append(comeco.name)

    # ---- configuração do painel
    existentes = descobrir(vault)
    captura = None
    if not ja_era_vault:
        captura = "entrada" if "entrada" in existentes else ""
    _definir(
        vault / "orquestra.yaml",
        nome=(nome or "").strip() or None,
        tema=tema or None,
        captura=captura,
        backup_auto_commit=None if ja_era_vault else bool(com_backup),
    )

    env = pasta_app() / ".env"
    if not env.exists():
        env.parent.mkdir(parents=True, exist_ok=True)
        armazenamento.gravar_bytes(env, MODELO_ENV.encode("utf-8"), criar=True, backup=False)
        if os.name != "nt":
            env.chmod(0o600)

    if com_backup:
        relatorio.com_git = backup.iniciar(vault)
        if relatorio.com_git:
            if relatorio.novo:
                revisao = backup.resumo(vault)
                backup.autorizar(vault, revisao["assinatura"])
            if backup.resumo(vault)["confiavel"]:
                resultado = backup.commit(vault, "Vault criado pelo Orquestra" if relatorio.novo else "Orquestra configurado neste vault")
                if resultado not in ("feito", "nada"):
                    relatorio.avisos.append(resultado)
                    relatorio.com_git = False
            else:
                relatorio.avisos.append("O histórico foi preparado. Revise e autorize a configuração Git em Ajustes neste computador antes de fazer cópias.")
                relatorio.com_git = False
    return relatorio


# ---------------------------------------------------------------- olhar antes de mexer


def cofres_obsidian() -> list[dict[str, Any]]:
    """Vaults que o Obsidian desta máquina conhece, do mais recente para o mais antigo.

    O Obsidian guarda a lista num `obsidian.json` na pasta de configuração dele. Só
    lemos esse arquivo; nada nele é alterado.
    """
    casa = Path.home()
    candidatos = [
        Path(os.environ.get("APPDATA", "")) / "obsidian" / "obsidian.json" if os.environ.get("APPDATA") else None,
        casa / "Library" / "Application Support" / "obsidian" / "obsidian.json",
        Path(os.environ.get("XDG_CONFIG_HOME") or casa / ".config") / "obsidian" / "obsidian.json",
        casa / ".var" / "app" / "md.obsidian.Obsidian" / "config" / "obsidian" / "obsidian.json",
        casa / "snap" / "obsidian" / "current" / ".config" / "obsidian" / "obsidian.json",
    ]
    achados: dict[str, dict[str, Any]] = {}
    for arquivo in candidatos:
        if arquivo is None or not arquivo.is_file():
            continue
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cofres = dados.get("vaults") if isinstance(dados, dict) else None
        for cofre in (cofres or {}).values() if isinstance(cofres, dict) else []:
            caminho = Path(str(cofre.get("path") or "")) if isinstance(cofre, dict) else None
            if caminho is None or not caminho.is_dir():
                continue
            achados[str(caminho).lower()] = {
                "caminho": str(caminho),
                "nome": caminho.name,
                "ts": int(cofre.get("ts") or 0),
                "aberto": bool(cofre.get("open")),
                "ja_e_vault": (caminho / "orquestra.yaml").is_file(),
            }
    return sorted(achados.values(), key=lambda c: c["ts"], reverse=True)


def analisar(caminho: str | Path) -> dict[str, Any]:
    """Olha uma pasta sem alterar nada e conta o que há nela, para a pessoa decidir."""
    vault = conferir_pasta(caminho)
    info: dict[str, Any] = {
        "caminho": str(vault),
        "nome": vault.name,
        "existe": vault.is_dir(),
        "vazia": True,
        "ja_e_vault": False,
        "obsidian": False,
        "tem_agents": False,
        "tem_git": False,
        "notas": 0,
        "soltas": 0,
        "pastas": [],
        "estilo": {"id": "vazio", "nome": adocao.ESTILOS["vazio"][0], "descricao": adocao.ESTILOS["vazio"][1]},
        "modulos": [],
    }
    if not vault.is_dir():
        return info

    info["vazia"] = not any(vault.iterdir())
    info["ja_e_vault"] = (vault / "orquestra.yaml").is_file()
    info["obsidian"] = (vault / ".obsidian").is_dir()
    info["tem_agents"] = (vault / "AGENTS.md").is_file()
    info["tem_git"] = (vault / ".git").exists()

    contagem: dict[str, int] = {}
    nomes: list[str] = []
    vistos = 0
    for rel, arquivo, _stat in arquivos_do_vault(vault):
        topo = rel.split("/", 1)[0] if "/" in rel else ""
        vistos += 1
        if arquivo.suffix.lower() == ".md":
            info["notas"] += 1
            if topo:
                contagem[topo] = contagem.get(topo, 0) + 1
            else:
                info["soltas"] += 1
            if len(nomes) < 4000:
                nomes.append(arquivo.stem)
        if vistos > LIMITE_DE_ARQUIVOS:
            info["truncado"] = True
            break

    existentes = descobrir(vault)
    info["modulos"] = [{"id": m.id, "nome": m.nome} for m in existentes.values()]
    for nome_pasta in sorted(contagem, key=str.lower):
        if nome_pasta.startswith("_") or nome_pasta == "diario":
            continue
        entrada: dict[str, Any] = {"pasta": nome_pasta, "notas": contagem[nome_pasta], "modulo": nome_pasta in existentes}
        if not entrada["modulo"]:
            entrada.update(adocao.resumo_da_pasta(caminho_no_vault(vault, nome_pasta)))
        info["pastas"].append(entrada)
    estilo = adocao.detectar_estilo([p["pasta"] for p in info["pastas"]], nomes)
    info["estilo"] = {"id": estilo, "nome": adocao.ESTILOS[estilo][0], "descricao": adocao.ESTILOS[estilo][1]}
    return info


# ---------------------------------------------------------------- escolher pasta pela janela do sistema

_JANELA = """
import tkinter, tkinter.filedialog
raiz = tkinter.Tk()
raiz.withdraw()
raiz.attributes("-topmost", True)
print(tkinter.filedialog.askdirectory(parent=raiz, title="Escolha a pasta do vault", mustexist=False) or "")
"""


def escolher_pasta_no_sistema() -> str | None:
    """Abre a janela "escolher pasta" do sistema. Devolve None se ela não estiver disponível.

    Roda em outro processo porque a janela trava quem a abre até a pessoa responder.
    """
    import subprocess

    try:
        r = subprocess.run([sys.executable, "-c", _JANELA], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()
