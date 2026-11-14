"""Snapshots Git recuperáveis sem alterar HEAD ou o staging da pessoa."""
from __future__ import annotations

import configparser
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import tempfile
import threading
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from orquestra.armazenamento import atualizar_bytes, gravar_bytes, pasta_local, trava
from orquestra.caminhos import caminho_no_vault, eh_link

REF_BACKUP = "refs/orquestra/backups"
BRANCH_REMOTO = "orquestra-backup"
_locais = threading.local()
_AMBIENTE_GIT = {
    "PATH", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR",
    "SSH_AUTH_SOCK", "SSH_AGENT_PID", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "GIT_SSL_CAINFO", "GIT_SSL_CAPATH",
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "LC_COLLATE", "LC_TIME", "TERM", "NO_COLOR",
}
GITIGNORE_DO_VAULT = """\
# Estado do Orquestra e do Obsidian
_orquestra/estado.json
.obsidian/workspace*.json
.obsidian/cache
.trash/
*.orq-tmp

# Segredos ficam fora do vault
.env
.env.*
!.env.example
!.env.sample
!.env.template
*.pem
*.key
*.p12
*.pfx
id_rsa
id_ed25519
credentials.json
secrets.json
"""

class ErroBackup(ValueError):
    """Erro sem stderr/credenciais do Git."""


@contextlib.contextmanager
def _operacao_git(vault: Path):
    """Cache apenas de Paths por operação, nunca da decisão de segurança.

    Cada comando reenumera a árvore com scandir e atributos no-follow atuais.
    Isso evita que uma validação antiga autorize um link criado entre comandos.
    """
    anterior = getattr(_locais, "caminhos", None)
    if anterior is None:
        _locais.caminhos = {}
    try:
        yield
    finally:
        if anterior is None:
            del _locais.caminhos


def _com_operacao_git(funcao):
    @wraps(funcao)
    def executar(vault, *args, **kwargs):
        with _operacao_git(vault):
            return funcao(vault, *args, **kwargs)
    return executar


def _path_meta(texto: str) -> Path:
    cache = getattr(_locais, "caminhos", None)
    if cache is None:
        return Path(texto)
    caminho = cache.get(texto)
    if caminho is None:
        caminho = cache[texto] = Path(texto)
    return caminho


def _e_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _validar_arvore_git(vault: Path, *, permitir_ausente: bool = False, conferir_criticos: bool = True) -> Path:
    raiz = Path(os.path.abspath(vault))
    pasta = caminho_no_vault(raiz, raiz / ".git")
    try:
        info = pasta.lstat()
    except FileNotFoundError:
        if permitir_ausente:
            return pasta
        raise ErroBackup("O vault não tem uma pasta .git local.") from None
    if _e_link(info) or not stat.S_ISDIR(info.st_mode):
        raise ErroBackup("Metadados Git vinculados/worktrees não são aceitos no backup do Orquestra.")
    pendentes = [pasta]
    while pendentes:
        atual = caminho_no_vault(raiz, pendentes.pop())
        with os.scandir(atual) as entradas:
            for entrada in entradas:
                info = entrada.stat(follow_symlinks=False)
                if _e_link(info):
                    raise ErroBackup("A pasta .git contém link simbólico/junction. O backup foi bloqueado antes de executar Git.")
                caminho = _path_meta(entrada.path)
                if stat.S_ISDIR(info.st_mode):
                    pendentes.append(caminho)
                elif not stat.S_ISREG(info.st_mode):
                    raise ErroBackup("A pasta .git contém um arquivo especial incompatível com backup seguro.")
    if conferir_criticos:
        _validar_criticos_git(raiz, pasta)
    return pasta


def _validar_criticos_git(vault: Path, pasta: Path) -> None:
    # Rechecagem imediatamente antes do subprocesso, inclusive componentes que
    # ainda não existem e podem ser substituídos por uma junction após a varredura.
    criticos = ("config", "config.lock", "config.worktree", "index", "index.lock", "HEAD", "packed-refs", "packed-refs.lock",
                "objects", "objects/info", "objects/pack", "refs", "refs/heads", "refs/tags", "refs/orquestra",
                "refs/orquestra/backups", "refs/orquestra/backups.lock", "logs", "logs/refs", "logs/refs/heads",
                "logs/refs/orquestra", "logs/refs/orquestra/backups", "info", "info/exclude", "info/attributes", "worktrees")
    for relativo in criticos:
        caminho_no_vault(vault, _path_meta(str(pasta / relativo)))
    for relativo in ("commondir", "objects/info/alternates", "objects/info/http-alternates", "config.worktree"):
        caminho = caminho_no_vault(vault, pasta / relativo)
        try:
            info = caminho.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_size:
            raise ErroBackup("Git com alternates, commondir ou configuração de worktree externa não é aceito no backup.")
    worktrees = caminho_no_vault(vault, pasta / "worktrees")
    if worktrees.is_dir():
        with os.scandir(worktrees) as entradas:
            if next(entradas, None) is not None:
                raise ErroBackup("Repositórios com worktrees vinculados não são aceitos no backup automático.")
    config_git = caminho_no_vault(vault, pasta / "config")
    if config_git.is_file():
        if config_git.stat().st_size > 16 * 1024 * 1024:
            raise ErroBackup("A configuração Git excede o limite de revisão de 16 MB.")
        if re.search(rb"(?im)^\s*\[\s*include(?:if\b|\s*\])", config_git.read_bytes()):
            raise ErroBackup("Includes de configuração Git externa não são aceitos no backup automático.")
    head = caminho_no_vault(vault, pasta / "HEAD")
    if head.is_file():
        if head.stat().st_size > 4096:
            raise ErroBackup("O HEAD do repositório tem um formato incompatível.")
        texto = head.read_text(encoding="utf-8").strip()
        if texto.startswith("ref: "):
            referencia = texto[5:]
            if not referencia.startswith("refs/") or "\\" in referencia:
                raise ErroBackup("O HEAD do repositório aponta para uma referência inválida.")
            caminho_no_vault(vault, pasta / referencia)
            caminho_no_vault(vault, pasta / "logs" / referencia)


def git_disponivel() -> bool:
    return shutil.which("git") is not None


def _ambiente() -> dict[str, str]:
    ambiente = {k: v for k, v in os.environ.items() if k.upper() in _AMBIENTE_GIT}
    ambiente.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull,
                    GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1", GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1")
    return ambiente


def git(vault: Path, *args: str, tempo: int = 120, ambiente: dict[str, str] | None = None,
        texto: bool = True, entrada: bytes | None = None) -> subprocess.CompletedProcess:
    raiz = Path(os.path.abspath(vault))
    pasta_git = _validar_arvore_git(raiz, permitir_ausente=bool(args and args[0] == "init"), conferir_criticos=False)
    hooks = pasta_local() / "git-hooks-vazios"
    hooks.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = _ambiente()
    if ambiente:
        if set(ambiente) != {"GIT_INDEX_FILE"}:
            raise ErroBackup("A execução Git recebeu variáveis não autorizadas.")
        env.update(ambiente)
    _validar_criticos_git(raiz, pasta_git)
    credenciais = []
    # O backup ignora helpers herdados. No envio, permite apenas o helper oficial
    # instalado, para o host exato do login oferecido na interface. O token nunca
    # passa pelo app, por argumentos de processo ou pela configuração do vault.
    if args and args[0] == "push" and (gh := shutil.which("gh")):
        executavel = shlex.quote(Path(gh).resolve().as_posix())
        credenciais = ["-c", "credential.https://github.com.helper=", "-c",
                       f"credential.https://github.com.helper=!{executavel} auth git-credential"]
    return subprocess.run(
        ["git", f"--git-dir={pasta_git}", f"--work-tree={raiz}",
         "-c", f"core.hooksPath={hooks.resolve()}", "-c", "core.fsmonitor=false",
         "-c", "log.showSignature=false", "-c", "core.logAllRefUpdates=true",
         "-c", "commit.gpgSign=false", "-c", "credential.helper=", "-c", "core.sshCommand=ssh",
         "-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=always",
         "-c", f"core.attributesFile={os.devnull}", *credenciais, *args], cwd=raiz,
        capture_output=True, text=texto, encoding="utf-8" if texto else None,
        errors="replace" if texto else None, timeout=tempo, env=env, input=entrada,
    )


def _ok(resultado: subprocess.CompletedProcess, operacao: str, aceitos: tuple[int, ...] = (0,)):
    if resultado.returncode not in aceitos:
        raise ErroBackup(f"Git não conseguiu {operacao} (código {resultado.returncode}). Nenhuma confirmação de backup foi registrada.")
    return resultado


def _destino_visivel(endereco: str) -> str:
    """Resumo de remoto sem userinfo/query/fragmento, inclusive SCP e helpers."""
    personalizado = "[destino personalizado; consulte a configuração local]"
    # git config coloca valores com #/espaços entre aspas. RawConfigParser não
    # interpreta essas aspas; só decodificamos a forma literal conhecida, sem
    # expandir variáveis ou executar o próprio Git para mostrar um remoto.
    if endereco.startswith('"'):
        try:
            decodificado = json.loads(endereco)
        except ValueError:
            return personalizado
        if not isinstance(decodificado, str):
            return personalizado
        endereco = decodificado
    if any(ord(c) < 32 for c in endereco):
        return personalizado
    limpo = endereco.split("?", 1)[0].split("#", 1)[0]
    if re.match(r"^[A-Za-z]:[/\\]", limpo):
        return limpo  # caminho de disco Windows, não um esquema de URL
    if "::" in limpo and not limpo.startswith(("http://", "https://", "ssh://", "git://", "file://")):
        return personalizado  # remote-helper pode conter comando e segredos arbitrários
    try:
        partes = urlsplit(endereco)
        if partes.scheme in ("https", "http", "ssh", "git", "file"):
            if partes.netloc:
                host = partes.hostname or ""
                if ":" in host:
                    host = "[" + host + "]"
                if partes.port:
                    host += ":" + str(partes.port)
                return urlunsplit((partes.scheme, host, partes.path, "", ""))
            if partes.scheme == "file":
                return urlunsplit(("file", "", partes.path, "", ""))
            return personalizado
    except ValueError:
        return personalizado
    # Sintaxe SSH do Git não é uma URI: [usuario@]host:caminho.
    if ":" in limpo and "://" not in limpo:
        sem_usuario = limpo.rsplit("@", 1)[-1]
        if re.fullmatch(r"(?:\[[^\]]+\]|[^/:\s]+):.+", sem_usuario):
            return sem_usuario
        return personalizado
    return personalizado if "://" in limpo or "@" in limpo else limpo


def _metadados(vault: Path) -> tuple[dict, dict[str, bytes]]:
    vault = Path(os.path.abspath(vault))
    pasta = _validar_arvore_git(vault)
    if not pasta.is_dir():
        raise ErroBackup("O histórico precisa de uma pasta .git local; metadados Git vinculados não são aceitos.")
    dados = caminho_no_vault(vault, pasta / "config").read_bytes()
    if re.search(rb"(?im)^\s*\[\s*include(?:if\b|\s*\])", dados):
        raise ErroBackup("Includes de configuração Git externa não são aceitos no backup automático. Use uma configuração local revisável.")
    arquivos = {".git/config": dados}
    total = len(dados)
    for raiz, pastas, nomes in os.walk(vault, followlinks=False):
        base = Path(raiz)
        pastas[:] = sorted(p for p in pastas if p not in (".git", ".obsidian", "node_modules", ".venv") and not eh_link(base / p))
        if ".gitattributes" not in nomes:
            continue
        caminho = caminho_no_vault(vault, base / ".gitattributes")
        bruto = caminho.read_bytes()
        total += len(bruto)
        if len(arquivos) >= 1000 or total > 16 * 1024 * 1024:
            raise ErroBackup("Configuração/attributes Git excedem o limite de revisão do backup.")
        arquivos[caminho.relative_to(vault).as_posix()] = bruto
    parser = configparser.RawConfigParser(strict=False, allow_no_value=True)
    try:
        parser.read_string(dados.decode("utf-8"))
    except (configparser.Error, UnicodeError) as erro:
        raise ErroBackup("A configuração Git precisa ser UTF-8 válido e ter uma estrutura legível.") from erro
    remotos, avisos = [], []
    for secao in parser.sections():
        if secao.lower().startswith('remote "'):
            nome = secao[8:-1]
            for chave in ("url", "pushurl"):
                endereco = parser.get(secao, chave, fallback="") or ""
                if endereco:
                    remotos.append({"nome": nome, "tipo": chave, "destino": _destino_visivel(endereco)})
        if secao.lower().startswith(('filter ', 'credential ')) or any(
            chave.lower() in ("sshcommand", "receivepack", "uploadpack") for chave in parser[secao]
        ):
            avisos.append("A configuração Git contém comandos/filtros auxiliares; autorize somente se você a revisou.")
    manifesto = {nome: hashlib.sha256(bruto).hexdigest() for nome, bruto in sorted(arquivos.items())}
    assinatura = hashlib.sha256(json.dumps(manifesto, sort_keys=True).encode()).hexdigest()
    return {"assinatura": assinatura, "remotos": remotos, "avisos": sorted(set(avisos)), "arquivos": list(manifesto)}, arquivos


def _registro(vault: Path) -> tuple[Path, str]:
    casa = pasta_local().resolve()
    if casa == vault.resolve() or casa.is_relative_to(vault.resolve()):
        raise ErroBackup("ORQUESTRA_HOME precisa ficar fora do vault para guardar o aceite local de backup.")
    arquivo = casa / "confianca-backup.json"
    if eh_link(arquivo):
        raise ErroBackup("O registro local de confiança não pode ser um link.")
    return arquivo, hashlib.sha256(os.path.normcase(str(vault.resolve())).encode()).hexdigest()


def _aceites(vault: Path) -> dict:
    arquivo, _ = _registro(vault)
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


@_com_operacao_git
def resumo(vault: Path) -> dict:
    try:
        estado, _ = _metadados(vault)
        _, chave = _registro(vault)
        estado["confiavel"] = secrets.compare_digest(str(_aceites(vault).get(chave, "")), estado["assinatura"])
        return estado
    except (OSError, ValueError) as erro:
        return {"assinatura": "", "confiavel": False, "remotos": [], "avisos": [], "arquivos": [], "erro": str(erro)}


@_com_operacao_git
def autorizar(vault: Path, assinatura_esperada: str) -> dict:
    estado, _ = _metadados(vault)
    if not assinatura_esperada or not secrets.compare_digest(estado["assinatura"], str(assinatura_esperada)):
        raise ErroBackup("A configuração Git mudou. Confira a versão nova antes de autorizar.")
    arquivo, chave = _registro(vault)
    def alterar(bruto: bytes) -> bytes:
        aceites = json.loads(bruto) if bruto else {}
        if not isinstance(aceites, dict):
            raise ErroBackup("O registro local de backup está ilegível; não foi substituído.")
        aceites[chave] = estado["assinatura"]
        return json.dumps(aceites, ensure_ascii=False, sort_keys=True).encode("utf-8")
    atualizar_bytes(arquivo, alterar, backup=False)
    return {**estado, "confiavel": True}


def revogar(vault: Path) -> None:
    arquivo, chave = _registro(vault)
    def alterar(bruto: bytes) -> bytes:
        aceites = json.loads(bruto) if bruto else {}
        if not isinstance(aceites, dict):
            raise ErroBackup("O registro local de backup está ilegível.")
        aceites.pop(chave, None)
        return json.dumps(aceites, ensure_ascii=False, sort_keys=True).encode("utf-8")
    atualizar_bytes(arquivo, alterar, backup=False)


def _exigir_confianca(vault: Path) -> None:
    estado = resumo(vault)
    if not estado["confiavel"]:
        raise ErroBackup("Revise e autorize o histórico Git local em Ajustes antes de executar o backup. " + str(estado.get("erro") or "Configuração ou attributes ainda não autorizados."))


def e_repositorio(vault: Path) -> bool:
    try:
        return caminho_no_vault(vault, vault / ".git").is_dir()
    except (OSError, ValueError):
        return False


def tem_remoto(vault: Path) -> bool:
    return bool(resumo(vault).get("remotos")) if e_repositorio(vault) else False


def _identidade(vault: Path) -> list[str]:
    nome, email = git(vault, "config", "user.name"), git(vault, "config", "user.email")
    _ok(nome, "ler o nome do autor", (0, 1))
    _ok(email, "ler o e-mail do autor", (0, 1))
    return [] if nome.stdout.strip() and email.stdout.strip() else ["-c", "user.name=Orquestra", "-c", "user.email=orquestra@localhost"]


def _sensivel(nome: str) -> bool:
    base = Path(nome).name.lower()
    return ((base == ".env" or base.startswith(".env.")) and base not in (".env.example", ".env.sample", ".env.template")) or (
        base.endswith((".pem", ".key", ".p12", ".pfx")) or base in ("id_rsa", "id_ed25519", "credentials.json", "secrets.json")
    )


def _conferir_sensiveis(vault: Path, ambiente: dict[str, str] | None = None) -> None:
    resultado = _ok(git(vault, "ls-files", "-z", ambiente=ambiente), "conferir os arquivos rastreados")
    nomes = [nome for nome in resultado.stdout.split("\0") if nome and _sensivel(nome)]
    if nomes:
        raise ErroBackup("Há arquivos de segredo rastreados pelo Git. Remova-os do índice e revise o histórico antes de enviar: " + ", ".join(nomes[:4]))


def _conferir_historico(vault: Path, revisao: str) -> None:
    """Recusa nomes sensíveis em qualquer ancestral, inclusive ramos de merges.

    O formato raw sem renomes separa metadados e caminhos por NUL. Assim não
    perdemos nomes com espaços/quebras de linha nem arquivos já removidos.
    A revisão deve ser o hash imutável que será herdado ou enviado.
    """
    resultado = _ok(git(vault, "log", "--format=", "--raw", "-z", "--no-abbrev", "--no-renames",
                        "--full-history", "--root", "-m", "--no-ext-diff", "--no-textconv",
                        "--no-show-signature", revisao, "--", texto=False), "conferir o histórico do backup")
    registros = resultado.stdout.split(b"\0")
    if registros[-1] != b"" or (len(registros) - 1) % 2:
        raise ErroBackup("Não foi possível verificar todo o histórico do backup; o envio foi bloqueado.")
    sensiveis = set()
    for i in range(0, len(registros) - 1, 2):
        if not re.fullmatch(rb":[0-7]{6} [0-7]{6} [a-f0-9]{40,64} [a-f0-9]{40,64} [A-Z]", registros[i]):
            raise ErroBackup("O histórico do backup tem um formato inesperado; o envio foi bloqueado.")
        nome = registros[i + 1].decode("utf-8", errors="replace")
        if _sensivel(nome):
            sensiveis.add(nome)
    if sensiveis:
        raise ErroBackup("O histórico do backup contém arquivos de segredo, mesmo que já removidos. "
                         "O snapshot e o envio foram bloqueados; revise o histórico e rotacione segredos expostos. "
                         "Nenhuma versão antiga foi apagada: " + ", ".join(sorted(sensiveis)[:4]))


def _capturar_indice(vault: Path, ambiente: dict[str, str], pasta: Path) -> None:
    """Hash em lote de cópias imutáveis; nunca executa clean filters do vault."""
    resultado = _ok(git(vault, "ls-files", "--cached", "--others", "--exclude-standard", "-z", ambiente=ambiente),
                    "listar os arquivos do snapshot")
    nomes = sorted(set(n for n in resultado.stdout.split("\0") if n))
    copias, modos, removidos = [], [], []
    for numero, nome in enumerate(nomes):
        original = caminho_no_vault(vault, nome)
        if _sensivel(nome):
            raise ErroBackup("Um arquivo de segredo entraria no snapshot: " + nome)
        try:
            antes = original.stat()
            if not stat.S_ISREG(antes.st_mode):
                raise ErroBackup("O backup só aceita arquivos regulares dentro do vault: " + nome)
            dados = original.read_bytes()
            depois = original.stat()
        except FileNotFoundError:
            removidos.append(nome)
            continue
        if (antes.st_mtime_ns, antes.st_size, antes.st_ino) != (depois.st_mtime_ns, depois.st_size, depois.st_ino):
            raise ErroBackup("Um arquivo mudou durante a captura. Tente o snapshot novamente: " + nome)
        if b"-----BEGIN " in dados[:8192] and b"PRIVATE KEY-----" in dados[:8192]:
            raise ErroBackup("Uma chave privada entraria no snapshot; mantenha segredos fora do vault: " + nome)
        copia = pasta / f"arquivo-{numero}"
        copia.write_bytes(dados)
        copias.append((nome, copia))
        modos.append("100755" if os.name != "nt" and antes.st_mode & 0o111 else "100644")
    entrada = "\n".join(json.dumps(str(p.resolve()).replace("\\", "/"), ensure_ascii=False) for _, p in copias) + ("\n" if copias else "")
    hashes = []
    if copias:
        r = _ok(git(vault, "hash-object", "--no-filters", "-w", "--stdin-paths", texto=False,
                    entrada=entrada.encode("utf-8")), "gravar os objetos do snapshot sem filtros")
        hashes = r.stdout.decode("ascii").splitlines()
        if len(hashes) != len(copias) or any(not re.fullmatch(r"[a-f0-9]{40,64}", valor) for valor in hashes):
            raise ErroBackup("Git devolveu uma lista de objetos incompleta; o snapshot não foi confirmado.")
    registros = []
    for (nome, _), modo, objeto in zip(copias, modos, hashes):
        registros.append(f"{modo} {objeto}\t".encode("ascii") + nome.encode("utf-8") + b"\0")
    for nome in removidos:
        registros.append(b"0 " + b"0" * 40 + b"\t" + nome.encode("utf-8") + b"\0")
    if registros:
        _ok(git(vault, "update-index", "-z", "--index-info", ambiente=ambiente, texto=False,
                entrada=b"".join(registros)), "atualizar o índice independente")


@_com_operacao_git
def iniciar(vault: Path) -> bool:
    """Prepara ignores/repositório. O aceite de um repo importado é separado."""
    if not git_disponivel():
        return False
    vault = Path(os.path.abspath(vault))
    _validar_arvore_git(vault, permitir_ausente=True)
    ignorar = caminho_no_vault(vault, vault / ".gitignore")
    def combinar(bruto: bytes) -> bytes:
        try:
            texto = bruto.decode("utf-8-sig")
        except UnicodeError as erro:
            raise ErroBackup("O .gitignore não está em UTF-8; não foi alterado.") from erro
        existentes = set(texto.splitlines())
        faltam = [linha for linha in GITIGNORE_DO_VAULT.splitlines() if linha and not linha.startswith("#") and linha not in existentes]
        if not faltam:
            return bruto
        novo = texto.rstrip("\r\n") + ("\n\n" if texto else "") + "# Proteções do Orquestra\n" + "\n".join(faltam) + "\n"
        return (b"\xef\xbb\xbf" if bruto.startswith(b"\xef\xbb\xbf") else b"") + novo.encode("utf-8")
    atualizar_bytes(ignorar, combinar, validar=lambda: caminho_no_vault(vault, ignorar))
    if not e_repositorio(vault):
        if (vault / ".git").exists():
            raise ErroBackup("O vault usa metadados Git vinculados ou incompatíveis; eles não foram alterados.")
        r = git(vault, "init", "-b", "main")
        if r.returncode != 0:
            _ok(git(vault, "init"), "criar o histórico")
    _conferir_sensiveis(vault)
    return e_repositorio(vault)


def _referencia(vault: Path, ref: str) -> str | None:
    r = git(vault, "rev-parse", "--verify", ref)
    if r.returncode == 128:
        return None
    return _ok(r, "ler a referência do histórico").stdout.strip()


@_com_operacao_git
def commit(vault: Path, mensagem: str | None = None) -> str:
    """Cria snapshot em REF_BACKUP, sem alterar índice nem HEAD da pessoa."""
    if not git_disponivel() or not e_repositorio(vault):
        return "sem_git"
    indice = None
    try:
        _exigir_confianca(vault)
        with trava(vault / ".git" / "orquestra-snapshots"):
            _conferir_sensiveis(vault)
            anterior = _referencia(vault, REF_BACKUP)
            if anterior:
                _conferir_historico(vault, anterior)
            base = anterior or _referencia(vault, "HEAD")
            pasta = pasta_local() / "indices-git"
            pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
            descritor, nome = tempfile.mkstemp(prefix="indice-", dir=pasta)
            os.close(descritor)
            indice = Path(nome)
            indice.unlink()
            env = {"GIT_INDEX_FILE": str(indice.resolve())}
            _ok(git(vault, "read-tree", base if base else "--empty", ambiente=env), "preparar o índice independente")
            with tempfile.TemporaryDirectory(prefix="captura-", dir=pasta) as captura:
                _capturar_indice(vault, env, Path(captura))
            _conferir_sensiveis(vault, env)
            if base:
                diferenca = _ok(git(vault, "diff-index", "--cached", "--quiet", base, "--", ambiente=env), "comparar o snapshot", (0, 1))
                if diferenca.returncode == 0 and anterior is not None:
                    return "nada"
            arvore = _ok(git(vault, "write-tree", ambiente=env), "criar a árvore do snapshot").stdout.strip()
            mensagem = mensagem or f"orquestra: snapshot {dt.datetime.now():%Y-%m-%d %H:%M}"
            args = ["commit-tree", arvore]
            # Não herda o histórico anterior do usuário: ele pode conter um
            # segredo já removido. O primeiro snapshot é uma raiz independente.
            if anterior:
                args.extend(("-p", anterior))
            args.extend(("-m", mensagem))
            novo = _ok(git(vault, *_identidade(vault), *args, ambiente=env), "criar o snapshot").stdout.strip()
            _exigir_confianca(vault)
            _ok(git(vault, "update-ref", REF_BACKUP, novo, anterior or "0" * len(novo)), "publicar o snapshot")
            return "feito"
    except (OSError, ValueError, subprocess.TimeoutExpired) as erro:
        return "erro: " + (str(erro) if isinstance(erro, ErroBackup) else "Não foi possível concluir o snapshot; confira permissões e tente novamente.")
    finally:
        if indice is not None:
            indice.unlink(missing_ok=True)
            Path(str(indice) + ".lock").unlink(missing_ok=True)


@_com_operacao_git
def push(vault: Path) -> str:
    """Envia só o ref de backup, sem mudar upstream nem forçar histórico."""
    if not git_disponivel() or not e_repositorio(vault):
        return "sem_remoto"
    try:
        _exigir_confianca(vault)
        revisao = _referencia(vault, REF_BACKUP)
        if not revisao:
            return "erro: Ainda não há snapshot local para enviar."
        _conferir_historico(vault, revisao)
        remotos = _ok(git(vault, "remote"), "ler os remotos").stdout.splitlines()
        if not remotos:
            return "sem_remoto"
        remoto = "origin" if "origin" in remotos else remotos[0]
        # A expressão não pode ser um nome de branch: até uma branch chamada
        # com os mesmos 40/64 caracteres do hash não deve substituir o commit.
        _ok(git(vault, "push", remoto, f"{revisao}^{{commit}}:refs/heads/{BRANCH_REMOTO}", tempo=180), "enviar o snapshot")
        return "feito"
    except (OSError, ValueError, subprocess.TimeoutExpired) as erro:
        return "erro: " + (str(erro) if isinstance(erro, ErroBackup) else "Não foi possível enviar o snapshot. Confira conexão e credenciais e tente novamente.")


@_com_operacao_git
def ultimo_commit(vault: Path) -> str:
    if not git_disponivel() or not e_repositorio(vault):
        return ""
    try:
        r = git(vault, "log", "-1", "--format=%cd", "--date=format:%d/%m/%Y %H:%M", REF_BACKUP)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ""


@_com_operacao_git
def restaurar_arquivo(vault: Path, rel: str, *, esperado: object, revisao: str = REF_BACKUP, destino: str | None = None) -> Path:
    """Restaura bytes protegidos, sem checkout/reset do índice."""
    _exigir_confianca(vault)
    origem = caminho_no_vault(vault, rel)
    alvo = caminho_no_vault(vault, destino or rel)
    if not re.fullmatch(r"(?:[a-fA-F0-9]{7,64}|refs/[A-Za-z0-9_./-]+)", revisao) or ".." in revisao:
        raise ErroBackup("Revisão de backup inválida.")
    rel_real = origem.relative_to(vault.resolve()).as_posix()
    resultado = _ok(git(vault, "show", f"{revisao}:{rel_real}", texto=False), "ler o arquivo do snapshot")
    gravar_bytes(alvo, resultado.stdout, esperado=esperado, validar=lambda: caminho_no_vault(vault, alvo))
    return alvo
