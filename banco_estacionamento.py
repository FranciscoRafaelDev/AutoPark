import sqlite3
from datetime import datetime
from pathlib import Path

# Banco de dados local da AutoPark
ARQUIVO_BANCO = Path(__file__).resolve().parent / "autopark.db"


def conectar():
    """Abre uma conexão com o banco SQLite."""
    conexao = sqlite3.connect(ARQUIVO_BANCO, timeout=10)
    conexao.row_factory = sqlite3.Row
    return conexao


def inicializar_banco():
    """Cria a tabela caso ela ainda não exista."""
    with conectar() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS estacionamentos (
                ticket_id TEXT PRIMARY KEY,
                placa TEXT NOT NULL,
                entrada TEXT NOT NULL,
                saida TEXT,
                status TEXT NOT NULL DEFAULT 'ESTACIONADO'
                    CHECK (status IN ('ESTACIONADO', 'SAIU')),
                valor_total REAL
            )
        """)


def cadastrar_entrada(
    ticket_id: str,
    placa: str,
    data_hora_entrada: str | None = None
) -> dict:
    """Registra a entrada de um veículo."""
    ticket_id = str(ticket_id)
    placa = placa.strip().upper()

    if not data_hora_entrada:
        data_hora_entrada = datetime.now().isoformat(
            timespec="seconds"
        )

    with conectar() as conexao:
        conexao.execute("""
            INSERT INTO estacionamentos
                (ticket_id, placa, entrada, status)
            VALUES (?, ?, ?, 'ESTACIONADO')
        """, (ticket_id, placa, data_hora_entrada))

    return buscar_ticket(ticket_id)


def buscar_ticket(ticket_id: str) -> dict | None:
    """Busca um veículo pelo número do ticket."""
    with conectar() as conexao:
        registro = conexao.execute("""
            SELECT *
            FROM estacionamentos
            WHERE ticket_id = ?
        """, (str(ticket_id),)).fetchone()

    return dict(registro) if registro else None


def registrar_pagamento(
    ticket_id: str,
    valor_total: float
) -> bool:
    """
    Registra o pagamento e a saída do veículo.

    Chame esta função somente depois de confirmar
    que o pagamento foi realizado.
    """
    horario_saida = datetime.now().isoformat(
        timespec="seconds"
    )

    with conectar() as conexao:
        cursor = conexao.execute("""
            UPDATE estacionamentos
            SET saida = ?,
                status = 'SAIU',
                valor_total = ?
            WHERE ticket_id = ?
              AND status = 'ESTACIONADO'
        """, (
            horario_saida,
            valor_total,
            str(ticket_id)
        ))

        return cursor.rowcount == 1


def listar_estacionados() -> list[dict]:
    """Lista todos os veículos que ainda estão estacionados."""
    with conectar() as conexao:
        registros = conexao.execute("""
            SELECT *
            FROM estacionamentos
            WHERE status = 'ESTACIONADO'
            ORDER BY entrada
        """).fetchall()

    return [dict(registro) for registro in registros]


# Inicializa o banco ao importar este módulo.
inicializar_banco()
