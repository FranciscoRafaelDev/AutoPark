import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error
import json

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

PADRAO_PLACA_BR = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
ARQUIVO_SQLITE_FALLBACK = Path(__file__).resolve().parent / "autopark.db"
VALOR_HORA_BASE = float(os.getenv("VALOR_HORA_BASE", "10.0"))


def validar_placa(placa: str) -> str:
    limpa = re.sub(r"[^A-Z0-9]", "", (placa or "").upper())
    if not PADRAO_PLACA_BR.match(limpa):
        raise ValueError(f"Placa inválida '{placa}'. Use o padrão ABC1D23 ou ABC1234.")
    return limpa


def usar_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _req_supabase(metodo: str, caminho: str, payload: dict | list | None = None, prefer: str = "return=representation"):
    url = f"{SUPABASE_URL}/rest/v1/{caminho}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "application/json",
        "Prefer": prefer,
    }
    if not SUPABASE_SERVICE_ROLE_KEY.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"

    dados = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=dados, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            corpo = resp.read().decode("utf-8")
            return json.loads(corpo) if corpo else []
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Erro Supabase ({e.code}): {detalhe}") from e


def conectar_sqlite():
    con = sqlite3.connect(ARQUIVO_SQLITE_FALLBACK, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def inicializar_banco():
    if usar_supabase():
        return
    with conectar_sqlite() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS vagas (
                codigo TEXT PRIMARY KEY,
                setor TEXT NOT NULL,
                ocupada INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS veiculos (
                placa TEXT PRIMARY KEY,
                responsavel_nome TEXT,
                responsavel_telefone TEXT,
                criado_em TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessoes (
                ticket_id TEXT PRIMARY KEY,
                placa TEXT NOT NULL REFERENCES veiculos(placa),
                vaga_codigo TEXT REFERENCES vagas(codigo),
                entrada TEXT NOT NULL,
                saida TEXT,
                status TEXT NOT NULL DEFAULT 'ESTACIONADO'
                    CHECK (status IN ('ESTACIONADO', 'FINALIZADO', 'CANCELADO')),
                valor_total REAL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unica_sessao_aberta
                ON sessoes(placa) WHERE status = 'ESTACIONADO';
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL UNIQUE REFERENCES sessoes(ticket_id),
                metodo TEXT NOT NULL CHECK (metodo IN ('PIX', 'CARTAO', 'DINHEIRO')),
                valor REAL NOT NULL,
                pago_em TEXT NOT NULL
            );
        """)
        qtd = con.execute("SELECT COUNT(*) FROM vagas").fetchone()[0]
        if qtd == 0:
            vagas_iniciais = [
                ("A-01", "A", 0), ("A-02", "A", 0), ("A-03", "A", 0), ("A-04", "A", 0), ("A-05", "A", 0),
                ("B-01", "B", 0), ("B-02", "B", 0), ("B-03", "B", 0), ("B-04", "B", 0),
                ("C-01", "C", 0), ("C-02", "C", 0), ("C-03", "C", 0),
            ]
            con.executemany("INSERT INTO vagas (codigo, setor, ocupada) VALUES (?, ?, ?)", vagas_iniciais)


def calcular_tarifa_e_duracao(entrada_iso: str) -> tuple[float, str]:
    try:
        dt_entrada = datetime.fromisoformat(entrada_iso.replace("Z", "+00:00"))
    except ValueError:
        dt_entrada = datetime.now()
    agora = datetime.now(dt_entrada.tzinfo) if dt_entrada.tzinfo else datetime.now()
    segundos = max(0, int((agora - dt_entrada).total_seconds()))
    minutos_totais = max(1, segundos // 60)
    horas, mins = divmod(minutos_totais, 60)
    duracao_str = f"{horas}h {mins:02d}min" if horas else f"{mins}min"
    blocos_30m = max(1, (minutos_totais + 29) // 30)
    tarifa = round(8.0 + max(0, blocos_30m - 1) * (VALOR_HORA_BASE / 2), 2)
    return tarifa, duracao_str


def listar_vagas() -> list[dict]:
    if usar_supabase():
        return _req_supabase("GET", "vagas?select=*&order=codigo.asc")
    with conectar_sqlite() as con:
        rows = con.execute("SELECT codigo, setor, ocupada FROM vagas ORDER BY codigo").fetchall()
        return [{"codigo": r["codigo"], "setor": r["setor"], "ocupada": bool(r["ocupada"])} for r in rows]


def listar_estacionados() -> list[dict]:
    if usar_supabase():
        rows = _req_supabase("GET", "sessoes?status=eq.ESTACIONADO&select=*&order=entrada.desc")
    else:
        with conectar_sqlite() as con:
            rows = [dict(r) for r in con.execute(
                "SELECT * FROM sessoes WHERE status = 'ESTACIONADO' ORDER BY entrada DESC"
            ).fetchall()]
    resultado = []
    for r in rows:
        tarifa, duracao = calcular_tarifa_e_duracao(r["entrada"])
        resultado.append({
            "ticket_id": r["ticket_id"],
            "placa": r["placa"],
            "vaga_codigo": r.get("vaga_codigo") or "Pátio",
            "entrada": r["entrada"],
            "duracao": duracao,
            "valor_parcial": tarifa,
            "status": r["status"],
        })
    return resultado


def cadastrar_entrada(
    ticket_id: str,
    placa: str,
    vaga_codigo: str | None = None,
    responsavel_nome: str | None = None,
) -> dict:
    placa_limpa = validar_placa(placa)
    agora_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if usar_supabase():
        abertas = _req_supabase("GET", f"sessoes?placa=eq.{placa_limpa}&status=eq.ESTACIONADO&select=ticket_id")
        if abertas:
            raise ValueError(f"O veículo {placa_limpa} já possui sessão aberta (Ticket {abertas[0]['ticket_id']}).")

        _req_supabase(
            "POST",
            "veiculos?on_conflict=placa",
            {"placa": placa_limpa, "responsavel_nome": responsavel_nome},
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not vaga_codigo:
            livres = _req_supabase("GET", "vagas?ocupada=eq.false&select=codigo&order=codigo.asc&limit=1")
            vaga_codigo = livres[0]["codigo"] if livres else None

        if vaga_codigo:
            _req_supabase("PATCH", f"vagas?codigo=eq.{vaga_codigo}", {"ocupada": True})

        criado = _req_supabase(
            "POST",
            "sessoes",
            {
                "ticket_id": str(ticket_id),
                "placa": placa_limpa,
                "vaga_codigo": vaga_codigo,
                "entrada": agora_iso,
                "status": "ESTACIONADO",
            },
        )
        return criado[0]

    with conectar_sqlite() as con:
        existente = con.execute(
            "SELECT ticket_id FROM sessoes WHERE placa = ? AND status = 'ESTACIONADO'",
            (placa_limpa,),
        ).fetchone()
        if existente:
            raise ValueError(f"O veículo {placa_limpa} já está estacionado (Ticket {existente['ticket_id']}).")

        con.execute(
            "INSERT INTO veiculos (placa, responsavel_nome, criado_em) VALUES (?, ?, ?) "
            "ON CONFLICT(placa) DO UPDATE SET responsavel_nome = COALESCE(excluded.responsavel_nome, veiculos.responsavel_nome)",
            (placa_limpa, responsavel_nome, agora_iso),
        )

        if not vaga_codigo:
            livre = con.execute("SELECT codigo FROM vagas WHERE ocupada = 0 ORDER BY codigo LIMIT 1").fetchone()
            vaga_codigo = livre["codigo"] if livre else None

        if vaga_codigo:
            con.execute("UPDATE vagas SET ocupada = 1 WHERE codigo = ?", (vaga_codigo,))

        con.execute(
            "INSERT INTO sessoes (ticket_id, placa, vaga_codigo, entrada, status) VALUES (?, ?, ?, ?, 'ESTACIONADO')",
            (str(ticket_id), placa_limpa, vaga_codigo, agora_iso),
        )
    return buscar_ticket(ticket_id)


def buscar_ticket(ticket_id: str) -> dict | None:
    if usar_supabase():
        rows = _req_supabase("GET", f"sessoes?ticket_id=eq.{ticket_id}&select=*")
        return rows[0] if rows else None
    with conectar_sqlite() as con:
        row = con.execute("SELECT * FROM sessoes WHERE ticket_id = ?", (str(ticket_id),)).fetchone()
        return dict(row) if row else None


def registrar_saida(ticket_id: str, metodo_pagamento: str = "PIX", valor_pago: float | None = None) -> dict:
    metodo = metodo_pagamento.strip().upper()
    if metodo not in ("PIX", "CARTAO", "DINHEIRO"):
        raise ValueError("Método de pagamento deve ser PIX, CARTAO ou DINHEIRO.")

    sessao = buscar_ticket(ticket_id)
    if not sessao:
        raise LookupError(f"Ticket {ticket_id} não encontrado.")
    if sessao["status"] != "ESTACIONADO":
        raise ValueError(f"Ticket {ticket_id} já foi finalizado.")

    tarifa_calculada, _ = calcular_tarifa_e_duracao(sessao["entrada"])
    valor_final = float(valor_pago) if valor_pago is not None else tarifa_calculada
    agora_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if usar_supabase():
        _req_supabase(
            "POST",
            "pagamentos",
            {"ticket_id": str(ticket_id), "metodo": metodo, "valor": valor_final, "pago_em": agora_iso},
        )
        atualizado = _req_supabase(
            "PATCH",
            f"sessoes?ticket_id=eq.{ticket_id}",
            {"saida": agora_iso, "status": "FINALIZADO", "valor_total": valor_final},
        )
        if sessao.get("vaga_codigo"):
            _req_supabase("PATCH", f"vagas?codigo=eq.{sessao['vaga_codigo']}", {"ocupada": False})
        return atualizado[0]

    with conectar_sqlite() as con:
        con.execute(
            "INSERT INTO pagamentos (ticket_id, metodo, valor, pago_em) VALUES (?, ?, ?, ?)",
            (str(ticket_id), metodo, valor_final, agora_iso),
        )
        con.execute(
            "UPDATE sessoes SET saida = ?, status = 'FINALIZADO', valor_total = ? WHERE ticket_id = ?",
            (agora_iso, valor_final, str(ticket_id)),
        )
        if sessao.get("vaga_codigo"):
            con.execute("UPDATE vagas SET ocupada = 0 WHERE codigo = ?", (sessao["vaga_codigo"],))
    return buscar_ticket(ticket_id)


def listar_tickets(limite: int = 50) -> list[dict]:
    if usar_supabase():
        return _req_supabase("GET", f"sessoes?select=*&order=entrada.desc&limit={limite}")
    with conectar_sqlite() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM sessoes ORDER BY entrada DESC LIMIT ?", (limite,)
        ).fetchall()]


def listar_pagamentos(limite: int = 50) -> list[dict]:
    if usar_supabase():
        rows = _req_supabase("GET", f"pagamentos?select=*,sessoes(placa)&order=pago_em.desc&limit={limite}")
        return [
            {
                "ticket_id": r["ticket_id"],
                "placa": (r.get("sessoes") or {}).get("placa", "---"),
                "metodo": r["metodo"],
                "valor": float(r["valor"]),
                "pago_em": r["pago_em"],
            }
            for r in rows
        ]
    with conectar_sqlite() as con:
        rows = con.execute("""
            SELECT p.ticket_id, s.placa, p.metodo, p.valor, p.pago_em
            FROM pagamentos p
            JOIN sessoes s ON s.ticket_id = p.ticket_id
            ORDER BY p.pago_em DESC
            LIMIT ?
        """, (limite,)).fetchall()
        return [dict(r) for r in rows]
