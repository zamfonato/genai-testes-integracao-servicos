# Relatório do experimento

## Cenário

Dois serviços REST em FastAPI. O **Pedidos** recebe `POST /pedidos` e, para cada item, chama o **Estoque** por HTTP (`POST /reservas`). Só grava o pedido no SQLite quando todas as reservas dão certo. Se algo falha, cancela as reservas já feitas (`DELETE /reservas/{id}`).

O ponto de integração testado é essa chamada entre os dois serviços. Os testes usam o Estoque real (via `TestClient`) ou um Estoque simulado (`httpx.MockTransport`) para injetar falhas.

## Como os prompts foram executados

- LLM: **Claude Sonnet 5.5**, numa sessão limpa por prompt. O modelo recebeu só o texto do prompt, sem histórico, código extra ou ferramentas.
- O texto exato enviado está em `prompts/renderizados/` (versão atual) e `prompts/versoes-anteriores/`.
- As respostas estão sem edição em `saidas/`. O arquivo de teste foi extraído com `scripts/extrair_teste.py` e executado como veio.

## Os dois tipos de prompt

| | P1: zero-shot de contrato | P2: few-shot + análise em passos (chain-of-thought) |
|---|---|---|
| Papel | testador sênior de APIs REST | testador sênior de integração e tolerância a falhas |
| Critério | partição de equivalência + valor-limite; todos os verbos e status documentados | cada ponto de falha Pedidos → Estoque + cobertura de decisões |
| Contexto | só os contratos OpenAPI dos dois serviços (caixa-preta) | código do Pedidos + contrato do Estoque + fixtures + 2 testes de exemplo |

## Resultados

Cobertura de comandos e decisões (`pytest --cov --cov-branch`) do ponto de integração `servicos/pedidos/cliente_estoque.py`:

| Conjunto | Testes | Resultado na 1ª execução | Cobertura do cliente |
|---|---|---|---|
| Exemplos escritos à mão | 2 | 2 passam | 57% |
| P1 v1 | 37 | 35 passam, 2 skip (502 e 503) | 76% |
| P1 v2 | 42 | 42 passam | 89% |
| P2 v1 | 41 | 33 passam, **8 falham por defeito real** | 100% |
| Todos juntos | | | 100% (99% do sistema) |

**O P1** gerou testes corretos de primeira, mas só do comportamento documentado. A versão v2 passou **inteira também contra o código com defeitos** (commit da rodada 1). Ou seja, não revelou nenhum dos defeitos.

**O P2** apontou, antes de rodar, quais testes deveriam falhar, e foram exatamente esses 8. Os defeitos encontrados:

1. Erro do httpx fora da camada de transporte (ex.: `DecodingError`) virava 500 e deixava as reservas presas.
2. Um 2xx diferente de 201 era tratado como 503, e não como resposta fora do contrato (502).
3. Um 201 com corpo que não é objeto, ou com `reserva_id` nulo ou numérico, virava 500.
4. Uma falha ao gravar o pedido não cancelava as reservas.

Depois da correção humana (diferença entre os commits da rodada 1 e da rodada 2), a suíte inteira passa.

## Ajustes de prompt

1. **P2 v0 → v1.** A primeira versão pedia "pense passo a passo e mostre o raciocínio". O filtro do modelo bloqueou o pedido como extração de raciocínio (`saidas/rodada-1/p2-v0-bloqueado.md`). Trocamos por "escreva uma análise em passos, como parte da resposta". É o mesmo chain-of-thought, pedido como entregável.
2. **P1 v1 → v2.** O próprio modelo avisou que 502 e 503 não dão para provocar só com o Estoque real. Ele marcou esses testes como `skip`, em vez de inventar. Na v2 o prompt descreve a fixture de Estoque simulado, com a regra de seguir o contrato do Estoque. A cobertura do cliente subiu de 76% para 89%.

## Observações

- **O tipo de prompt mudou o tipo de teste, não só a quantidade.** O P1 é bom para validar o contrato e os valores-limite. O P2 achou os defeitos de integração. Os dois se complementam, como o ebook descreve.
- **Oráculos fracos.** Quando o contrato não define o resultado, o modelo aceitou dois status (`in (502, 503)`, `in (500, 503)`). Essa decisão continua sendo do testador.
- **Mais teste ≠ teste melhor.** O P1 v2 tem mais testes que o P2 e achou zero defeitos.
