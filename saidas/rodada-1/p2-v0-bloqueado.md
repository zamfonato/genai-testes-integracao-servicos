# P2 v0: execução bloqueada

Modelo: claude-sonnet-5-5 (agente limpo, só o prompt como contexto)
Prompt: `prompts/versoes-anteriores/p2-fewshot-cot-falhas-v0.md`

O modelo não respondeu. A API devolveu:

> API Error: Sonnet 5.5's safeguards flagged this message. Details: `[reasoning_extraction]`
> (error type invalid_request, request id req_011CgNkYAWnN4nA6gfrZ3qny)

Causa provável: a seção "Raciocínio" pedia "pense passo a passo e mostre o raciocínio".
Modelos atuais tratam pedido de expor o raciocínio interno como extração de raciocínio.
Ajuste (v1): pedir uma análise escrita como parte da entrega, com os mesmos passos.
