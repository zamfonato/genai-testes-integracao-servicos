"""Dois testes escritos à mão. São os exemplos usados no prompt few-shot (P2)."""

import httpx


def test_pedido_valido_reserva_no_estoque_e_persiste(pedidos, estoque, repositorio):
    resposta = pedidos.post("/pedidos", json={"cliente": "ana", "itens": [{"sku": "CAD-001", "quantidade": 2}]})

    assert resposta.status_code == 201
    pedido = resposta.json()
    assert pedido["status"] == "confirmado"
    assert estoque.get("/produtos/CAD-001").json()["disponivel"] == 8
    assert repositorio.contar() == 1
    assert pedidos.get(f"/pedidos/{pedido['id']}").json() == pedido


def test_timeout_no_estoque_retorna_503_sem_gravar_pedido(pedidos_com_estoque_simulado, repositorio):
    def estoque_lento(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    cliente = pedidos_com_estoque_simulado(estoque_lento)
    resposta = cliente.post("/pedidos", json={"cliente": "ana", "itens": [{"sku": "CAD-001", "quantidade": 1}]})

    assert resposta.status_code == 503
    assert repositorio.contar() == 0
