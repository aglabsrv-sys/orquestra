"""O canal ao vivo não prende um encerramento solicitado do servidor."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from orquestra.seguranca import CapabilityLocal
from orquestra.servidor import criar_app


def test_eventos_liberam_assinatura_ao_encerrar_servidor(vault):
    hospedeiro = SimpleNamespace(capacidade=CapabilityLocal(), servidor=SimpleNamespace(should_exit=True))
    app = criar_app(vault, vigiar=False, agendar=False, hospedeiro=hospedeiro)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        resposta = cliente.get("/eventos")
        assert resposta.status_code == 200
        marca = app.state.painel.eventos.marca()
        assert resposta.text == 'retry: 3000\n\ndata: {"tipo": "estado", "marca": "' + marca + '"}\n\n'
        assert not app.state.painel.eventos._filas
