# GenAI em testes de integração entre serviços

Atividade do fórum da Unidade III do curso *Testes de Software Automatizados com IA Generativa* (Especialização em Eng. de Software com IA Generativa, AKCIT/CEIA/UFG).

Dois tipos de prompt geram testes de integração entre dois serviços REST (**Pedidos → Estoque**). Os testes gerados foram executados e comparados. O relatório completo está em [`docs/relatorio.md`](docs/relatorio.md).

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `servicos/` | serviços Estoque e Pedidos (FastAPI + SQLite) |
| `openapi/` | contratos exportados dos dois serviços |
| `prompts/templates/` | prompts com placeholders (`{{OPENAPI_ESTOQUE}}`, `{{CODIGO_PEDIDOS}}`...) |
| `prompts/renderizados/` | texto exato enviado à LLM |
| `prompts/versoes-anteriores/` | versões antes dos ajustes |
| `saidas/` | respostas da LLM, sem edição |
| `tests/exemplos/` | 2 testes escritos à mão (os exemplos do few-shot) |
| `tests/geradas/` | testes extraídos das respostas, executados como vieram |

## Como rodar

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Linux/macOS: .venv/bin/pip
python -m pytest --cov=servicos --cov-branch
python -m scripts.montar_prompts                # regera openapi/ e prompts/renderizados/
```
