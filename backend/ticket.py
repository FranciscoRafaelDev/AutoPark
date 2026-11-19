import os
import random
import subprocess
from datetime import datetime
from pathlib import Path
from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PASTA_RAIZ = Path(__file__).resolve().parent
PASTA_TICKETS = PASTA_RAIZ / "tickets_pdf"
PASTA_TICKETS.mkdir(exist_ok=True)
MODO_IMPRESSAO = os.getenv("MODO_IMPRESSAO", "simulado")


def gerar_numero_ticket_unico() -> str:
    agora = datetime.now().strftime("%Y%m%d%H%M%S")
    aleatorio = str(random.randint(10, 99))
    return f"{agora}{aleatorio}"


def emitir_ticket(
    placa: str = "NÃO INFORMADA",
    numero_ticket: str | None = None,
    nome_estacionamento: str = "AUTO PARK ESTACIONAMENTO",
    nome_arquivo_logo: str = "logo.png",
    arquivo_saida: str | Path | None = None,
) -> dict:
    if not numero_ticket:
        numero_ticket = gerar_numero_ticket_unico()

    if not arquivo_saida:
        arquivo_saida = PASTA_TICKETS / f"ticket_{numero_ticket}.pdf"
    arquivo_saida = Path(arquivo_saida)

    caminho_logo = PASTA_RAIZ / nome_arquivo_logo
    tem_logo = caminho_logo.exists()

    largura = 80 * mm
    altura = 150 * mm if tem_logo else 130 * mm
    c = canvas.Canvas(str(arquivo_saida), pagesize=(largura, altura))
    topo_atual = altura - 4 * mm

    if tem_logo:
        largura_logo = 68 * mm
        altura_logo = 23 * mm
        posicao_x_logo = (largura - largura_logo) / 2
        posicao_y_logo = topo_atual - altura_logo
        c.drawImage(
            str(caminho_logo),
            posicao_x_logo,
            posicao_y_logo,
            width=largura_logo,
            height=altura_logo,
            preserveAspectRatio=True,
            mask="auto",
        )
        topo_atual = posicao_y_logo - 3 * mm
    else:
        topo_atual -= 6 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(largura / 2, topo_atual, nome_estacionamento)

    c.setFont("Helvetica", 8)
    c.drawCentredString(largura / 2, topo_atual - 4.5 * mm, "CNPJ: 00.000.000/0001-00")

    c.setDash(2, 2)
    c.line(5 * mm, topo_atual - 8 * mm, largura - 5 * mm, topo_atual - 8 * mm)
    c.setDash([])

    pos_dados = topo_atual - 15 * mm
    data_hora_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    c.setFont("Helvetica-Bold", 9)
    c.drawString(6 * mm, pos_dados, "ENTRADA:")
    c.setFont("Helvetica", 9)
    c.drawString(25 * mm, pos_dados, data_hora_atual)

    c.setFont("Helvetica-Bold", 9)
    c.drawString(6 * mm, pos_dados - 6 * mm, "PLACA:")
    c.setFont("Helvetica", 9)
    placa_formatada = placa.strip().upper()
    c.drawString(25 * mm, pos_dados - 6 * mm, placa_formatada)

    c.setDash(2, 2)
    c.line(5 * mm, pos_dados - 11 * mm, largura - 5 * mm, pos_dados - 11 * mm)
    c.setDash([])

    largura_barra = 0.28 * mm
    altura_barra = 18 * mm
    barcode = code128.Code128(
        numero_ticket,
        barWidth=largura_barra,
        barHeight=altura_barra,
        humanReadable=False,
    )
    barcode_x = (largura - barcode.width) / 2
    barcode_y = pos_dados - 34 * mm
    barcode.drawOn(c, barcode_x, barcode_y)

    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(largura / 2, barcode_y - 5 * mm, numero_ticket)

    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(largura / 2, barcode_y - 12 * mm, "APRESENTE NO TOTEM/GUICHÊ PARA PAGAR")

    c.setFont("Helvetica", 6.5)
    c.drawCentredString(largura / 2, barcode_y - 17 * mm, "Tolerância após pagamento: 15 minutos")
    c.drawCentredString(largura / 2, barcode_y - 21 * mm, "Não deixe este ticket visível no interior do veículo")

    c.save()
    impresso = imprimir_ticket(arquivo_saida)
    return {
        "ticket_id": numero_ticket,
        "arquivo_pdf": str(arquivo_saida),
        "impresso": impresso,
    }


def imprimir_ticket(caminho_pdf: str | Path) -> bool:
    caminho_pdf = Path(caminho_pdf)
    if not caminho_pdf.exists():
        raise FileNotFoundError(f"Ticket não encontrado: {caminho_pdf}")
    if MODO_IMPRESSAO == "simulado":
        return True
    if MODO_IMPRESSAO == "real":
        resultado = subprocess.run(
            ["lp", str(caminho_pdf)], capture_output=True, text=True, check=False
        )
        return resultado.returncode == 0
    raise ValueError(f"Modo de impressão inválido: {MODO_IMPRESSAO}")
