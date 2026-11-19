import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from db import (
    buscar_ticket,
    cadastrar_entrada,
    inicializar_banco,
    listar_estacionados,
    listar_pagamentos,
    listar_tickets,
    listar_vagas,
    registrar_saida,
    usar_supabase,
)
from ticket import PASTA_TICKETS, emitir_ticket, gerar_numero_ticket_unico
from camera import (
    iniciar_camera_background,
    obter_status_camera,
    parar_camera_background,
    processar_placa_detectada,
)

inicializar_banco()

app = FastAPI(
    title="AutoPark API",
    description="API REST para gestão de estacionamento, câmera OCR, emissão de tickets térmicos e integração com Supabase.",
    version="2.1.0",
)

origens_permitidas = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origens_permitidas,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EntradaPayload(BaseModel):
    placa: str = Field(..., min_length=7, max_length=8, examples=["ABC1D23"])
    vaga_codigo: str | None = Field(default=None, examples=["A-01"])
    responsavel_nome: str | None = Field(default=None, examples=["Cliente Avulso"])


class SaidaPayload(BaseModel):
    ticket_id: str = Field(..., examples=["2026111214000012"])
    metodo_pagamento: str = Field(default="PIX", examples=["PIX", "CARTAO", "DINHEIRO"])
    valor_pago: float | None = Field(default=None)


class CameraDeteccaoPayload(BaseModel):
    placa: str = Field(..., min_length=7, max_length=8, examples=["BRA2E19"])


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "banco": "supabase" if usar_supabase() else "sqlite_local",
        "camera": obter_status_camera(),
    }


@app.get("/api/resumo")
def obter_resumo():
    vagas = listar_vagas()
    ativos = listar_estacionados()
    tickets = listar_tickets(limite=200)
    pagamentos = listar_pagamentos(limite=200)
    faturamento_total = round(sum(float(p["valor"]) for p in pagamentos), 2)
    saidas_hoje = sum(1 for t in tickets if t.get("status") == "FINALIZADO")

    return {
        "capacidade": len(vagas) or 12,
        "estacionados_agora": len(ativos),
        "entradas_hoje": len(tickets),
        "saidas_hoje": saidas_hoje,
        "faturamento_hoje": faturamento_total,
        "banco_ativo": "Supabase (PostgreSQL)" if usar_supabase() else "SQLite Local (Fallback)",
        "camera": obter_status_camera(),
    }


@app.get("/api/camera/status")
def get_camera_status():
    return obter_status_camera()


@app.post("/api/camera/iniciar")
def post_camera_iniciar():
    return iniciar_camera_background()


@app.post("/api/camera/parar")
def post_camera_parar():
    return parar_camera_background()


@app.post("/api/camera/simular-deteccao", status_code=201)
def post_camera_simular(payload: CameraDeteccaoPayload):
    try:
        resultado = processar_placa_detectada(payload.placa)
        return {
            **resultado,
            "pdf_url": f"/api/tickets/{resultado['ticket_id']}/pdf",
            "camera": obter_status_camera(),
        }
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@app.get("/api/vagas")
def get_vagas():
    return listar_vagas()


@app.get("/api/estacionamento/ativos")
def get_ativos():
    return listar_estacionados()


@app.post("/api/estacionamento/entrada", status_code=201)
def post_entrada(payload: EntradaPayload):
    try:
        numero_ticket = gerar_numero_ticket_unico()
        sessao = cadastrar_entrada(
            ticket_id=numero_ticket,
            placa=payload.placa,
            vaga_codigo=payload.vaga_codigo,
            responsavel_nome=payload.responsavel_nome,
        )
        pdf_info = emitir_ticket(placa=sessao["placa"], numero_ticket=numero_ticket)
        return {
            **sessao,
            "pdf_url": f"/api/tickets/{numero_ticket}/pdf",
            "impresso": pdf_info["impresso"],
        }
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    except RuntimeError as erro:
        raise HTTPException(status_code=502, detail=str(erro)) from erro


@app.post("/api/estacionamento/saida")
def post_saida(payload: SaidaPayload):
    try:
        return registrar_saida(
            ticket_id=payload.ticket_id,
            metodo_pagamento=payload.metodo_pagamento,
            valor_pago=payload.valor_pago,
        )
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@app.get("/api/tickets")
def get_tickets():
    return listar_tickets()


@app.get("/api/tickets/{ticket_id}/pdf")
def get_ticket_pdf(ticket_id: str):
    caminho = PASTA_TICKETS / f"ticket_{ticket_id}.pdf"
    if not caminho.exists():
        sessao = buscar_ticket(ticket_id)
        if not sessao:
            raise HTTPException(status_code=404, detail="Ticket não encontrado.")
        emitir_ticket(placa=sessao["placa"], numero_ticket=ticket_id, arquivo_saida=caminho)
    return FileResponse(caminho, media_type="application/pdf", filename=f"ticket_{ticket_id}.pdf")


@app.get("/api/pagamentos")
def get_pagamentos():
    return listar_pagamentos()
