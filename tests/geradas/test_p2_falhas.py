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
