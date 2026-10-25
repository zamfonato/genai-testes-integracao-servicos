"""Fixtures compartilhadas pelos testes de integração Pedidos <-> Estoque."""

import httpx
import pytest
from fastapi.testclient import TestClient

from servicos.estoque.app import create_app as criar_estoque
from servicos.pedidos.app import create_app as criar_pedidos
from servicos.pedidos.repositorio import RepositorioPedidos


@pytest.fixture
def estoque():
    """Cliente HTTP do serviço de Estoque real, com estado inicial novo a cada teste."""
    return TestClient(criar_estoque(), base_url="http://estoque")


@pytest.fixture
def repositorio():
    """Repositório SQLite em memória usado pelo serviço de Pedidos."""
    return RepositorioPedidos()


@pytest.fixture
def pedidos(estoque, repositorio):
    """Cliente HTTP do serviço de Pedidos falando com o Estoque real (fixture `estoque`)."""
    return TestClient(criar_pedidos(estoque, repositorio))


@pytest.fixture
def pedidos_com_estoque_simulado(repositorio):
    """Fábrica: recebe handler(request: httpx.Request) -> httpx.Response, que também pode
    levantar exceções do httpx, e devolve um cliente do serviço de Pedidos cujo Estoque
    é esse handler."""

    def fabrica(handler):
        http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://estoque")
        return TestClient(criar_pedidos(http, repositorio))

    return fabrica
