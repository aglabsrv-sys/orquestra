"""Sincroniza a instalação com a versão oficial, sem alterar o vault."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

REMOTOS = {"https://github.com/aglabsrv-sys/orquestra.git", "https://github.com/aglabsrv-sys/orquestra", "git@github.com:aglabsrv-sys/orquestra.git"}


class Dependencias:
    """No Windows, prepara sem tocar nos executáveis que o painel mantém abertos."""
    def __init__(self, raiz: Path, uv: str, pasta: Path, *, preparado: Path | None = None, ambiente: dict | None = None):
        self.raiz, self.uv, self.pasta = raiz, uv, pasta
        self.ambiente = dict(os.environ if ambiente is None else ambiente)
        self.ambiente.pop("VIRTUAL_ENV", None)
        self.preparado = preparado
        self.usando_preparado = False

    def sincronizar(self, ambiente: dict, *, offline: bool = False) -> None:
        resultado = subprocess.run([self.uv, "sync", "--locked", *(["--offline"] if offline else [])],
                                   cwd=self.raiz, env=ambiente, capture_output=True, timeout=300,
                                   **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        if resultado.returncode:
            raise RuntimeError("Não foi possível preparar as dependências. Confira a conexão, o espaço livre e as permissões e tente novamente.")

    def preparar(self) -> None:
        ambiente = self.ambiente
        if os.name == "nt":
            self.pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.preparado = Path(tempfile.mkdtemp(prefix="ambiente-", dir=self.pasta))
            ambiente = {**ambiente, "UV_PROJECT_ENVIRONMENT": str(self.preparado)}
        self.sincronizar(ambiente)

    def concluir(self) -> dict:
        if self.preparado:
            try:
                # Os pacotes e o projeto já foram preparados e estão no cache local.
                self.sincronizar(self.ambiente, offline=True)
            except (OSError, RuntimeError, subprocess.SubprocessError):
                # Por exemplo, o próprio comando atualizar ainda mantém seu .exe aberto.
                # O painel pode retomar com o ambiente já completo, sem depender dele.
                self.usando_preparado = True
                return {**self.ambiente, "UV_PROJECT_ENVIRONMENT": str(self.preparado)}
        return self.ambiente

    def limpar(self) -> None:
        if not self.preparado or self.usando_preparado or self.preparado.resolve() == Path(sys.prefix).resolve():
            return
        alvo = self.preparado.resolve()
        if alvo.parent != self.pasta.resolve() or not alvo.name.startswith("ambiente-") or self.preparado.is_symlink():
            return
        try:
            shutil.rmtree(alvo)
        except OSError:
            pass  # um arquivo ainda em uso pode ser removido pela pessoa mais tarde


class Instalacao:
    def __init__(self, raiz: Path):
        self.raiz = raiz.resolve()
        identificador = hashlib.sha256(os.fsencode(str(self.raiz))).hexdigest()[:16]
        self.pasta = (Path(os.environ.get("ORQUESTRA_HOME") or Path.home() / ".orquestra") / "atualizacoes" / identificador).resolve()

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
            dados = json.loads((self.pasta / "estado.json").read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    def registrar(self, **dados) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporario = self.pasta / f"{uuid.uuid4().hex}.tmp"
        temporario.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        temporario.replace(self.pasta / "estado.json")

    @contextmanager
    def trava(self):
        self.pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.pasta / "operacao.lock").open("a+b") as arquivo:
            arquivo.seek(0)
            if os.name == "nt":
                import msvcrt
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
                if os.fstat(arquivo.fileno()).st_size == 0:
                    arquivo.write(b"0")
                    arquivo.flush()
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

    def caminhos_da_sincronizacao(self, revisao: str, vault: Path | None = None) -> list[str]:
        caminhos = set(self.alterados())
        caminhos.update(os.fsdecode(p) for p in self.git("diff", "--no-renames", "--name-only", "-z", "HEAD", revisao).split(b"\0") if p)
        atuais = {os.fsdecode(p) for p in self.git("ls-files", "-z").split(b"\0") if p}
        novos = {os.fsdecode(p) for p in self.git("ls-tree", "-r", "--name-only", "-z", revisao).split(b"\0") if p}
        for nome in novos:
            # Identifica extras que ocupam caminhos da versão oficial.
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

    def atualizar(self, revisao: str | None = None, *, vault: Path | None = None) -> dict:
        if self.pasta.is_relative_to(self.raiz) or (vault and self.pasta.is_relative_to(vault.resolve())):
            raise RuntimeError("Os dados do Orquestra precisam ficar fora do aplicativo e do vault para atualizar.")
        with self.trava():
            antes = self.conferir()
            self.git("fetch", "--quiet", "origin", "main")
            nova = self.texto("rev-parse", "FETCH_HEAD")
            if revisao and nova != revisao:
                raise RuntimeError("Uma nova revisão foi publicada. Tente atualizar novamente.")
            try:
                self.git("merge-base", "--is-ancestor", antes, nova)
            except RuntimeError:
                raise RuntimeError("Esta instalação tem commits próprios. A atualização exige a main oficial sem divergências.") from None
            # A ação sincroniza somente a instalação. Extras sem conflito ficam no lugar.
            # Confira todos os caminhos afetados antes de o Git substituir qualquer arquivo.
            for nome in self.caminhos_da_sincronizacao(nova, vault):
                caminho = self.raiz / nome
                if not caminho.is_relative_to(self.raiz) or caminho.parent.resolve() != caminho.parent.absolute():
                    raise RuntimeError("Há um link de pasta nos arquivos do aplicativo. Confira a instalação antes de atualizar.")
                self.proteger_vault(caminho, vault)
                if caminho.is_dir() and not caminho.is_symlink():
                    for pasta, _, _ in os.walk(caminho, followlinks=False):
                        self.proteger_vault(Path(pasta), vault)
            self.git("reset", "--hard", nova)
            self.registrar(estado="preparado", revisao=nova)
            return {"revisao": nova, "mudou": nova != antes}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincroniza e atualiza o Orquestra.")
    parser.add_argument("--aplicativo", type=Path, required=True)
    parser.add_argument("--confirmar", action="store_true")
    args = parser.parse_args()
    instalacao = Instalacao(args.aplicativo)
    uv = shutil.which("uv")
    if not args.confirmar or not uv:
        parser.error("Use --confirmar e mantenha o uv instalado.")
    try:
        # Mesmo a versão antiga registra o vault em uso; preserve-o durante a recuperação.
        casa = Path(os.environ.get("ORQUESTRA_HOME") or Path.home() / ".orquestra")
        try:
            painel = json.loads((casa / "painel.json").read_text(encoding="utf-8"))
            vault = Path(painel["vault"]) if painel.get("vault") else None
        except (OSError, ValueError, TypeError, AttributeError):
            vault = None
        instalacao.atualizar(vault=vault)
        dependencias = Dependencias(instalacao.raiz, uv, instalacao.pasta)
        dependencias.preparar()
        # O pacote atualizado localiza e reabre o painel usando o mesmo vault e porta.
        codigo = ("import json; from orquestra.atualizacao import retomar_recuperacao; r = retomar_recuperacao("
                  + repr(str(dependencias.preparado) if dependencias.preparado else "") + ", "
                  + repr(dependencias.ambiente.get("UV_PROJECT_ENVIRONMENT")) + "); print(json.dumps({'usando_preparado':r}))")
        ambiente = {**dependencias.ambiente, **({"UV_PROJECT_ENVIRONMENT": str(dependencias.preparado)} if dependencias.preparado else {})}
        retomada = subprocess.run([uv, "run", "--frozen", "python", "-c", codigo],
                                  cwd=instalacao.raiz, env=ambiente, check=True, timeout=360, capture_output=True, text=True, encoding="utf-8")
        dependencias.usando_preparado = json.loads(retomada.stdout)["usando_preparado"]
        dependencias.limpar()
        print("Orquestra atualizado. Recarregue a página do painel. Se estava fechado, abra pelo atalho habitual.")
    except (OSError, RuntimeError, subprocess.SubprocessError) as erro:
        print(str(erro) if isinstance(erro, RuntimeError) else "A atualização não terminou. Confira a conexão e as permissões e tente novamente.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
