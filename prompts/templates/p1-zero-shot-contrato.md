# Papel

Você é um Testador de Software Sênior, especialista em testes de integração de APIs REST.

# Tarefa

Gere casos de teste de integração entre dois serviços REST, Pedidos e Estoque. Ao receber `POST /pedidos`, o serviço de Pedidos chama o serviço de Estoque por HTTP para reservar cada item do pedido.

# Critério de teste

Use particionamento de equivalência e análise de valor-limite sobre os contratos abaixo. O conjunto deve exercitar todos os métodos HTTP e todos os status codes documentados nos dois contratos.

# Contexto

## Contrato OpenAPI do serviço de Pedidos

{{OPENAPI_PEDIDOS}}

## Contrato OpenAPI do serviço de Estoque

{{OPENAPI_ESTOQUE}}

## Estado inicial do Estoque (recriado a cada teste)

{{ESTOQUE_INICIAL}}

# Ambiente de teste

Os testes usam pytest. O `conftest.py` já existe e fornece estas fixtures:

- `pedidos`: cliente HTTP (TestClient do FastAPI, compatível com httpx) do serviço de Pedidos, já ligado ao serviço de Estoque real.
- `estoque`: cliente HTTP do mesmo serviço de Estoque que o Pedidos usa. Serve para conferir efeitos da integração, por exemplo `estoque.get("/produtos/CAD-001")`.
- `pedidos_com_estoque_simulado`: fábrica que recebe `handler(request: httpx.Request) -> httpx.Response` e devolve um cliente do serviço de Pedidos cujo Estoque é esse handler. O handler pode levantar exceções do httpx (por exemplo `httpx.ReadTimeout("timeout", request=request)`) para simular falhas de rede. Use-a para os status do Pedidos que dependem do comportamento do Estoque. As respostas simuladas devem seguir o contrato do Estoque, exceto quando o caso for justamente uma resposta fora do contrato.

# Formato de saída

1. Uma tabela com os casos: ID | Partição ou limite | Entrada | Resultado esperado.
2. Um único arquivo `tests/geradas/test_p1_contrato.py`, completo e executável, com os imports necessários e um teste por caso da tabela. Não redefina as fixtures.
