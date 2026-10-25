"""Exporta os contratos OpenAPI e preenche os templates de prompt.

Os templates em prompts/templates usam placeholders {{NOME}}. O resultado vai para
prompts/renderizados, que é exatamente o texto enviado à LLM.
"""

import json
from pathlib import Path

import httpx

from servicos.estoque.app import ESTOQUE_INICIAL
from servicos.estoque.app import create_app as criar_estoque
from servicos.pedidos.app import create_app as criar_pedidos

RAIZ = Path(__file__).resolve().parent.parent


def ler(caminho: str) -> str:
    return (RAIZ / caminho).read_text(encoding="utf-8")


def bloco(linguagem: str, conteudo: str, titulo: str | None = None) -> str:
    cabecalho = f"### `{titulo}`\n\n" if titulo else ""
    return f"{cabecalho}```{linguagem}\n{conteudo.strip()}\n```"


def main() -> None:
    openapi = {
        "estoque": criar_estoque().openapi(),
        "pedidos": criar_pedidos(httpx.Client()).openapi(),
    }
    (RAIZ / "openapi").mkdir(exist_ok=True)
    for nome, spec in openapi.items():
        (RAIZ / "openapi" / f"{nome}.json").write_text(
            json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    tabela_estoque = "| sku | nome | disponível |\n|---|---|---|\n" + "\n".join(
        f"| {sku} | {nome} | {qtd} |" for sku, (nome, qtd) in ESTOQUE_INICIAL.items()
    )
    valores = {
        "OPENAPI_ESTOQUE": bloco("json", ler("openapi/estoque.json")),
        "OPENAPI_PEDIDOS": bloco("json", ler("openapi/pedidos.json")),
        "ESTOQUE_INICIAL": tabela_estoque,
        "CODIGO_PEDIDOS": "\n\n".join(
            bloco("python", ler(f"servicos/pedidos/{arquivo}"), f"servicos/pedidos/{arquivo}")
            for arquivo in ("app.py", "cliente_estoque.py", "repositorio.py")
        ),
        "CONFTEST": bloco("python", ler("tests/conftest.py"), "tests/conftest.py"),
        "EXEMPLOS": bloco("python", ler("tests/exemplos/test_exemplos.py"), "tests/exemplos/test_exemplos.py"),
    }

    destino = RAIZ / "prompts" / "renderizados"
    destino.mkdir(parents=True, exist_ok=True)
    for template in sorted((RAIZ / "prompts" / "templates").glob("*.md")):
        texto = template.read_text(encoding="utf-8")
        for nome, valor in valores.items():
            texto = texto.replace("{{" + nome + "}}", valor)
        (destino / template.name).write_text(texto, encoding="utf-8")
        print(f"{template.name}: {len(texto)} caracteres")


if __name__ == "__main__":
    main()
