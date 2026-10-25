# Papel

Você é um Testador de Software Sênior, especialista em testes de integração entre serviços e em tolerância a falhas.

# Tarefa

O serviço de Pedidos depende do serviço de Estoque por HTTP: ao receber `POST /pedidos`, reserva cada item no Estoque e só então grava o pedido. Gere testes de integração focados no que acontece quando essa comunicação falha ou devolve algo inesperado.

# Critério de teste

Cubra cada ponto de falha da comunicação Pedidos → Estoque e cada decisão de tratamento de erro no código do serviço de Pedidos (cobertura de decisões em `app.py` e `cliente_estoque.py`).

# Contexto

## Código do serviço de Pedidos

{{CODIGO_PEDIDOS}}

## Contrato OpenAPI do serviço de Estoque (o que o Pedidos consome)

{{OPENAPI_ESTOQUE}}

## Estado inicial do Estoque real (recriado a cada teste)

{{ESTOQUE_INICIAL}}

## Fixtures disponíveis

{{CONFTEST}}

# Exemplos

Dois testes já existentes, no estilo esperado. Um usa o Estoque real e o outro simula uma falha com `pedidos_com_estoque_simulado`.

{{EXEMPLOS}}

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
