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
