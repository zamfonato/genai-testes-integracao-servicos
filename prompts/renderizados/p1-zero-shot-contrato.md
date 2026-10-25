# Papel

Você é um Testador de Software Sênior, especialista em testes de integração de APIs REST.

# Tarefa

Gere casos de teste de integração entre dois serviços REST, Pedidos e Estoque. Ao receber `POST /pedidos`, o serviço de Pedidos chama o serviço de Estoque por HTTP para reservar cada item do pedido.

# Critério de teste

Use particionamento de equivalência e análise de valor-limite sobre os contratos abaixo. O conjunto deve exercitar todos os métodos HTTP e todos os status codes documentados nos dois contratos.

# Contexto

## Contrato OpenAPI do serviço de Pedidos

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Serviço de Pedidos",
    "version": "1.0.0"
  },
  "paths": {
    "/pedidos": {
      "post": {
        "summary": "Criar Pedido",
        "operationId": "criar_pedido_pedidos_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/PedidoIn"
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
                  "$ref": "#/components/schemas/Pedido"
                }
              }
            }
          },
          "409": {
            "description": "Estoque insuficiente para algum item",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Erro"
                }
              }
            }
          },
          "422": {
            "description": "Dados inválidos ou produto inexistente no estoque"
          },
          "502": {
            "description": "Estoque respondeu fora do contrato",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Erro"
                }
              }
            }
          },
          "503": {
            "description": "Estoque indisponível (timeout, conexão ou erro)",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Erro"
                }
              }
            }
          }
        }
      }
    },
    "/pedidos/{pedido_id}": {
      "get": {
        "summary": "Consultar Pedido",
        "operationId": "consultar_pedido_pedidos__pedido_id__get",
        "parameters": [
          {
            "name": "pedido_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "Pedido Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Pedido"
                }
              }
            }
          },
          "404": {
            "description": "Pedido não encontrado",
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
      "ItemIn": {
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
        "title": "ItemIn"
      },
      "ItemPedido": {
        "properties": {
          "sku": {
            "type": "string",
            "title": "Sku"
          },
          "quantidade": {
            "type": "integer",
            "title": "Quantidade"
          },
          "reserva_id": {
            "type": "string",
            "title": "Reserva Id"
          }
        },
        "type": "object",
        "required": [
          "sku",
          "quantidade",
          "reserva_id"
        ],
        "title": "ItemPedido"
      },
      "Pedido": {
        "properties": {
          "id": {
            "type": "string",
            "title": "Id"
          },
          "cliente": {
            "type": "string",
            "title": "Cliente"
          },
          "status": {
            "type": "string",
            "title": "Status"
          },
          "itens": {
            "items": {
              "$ref": "#/components/schemas/ItemPedido"
            },
            "type": "array",
            "title": "Itens"
          }
        },
        "type": "object",
        "required": [
          "id",
          "cliente",
          "status",
          "itens"
        ],
        "title": "Pedido"
      },
      "PedidoIn": {
        "properties": {
          "cliente": {
            "type": "string",
            "minLength": 1,
            "title": "Cliente"
          },
          "itens": {
            "items": {
              "$ref": "#/components/schemas/ItemIn"
            },
            "type": "array",
            "minItems": 1,
            "title": "Itens"
          }
        },
        "type": "object",
        "required": [
          "cliente",
          "itens"
        ],
        "title": "PedidoIn"
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

## Contrato OpenAPI do serviço de Estoque

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

## Estado inicial do Estoque (recriado a cada teste)

| sku | nome | disponível |
|---|---|---|
| CAD-001 | Cadeira | 10 |
| MES-001 | Mesa | 2 |
| LUM-001 | Luminária | 0 |

# Ambiente de teste

Os testes usam pytest. O `conftest.py` já existe e fornece estas fixtures:

- `pedidos`: cliente HTTP (TestClient do FastAPI, compatível com httpx) do serviço de Pedidos, já ligado ao serviço de Estoque real.
- `estoque`: cliente HTTP do mesmo serviço de Estoque que o Pedidos usa. Serve para conferir efeitos da integração, por exemplo `estoque.get("/produtos/CAD-001")`.

# Formato de saída

1. Uma tabela com os casos: ID | Partição ou limite | Entrada | Resultado esperado.
2. Um único arquivo `tests/geradas/test_p1_contrato.py`, completo e executável, com os imports necessários e um teste por caso da tabela. Não redefina as fixtures.
