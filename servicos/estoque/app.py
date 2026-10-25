"""Serviço de Estoque: consulta produtos e reserva/cancela quantidades."""

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ESTOQUE_INICIAL = {
    "CAD-001": ("Cadeira", 10),
    "MES-001": ("Mesa", 2),
    "LUM-001": ("Luminária", 0),
}

TIPOS_ACEITOS = ("application/json", "application/*", "*/*")


class Erro(BaseModel):
    detail: str


class Produto(BaseModel):
    sku: str
    nome: str
    disponivel: int


class ReservaIn(BaseModel):
    sku: str = Field(min_length=1)
    quantidade: int = Field(gt=0, le=100)


class Reserva(BaseModel):
    reserva_id: str
    sku: str
    quantidade: int


def create_app(estoque_inicial: dict[str, tuple[str, int]] | None = None) -> FastAPI:
    app = FastAPI(title="Serviço de Estoque", version="1.0.0")
    itens = estoque_inicial if estoque_inicial is not None else ESTOQUE_INICIAL
    produtos = {sku: Produto(sku=sku, nome=nome, disponivel=qtd) for sku, (nome, qtd) in itens.items()}
    reservas: dict[str, Reserva] = {}

    @app.middleware("http")
    async def exige_json(request: Request, call_next):
        accept = request.headers.get("accept", "*/*")
        if not any(tipo in accept for tipo in TIPOS_ACEITOS):
            return JSONResponse(status_code=406, content={"detail": "Apenas application/json é suportado"})
        return await call_next(request)

    @app.get(
        "/produtos/{sku}",
        response_model=Produto,
        responses={404: {"model": Erro, "description": "Produto não encontrado"}},
    )
    def consultar_produto(sku: str):
        if sku not in produtos:
            raise HTTPException(404, f"Produto {sku} não encontrado")
        return produtos[sku]

    @app.post(
        "/reservas",
        status_code=201,
        response_model=Reserva,
        responses={
            404: {"model": Erro, "description": "Produto não encontrado"},
            406: {"model": Erro, "description": "Header Accept não aceita application/json"},
            409: {"model": Erro, "description": "Estoque insuficiente"},
        },
    )
    def reservar(dados: ReservaIn):
        produto = produtos.get(dados.sku)
        if produto is None:
            raise HTTPException(404, f"Produto {dados.sku} não encontrado")
        if produto.disponivel < dados.quantidade:
            raise HTTPException(409, f"Estoque insuficiente para {dados.sku}")
        produto.disponivel -= dados.quantidade
        reserva = Reserva(reserva_id=str(uuid4()), sku=dados.sku, quantidade=dados.quantidade)
        reservas[reserva.reserva_id] = reserva
        return reserva

    @app.delete(
        "/reservas/{reserva_id}",
        status_code=204,
        responses={404: {"model": Erro, "description": "Reserva não encontrada"}},
    )
    def cancelar(reserva_id: str):
        reserva = reservas.pop(reserva_id, None)
        if reserva is None:
            raise HTTPException(404, f"Reserva {reserva_id} não encontrada")
        produtos[reserva.sku].disponivel += reserva.quantidade
        return Response(status_code=204)

    return app


app = create_app()
