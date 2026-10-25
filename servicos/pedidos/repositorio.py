"""Persistência dos pedidos em SQLite."""

import sqlite3


class RepositorioPedidos:
    def __init__(self, caminho: str = ":memory:"):
        self.conn = sqlite3.connect(caminho, check_same_thread=False)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pedidos (
                id TEXT PRIMARY KEY,
                cliente TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS itens_pedido (
                pedido_id TEXT NOT NULL REFERENCES pedidos(id),
                sku TEXT NOT NULL,
                quantidade INTEGER NOT NULL,
                reserva_id TEXT NOT NULL
            );
            """
        )

    def salvar(self, pedido: dict) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO pedidos (id, cliente, status) VALUES (?, ?, ?)",
                (pedido["id"], pedido["cliente"], pedido["status"]),
            )
            self.conn.executemany(
                "INSERT INTO itens_pedido (pedido_id, sku, quantidade, reserva_id) VALUES (?, ?, ?, ?)",
                [(pedido["id"], i["sku"], i["quantidade"], i["reserva_id"]) for i in pedido["itens"]],
            )

    def buscar(self, pedido_id: str) -> dict | None:
        linha = self.conn.execute(
            "SELECT id, cliente, status FROM pedidos WHERE id = ?", (pedido_id,)
        ).fetchone()
        if linha is None:
            return None
        itens = self.conn.execute(
            "SELECT sku, quantidade, reserva_id FROM itens_pedido WHERE pedido_id = ?", (pedido_id,)
        ).fetchall()
        return {
            "id": linha[0],
            "cliente": linha[1],
            "status": linha[2],
            "itens": [{"sku": s, "quantidade": q, "reserva_id": r} for s, q, r in itens],
        }

    def contar(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]
