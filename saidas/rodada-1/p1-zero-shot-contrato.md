# Resposta

## Tabela de casos

| ID | Partição ou limite | Entrada | Resultado esperado |
|---|---|---|---|
| T01 | Pedido válido, 1 item, quantidade mínima (limite 1) | POST /pedidos, cliente "Ana", CAD-001 x1 | 201; 1 item com reserva_id; estoque CAD-001 = 9 |
| T02 | Quantidade igual ao disponível (limite exato) | POST /pedidos, CAD-001 x10 | 201; estoque CAD-001 = 0 |
| T03 | Quantidade igual ao disponível + 1 | POST /pedidos, CAD-001 x11 | 409 com detail; estoque continua 10 |
| T04 | Quantidade no máximo do schema (100), maior que o estoque | POST /pedidos, CAD-001 x100 | 409 |
| T05 | Quantidade acima do máximo (101) | POST /pedidos, CAD-001 x101 | 422 |
| T06 | Quantidade 0 (limite inferior exclusivo) | POST /pedidos, CAD-001 x0 | 422 |
| T07 | Quantidade negativa | POST /pedidos, CAD-001 x(-1) | 422 |
| T08 | Quantidade com tipo inválido | POST /pedidos, quantidade "abc" | 422 |
| T09 | SKU sem estoque (disponível 0) | POST /pedidos, LUM-001 x1 | 409 |
| T10 | SKU com estoque 2 (MES-001): x2 e depois x1 | POST /pedidos MES-001 x2, depois MES-001 x1 | 201 e depois 409 |
| T11 | SKU inexistente no estoque | POST /pedidos, SKU-XXX x1 | 422 |
| T12 | SKU vazio (minLength 1) | POST /pedidos, sku "" | 422 |
| T13 | Cliente vazio (minLength 1) | POST /pedidos, cliente "" | 422 |
| T14 | Lista de itens vazia (minItems 1) | POST /pedidos, itens [] | 422 |
| T15 | Campos obrigatórios ausentes | POST /pedidos, {} | 422 |
| T16 | Múltiplos itens, todos disponíveis | POST /pedidos, CAD-001 x2 e MES-001 x1 | 201; 2 itens com reserva_id distintos; estoque 8 e 1 |
| T17 | Múltiplos itens, o 2º sem estoque | POST /pedidos, CAD-001 x2 e LUM-001 x1 | 409; reserva do 1º desfeita (CAD-001 = 10) |
| T18 | Múltiplos itens, o 2º com SKU inexistente | POST /pedidos, CAD-001 x2 e SKU-XXX x1 | 422; CAD-001 = 10 |
| T19 | Estoque responde fora do contrato | POST /pedidos com Estoque inválido | 502 (não executável só com as fixtures; skip) |
| T20 | Estoque indisponível | POST /pedidos com Estoque em timeout ou fora do ar | 503 (não executável só com as fixtures; skip) |
| T21 | Consultar pedido existente | GET /pedidos/{id} de pedido criado | 200 com mesmo id, cliente e itens |
| T22 | Consultar pedido inexistente | GET /pedidos/nao-existe | 404 com detail |
| T23 | Estoque: produto existente | GET /produtos/CAD-001 | 200 {CAD-001, Cadeira, 10} |
| T24 | Estoque: produto inexistente | GET /produtos/SKU-XXX | 404 |
| T25 | Estoque: reserva válida, quantidade mínima | POST /reservas, CAD-001 x1 | 201; disponível 9 |
| T26 | Estoque: reserva igual ao disponível | POST /reservas, MES-001 x2 | 201; disponível 0 |
| T27 | Estoque: reserva acima do disponível | POST /reservas, MES-001 x3 | 409; disponível 2 |
| T28 | Estoque: SKU inexistente | POST /reservas, SKU-XXX x1 | 404 |
| T29 | Estoque: Accept incompatível | POST /reservas válido com Accept: text/html | 406; disponível 10 |
| T30 | Estoque: quantidade 0 | POST /reservas, CAD-001 x0 | 422 |
| T31 | Estoque: quantidade 101 | POST /reservas, CAD-001 x101 | 422 |
| T32 | Estoque: quantidade 100 (máximo do schema) | POST /reservas, CAD-001 x100 | 409 |
| T33 | Estoque: SKU vazio | POST /reservas, sku "" | 422 |
| T34 | Estoque: corpo vazio | POST /reservas, {} | 422 |
| T35 | Estoque: cancelar reserva existente | DELETE /reservas/{id} | 204 sem corpo; disponível volta a 10 |
| T36 | Estoque: cancelar reserva inexistente | DELETE /reservas/nao-existe | 404 |
| T37 | Estoque: cancelar a mesma reserva duas vezes | DELETE duas vezes | 204 e depois 404 |

## Arquivo `tests/geradas/test_p1_contrato.py`

```python
"""Testes de integração Pedidos <-> Estoque (particionamento de equivalência
e análise de valor-limite sobre os contratos OpenAPI).

Fixtures `pedidos` e `estoque` vêm do conftest.py existente.
"""
import pytest


# ---------------------------------------------------------------- helpers

def _pedido(cliente="Ana", itens=None):
    return {"cliente": cliente, "itens": itens if itens is not None else []}


def _item(sku, quantidade):
    return {"sku": sku, "quantidade": quantidade}


def _disponivel(estoque, sku):
    r = estoque.get(f"/produtos/{sku}")
    assert r.status_code == 200
    return r.json()["disponivel"]


# ------------------------------------------------- POST /pedidos: 201

def test_t01_pedido_valido_quantidade_minima(pedidos, estoque):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", 1)]))
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["cliente"] == "Ana"
    assert isinstance(corpo["id"], str) and corpo["id"]
    assert isinstance(corpo["status"], str) and corpo["status"]
    assert len(corpo["itens"]) == 1
    item = corpo["itens"][0]
    assert item["sku"] == "CAD-001"
    assert item["quantidade"] == 1
    assert isinstance(item["reserva_id"], str) and item["reserva_id"]
    assert _disponivel(estoque, "CAD-001") == 9


def test_t02_quantidade_igual_ao_disponivel(pedidos, estoque):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", 10)]))
    assert r.status_code == 201
    assert r.json()["itens"][0]["quantidade"] == 10
    assert _disponivel(estoque, "CAD-001") == 0


# ------------------------------------------------- POST /pedidos: 409

def test_t03_quantidade_disponivel_mais_um(pedidos, estoque):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", 11)]))
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)
    assert _disponivel(estoque, "CAD-001") == 10


def test_t04_quantidade_maxima_do_schema_sem_estoque(pedidos, estoque):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", 100)]))
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)
    assert _disponivel(estoque, "CAD-001") == 10


# ------------------------------------------------- POST /pedidos: 422

def test_t05_quantidade_acima_do_maximo(pedidos, estoque):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", 101)]))
    assert r.status_code == 422
    assert _disponivel(estoque, "CAD-001") == 10


def test_t06_quantidade_zero(pedidos, estoque):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", 0)]))
    assert r.status_code == 422
    assert _disponivel(estoque, "CAD-001") == 10


def test_t07_quantidade_negativa(pedidos, estoque):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", -1)]))
    assert r.status_code == 422
    assert _disponivel(estoque, "CAD-001") == 10


def test_t08_quantidade_tipo_invalido(pedidos, estoque):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", "abc")]))
    assert r.status_code == 422
    assert _disponivel(estoque, "CAD-001") == 10


def test_t09_sku_sem_estoque(pedidos):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("LUM-001", 1)]))
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)


def test_t10_sku_com_estoque_dois_limite(pedidos, estoque):
    r_ok = pedidos.post("/pedidos", json=_pedido("Ana", [_item("MES-001", 2)]))
    assert r_ok.status_code == 201
    assert _disponivel(estoque, "MES-001") == 0

    # Estado recriado a cada teste: dentro do mesmo teste, o estoque já foi consumido.
    r_falha = pedidos.post("/pedidos", json=_pedido("Bia", [_item("MES-001", 1)]))
    assert r_falha.status_code == 409


def test_t11_sku_inexistente_no_estoque(pedidos):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("SKU-XXX", 1)]))
    assert r.status_code == 422


def test_t12_sku_vazio(pedidos):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("", 1)]))
    assert r.status_code == 422


def test_t13_cliente_vazio(pedidos, estoque):
    r = pedidos.post("/pedidos", json=_pedido("", [_item("CAD-001", 1)]))
    assert r.status_code == 422
    assert _disponivel(estoque, "CAD-001") == 10


def test_t14_lista_de_itens_vazia(pedidos):
    r = pedidos.post("/pedidos", json=_pedido("Ana", []))
    assert r.status_code == 422


def test_t15_campos_obrigatorios_ausentes(pedidos):
    r = pedidos.post("/pedidos", json={})
    assert r.status_code == 422


# ------------------------------------------------- POST /pedidos: múltiplos itens

def test_t16_multiplos_itens_validos(pedidos, estoque):
    r = pedidos.post(
        "/pedidos",
        json=_pedido("Ana", [_item("CAD-001", 2), _item("MES-001", 1)]),
    )
    assert r.status_code == 201
    itens = r.json()["itens"]
    assert len(itens) == 2
    assert {i["sku"] for i in itens} == {"CAD-001", "MES-001"}
    assert len({i["reserva_id"] for i in itens}) == 2
    assert _disponivel(estoque, "CAD-001") == 8
    assert _disponivel(estoque, "MES-001") == 1


def test_t17_segundo_item_sem_estoque_desfaz_primeiro(pedidos, estoque):
    r = pedidos.post(
        "/pedidos",
        json=_pedido("Ana", [_item("CAD-001", 2), _item("LUM-001", 1)]),
    )
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)
    assert _disponivel(estoque, "CAD-001") == 10
    assert _disponivel(estoque, "LUM-001") == 0


def test_t18_segundo_item_com_sku_inexistente_desfaz_primeiro(pedidos, estoque):
    r = pedidos.post(
        "/pedidos",
        json=_pedido("Ana", [_item("CAD-001", 2), _item("SKU-XXX", 1)]),
    )
    assert r.status_code == 422
    assert _disponivel(estoque, "CAD-001") == 10


# ------------------------------------------------- POST /pedidos: 502 e 503

@pytest.mark.skip(
    reason="502 exige que o Estoque responda fora do contrato; as fixtures "
    "`pedidos` e `estoque` não permitem injetar essa falha."
)
def test_t19_estoque_fora_do_contrato(pedidos):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", 1)]))
    assert r.status_code == 502
    assert isinstance(r.json()["detail"], str)


@pytest.mark.skip(
    reason="503 exige Estoque em timeout/indisponível; as fixtures `pedidos` "
    "e `estoque` não permitem derrubar ou atrasar o Estoque."
)
def test_t20_estoque_indisponivel(pedidos):
    r = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", 1)]))
    assert r.status_code == 503
    assert isinstance(r.json()["detail"], str)


# ------------------------------------------------- GET /pedidos/{pedido_id}

def test_t21_consultar_pedido_existente(pedidos):
    criado = pedidos.post("/pedidos", json=_pedido("Ana", [_item("CAD-001", 3)]))
    assert criado.status_code == 201
    pedido_id = criado.json()["id"]

    r = pedidos.get(f"/pedidos/{pedido_id}")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["id"] == pedido_id
    assert corpo["cliente"] == "Ana"
    assert corpo["itens"] == criado.json()["itens"]


def test_t22_consultar_pedido_inexistente(pedidos):
    r = pedidos.get("/pedidos/nao-existe")
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)


# ------------------------------------------------- Estoque: GET /produtos/{sku}

def test_t23_estoque_consultar_produto_existente(estoque):
    r = estoque.get("/produtos/CAD-001")
    assert r.status_code == 200
    assert r.json() == {"sku": "CAD-001", "nome": "Cadeira", "disponivel": 10}


def test_t24_estoque_consultar_produto_inexistente(estoque):
    r = estoque.get("/produtos/SKU-XXX")
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)


# ------------------------------------------------- Estoque: POST /reservas

def test_t25_estoque_reserva_valida_quantidade_minima(estoque):
    r = estoque.post("/reservas", json=_item("CAD-001", 1))
    assert r.status_code == 201
    corpo = r.json()
    assert isinstance(corpo["reserva_id"], str) and corpo["reserva_id"]
    assert corpo["sku"] == "CAD-001"
    assert corpo["quantidade"] == 1
    assert _disponivel(estoque, "CAD-001") == 9


def test_t26_estoque_reserva_igual_ao_disponivel(estoque):
    r = estoque.post("/reservas", json=_item("MES-001", 2))
    assert r.status_code == 201
    assert _disponivel(estoque, "MES-001") == 0


def test_t27_estoque_reserva_acima_do_disponivel(estoque):
    r = estoque.post("/reservas", json=_item("MES-001", 3))
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)
    assert _disponivel(estoque, "MES-001") == 2


def test_t28_estoque_reserva_sku_inexistente(estoque):
    r = estoque.post("/reservas", json=_item("SKU-XXX", 1))
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)


def test_t29_estoque_reserva_accept_incompativel(estoque):
    r = estoque.post(
        "/reservas",
        json=_item("CAD-001", 1),
        headers={"Accept": "text/html"},
    )
    assert r.status_code == 406
    assert isinstance(r.json()["detail"], str)
    assert _disponivel(estoque, "CAD-001") == 10


def test_t30_estoque_reserva_quantidade_zero(estoque):
    r = estoque.post("/reservas", json=_item("CAD-001", 0))
    assert r.status_code == 422
    assert _disponivel(estoque, "CAD-001") == 10


def test_t31_estoque_reserva_quantidade_acima_do_maximo(estoque):
    r = estoque.post("/reservas", json=_item("CAD-001", 101))
    assert r.status_code == 422
    assert _disponivel(estoque, "CAD-001") == 10


def test_t32_estoque_reserva_quantidade_maxima_do_schema(estoque):
    r = estoque.post("/reservas", json=_item("CAD-001", 100))
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)
    assert _disponivel(estoque, "CAD-001") == 10


def test_t33_estoque_reserva_sku_vazio(estoque):
    r = estoque.post("/reservas", json=_item("", 1))
    assert r.status_code == 422


def test_t34_estoque_reserva_corpo_vazio(estoque):
    r = estoque.post("/reservas", json={})
    assert r.status_code == 422


# ------------------------------------------------- Estoque: DELETE /reservas/{reserva_id}

def test_t35_estoque_cancelar_reserva_existente(estoque):
    criada = estoque.post("/reservas", json=_item("CAD-001", 4))
    assert criada.status_code == 201
    assert _disponivel(estoque, "CAD-001") == 6

    r = estoque.delete(f"/reservas/{criada.json()['reserva_id']}")
    assert r.status_code == 204
    assert r.content == b""
    assert _disponivel(estoque, "CAD-001") == 10


def test_t36_estoque_cancelar_reserva_inexistente(estoque):
    r = estoque.delete("/reservas/nao-existe")
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)


def test_t37_estoque_cancelar_mesma_reserva_duas_vezes(estoque):
    criada = estoque.post("/reservas", json=_item("CAD-001", 1))
    assert criada.status_code == 201
    reserva_id = criada.json()["reserva_id"]

    assert estoque.delete(f"/reservas/{reserva_id}").status_code == 204
    segunda = estoque.delete(f"/reservas/{reserva_id}")
    assert segunda.status_code == 404
    assert _disponivel(estoque, "CAD-001") == 10
```

## Observações

- **502 e 503 (T19 e T20):** as fixtures só dão o Estoque real e saudável. Não há como injetar resposta inválida, timeout ou queda. Os dois testes estão marcados com `skip` e motivo. Para executá-los, seria preciso uma fixture que troque o cliente do Estoque por um stub ou mock.
- **422 em parâmetros de caminho:** os contratos listam 422 para GET /pedidos/{pedido_id}, GET /produtos/{sku} e DELETE /reservas/{reserva_id}. Os parâmetros são `string` sem restrição, então nenhuma entrada válida de URL gera esse erro. Não criei casos para isso.
- **Rollback (T17 e T18):** o contrato não descreve explicitamente que o Pedidos cancela as reservas já feitas quando um item posterior falha. Assumi esse comportamento porque o Estoque expõe DELETE /reservas/{id}. Se a implementação não fizer o rollback, esses testes falham e apontam o problema.
