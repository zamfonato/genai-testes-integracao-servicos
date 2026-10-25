# 1. Análise

## Passo 1: cadeia de chamadas de `POST /pedidos`

1. O cliente envia `POST /pedidos`. O FastAPI valida o corpo com `PedidoIn`: `cliente` não vazio, `itens` com pelo menos 1 item, `sku` não vazio, `quantidade` entre 1 e 100. Se falhar, responde 422 sem chamar o Estoque.
2. `criar_pedido` percorre os itens em ordem. Para cada um chama `ClienteEstoque.reservar(sku, quantidade)`.
3. `reservar` faz `POST /reservas` com JSON `{sku, quantidade}` e o header `Accept: application/json`. Depois interpreta a resposta:
   - `TimeoutException` vira `EstoqueIndisponivel`.
   - `TransportError` vira `EstoqueIndisponivel`.
   - 201 com `json()["reserva_id"]` devolve o id.
   - 404 vira `ProdutoNaoEncontrado`.
   - 409 vira `EstoqueInsuficiente`.
   - Qualquer outro status vira `EstoqueIndisponivel`.
4. Se algum item levanta `ErroEstoque`, o app chama `estoque.cancelar(reserva_id)` (um `DELETE /reservas/{id}`) para cada item já reservado. Em seguida converte o erro em `HTTPException` pelo mapa `STATUS_POR_ERRO`: 422, 409, 502 ou 503.
5. Se todos os itens foram reservados, o app monta o pedido com um uuid, chama `repo.salvar` (transação SQLite) e devolve 201 validado por `response_model=Pedido`.
6. `GET /pedidos/{id}` devolve o pedido, ou 404 se `repo.buscar` retornar `None`.

## Passos 2 e 3: o que pode dar errado, comportamento correto e o que o código faz

| Passo | Falha possível | Comportamento correto | O que o código faz hoje |
|---|---|---|---|
| Validação de entrada | Payload inválido | 422 e nenhuma chamada ao Estoque | Correto (Pydantic) |
| Rede | Timeout de conexão, escrita ou pool | 503 e compensação das reservas anteriores | Correto, via `TimeoutException` |
| Rede | Conexão recusada, leitura quebrada, erro de protocolo | 503 e compensação | Correto, via `TransportError` |
| Rede | Erro do httpx que não é `TransportError` (`DecodingError`, `TooManyRedirects`) | 502 ou 503 | **Não é capturado, vira 500 e as reservas vazam** |
| Status | 404 | 422 (produto inexistente) e compensação | Correto |
| Status | 409 | 409 e compensação | Correto |
| Status | 500, 503, 406 ou 422 do Estoque | 503 | Correto: todos viram `EstoqueIndisponivel` |
| Status | 2xx diferente de 201 (por exemplo 200) | 502, fora do contrato | **Devolve 503**, o que parece divergência |
| Corpo | 201 com corpo não JSON | 502 | Correto (`ValueError`) |
| Corpo | 201 com JSON sem `reserva_id` | 502 | Correto (`KeyError`) |
| Corpo | 201 com JSON de tipo errado (lista, `null`, string) | 502 | **`TypeError` não capturado, vira 500** |
| Corpo | 201 com `reserva_id` nulo ou numérico | 502 e nada gravado | **Aceita o valor.** Com `null` o SQLite rejeita (NOT NULL). Com `123` grava e a validação da resposta falha com 500. |
| Headers | `Accept` ausente no POST ou no DELETE | O Estoque exige `Accept: application/json` e responde 406 sem ele | Envia nos dois |
| Compensação | `DELETE` falha por transporte | Melhor esforço: devolve o erro original e tenta cancelar as demais | Correto (o `except HTTPError` engole) |
| Compensação | `DELETE` devolve 404 ou 500 | Ignorar e devolver o erro original | Correto, porque o status do DELETE nunca é verificado. Isso também esconde um 406 por header ausente. |
| Compensação | Falha no 1º item | Não há o que cancelar | Correto (`itens` vazio) |
| Persistência | `repo.salvar` levanta exceção depois de reservar tudo | 5xx e cancelar as reservas | **Não compensa. O `try` cobre só `ErroEstoque`, então a exceção sobe como 500 e as reservas vazam.** |
| Consulta | `GET` de pedido inexistente | 404 | Correto |

## Passo 4: derivação dos casos

Há um caso por decisão ou ponto de falha. Os marcados com (!) são os que eu espero que falhem hoje, porque expõem os defeitos acima: T3, S4, B3, P1.

# 2. Tabela de casos

| ID | Ponto de falha | Como simular | Resultado esperado |
|---|---|---|---|
| V1 | Payload inválido no Pedidos | POST com cliente vazio, itens vazios, sku vazio, quantidade 0, 101 ou -1, ou quantidade não numérica | 422, Estoque não chamado, nada gravado |
| T1 | Timeout (Connect, Write, Pool) no 2º item | Mock: 1º POST 201, 2º levanta o timeout | 503 "a tempo", DELETE da reserva 1, nada gravado |
| T2 | Conexão recusada, leitura quebrada ou erro de protocolo | Mock levanta `ConnectError`, `ReadError` ou `RemoteProtocolError` | 503 "conexão", sem DELETE, nada gravado |
| T3 (!) | Erro httpx fora de `TransportError` | Mock levanta `DecodingError` no 2º item | 502 ou 503 (não 500) e reserva 1 cancelada |
| S1 | 404 do Estoque | Estoque real, SKU `XXX-999` | 422 citando o SKU, nada gravado |
| S2 | 409 do Estoque | Estoque real: `LUM-001` ×1 (disponível 0) e `MES-001` ×3 (disponível 2) | 409, estoque intacto, nada gravado |
| S3 | Status inesperado | Mock responde 500, 503, 406 ou 422 | 503, nada gravado |
| S4 (!) | 2xx diferente de 201 | Mock responde 200 com JSON válido | 502 (fora do contrato), nada gravado |
| B1 | 201 com corpo não JSON | Mock responde 201 com HTML | 502, nada gravado |
| B2 | 201 sem `reserva_id` | Mock responde 201 com `{"sku": ...}` | 502, nada gravado |
| B3 (!) | 201 com JSON de tipo errado | Corpo `[]`, `null`, `"texto"`, `{"reserva_id": null}` ou `{"reserva_id": 123}` | 502, nada gravado |
| B4 | Resposta inválida no 2º item | Mock: 1º POST 201, 2º com corpo não JSON | 502 e DELETE da reserva 1 |
| H1 | Headers do POST | Mock grava a requisição de um pedido válido | `Accept` e `Content-Type` JSON, corpo `{sku, quantidade}` |
| H2 | Header do DELETE na compensação | Mock grava o DELETE depois de um 409 | `Accept: application/json` |
| C1 | Compensação com 409 no 2º item | Estoque real: `CAD-001`×2 e `MES-001`×3 | 409, `CAD-001` volta a 10, nada gravado |
| C2 | Compensação com 404 no 3º item | Estoque real: `CAD-001`, `MES-001`, `XXX-999` | 422, `CAD-001` em 10 e `MES-001` em 2 |
| C3 | Falha no 1º item | Mock: 1º POST devolve 409 | 409, nenhum DELETE |
| C4 | DELETE falha por transporte | Mock: 2 POSTs 201, 3º 409, DELETEs levantam `ConnectError` | 409 devolvido, as duas tentativas de DELETE feitas, nada gravado |
| C5 | DELETE devolve 404 ou 500 | Mock com o mesmo roteiro e DELETE respondendo 404 ou 500 | 409 devolvido, sem exceção |
| P1 (!) | Falha ao gravar o pedido | Estoque real, `repositorio.salvar` levanta `sqlite3.OperationalError` | 500 ou 503 e reservas canceladas (`CAD-001` em 10) |
| G1 | Pedido inexistente | `GET /pedidos/nao-existe` | 404 com id no detalhe |

# 3. Arquivo `tests/geradas/test_p2_falhas.py`

```python
"""Testes de integração Pedidos -> Estoque focados em falhas e respostas inesperadas (P2)."""

import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from servicos.pedidos.app import create_app as criar_pedidos


# ---------------------------------------------------------------- helpers

def _payload(*itens, cliente="ana"):
    return {"cliente": cliente, "itens": [{"sku": sku, "quantidade": qtd} for sku, qtd in itens]}


def _reserva_ok(reserva_id):
    def resposta(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"reserva_id": reserva_id, **json.loads(request.content)})

    return resposta


def _responde(status, **kwargs):
    return lambda request: httpx.Response(status, **kwargs)


def _levanta(excecao, mensagem="falha simulada"):
    def resposta(request: httpx.Request) -> httpx.Response:
        raise excecao(mensagem, request=request)

    return resposta


def _json_cru(corpo: bytes):
    return _responde(201, content=corpo, headers={"content-type": "application/json"})


class EstoqueFalso:
    """Handler para MockTransport: roteiro de respostas para os POSTs /reservas, em ordem,
    e uma resposta fixa para os DELETEs. Registra tudo o que o Pedidos enviou."""

    def __init__(self, reservas, cancelamento=None):
        self._reservas = list(reservas)
        self._cancelamento = cancelamento or _responde(204)
        self.posts = []
        self.deletes = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/reservas":
            indice = len(self.posts)
            self.posts.append(request)
            assert indice < len(self._reservas), "Pedidos reservou mais itens do que o esperado"
            return self._reservas[indice](request)
        if request.method == "DELETE" and request.url.path.startswith("/reservas/"):
            self.deletes.append(request)
            return self._cancelamento(request)
        raise AssertionError(f"Chamada inesperada ao Estoque: {request.method} {request.url.path}")

    @property
    def reservas_canceladas(self):
        return [r.url.path.rsplit("/", 1)[-1] for r in self.deletes]


def _cliente_tolerante(http, repositorio):
    """Pedidos que devolve 500 em vez de propagar exceções não tratadas (para casos com defeito provável)."""
    return TestClient(criar_pedidos(http, repositorio), raise_server_exceptions=False)


def _http_simulado(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://estoque")


# ---------------------------------------------------------------- V1: validação de entrada

@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param({"cliente": "", "itens": [{"sku": "CAD-001", "quantidade": 1}]}, id="cliente-vazio"),
        pytest.param({"cliente": "ana", "itens": []}, id="itens-vazio"),
        pytest.param({"cliente": "ana"}, id="sem-itens"),
        pytest.param(_payload(("", 1)), id="sku-vazio"),
        pytest.param(_payload(("CAD-001", 0)), id="quantidade-zero"),
        pytest.param(_payload(("CAD-001", -1)), id="quantidade-negativa"),
        pytest.param(_payload(("CAD-001", 101)), id="quantidade-acima-de-100"),
        pytest.param({"cliente": "ana", "itens": [{"sku": "CAD-001", "quantidade": "abc"}]}, id="quantidade-nao-numerica"),
    ],
)
def test_payload_invalido_retorna_422_sem_chamar_estoque(pedidos_com_estoque_simulado, repositorio, corpo):
    estoque = EstoqueFalso([])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=corpo)

    assert resposta.status_code == 422
    assert estoque.posts == []
    assert repositorio.contar() == 0


# ---------------------------------------------------------------- T1-T3: falhas de rede

@pytest.mark.parametrize("timeout", [httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout])
def test_timeout_no_segundo_item_retorna_503_e_cancela_primeira_reserva(
    pedidos_com_estoque_simulado, repositorio, timeout
):
    estoque = EstoqueFalso([_reserva_ok("r-1"), _levanta(timeout, "timeout")])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1), ("MES-001", 1)))

    assert resposta.status_code == 503
    assert "a tempo" in resposta.json()["detail"]
    assert estoque.reservas_canceladas == ["r-1"]
    assert repositorio.contar() == 0


@pytest.mark.parametrize("erro", [httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError])
def test_falha_de_conexao_ou_protocolo_retorna_503_sem_gravar(pedidos_com_estoque_simulado, repositorio, erro):
    estoque = EstoqueFalso([_levanta(erro, "conexão caiu")])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1)))

    assert resposta.status_code == 503
    assert "conexão" in resposta.json()["detail"]
    assert estoque.deletes == []
    assert repositorio.contar() == 0


def test_erro_httpx_fora_de_transporte_nao_vira_500_e_cancela_reservas(repositorio):
    # DecodingError é RequestError, mas não é TransportError: o cliente não o captura hoje.
    estoque = EstoqueFalso([_reserva_ok("r-1"), _levanta(httpx.DecodingError, "gzip corrompido")])
    cliente = _cliente_tolerante(_http_simulado(estoque), repositorio)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1), ("MES-001", 1)))

    assert resposta.status_code in (502, 503)
    assert estoque.reservas_canceladas == ["r-1"]
    assert repositorio.contar() == 0


# ---------------------------------------------------------------- S1-S4: status HTTP do Estoque

def test_produto_inexistente_no_estoque_retorna_422_sem_gravar(pedidos, repositorio):
    resposta = pedidos.post("/pedidos", json=_payload(("XXX-999", 1)))

    assert resposta.status_code == 422
    assert "XXX-999" in str(resposta.json()["detail"])
    assert repositorio.contar() == 0


@pytest.mark.parametrize(
    "sku, quantidade, disponivel",
    [
        pytest.param("LUM-001", 1, 0, id="estoque-zerado"),
        pytest.param("MES-001", 3, 2, id="um-acima-do-disponivel"),
    ],
)
def test_estoque_insuficiente_retorna_409_sem_alterar_estoque(
    pedidos, estoque, repositorio, sku, quantidade, disponivel
):
    resposta = pedidos.post("/pedidos", json=_payload((sku, quantidade)))

    assert resposta.status_code == 409
    assert estoque.get(f"/produtos/{sku}").json()["disponivel"] == disponivel
    assert repositorio.contar() == 0


@pytest.mark.parametrize(
    "status_estoque",
    [
        pytest.param(500, id="500"),
        pytest.param(503, id="503"),
        pytest.param(406, id="406-accept"),
        pytest.param(422, id="422-validacao"),
    ],
)
def test_status_inesperado_do_estoque_retorna_503(pedidos_com_estoque_simulado, repositorio, status_estoque):
    estoque = EstoqueFalso([_responde(status_estoque, json={"detail": "erro"})])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1)))

    assert resposta.status_code == 503
    assert repositorio.contar() == 0


def test_status_2xx_diferente_de_201_retorna_502_fora_do_contrato(pedidos_com_estoque_simulado, repositorio):
    # O contrato do Estoque só prevê 201 em sucesso; 200 é resposta fora do contrato.
    estoque = EstoqueFalso([_responde(200, json={"reserva_id": "r-1", "sku": "CAD-001", "quantidade": 1})])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1)))

    assert resposta.status_code == 502
    assert repositorio.contar() == 0


# ---------------------------------------------------------------- B1-B4: corpo da resposta

def test_201_com_corpo_nao_json_retorna_502(pedidos_com_estoque_simulado, repositorio):
    estoque = EstoqueFalso([_responde(201, content=b"<html>Bad Gateway</html>", headers={"content-type": "text/html"})])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1)))

    assert resposta.status_code == 502
    assert repositorio.contar() == 0


def test_201_sem_reserva_id_retorna_502(pedidos_com_estoque_simulado, repositorio):
    estoque = EstoqueFalso([_responde(201, json={"sku": "CAD-001", "quantidade": 1})])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1)))

    assert resposta.status_code == 502
    assert repositorio.contar() == 0


@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param(b"[]", id="lista"),
        pytest.param(b"null", id="null"),
        pytest.param(b'"texto"', id="string"),
        pytest.param(b'{"reserva_id": null}', id="reserva_id-nulo"),
        pytest.param(b'{"reserva_id": 123}', id="reserva_id-numerico"),
    ],
)
def test_201_com_json_de_tipo_inesperado_retorna_502_sem_gravar(repositorio, corpo):
    estoque = EstoqueFalso([_json_cru(corpo)])
    cliente = _cliente_tolerante(_http_simulado(estoque), repositorio)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1)))

    assert resposta.status_code == 502
    assert repositorio.contar() == 0


def test_resposta_invalida_no_segundo_item_retorna_502_e_cancela_primeira_reserva(
    pedidos_com_estoque_simulado, repositorio
):
    estoque = EstoqueFalso([_reserva_ok("r-1"), _responde(201, content=b"nao e json")])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1), ("MES-001", 1)))

    assert resposta.status_code == 502
    assert estoque.reservas_canceladas == ["r-1"]
    assert repositorio.contar() == 0


# ---------------------------------------------------------------- H1-H2: headers

def test_reserva_envia_accept_e_corpo_json_ao_estoque(pedidos_com_estoque_simulado):
    estoque = EstoqueFalso([_reserva_ok("r-1")])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 2)))

    assert resposta.status_code == 201
    requisicao = estoque.posts[0]
    assert requisicao.headers["accept"] == "application/json"
    assert requisicao.headers["content-type"].startswith("application/json")
    assert json.loads(requisicao.content) == {"sku": "CAD-001", "quantidade": 2}


def test_cancelamento_de_compensacao_envia_accept_json(pedidos_com_estoque_simulado):
    estoque = EstoqueFalso([_reserva_ok("r-1"), _responde(409, json={"detail": "insuficiente"})])
    cliente = pedidos_com_estoque_simulado(estoque)

    cliente.post("/pedidos", json=_payload(("CAD-001", 1), ("MES-001", 1)))

    assert len(estoque.deletes) == 1
    assert estoque.deletes[0].headers["accept"] == "application/json"


# ---------------------------------------------------------------- C1-C5: compensação

def test_409_no_segundo_item_devolve_a_reserva_do_primeiro(pedidos, estoque, repositorio):
    resposta = pedidos.post("/pedidos", json=_payload(("CAD-001", 2), ("MES-001", 3)))

    assert resposta.status_code == 409
    assert estoque.get("/produtos/CAD-001").json()["disponivel"] == 10
    assert estoque.get("/produtos/MES-001").json()["disponivel"] == 2
    assert repositorio.contar() == 0


def test_404_no_terceiro_item_devolve_as_duas_reservas_anteriores(pedidos, estoque, repositorio):
    resposta = pedidos.post("/pedidos", json=_payload(("CAD-001", 2), ("MES-001", 1), ("XXX-999", 1)))

    assert resposta.status_code == 422
    assert estoque.get("/produtos/CAD-001").json()["disponivel"] == 10
    assert estoque.get("/produtos/MES-001").json()["disponivel"] == 2
    assert repositorio.contar() == 0


def test_falha_no_primeiro_item_nao_dispara_cancelamento(pedidos_com_estoque_simulado, repositorio):
    estoque = EstoqueFalso([_responde(409, json={"detail": "insuficiente"})])
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("LUM-001", 1), ("CAD-001", 1)))

    assert resposta.status_code == 409
    assert len(estoque.posts) == 1
    assert estoque.deletes == []
    assert repositorio.contar() == 0


def test_cancelamento_com_erro_de_transporte_nao_mascara_o_erro_original(pedidos_com_estoque_simulado, repositorio):
    estoque = EstoqueFalso(
        [_reserva_ok("r-1"), _reserva_ok("r-2"), _responde(409, json={"detail": "insuficiente"})],
        cancelamento=_levanta(httpx.ConnectError, "estoque caiu"),
    )
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1), ("MES-001", 1), ("LUM-001", 1)))

    assert resposta.status_code == 409
    # Melhor esforço: tentou cancelar as duas, mesmo com a primeira tentativa falhando.
    assert estoque.reservas_canceladas == ["r-1", "r-2"]
    assert repositorio.contar() == 0


@pytest.mark.parametrize("status_delete", [404, 500])
def test_cancelamento_com_status_de_erro_e_ignorado(pedidos_com_estoque_simulado, repositorio, status_delete):
    estoque = EstoqueFalso(
        [_reserva_ok("r-1"), _responde(409, json={"detail": "insuficiente"})],
        cancelamento=_responde(status_delete, json={"detail": "erro no cancelamento"}),
    )
    cliente = pedidos_com_estoque_simulado(estoque)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 1), ("MES-001", 1)))

    assert resposta.status_code == 409
    assert estoque.reservas_canceladas == ["r-1"]
    assert repositorio.contar() == 0


# ---------------------------------------------------------------- P1: persistência

def test_falha_ao_gravar_pedido_devolve_as_reservas_ja_feitas(estoque, repositorio, monkeypatch):
    def salvar_com_falha(pedido):
        raise sqlite3.OperationalError("disco cheio")

    monkeypatch.setattr(repositorio, "salvar", salvar_com_falha)
    cliente = _cliente_tolerante(estoque, repositorio)

    resposta = cliente.post("/pedidos", json=_payload(("CAD-001", 2), ("MES-001", 1)))

    assert resposta.status_code in (500, 503)
    assert estoque.get("/produtos/CAD-001").json()["disponivel"] == 10
    assert estoque.get("/produtos/MES-001").json()["disponivel"] == 2


# ---------------------------------------------------------------- G1: consulta

def test_consultar_pedido_inexistente_retorna_404(pedidos):
    resposta = pedidos.get("/pedidos/nao-existe")

    assert resposta.status_code == 404
    assert "nao-existe" in resposta.json()["detail"]
```

## Observações

- Os casos marcados com (!) na tabela (T3, S4, B3, P1) devem **falhar** com o código atual. Eles expõem defeitos reais, não erros de teste:
  - `TypeError` não tratado quando o JSON do 201 não é um objeto.
  - `reserva_id` nulo ou numérico aceito.
  - Exceções do httpx fora de `TransportError` sem tratamento.
  - Nenhuma compensação quando `repo.salvar` falha.
  - Um 200 tratado como 503 em vez de 502.
- Esses casos usam um `TestClient(..., raise_server_exceptions=False)` local, para que a falha apareça como status 500 e não como exceção propagada. Isso é um helper, não uma redefinição das fixtures.
- Uso `parametrize` onde várias variantes pertencem ao mesmo ponto de falha. Cada ID da tabela corresponde a uma função de teste.
