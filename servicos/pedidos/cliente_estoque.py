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
