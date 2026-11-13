from fastapi.testclient import TestClient

from orquestra.hospedeiro import Hospedeiro


def test_reabrir_cofre_configurado_preserva_as_opcoes(vault):
    arquivo = vault / "orquestra.yaml"
    antes = arquivo.read_bytes()
    with TestClient(Hospedeiro(vault, vigiar=False, agendar=False), base_url="http://localhost", client=("127.0.0.1", 50000)) as cliente:
        token = cliente.get("/api/local/capacidade").json()["token"]
        resposta = cliente.post("/api/boas-vindas/concluir", headers={"X-Orquestra-Local": token}, json={
            "modo": "existente", "caminho": str(vault), "nome": "Não substituir",
            "aparencia": {"cantos": "redondo"}, "modulos": ["habitos"],
        })
        assert resposta.status_code == 200
        assert resposta.json()["reaberto"]
        assert cliente.get("/").status_code == 200
    assert arquivo.read_bytes() == antes
    assert not (vault / "habitos").exists()
