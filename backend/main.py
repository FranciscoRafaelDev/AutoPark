import csv
import io
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from auth import (
    COOKIE_NAME,
    atualizar_perfil,
    autenticar_supabase,
    encerrar_sessao_supabase,
    exigir_admin,
    exigir_permissao,
    listar_perfis,
    obter_usuario_atual,
)
from camera import (
    iniciar_camera_background,
    obter_status_camera,
    parar_camera_background,
    processar_placa_detectada,
)
from db import (
    _req_supabase,
    atualizar_config_tarifa,
    buscar_ticket,
    cadastrar_entrada,
    inicializar_banco,
    listar_estacionados,
    listar_pagamentos,
    listar_tickets,
    listar_vagas,
    obter_config_tarifa,
    registrar_saida,
    usar_supabase,
)
from ticket import PASTA_TICKETS, emitir_ticket, gerar_numero_ticket_unico

inicializar_banco()

EM_PRODUCAO = os.getenv("APP_ENV", "development").lower() == "production"

app = FastAPI(
    title="AutoPark API",
    version="2.3.0",
)

origens_permitidas = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origens_permitidas,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginPayload(BaseModel):
    email: str
    password: str


class EntradaPayload(BaseModel):
    placa: str = Field(..., min_length=7, max_length=8)
    marca: str | None = None
    modelo: str | None = None
    vaga_codigo: str | None = None
    responsavel_nome: str | None = None


class SaidaPayload(BaseModel):
    ticket_id: str
    metodo_pagamento: str = "PIX"
    valor_pago: float | None = None


class CameraDeteccaoPayload(BaseModel):
    placa: str = Field(..., min_length=7, max_length=8)


class AtualizarPerfilPayload(BaseModel):
    papel: str
    ativo: bool
    permissoes: dict[str, bool]


class TarifaPayload(BaseModel):
    modo_cobranca: str
    valor_hora: float = Field(..., gt=0)
    valor_fixo: float = Field(..., gt=0)


@app.post("/api/auth/login")
def post_login(payload: LoginPayload, response: Response):
    resultado = autenticar_supabase(payload.email, payload.password)
    response.set_cookie(
        key=COOKIE_NAME,
        value=resultado["access_token"],
        httponly=True,
        samesite="none" if EM_PRODUCAO else "lax",
        secure=EM_PRODUCAO,
        max_age=60 * 60 * 8,
    )
    return {"usuario": resultado["usuario"]}


@app.post("/api/auth/logout")
def post_logout(response: Response, autopark_session: str | None = Cookie(default=None)):
    encerrar_sessao_supabase(autopark_session)
    response.delete_cookie(
        key=COOKIE_NAME,
        samesite="none" if EM_PRODUCAO else "lax",
        secure=EM_PRODUCAO,
    )
    return {"ok": True}


@app.get("/api/auth/me")
def get_me(usuario: dict = Depends(obter_usuario_atual)):
    return {"usuario": usuario}


@app.get("/api/admin/usuarios")
def get_admin_usuarios(_: dict = Depends(exigir_admin)):
    return listar_perfis()


@app.patch("/api/admin/usuarios/{user_id}")
def patch_admin_usuario(user_id: str, payload: AtualizarPerfilPayload, _: dict = Depends(exigir_admin)):
    return atualizar_perfil(user_id, payload.papel, payload.ativo, payload.permissoes)


@app.get("/api/configuracoes/tarifa")
def get_tarifa(_: dict = Depends(obter_usuario_atual)):
    return obter_config_tarifa()


@app.put("/api/configuracoes/tarifa")
def put_tarifa(payload: TarifaPayload, _: dict = Depends(exigir_admin)):
    try:
        return atualizar_config_tarifa(payload.modo_cobranca, payload.valor_hora, payload.valor_fixo)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@app.get("/api/relatorios/exportar.csv")
def exportar_relatorio_csv(_: dict = Depends(exigir_permissao("reports"))):
    pagamentos = listar_pagamentos(limite=1000)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Ticket", "Placa", "Metodo", "Valor", "Pago em"])
    for p in pagamentos:
        writer.writerow([p.get("ticket_id"), p.get("placa"), p.get("metodo"), p.get("valor"), p.get("pago_em")])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=relatorio_autopark.csv"},
    )


@app.get("/api/relatorios/exportar.pdf")
def exportar_relatorio_pdf(_: dict = Depends(exigir_permissao("reports"))):
    pagamentos = listar_pagamentos(limite=1000)
    total = sum(float(p.get("valor", 0)) for p in pagamentos)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, 800, "AutoPark - Relatorio Financeiro")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, 780, f"Total de pagamentos: {len(pagamentos)} | Faturamento total: R$ {total:.2f}")

    y = 750
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(40, y, "Ticket")
    pdf.drawString(130, y, "Placa")
    pdf.drawString(210, y, "Metodo")
    pdf.drawString(290, y, "Valor (R$)")
    pdf.drawString(370, y, "Horario")
    y -= 18
    pdf.setFont("Helvetica", 9)

    for p in pagamentos:
        if y < 50:
            pdf.showPage()
            y = 800
            pdf.setFont("Helvetica", 9)
        pdf.drawString(40, y, str(p.get("ticket_id", "")))
        pdf.drawString(130, y, str(p.get("placa", "")))
        pdf.drawString(210, y, str(p.get("metodo", "")))
        pdf.drawString(290, y, f"{float(p.get('valor', 0)):.2f}")
        pdf.drawString(370, y, str(p.get("pago_em", ""))[:19])
        y -= 16

    pdf.save()
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=relatorio_autopark.pdf"},
    )


@app.delete("/api/lgpd/anonimizar/{placa}")
def anonimizar_dados_cliente(placa: str, _: dict = Depends(exigir_admin)):
    placa_limpa = placa.strip().upper()
    if usar_supabase():
        _req_supabase(
            "PATCH",
            f"sessoes?placa=eq.{placa_limpa}",
            {"responsavel_nome": "ANONIMIZADO (LGPD)"},
        )
    return {"ok": True, "placa": placa_limpa}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "banco": "supabase" if usar_supabase() else "sqlite_local",
        "camera": obter_status_camera(),
    }


@app.get("/api/resumo")
def obter_resumo(usuario: dict = Depends(exigir_permissao("overview"))):
    vagas = listar_vagas()
    ativos = listar_estacionados()
    tickets = listar_tickets(limite=200)
    pagamentos = listar_pagamentos(limite=200)
    pode_ver_financeiro = usuario.get("papel") == "admin" or bool((usuario.get("permissoes") or {}).get("reports"))
    faturamento_total = round(sum(float(p["valor"]) for p in pagamentos), 2) if pode_ver_financeiro else None
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
def get_camera_status(_: dict = Depends(exigir_permissao("camera"))):
    return obter_status_camera()


@app.post("/api/camera/iniciar")
def post_camera_iniciar(_: dict = Depends(exigir_permissao("camera"))):
    return iniciar_camera_background()


@app.post("/api/camera/parar")
def post_camera_parar(_: dict = Depends(exigir_permissao("camera"))):
    return parar_camera_background()


@app.post("/api/camera/simular-deteccao", status_code=201)
def post_camera_simular(payload: CameraDeteccaoPayload, _: dict = Depends(exigir_permissao("camera"))):
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
def get_vagas(_: dict = Depends(exigir_permissao("spots"))):
    return listar_vagas()


@app.get("/api/estacionamento/ativos")
def get_ativos(_: dict = Depends(exigir_permissao("vehicles"))):
    return listar_estacionados()


@app.post("/api/estacionamento/entrada", status_code=201)
def post_entrada(payload: EntradaPayload, _: dict = Depends(exigir_permissao("vehicles"))):
    try:
        numero_ticket = gerar_numero_ticket_unico()
        sessao = cadastrar_entrada(
            ticket_id=numero_ticket,
            placa=payload.placa,
            marca=payload.marca,
            modelo=payload.modelo,
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
def post_saida(payload: SaidaPayload, _: dict = Depends(exigir_permissao("vehicles"))):
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
def get_tickets(_: dict = Depends(exigir_permissao("tickets"))):
    return listar_tickets()


@app.get("/api/tickets/{ticket_id}/pdf")
def get_ticket_pdf(ticket_id: str, _: dict = Depends(exigir_permissao("tickets"))):
    caminho = PASTA_TICKETS / f"ticket_{ticket_id}.pdf"
    if not caminho.exists():
        sessao = buscar_ticket(ticket_id)
        if not sessao:
            raise HTTPException(status_code=404, detail="Ticket não encontrado.")
        emitir_ticket(placa=sessao["placa"], numero_ticket=ticket_id, arquivo_saida=caminho)
    return FileResponse(caminho, media_type="application/pdf", filename=f"ticket_{ticket_id}.pdf")


@app.get("/api/pagamentos")
def get_pagamentos(_: dict = Depends(exigir_permissao("payments"))):
    return listar_pagamentos()
