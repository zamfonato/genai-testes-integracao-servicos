# Papel

Você é um Testador de Software Sênior, especialista em testes de integração entre serviços e em tolerância a falhas.

# Tarefa

O serviço de Pedidos depende do serviço de Estoque por HTTP: ao receber `POST /pedidos`, reserva cada item no Estoque e só então grava o pedido. Gere testes de integração focados no que acontece quando essa comunicação falha ou devolve algo inesperado.

# Critério de teste

Cubra cada ponto de falha da comunicação Pedidos → Estoque e cada decisão de tratamento de erro no código do serviço de Pedidos (cobertura de decisões em `app.py` e `cliente_estoque.py`).

# Contexto

## Código do serviço de Pedidos

### `servicos/pedidos/app.py`

```python
"""Serviço de Pedidos: cria pedidos reservando itens no serviço de Estoque."""

import os
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from servicos.pedidos.cliente_estoque import (
    ClienteEstoque,
    ErroEstoque,
    EstoqueIndisponivel,
    EstoqueInsuficiente,
    ProdutoNaoEncontrado,
    RespostaInvalida,
)
from servicos.pedidos.repositorio import RepositorioPedidos

STATUS_POR_ERRO = {
    ProdutoNaoEncontrado: 422,
    EstoqueInsuficiente: 409,
    RespostaInvalida: 502,
    EstoqueIndisponivel: 503,
}


class Erro(BaseModel):
    detail: str


class ItemIn(BaseModel):
    sku: str = Field(min_length=1)
    quantidade: int = Field(gt=0, le=100)


class PedidoIn(BaseModel):
    cliente: str = Field(min_length=1)
    itens: list[ItemIn] = Field(min_length=1)


class ItemPedido(BaseModel):
    sku: str
    quantidade: int
    reserva_id: str


class Pedido(BaseModel):
    id: str
    cliente: str
    status: str
    itens: list[ItemPedido]


def create_app(http_estoque: httpx.Client, repositorio: RepositorioPedidos | None = None) -> FastAPI:
    app = FastAPI(title="Serviço de Pedidos", version="1.0.0")
    estoque = ClienteEstoque(http_estoque)
    repo = repositorio or RepositorioPedidos()

    @app.post(
        "/pedidos",
        status_code=201,
        response_model=Pedido,
        responses={
            409: {"model": Erro, "description": "Estoque insuficiente para algum item"},
            422: {"description": "Dados inválidos ou produto inexistente no estoque"},
            502: {"model": Erro, "description": "Estoque respondeu fora do contrato"},
            503: {"model": Erro, "description": "Estoque indisponível (timeout, conexão ou erro)"},
        },
    )
    def criar_pedido(dados: PedidoIn):
        itens = []
        try:
            for item in dados.itens:
                reserva_id = estoque.reservar(item.sku, item.quantidade)
                itens.append({"sku": item.sku, "quantidade": item.quantidade, "reserva_id": reserva_id})
        except ErroEstoque as erro:
            for reservado in itens:
                estoque.cancelar(reservado["reserva_id"])
            raise HTTPException(STATUS_POR_ERRO[type(erro)], str(erro))

        pedido = {"id": str(uuid4()), "cliente": dados.cliente, "status": "confirmado", "itens": itens}
        repo.salvar(pedido)
        return pedido

    @app.get(
        "/pedidos/{pedido_id}",
        response_model=Pedido,
        responses={404: {"model": Erro, "description": "Pedido não encontrado"}},
    )
    def consultar_pedido(pedido_id: str):
        pedido = repo.buscar(pedido_id)
        if pedido is None:
            raise HTTPException(404, f"Pedido {pedido_id} não encontrado")
        return pedido

    return app


def app_de_producao() -> FastAPI:
    url = os.environ.get("ESTOQUE_URL", "http://localhost:8001")
    return create_app(httpx.Client(base_url=url, timeout=2.0), RepositorioPedidos("pedidos.db"))
```

### `servicos/pedidos/cliente_estoque.py`

```python
"""Cliente HTTP que o serviço de Pedidos usa para falar com o Estoque."""

import httpx


class ErroEstoque(Exception):
    pass


class ProdutoNaoEncontrado(ErroEstoque):
    pass


class EstoqueInsuficiente(ErroEstoque):
    pass


class RespostaInvalida(ErroEstoque):
    pass


class EstoqueIndisponivel(ErroEstoque):
    pass


class ClienteEstoque:
    def __init__(self, http: httpx.Client):
        self.http = http

    def reservar(self, sku: str, quantidade: int) -> str:
        try:
            resposta = self.http.post(
                "/reservas",
                json={"sku": sku, "quantidade": quantidade},
                headers={"Accept": "application/json"},
            )
        except httpx.TimeoutException as erro:
            raise EstoqueIndisponivel("Estoque não respondeu a tempo") from erro
        except httpx.TransportError as erro:
            raise EstoqueIndisponivel("Falha de conexão com o estoque") from erro

        if resposta.status_code == 201:
            try:
                return resposta.json()["reserva_id"]
            except (ValueError, KeyError) as erro:
                raise RespostaInvalida("Resposta do estoque fora do contrato") from erro
        if resposta.status_code == 404:
            raise ProdutoNaoEncontrado(f"Produto {sku} não existe")
        if resposta.status_code == 409:
            raise EstoqueInsuficiente(f"Estoque insuficiente para {sku}")
        raise EstoqueIndisponivel(f"Estoque respondeu {resposta.status_code}")

    def cancelar(self, reserva_id: str) -> None:
        # Compensação em melhor esforço: se falhar, a reserva fica no estoque.
        try:
            self.http.delete(f"/reservas/{reserva_id}", headers={"Accept": "application/json"})
        except httpx.HTTPError:
            pass
```

### `servicos/pedidos/repositorio.py`

```python
"""Persistência dos pedidos em SQLite."""

import sqlite3


class RepositorioPedidos:
    def __init__(self, caminho: str = ":memory:"):
        self.conn = sqlite3.connect(caminho, check_same_thread=False)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pedidos (
                id TEXT PRIMARY KEY,
                cliente TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS itens_pedido (
                pedido_id TEXT NOT NULL REFERENCES pedidos(id),
                sku TEXT NOT NULL,
                quantidade INTEGER NOT NULL,
                reserva_id TEXT NOT NULL
            );
            """
        )

    def salvar(self, pedido: dict) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO pedidos (id, cliente, status) VALUES (?, ?, ?)",
                (pedido["id"], pedido["cliente"], pedido["status"]),
            )
            self.conn.executemany(
                "INSERT INTO itens_pedido (pedido_id, sku, quantidade, reserva_id) VALUES (?, ?, ?, ?)",
                [(pedido["id"], i["sku"], i["quantidade"], i["reserva_id"]) for i in pedido["itens"]],
            )

    def buscar(self, pedido_id: str) -> dict | None:
        linha = self.conn.execute(
            "SELECT id, cliente, status FROM pedidos WHERE id = ?", (pedido_id,)
        ).fetchone()
        if linha is None:
            return None
        itens = self.conn.execute(
            "SELECT sku, quantidade, reserva_id FROM itens_pedido WHERE pedido_id = ?", (pedido_id,)
        ).fetchall()
        return {
            "id": linha[0],
            "cliente": linha[1],
            "status": linha[2],
            "itens": [{"sku": s, "quantidade": q, "reserva_id": r} for s, q, r in itens],
        }

    def contar(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]
```

## Contrato OpenAPI do serviço de Estoque (o que o Pedidos consome)

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Serviço de Estoque",
    "version": "1.0.0"
  },
  "paths": {
    "/produtos/{sku}": {
      "get": {
        "summary": "Consultar Produto",
        "operationId": "consultar_produto_produtos__sku__get",
        "parameters": [
          {
            "name": "sku",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "Sku"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Produto"
                }
              }
            }
          },
          "404": {
            "description": "Produto não encontrado",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Erro"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/reservas": {
      "post": {
        "summary": "Reservar",
        "operationId": "reservar_reservas_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ReservaIn"
              }
            }
          },
          "required": true
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Reserva"
                }
              }
            }
          },
          "404": {
            "description": "Produto não encontrado",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Erro"
                }
              }
            }
          },
          "406": {
            "description": "Header Accept não aceita application/json",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Erro"
                }
              }
            }
          },
          "409": {
            "description": "Estoque insuficiente",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Erro"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/reservas/{reserva_id}": {
      "delete": {
        "summary": "Cancelar",
        "operationId": "cancelar_reservas__reserva_id__delete",
        "parameters": [
          {
            "name": "reserva_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "Reserva Id"
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Successful Response"
          },
          "404": {
            "description": "Reserva não encontrada",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Erro"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "Erro": {
        "properties": {
          "detail": {
            "type": "string",
            "title": "Detail"
          }
        },
        "type": "object",
        "required": [
          "detail"
        ],
        "title": "Erro"
      },
      "HTTPValidationError": {
        "properties": {
          "detail": {
            "items": {
              "$ref": "#/components/schemas/ValidationError"
            },
            "type": "array",
            "title": "Detail"
          }
        },
        "type": "object",
        "title": "HTTPValidationError"
      },
      "Produto": {
        "properties": {
          "sku": {
            "type": "string",
            "title": "Sku"
          },
          "nome": {
            "type": "string",
            "title": "Nome"
          },
          "disponivel": {
            "type": "integer",
            "title": "Disponivel"
          }
        },
        "type": "object",
        "required": [
          "sku",
          "nome",
          "disponivel"
        ],
        "title": "Produto"
      },
      "Reserva": {
        "properties": {
          "reserva_id": {
            "type": "string",
            "title": "Reserva Id"
          },
          "sku": {
            "type": "string",
            "title": "Sku"
          },
          "quantidade": {
            "type": "integer",
            "title": "Quantidade"
          }
        },
        "type": "object",
        "required": [
          "reserva_id",
          "sku",
          "quantidade"
        ],
        "title": "Reserva"
      },
      "ReservaIn": {
        "properties": {
          "sku": {
            "type": "string",
            "minLength": 1,
            "title": "Sku"
          },
          "quantidade": {
            "type": "integer",
            "maximum": 100.0,
            "exclusiveMinimum": 0.0,
            "title": "Quantidade"
          }
        },
        "type": "object",
        "required": [
          "sku",
          "quantidade"
        ],
        "title": "ReservaIn"
      },
      "ValidationError": {
        "properties": {
          "loc": {
            "items": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "integer"
                }
              ]
            },
            "type": "array",
            "title": "Location"
          },
          "msg": {
            "type": "string",
            "title": "Message"
          },
          "type": {
            "type": "string",
            "title": "Error Type"
          }
        },
        "type": "object",
        "required": [
          "loc",
          "msg",
          "type"
        ],
        "title": "ValidationError"
      }
    }
  }
}
```

## Estado inicial do Estoque real (recriado a cada teste)

| sku | nome | disponível |
|---|---|---|
| CAD-001 | Cadeira | 10 |
| MES-001 | Mesa | 2 |
| LUM-001 | Luminária | 0 |

## Fixtures disponíveis

### `tests/conftest.py`

```python
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
```

# Exemplos

Dois testes já existentes, no estilo esperado. Um usa o Estoque real e o outro simula uma falha com `pedidos_com_estoque_simulado`.

### `tests/exemplos/test_exemplos.py`

```python
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
```

# Análise antes do código

Antes do código, escreva uma análise em passos, como parte da resposta:

1. Descreva a cadeia de chamadas de `POST /pedidos`, desde a requisição do cliente até a gravação no banco.
2. Em cada passo, liste o que pode dar errado na comunicação: rede, status HTTP, corpo da resposta, headers, persistência e compensação das reservas já feitas.
3. Para cada falha, diga qual deveria ser o comportamento correto e o que o código faz hoje.
4. Só então derive os casos de teste.

# Formato de saída

1. A análise, passos 1 a 4.
2. Uma tabela com os casos: ID | Ponto de falha | Como simular | Resultado esperado.
3. Um único arquivo `tests/geradas/test_p2_falhas.py`, completo e executável, no estilo dos exemplos, com um teste por caso da tabela. Não redefina as fixtures.
