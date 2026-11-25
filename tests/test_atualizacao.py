"""Detecção, permissões e preparação de atualização sem encerrar prematuramente."""
from unittest.mock import Mock

import pytest

from orquestra import atualizacao as a, processo


def preparar(monkeypatch):
    monkeypatch.setattr(a, "conferir_instalacao", lambda: "a" * 40)
    monkeypatch.setattr(a, "alteracoes_locais", lambda: [])
    comando = Mock()
    def responder(*args, **kwargs):
        if "ls-remote" in args:
            return "b" * 40 + "\trefs/heads/main"
        if "merge-base" in args:
            raise RuntimeError("Revisão ainda não baixada")
        return ""
    comando.side_effect = responder
    monkeypatch.setattr(a, "executar", comando)
    return comando


@pytest.mark.parametrize("tempo_ligado", [0.0, 1.0, 1799.0, 3600.0])
def test_consulta_cache_e_revisao_sem_mudar_numero_de_versao(monkeypatch, tempo_ligado):
    comando = preparar(monkeypatch)
    relogio = Mock(return_value=tempo_ligado)
    monkeypatch.setattr(a.time, "monotonic", relogio)
    atualizador = a.Atualizador()
    estado = atualizador.consultar()
    assert estado["disponivel"] and estado["revisao"] == "b" * 40
    assert estado["instalada"] == "a" * 40
    chamadas = comando.call_count
    assert atualizador.consultar() == estado
    assert comando.call_count == chamadas
    relogio.return_value += 1800
    assert atualizador.consultar() == estado
    assert comando.call_count > chamadas


def test_consulta_falha_sem_expor_saida_do_provedor(monkeypatch):
    preparar(monkeypatch)
    monkeypatch.setattr(a.time, "monotonic", lambda: 1.0)
    atualizador = a.Atualizador()
    monkeypatch.setattr(a, "executar", Mock(side_effect=RuntimeError("credencial secreta")))
    estado = atualizador.consultar()
    assert estado == {"disponivel": False, "estado": "indisponivel"}


def test_alteracoes_locais_exigem_confirmar_copia(monkeypatch, tmp_path):
    preparar(monkeypatch)
    atualizador = a.Atualizador()
    monkeypatch.setattr(a, "alteracoes_locais", lambda: ["arquivo.py"])
    iniciar = Mock()
    monkeypatch.setattr(a.subprocess, "Popen", iniciar)
    with pytest.raises(RuntimeError, match="Guardar cópia"):
        atualizador.iniciar(tmp_path, 8420, 123)
    iniciar.assert_not_called()
    monkeypatch.setattr(a.shutil, "which", lambda _: "uv")
    atualizador.iniciar(tmp_path, 8420, 123, preservar=True)
    assert iniciar.call_args.args[0][-1] == "--preservar"


def test_consulta_nao_anuncia_codigo_local_a_frente(monkeypatch):
    comando = preparar(monkeypatch)
    comando.side_effect = lambda *args, **kwargs: "b" * 40 + "\trefs/heads/main" if "ls-remote" in args else ""
    assert not a.Atualizador().consultar()["disponivel"]


def test_codigo_local_mudou_com_consulta_remota_em_cache(monkeypatch, tmp_path):
    comando = preparar(monkeypatch)
    monkeypatch.setattr(a, "RAIZ", tmp_path)
    (tmp_path / ".git").mkdir()
    fonte = tmp_path / "src/orquestra"
    fonte.mkdir(parents=True)
    codigo = fonte / "painel.py"
    codigo.write_text("x = 1")
    atualizador = a.Atualizador()
    assert atualizador.consultar()["revisao"] == "b" * 40
    chamadas = comando.call_count
    cache = fonte / "__pycache__"
    cache.mkdir()
    (cache / "painel.pyc").write_bytes(b"cache")
    assert atualizador.consultar().get("modo") is None
    codigo.write_text("x = 22")
    assert atualizador.consultar()["modo"] == "reiniciar"
    assert comando.call_count == chamadas


def test_reinicio_local_aceita_arquivos_editados_e_preserva_vault(monkeypatch, tmp_path):
    preparar(monkeypatch)
    marca = Mock(return_value="antiga")
    monkeypatch.setattr(a, "marca_codigo", marca)
    atualizador = a.Atualizador()
    marca.return_value = "nova"
    monkeypatch.setattr(a.shutil, "which", lambda _: "uv")
    limpeza = Mock(side_effect=RuntimeError("Há alterações locais"))
    monkeypatch.setattr(a, "alteracoes_locais", limpeza)
    iniciar = Mock()
    monkeypatch.setattr(a.subprocess, "Popen", iniciar)
    with pytest.raises(RuntimeError, match="mudou"):
        atualizador.iniciar(tmp_path, 8427, 123, "baixar")
    resposta = atualizador.iniciar(tmp_path, 8427, 123, "reiniciar")
    assert resposta == {"estado": "atualizando", "modo": "reiniciar"}
    assert iniciar.call_args.args[0][-5:] == [str(tmp_path), "8427", "123", "--local", "uv"]
    limpeza.assert_not_called()
    monkeypatch.setattr(a.time, "sleep", lambda _: None)
    monkeypatch.setattr(processo, "consultar", lambda porta: {"pid": 123, "vault": str(tmp_path)})
    passos = []
    monkeypatch.setattr(a, "executar", lambda *args, **kwargs: passos.append(args))
    monkeypatch.setattr(processo, "parar", lambda porta, pid_esperado: passos.append(("parar", porta, pid_esperado)))
    monkeypatch.setattr(a.subprocess, "check_call", lambda args, **kwargs: passos.append(tuple(args)))
    a.aplicar(tmp_path, 8427, 123, "--local", "uv")
    assert passos == [
        ("uv", "sync", "--locked"), ("parar", 8427, 123),
        ("uv", "run", "--frozen", "orquestra", "iniciar", "--vault", str(tmp_path), "--porta", "8427"),
    ]


def test_falha_dependencias_preserva_processo_rodando(monkeypatch, tmp_path):
    preparar(monkeypatch)
    monkeypatch.setattr(a.time, "sleep", lambda _: None)
    monkeypatch.setattr(a.Instalacao, "atualizar", lambda *args, **kwargs: {})
    monkeypatch.setattr(processo, "consultar", lambda porta: {"pid": 123, "vault": str(tmp_path)})
    parar = Mock()
    monkeypatch.setattr(processo, "parar", parar)
    def executar(*args, **kwargs):
        if args[:2] == ("uv", "sync"):
            raise RuntimeError("Falhou a dependência")
        return "b" * 40 if "rev-parse" in args else ""
    monkeypatch.setattr(a, "executar", executar)
    with pytest.raises(RuntimeError, match="dependência"):
        a.aplicar(tmp_path, 8420, 123, "b" * 40, "uv")
    parar.assert_not_called()


def test_aplicar_confere_pid_e_vault_antes_de_alterar_codigo(monkeypatch, tmp_path):
    monkeypatch.setattr(a.time, "sleep", lambda _: None)
    monkeypatch.setattr(processo, "consultar", lambda porta: {"pid": 456, "vault": str(tmp_path)})
    comando = Mock()
    monkeypatch.setattr(a, "executar", comando)
    with pytest.raises(RuntimeError, match="mudou"):
        a.aplicar(tmp_path, 8420, 123, "b" * 40, "uv")
    comando.assert_not_called()


def test_api_exige_capacidade_local_mesmo_com_host_autorizado(cliente, monkeypatch):
    monkeypatch.setattr(a.Atualizador, "consultar", lambda self: {"disponivel": True, "revisao": "b" * 40})
    assert cliente.get("/api/atualizacao").json()["disponivel"]
    assert cliente.post("/api/atualizacao", json={}).status_code == 403
    token = cliente.get("/api/local/capacidade").json()["token"]
    headers = {"X-Orquestra-Local": token}
    assert cliente.post("/api/tailscale/host", headers=headers, json={"url": "https://pc.exemplo.ts.net"}).status_code == 200
    assert not cliente.get("/api/atualizacao", headers={"Host": "pc.exemplo.ts.net"}).json()["local"]
    assert cliente.post("/api/atualizacao", headers={**headers, "Host": "pc.exemplo.ts.net"}, json={}).status_code == 403
    assert cliente.post("/api/atualizacao", headers={**headers, "X-Orquestra-Vault": "outro"}, json={}).status_code == 409


def test_aplicar_prepara_antes_de_parar_e_preserva_porta_e_vault(monkeypatch, tmp_path):
    preparar(monkeypatch)
    monkeypatch.setattr(a.time, "sleep", lambda _: None)
    monkeypatch.setattr(a.Instalacao, "atualizar", lambda *args, **kwargs: {})
    monkeypatch.setattr(processo, "consultar", lambda porta: {"pid": 123, "vault": str(tmp_path)})
    passos = []
    def executar(*args, **kwargs):
        passos.append(args)
        return "b" * 40 if "rev-parse" in args else ""
    monkeypatch.setattr(a, "executar", executar)
    monkeypatch.setattr(processo, "parar", lambda porta, pid_esperado: passos.append(("parar", porta, pid_esperado)))
    monkeypatch.setattr(a.subprocess, "check_call", lambda args, **kwargs: passos.append(tuple(args)))
    a.aplicar(tmp_path, 8427, 123, "b" * 40, "uv")
    assert passos[-3] == ("uv", "sync", "--locked")
    assert passos[-2] == ("parar", 8427, 123)
    assert passos[-1] == ("uv", "run", "--frozen", "orquestra", "iniciar", "--vault", str(tmp_path), "--porta", "8427")


def test_falha_na_preparacao_nao_para_painel(monkeypatch, tmp_path):
    monkeypatch.setattr(a.time, "sleep", lambda _: None)
    monkeypatch.setattr(processo, "consultar", lambda porta: {"pid": 123, "vault": str(tmp_path)})
    monkeypatch.setattr(a.Instalacao, "atualizar", Mock(side_effect=RuntimeError("Uma nova revisão foi publicada")))
    parar = Mock()
    monkeypatch.setattr(processo, "parar", parar)
    with pytest.raises(RuntimeError, match="publicada"):
        a.aplicar(tmp_path, 8420, 123, "b" * 40, "uv")
    parar.assert_not_called()


def test_copia_da_atualizacao_exige_capacidade_local(cliente, monkeypatch, tmp_path):
    from orquestra.atualizacao_git import Instalacao
    import zipfile

    monkeypatch.setattr(a, "RAIZ", tmp_path / "app")
    instalacao = Instalacao(a.RAIZ)
    identificador = "a" * 32
    instalacao.registrar(estado="preparado", copia={"id": identificador, "quantidade": 1})
    with zipfile.ZipFile(instalacao.copias / (identificador + ".zip"), "w") as copia:
        copia.writestr("arquivos/teste.txt", b"alteracao")
    assert cliente.post("/api/atualizacao/copia", json={}).status_code == 403
    token = cliente.get("/api/local/capacidade").json()["token"]
    headers = {"X-Orquestra-Local": token}
    resposta = cliente.post("/api/atualizacao/copia", headers=headers, json={})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/zip"
    instalacao.registrar(copia={"id": "../../arquivo"})
    assert cliente.post("/api/atualizacao/copia", headers=headers, json={}).status_code == 400


def test_falha_do_processo_mostra_mensagem_guardada(monkeypatch):
    preparar(monkeypatch)
    atualizador = a.Atualizador()
    atualizador.processo = Mock(poll=Mock(return_value=1))
    a.Instalacao(a.RAIZ).registrar(estado="falhou", mensagem="Cópia guardada; confira espaço livre.")
    assert atualizador.consultar()["mensagem"] == "Cópia guardada; confira espaço livre."


def test_recuperacao_so_confirma_apos_novo_painel_no_mesmo_vault(monkeypatch, tmp_path):
    aberto = {"vault": str(tmp_path), "porta": 8420, "pid": 123}
    monkeypatch.setattr(processo, "localizar", lambda: aberto)
    destacar = Mock()
    monkeypatch.setattr(processo, "destacar", destacar)
    monkeypatch.setattr(a.time, "sleep", lambda _: None)
    consultar = Mock(side_effect=[aberto, {**aberto, "pid": 456, "vault": "outro"}, {**aberto, "pid": 456}])
    monkeypatch.setattr(processo, "consultar", consultar)
    a.retomar_recuperacao()
    assert consultar.call_count == 3
    destacar.assert_called_once_with(tmp_path, 8420, 123)
