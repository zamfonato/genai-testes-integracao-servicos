Os casos de teste estão na tabela, seguida do arquivo `tests/geradas/test_p1_contrato.py`. Não executei nada.

## Tabela de casos

| ID | Partição ou limite | Entrada | Resultado esperado |
|---|---|---|---|
| T01 | Pedidos POST válido, 1 item, caso típico | `{"cliente":"Ana","itens":[{"sku":"CAD-001","quantidade":5}]}` | 201; corpo com `id`, `cliente`="Ana", `status`, 1 item com `reserva_id`; Estoque CAD-001 fica com 5 disponíveis |
| T02 | Quantidade no limite inferior válido (1) | CAD-001, quantidade 1 | 201; Estoque fica com 9 |
| T03 | Quantidade no limite superior válido (100), mas acima do estoque | CAD-001, quantidade 100 | 409 (o limite do schema passa; falta estoque); corpo com `detail` |
| T04 | Quantidade igual ao disponível (limite do estoque) | MES-001, quantidade 2 | 201; Estoque MES-001 fica com 0 |
| T05 | Quantidade = disponível + 1 | MES-001, quantidade 3 | 409; `detail` string; estoque de MES-001 continua 2 |
| T06 | Estoque zerado | LUM-001, quantidade 1 | 409 |
| T07 | Vários itens válidos | CAD-001 x2 e MES-001 x1 | 201; 2 itens com `reserva_id` distintos |
| T08 | Falha parcial, segundo item sem estoque | CAD-001 x3, depois LUM-001 x1 | 409; reserva do primeiro item desfeita (CAD-001 continua com 10) |
| T09 | Quantidade 0 (limite inválido) | CAD-001, quantidade 0 | 422; nada reservado |
| T10 | Quantidade negativa | CAD-001, quantidade -1 | 422 |
| T11 | Quantidade 101 (limite superior inválido) | CAD-001, quantidade 101 | 422; nada reservado |
| T12 | Quantidade com tipo errado | quantidade "abc" | 422 |
| T13 | `sku` vazio (minLength 1) | sku "" | 422 |
| T14 | `cliente` vazio (minLength 1) | cliente "" | 422 |
| T15 | `itens` vazio (minItems 1) | `itens: []` | 422 |
| T16 | Campo obrigatório ausente (`cliente`) | corpo sem `cliente` | 422 |
| T17 | Campo obrigatório ausente (`itens`) | corpo sem `itens` | 422 |
| T18 | Produto inexistente no Estoque | sku "NAO-EXISTE", quantidade 1 | 422 (regra do Pedidos, não 404) |
| T19 | Estoque responde fora do contrato (201 sem os campos de Reserva) | Estoque simulado devolve `{"foo":"bar"}` | 502; corpo com `detail` |
| T20 | Estoque responde 201 com corpo não JSON | Estoque simulado devolve texto | 502 |
| T21 | Estoque com timeout | Estoque simulado levanta `ReadTimeout` | 503; corpo com `detail` |
| T22 | Estoque com falha de conexão | Estoque simulado levanta `ConnectError` | 503 |
| T23 | Estoque com erro interno | Estoque simulado devolve 500 | 503 |
| T24 | Pedidos GET existente | POST válido e depois GET do `id` | 200; mesmo `id`, `cliente`, `itens` |
| T25 | Pedidos GET inexistente | `GET /pedidos/nao-existe` | 404; corpo com `detail` |
| T26 | Pedidos GET com segmento extra no path | `GET /pedidos/a/b` | 404 ou 422 (ver nota) |
| T27 | Estoque GET produto existente | `GET /produtos/CAD-001` | 200; `sku`, `nome`="Cadeira", `disponivel`=10 |
| T28 | Estoque GET produto sem saldo | `GET /produtos/LUM-001` | 200; `disponivel`=0 |
| T29 | Estoque GET produto inexistente | `GET /produtos/NAO-EXISTE` | 404; `detail` |
| T30 | Estoque POST reserva válida, limite inferior (1) | CAD-001, quantidade 1 | 201; `reserva_id`, `sku`, `quantidade`=1; CAD-001 com 9 |
| T31 | Estoque POST reserva 100 acima do saldo | CAD-001, quantidade 100 | 409 |
| T32 | Estoque POST reserva igual ao saldo | MES-001, quantidade 2 | 201; MES-001 com 0 |
| T33 | Estoque POST reserva saldo + 1 | MES-001, quantidade 3 | 409 |
| T34 | Estoque POST produto inexistente | sku "NAO-EXISTE", quantidade 1 | 404 |
| T35 | Estoque POST `Accept` incompatível | `Accept: text/html`, corpo válido | 406; `detail`; saldo inalterado |
| T36 | Estoque POST quantidade 0 | CAD-001, quantidade 0 | 422 |
| T37 | Estoque POST quantidade 101 | CAD-001, quantidade 101 | 422 |
| T38 | Estoque POST sku vazio | sku "" | 422 |
| T39 | Estoque POST corpo sem `quantidade` | `{"sku":"CAD-001"}` | 422 |
| T40 | Estoque DELETE reserva existente | reservar e depois `DELETE /reservas/{id}` | 204 sem corpo; saldo devolvido (CAD-001 volta a 10) |
| T41 | Estoque DELETE reserva inexistente | `DELETE /reservas/nao-existe` | 404; `detail` |
| T42 | Estoque DELETE repetido | cancelar a mesma reserva duas vezes | 204 e depois 404 |

Nota sobre o 422 dos GET e do DELETE: `pedido_id`, `sku` e `reserva_id` são strings livres, então nenhum valor de path deveria causar 422. O T26 é a aproximação mais próxima (segmento extra no path). Os 422 de POST estão cobertos em T09 a T18 e T36 a T39.

## Arquivo `tests/geradas/test_p1_contrato.py`

```python
"""Testes de integração Pedidos <-> Estoque (particionamento de equivalência e valor-limite)."""
import httpx
import pytest


# ---------------------------------------------------------------- helpers

def pedido(itens, cliente="Ana"):
    return {"cliente": cliente, "itens": itens}


def item(sku="CAD-001", quantidade=1):
    return {"sku": sku, "quantidade": quantidade}


def disponivel(estoque, sku):
    r = estoque.get(f"/produtos/{sku}")
    assert r.status_code == 200
    return r.json()["disponivel"]


def _produto_ok(request):
    sku = request.url.path.rsplit("/", 1)[-1]
    return httpx.Response(200, json={"sku": sku, "nome": "X", "disponivel": 100})


def _handler_com_reserva(reserva_resp):
    """GET /produtos/{sku} responde conforme o contrato; POST /reservas usa reserva_resp."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.startswith("/produtos/"):
            return _produto_ok(request)
        if request.method == "POST" and request.url.path == "/reservas":
            return reserva_resp(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": "nao encontrado"})
    return handler


# ---------------------------------------------------------------- Pedidos: POST /pedidos

def test_t01_pedido_valido_201(pedidos, estoque):
    r = pedidos.post("/pedidos", json=pedido([item("CAD-001", 5)]))
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["id"]
    assert corpo["cliente"] == "Ana"
    assert isinstance(corpo["status"], str)
    assert len(corpo["itens"]) == 1
    assert corpo["itens"][0]["sku"] == "CAD-001"
    assert corpo["itens"][0]["quantidade"] == 5
    assert corpo["itens"][0]["reserva_id"]
    assert disponivel(estoque, "CAD-001") == 5


def test_t02_quantidade_limite_inferior_1(pedidos, estoque):
    r = pedidos.post("/pedidos", json=pedido([item("CAD-001", 1)]))
    assert r.status_code == 201
    assert disponivel(estoque, "CAD-001") == 9


def test_t03_quantidade_100_valida_no_schema_mas_sem_estoque(pedidos, estoque):
    r = pedidos.post("/pedidos", json=pedido([item("CAD-001", 100)]))
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)
    assert disponivel(estoque, "CAD-001") == 10


def test_t04_quantidade_igual_ao_disponivel(pedidos, estoque):
    r = pedidos.post("/pedidos", json=pedido([item("MES-001", 2)]))
    assert r.status_code == 201
    assert disponivel(estoque, "MES-001") == 0


def test_t05_quantidade_disponivel_mais_um(pedidos, estoque):
    r = pedidos.post("/pedidos", json=pedido([item("MES-001", 3)]))
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)
    assert disponivel(estoque, "MES-001") == 2


def test_t06_estoque_zerado(pedidos, estoque):
    r = pedidos.post("/pedidos", json=pedido([item("LUM-001", 1)]))
    assert r.status_code == 409
    assert disponivel(estoque, "LUM-001") == 0


def test_t07_varios_itens_validos(pedidos, estoque):
    r = pedidos.post("/pedidos", json=pedido([item("CAD-001", 2), item("MES-001", 1)]))
    assert r.status_code == 201
    itens = r.json()["itens"]
    assert len(itens) == 2
    assert len({i["reserva_id"] for i in itens}) == 2
    assert disponivel(estoque, "CAD-001") == 8
    assert disponivel(estoque, "MES-001") == 1


def test_t08_falha_parcial_desfaz_reservas_anteriores(pedidos, estoque):
    r = pedidos.post("/pedidos", json=pedido([item("CAD-001", 3), item("LUM-001", 1)]))
    assert r.status_code == 409
    assert disponivel(estoque, "CAD-001") == 10
    assert disponivel(estoque, "LUM-001") == 0


@pytest.mark.parametrize("qtd", [0, -1, 101])
def test_t09_t10_t11_quantidade_fora_do_intervalo_422(pedidos, estoque, qtd):
    r = pedidos.post("/pedidos", json=pedido([item("CAD-001", qtd)]))
    assert r.status_code == 422
    assert disponivel(estoque, "CAD-001") == 10


def test_t12_quantidade_tipo_errado(pedidos):
    r = pedidos.post("/pedidos", json=pedido([{"sku": "CAD-001", "quantidade": "abc"}]))
    assert r.status_code == 422


def test_t13_sku_vazio(pedidos):
    r = pedidos.post("/pedidos", json=pedido([item("", 1)]))
    assert r.status_code == 422


def test_t14_cliente_vazio(pedidos):
    r = pedidos.post("/pedidos", json=pedido([item("CAD-001", 1)], cliente=""))
    assert r.status_code == 422


def test_t15_itens_vazio(pedidos):
    r = pedidos.post("/pedidos", json=pedido([]))
    assert r.status_code == 422


def test_t16_sem_cliente(pedidos):
    r = pedidos.post("/pedidos", json={"itens": [item("CAD-001", 1)]})
    assert r.status_code == 422


def test_t17_sem_itens(pedidos):
    r = pedidos.post("/pedidos", json={"cliente": "Ana"})
    assert r.status_code == 422


def test_t18_produto_inexistente_422(pedidos):
    r = pedidos.post("/pedidos", json=pedido([item("NAO-EXISTE", 1)]))
    assert r.status_code == 422


def test_t19_estoque_fora_do_contrato_502(pedidos_com_estoque_simulado):
    cliente = pedidos_com_estoque_simulado(
        _handler_com_reserva(lambda req: httpx.Response(201, json={"foo": "bar"}))
    )
    r = cliente.post("/pedidos", json=pedido([item("CAD-001", 1)]))
    assert r.status_code == 502
    assert isinstance(r.json()["detail"], str)


def test_t20_estoque_corpo_nao_json_502(pedidos_com_estoque_simulado):
    cliente = pedidos_com_estoque_simulado(
        _handler_com_reserva(lambda req: httpx.Response(201, content=b"nao e json"))
    )
    r = cliente.post("/pedidos", json=pedido([item("CAD-001", 1)]))
    assert r.status_code == 502


def test_t21_estoque_timeout_503(pedidos_com_estoque_simulado):
    def handler(request):
        if request.method == "GET":
            return _produto_ok(request)
        raise httpx.ReadTimeout("timeout", request=request)

    cliente = pedidos_com_estoque_simulado(handler)
    r = cliente.post("/pedidos", json=pedido([item("CAD-001", 1)]))
    assert r.status_code == 503
    assert isinstance(r.json()["detail"], str)


def test_t22_estoque_conexao_503(pedidos_com_estoque_simulado):
    def handler(request):
        raise httpx.ConnectError("sem conexao", request=request)

    cliente = pedidos_com_estoque_simulado(handler)
    r = cliente.post("/pedidos", json=pedido([item("CAD-001", 1)]))
    assert r.status_code == 503


def test_t23_estoque_erro_interno_503(pedidos_com_estoque_simulado):
    cliente = pedidos_com_estoque_simulado(
        lambda request: httpx.Response(500, json={"detail": "erro interno"})
    )
    r = cliente.post("/pedidos", json=pedido([item("CAD-001", 1)]))
    assert r.status_code == 503


# ---------------------------------------------------------------- Pedidos: GET /pedidos/{id}

def test_t24_consultar_pedido_existente_200(pedidos):
    criado = pedidos.post("/pedidos", json=pedido([item("CAD-001", 2)])).json()
    r = pedidos.get(f"/pedidos/{criado['id']}")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["id"] == criado["id"]
    assert corpo["cliente"] == "Ana"
    assert corpo["itens"] == criado["itens"]


def test_t25_consultar_pedido_inexistente_404(pedidos):
    r = pedidos.get("/pedidos/nao-existe")
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)


def test_t26_consultar_pedido_path_com_segmento_extra(pedidos):
    # pedido_id é string livre; não há valor que gere 422. Segmento extra não casa com a rota.
    r = pedidos.get("/pedidos/a/b")
    assert r.status_code in (404, 422)


# ---------------------------------------------------------------- Estoque: GET /produtos/{sku}

def test_t27_produto_existente_200(estoque):
    r = estoque.get("/produtos/CAD-001")
    assert r.status_code == 200
    assert r.json() == {"sku": "CAD-001", "nome": "Cadeira", "disponivel": 10}


def test_t28_produto_sem_saldo_200(estoque):
    r = estoque.get("/produtos/LUM-001")
    assert r.status_code == 200
    assert r.json()["disponivel"] == 0


def test_t29_produto_inexistente_404(estoque):
    r = estoque.get("/produtos/NAO-EXISTE")
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)


# ---------------------------------------------------------------- Estoque: POST /reservas

def test_t30_reserva_valida_201(estoque):
    r = estoque.post("/reservas", json={"sku": "CAD-001", "quantidade": 1})
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["reserva_id"]
    assert corpo["sku"] == "CAD-001"
    assert corpo["quantidade"] == 1
    assert disponivel(estoque, "CAD-001") == 9


def test_t31_reserva_100_acima_do_saldo_409(estoque):
    r = estoque.post("/reservas", json={"sku": "CAD-001", "quantidade": 100})
    assert r.status_code == 409
    assert disponivel(estoque, "CAD-001") == 10


def test_t32_reserva_igual_ao_saldo(estoque):
    r = estoque.post("/reservas", json={"sku": "MES-001", "quantidade": 2})
    assert r.status_code == 201
    assert disponivel(estoque, "MES-001") == 0


def test_t33_reserva_saldo_mais_um_409(estoque):
    r = estoque.post("/reservas", json={"sku": "MES-001", "quantidade": 3})
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)
    assert disponivel(estoque, "MES-001") == 2


def test_t34_reserva_produto_inexistente_404(estoque):
    r = estoque.post("/reservas", json={"sku": "NAO-EXISTE", "quantidade": 1})
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)


def test_t35_reserva_accept_incompativel_406(estoque):
    r = estoque.post(
        "/reservas",
        json={"sku": "CAD-001", "quantidade": 1},
        headers={"Accept": "text/html"},
    )
    assert r.status_code == 406
    assert isinstance(r.json()["detail"], str)
    assert disponivel(estoque, "CAD-001") == 10


def test_t36_reserva_quantidade_zero_422(estoque):
    r = estoque.post("/reservas", json={"sku": "CAD-001", "quantidade": 0})
    assert r.status_code == 422


def test_t37_reserva_quantidade_101_422(estoque):
    r = estoque.post("/reservas", json={"sku": "CAD-001", "quantidade": 101})
    assert r.status_code == 422


def test_t38_reserva_sku_vazio_422(estoque):
    r = estoque.post("/reservas", json={"sku": "", "quantidade": 1})
    assert r.status_code == 422


def test_t39_reserva_sem_quantidade_422(estoque):
    r = estoque.post("/reservas", json={"sku": "CAD-001"})
    assert r.status_code == 422


# ---------------------------------------------------------------- Estoque: DELETE /reservas/{id}

def test_t40_cancelar_reserva_204(estoque):
    reserva = estoque.post("/reservas", json={"sku": "CAD-001", "quantidade": 4}).json()
    assert disponivel(estoque, "CAD-001") == 6
    r = estoque.delete(f"/reservas/{reserva['reserva_id']}")
    assert r.status_code == 204
    assert r.content == b""
    assert disponivel(estoque, "CAD-001") == 10


def test_t41_cancelar_reserva_inexistente_404(estoque):
    r = estoque.delete("/reservas/nao-existe")
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)


def test_t42_cancelar_reserva_duas_vezes(estoque):
    reserva = estoque.post("/reservas", json={"sku": "CAD-001", "quantidade": 1}).json()
    rid = reserva["reserva_id"]
    assert estoque.delete(f"/reservas/{rid}").status_code == 204
    assert estoque.delete(f"/reservas/{rid}").status_code == 404
    assert disponivel(estoque, "CAD-001") == 10
```
