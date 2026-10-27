import random
from datetime import datetime
from pathlib import Path
from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import subprocess

MODO_IMPRESSAO = "simulado"

# ==============================================================================
# >>> CONFIGURAÇÃO DA PASTA RAIZ (ONDE O SISTEMA BUSCA A LOGO E SALVA O PDF) <<<
# ==============================================================================
# Opção A (Automática): Pega a mesma pasta onde este arquivo (main.py) está salvo:
PASTA_RAIZ = Path(__file__).resolve().parent

# Opção B (Manual): Caso queira fixar outra pasta raiz manualmente, comente a
# linha acima com '#' e descomente a linha abaixo colocando o caminho desejado:
# PASTA_RAIZ = Path("/home/chico/Documentos/Gerenciamento Estacionamento/ticket")
# ==============================================================================


def gerar_numero_ticket_unico() -> str:
    """Gera um número único baseado em data/hora + sufixo aleatório."""
    agora = datetime.now().strftime("%Y%m%d%H%M%S")
    aleatorio = str(random.randint(10, 99))
    return f"{agora}{aleatorio}"


def emitir_ticket(
    placa: str = "NÃO INFORMADA",
    nome_estacionamento: str = "AUTO PARK ESTACIONAMENTO",
    nome_arquivo_logo: str = "logo.png",
    arquivo_saida: str | Path | None = None,
):
    numero_ticket = gerar_numero_ticket_unico()

    # Define onde o PDF será salvo usando a PASTA_RAIZ
    if not arquivo_saida:
        arquivo_saida = PASTA_RAIZ / f"ticket_{numero_ticket}.pdf"

    # Monta o caminho completo da logo a partir da PASTA_RAIZ
    caminho_logo = PASTA_RAIZ / nome_arquivo_logo
    tem_logo = caminho_logo.exists()

    if not tem_logo:
        print(f"⚠️ Aviso: Logo não encontrada no caminho: {caminho_logo}")

    largura = 80 * mm
    # Aumentamos a altura total do ticket para 150mm para caber a logo grande com folga
    altura = 150 * mm if tem_logo else 130 * mm

    c = canvas.Canvas(str(arquivo_saida), pagesize=(largura, altura))

    topo_atual = altura - 4 * mm

    # --- LOGO ---
    if tem_logo:
        # ======================================================================
        # >>> AJUSTE DO TAMANHO DA LOGO (PROPORÇÃO LARGA DA AUTOPARK) <<<
        # ======================================================================
        largura_logo = 68 * mm  # Ocupa quase toda a largura de 80mm do ticket
        altura_logo = 23 * mm  # Altura proporcional ao formato 3:1 da sua imagem

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

    # --- CABEÇALHO ---
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(largura / 2, topo_atual, nome_estacionamento)

    c.setFont("Helvetica", 8)
    c.drawCentredString(largura / 2, topo_atual - 4.5 * mm, "CNPJ: 00.000.000/0001-00")

    c.setDash(2, 2)
    c.line(5 * mm, topo_atual - 8 * mm, largura - 5 * mm, topo_atual - 8 * mm)
    c.setDash([])

    # --- ENTRADA E PLACA ---
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

    # --- CÓDIGO DE BARRAS ---
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

    # --- NÚMERO LEGÍVEL ---
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(largura / 2, barcode_y - 5 * mm, numero_ticket)

    # --- RODAPÉ ---
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(
        largura / 2, barcode_y - 12 * mm, "APRESENTE NO TOTEM/GUICHÊ PARA PAGAR"
    )

    c.setFont("Helvetica", 6.5)
    c.drawCentredString(
        largura / 2, barcode_y - 17 * mm, "Tolerância após pagamento: 15 minutos"
    )
    c.drawCentredString(
        largura / 2,
        barcode_y - 21 * mm,
        "Não deixe este ticket visível no interior do veículo",
    )

    c.save()

    print(f"\n✅ Ticket gerado com sucesso em: {arquivo_saida}")

    sucesso = imprimir_ticket(arquivo_saida)

    if sucesso:
        print("Fluxo de emissão concluído.")
        return numero_ticket
    else:
        print("Ticket Gerado, Mas Houve Falha na Impressão")
        return None

    return numero_ticket
    

def imprimir_ticket(caminho_pdf):
    caminho_pdf = Path(caminho_pdf)
    if not caminho_pdf.exists():
        raise FileNotFoundError(f"Ticket não encontrado: {caminho_pdf}")
    if MODO_IMPRESSAO == "simulado":
        print("\n[IMPRESSÃO SIMULADA]")
        print(f"Arquivo: {caminho_pdf}")
        print("Status: enviado para impressão")
        return True
    if MODO_IMPRESSAO == "real":
        resultado = subprocess.run(
            ["lp", str(caminho_pdf)], capture_output=True, text=True, check=False
        )
        if resultado.returncode != 0:
            print("Erro ao enviar para impressão:")
            print(resultado.stderr)
            return False

        print("Trabalho enviado para a fila de impressão.")
        print(resultado.stdout)
        return True

    raise ValueError(f"Modo de impressão inválido: {MODO_IMPRESSAO}")


if __name__ == "__main__":
    entrada_placa = input("Digite a placa do veículo (ou Enter para avulso): ")
    if not entrada_placa.strip():
        entrada_placa = "AVULSO"

    # ==========================================================================
    # >>> NOME DO ARQUIVO DA LOGO <<<
    # ==========================================================================
    emitir_ticket(
        placa=entrada_placa,
        nome_arquivo_logo="logo.png",  # Nome da imagem que está dentro da PASTA_RAIZ
    )
