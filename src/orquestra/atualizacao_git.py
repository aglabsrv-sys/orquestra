"""Atualização Git com cópia local; também funciona fora do pacote para recuperação."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path

REMOTOS = {"https://github.com/aglabsrv-sys/orquestra.git", "https://github.com/aglabsrv-sys/orquestra", "git@github.com:aglabsrv-sys/orquestra.git"}


class Instalacao:
    def __init__(self, raiz: Path):
        self.raiz = raiz.resolve()
        identificador = hashlib.sha256(os.fsencode(str(self.raiz))).hexdigest()[:16]
        self.copias = (Path(os.environ.get("ORQUESTRA_HOME") or Path.home() / ".orquestra") / "atualizacoes" / identificador).resolve()

    def git(self, *args: str, entrada: bytes | None = None) -> bytes:
        resultado = subprocess.run(
            ["git", *args], cwd=self.raiz, input=entrada, capture_output=True, timeout=120,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LITERAL_PATHSPECS": "1"},
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
        if resultado.returncode:
            raise RuntimeError("Não foi possível preparar a atualização. Confira a conexão, o espaço livre e as permissões da pasta do aplicativo.")
        return resultado.stdout

    def texto(self, *args: str) -> str:
        return self.git(*args).decode("utf-8", errors="replace").strip()

    def conferir(self) -> str:
        if not (self.raiz / ".git").exists() or not (self.raiz / "pyproject.toml").is_file():
            raise RuntimeError("Escolha a pasta do aplicativo, onde estão pyproject.toml e uv.lock.")
        if self.texto("remote", "get-url", "origin") not in REMOTOS or self.texto("branch", "--show-current") != "main":
            raise RuntimeError("A atualização exige a main do repositório oficial do Orquestra.")
        if Path(self.texto("rev-parse", "--show-toplevel")).resolve() != self.raiz:
            raise RuntimeError("Escolha a raiz da instalação do Orquestra.")
        return self.texto("rev-parse", "HEAD")

    def alterados(self) -> list[str]:
        registros = iter(self.git("status", "--porcelain=v1", "-z", "--untracked-files=no").split(b"\0"))
        caminhos = set()
        for registro in registros:
            if not registro:
                continue
            caminhos.add(os.fsdecode(registro[3:]))
            if b"R" in registro[:2] or b"C" in registro[:2]:
                caminhos.add(os.fsdecode(next(registros)))
        return sorted(caminhos)

    def ler_estado(self) -> dict:
        try:
            dados = json.loads((self.copias / "estado.json").read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    def registrar(self, **dados) -> None:
        self.copias.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporario = self.copias / f"{uuid.uuid4().hex}.tmp"
        temporario.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        temporario.replace(self.copias / "estado.json")

    @contextmanager
    def trava(self):
        self.copias.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.copias / "operacao.lock").open("a+b") as arquivo:
            arquivo.seek(0)
            if os.name == "nt":
                import msvcrt
                arquivo.write(b"0")
                arquivo.flush()
                arquivo.seek(0)
                try:
                    msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise RuntimeError("Uma atualização já está em andamento. Aguarde sua conclusão.") from None
            else:
                import fcntl
                try:
                    fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise RuntimeError("Uma atualização já está em andamento. Aguarde sua conclusão.") from None
            try:
                yield
            finally:
                if os.name == "nt":
                    arquivo.seek(0)
                    msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)

    def proteger_vault(self, caminho: Path, vault: Path | None) -> None:
        if vault and (caminho.resolve().is_relative_to(vault.resolve()) or vault.resolve().is_relative_to(caminho.resolve())):
            raise RuntimeError("O vault ocupa um caminho usado pelo aplicativo. Mova-o para uma pasta separada antes de atualizar.")
        for pasta in (caminho, *caminho.parents):
            if not pasta.is_relative_to(self.raiz):
                break
            if pasta == self.raiz / "src/orquestra/modelo_vault":
                break
            if (pasta / "orquestra.yaml").is_file():
                raise RuntimeError("Um vault ocupa um caminho usado pelo aplicativo. Mova-o para uma pasta separada antes de atualizar.")

    def caminhos_para_copia(self, revisao: str, vault: Path | None = None) -> list[str]:
        caminhos = set(self.alterados())
        atuais = {os.fsdecode(p) for p in self.git("ls-files", "-z").split(b"\0") if p}
        novos = {os.fsdecode(p) for p in self.git("ls-tree", "-r", "--name-only", "-z", revisao).split(b"\0") if p}
        for nome in novos:
            # Só extras que ocupariam o lugar de arquivos da nova versão entram na cópia.
            caminho = self.raiz / nome
            for pai in [*reversed(caminho.relative_to(self.raiz).parents)][1:]:
                candidato = self.raiz / pai
                if candidato.is_symlink() or candidato.is_file():
                    if pai.as_posix() not in atuais:
                        caminhos.add(pai.as_posix())
                    break
            else:
                if caminho.is_symlink():
                    if nome not in atuais:
                        caminhos.add(nome)
                elif nome not in atuais and caminho.is_file():
                    caminhos.add(nome)
                elif caminho.is_dir():
                    self.proteger_vault(caminho, vault)
                    for pasta, filhas, arquivos in os.walk(caminho, followlinks=False):
                        for filha in list(filhas):
                            if (Path(pasta) / filha).is_symlink():
                                arquivos.append(filha)
                                filhas.remove(filha)
                        caminhos.update((Path(pasta) / f).relative_to(self.raiz).as_posix() for f in arquivos)
        return sorted(caminhos)

    def guardar(self, caminhos: list[str], revisao: str, vault: Path | None) -> dict:
        identificador = uuid.uuid4().hex
        destino = self.copias / f"{identificador}.zip"
        registros = []
        conteudos = {}
        for nome in caminhos:
            caminho = self.raiz / nome
            # Não atravessa links de diretório nem move um vault usado dentro da instalação.
            if caminho.parent.resolve() != caminho.parent.absolute():
                raise RuntimeError("Há um link de pasta entre os arquivos alterados. A atualização foi cancelada para preservar seus dados.")
            self.proteger_vault(caminho, vault)
            if caminho.is_symlink():
                dados = os.fsencode(os.readlink(caminho))
                tipo = "link"
            elif caminho.is_file():
                dados = caminho.read_bytes()
                tipo = "arquivo"
            elif not caminho.exists():
                dados, tipo = b"", "excluido"
            else:
                raise RuntimeError("Há uma pasta ou submódulo alterado. A atualização foi cancelada para preservar seu conteúdo.")
            registros.append({"caminho": nome, "tipo": tipo, "sha256": hashlib.sha256(dados).hexdigest()})
            conteudos[nome] = dados
        # A cópia legível inclui também os patches do índice e do diretório de trabalho.
        with zipfile.ZipFile(destino, "x", compression=zipfile.ZIP_DEFLATED) as copia:
            copia.writestr("manifesto.json", json.dumps({"revisao": revisao, "arquivos": registros}, ensure_ascii=False, indent=2))
            copia.writestr("alteracoes.patch", self.git("diff", "--binary", "HEAD"))
            copia.writestr("preparadas.patch", self.git("diff", "--binary", "--cached"))
            for registro in registros:
                if registro["tipo"] != "excluido":
                    copia.writestr("arquivos/" + registro["caminho"], conteudos[registro["caminho"]])
        with zipfile.ZipFile(destino) as copia:
            if copia.testzip() is not None:
                raise RuntimeError("A cópia das alterações não pôde ser verificada. Nenhum arquivo foi movido.")
        for registro in registros:
            caminho = self.raiz / registro["caminho"]
            tipo = registro["tipo"]
            if tipo == "excluido":
                igual = not caminho.exists() and not caminho.is_symlink()
            elif tipo == "link":
                igual = caminho.is_symlink() and os.fsencode(os.readlink(caminho)) == conteudos[registro["caminho"]]
            else:
                igual = caminho.is_file() and not caminho.is_symlink() and caminho.read_bytes() == conteudos[registro["caminho"]]
            if not igual:
                raise RuntimeError("Um arquivo mudou durante a cópia. Salve as edições e tente atualizar novamente.")
        copia = {"id": identificador, "quantidade": len(caminhos)}
        self.registrar(estado="preparando", copia=copia)
        # Primeiro o índice e os rastreados, incluindo renomeações e exclusões.
        rastreados = set(self.alterados())
        comando = ("-c", "user.name=Orquestra", "-c", "user.email=atualizacao@localhost", "stash", "push", "--message", f"Orquestra: cópia {identificador}")
        if rastreados:
            self.git(*comando)
            self.git("update-ref", f"refs/orquestra/atualizacoes/{identificador}", self.texto("rev-parse", "refs/stash"))
        # Só extras conflitantes entram no segundo stash; outros arquivos ficam no lugar.
        extras = sorted(set(caminhos) - rastreados)
        if extras:
            self.git(*comando, "--all", "--pathspec-from-file=-", "--pathspec-file-nul",
                     entrada=b"".join(os.fsencode(p) + b"\0" for p in extras))
            self.git("update-ref", f"refs/orquestra/atualizacoes/{identificador}-extras", self.texto("rev-parse", "refs/stash"))
        return copia

    def atualizar(self, revisao: str | None = None, *, preservar: bool = False, vault: Path | None = None) -> dict:
        if self.copias.is_relative_to(self.raiz) or (vault and self.copias.is_relative_to(vault.resolve())):
            raise RuntimeError("A pasta de dados ORQUESTRA_HOME precisa ficar fora do aplicativo e do vault para guardar as cópias de atualização.")
        with self.trava():
            antes = self.conferir()
            self.git("fetch", "--quiet", "origin", "main")
            nova = self.texto("rev-parse", "FETCH_HEAD")
            if revisao and nova != revisao:
                raise RuntimeError("Uma nova revisão foi publicada. Verifique novamente.")
            try:
                self.git("merge-base", "--is-ancestor", antes, nova)
            except RuntimeError:
                raise RuntimeError("Esta instalação tem commits próprios. Eles foram preservados; a atualização automática exige a main oficial sem divergências.") from None
            caminhos = self.caminhos_para_copia(nova, vault)
            if caminhos and not preservar:
                raise RuntimeError("Há alterações no aplicativo. Confirme Guardar cópia e atualizar para continuar sem perdê-las.")
            copia = self.guardar(caminhos, antes, vault) if caminhos else self.ler_estado().get("copia")
            try:
                self.git("merge", "--ff-only", nova)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                if copia:
                    raise RuntimeError(f"A atualização não terminou. Suas alterações estão guardadas em {self.copias}. Tente novamente.") from None
                raise
            self.registrar(estado="preparado", revisao=nova, copia=copia)
            return {"revisao": nova, "copia": copia, "mudou": nova != antes}


def main() -> None:
    parser = argparse.ArgumentParser(description="Recupera uma atualização mantendo cópia das alterações do aplicativo.")
    parser.add_argument("--aplicativo", type=Path, required=True)
    parser.add_argument("--confirmar", action="store_true")
    args = parser.parse_args()
    instalacao = Instalacao(args.aplicativo)
    uv = shutil.which("uv")
    if not args.confirmar or not uv:
        parser.error("Confirme a cópia com --confirmar e mantenha o uv instalado.")
    try:
        # Mesmo a versão antiga registra o vault em uso; preserve-o durante a recuperação.
        casa = Path(os.environ.get("ORQUESTRA_HOME") or Path.home() / ".orquestra")
        try:
            painel = json.loads((casa / "painel.json").read_text(encoding="utf-8"))
            vault = Path(painel["vault"]) if painel.get("vault") else None
        except (OSError, ValueError, TypeError, AttributeError):
            vault = None
        resultado = instalacao.atualizar(preservar=True, vault=vault)
        subprocess.run([uv, "sync", "--locked"], cwd=instalacao.raiz, check=True, timeout=300)
        if resultado["copia"]:
            print(f"Cópia das alterações: {instalacao.copias}")
        # O pacote atualizado localiza e reabre o painel usando o mesmo vault e porta.
        subprocess.run([uv, "run", "--frozen", "python", "-c", "from orquestra.atualizacao import retomar_recuperacao; retomar_recuperacao()"],
                       cwd=instalacao.raiz, check=True, timeout=90)
        print("Orquestra atualizado. Recarregue a página do painel. Se estava fechado, abra pelo atalho habitual.")
    except (OSError, RuntimeError, subprocess.SubprocessError) as erro:
        print(str(erro) if isinstance(erro, RuntimeError) else "A atualização não terminou. Confira a conexão e as permissões e tente novamente.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
