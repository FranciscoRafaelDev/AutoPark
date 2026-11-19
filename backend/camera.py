import os
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"

import re
import threading
import time
from datetime import datetime
import cv2
from db import cadastrar_entrada, validar_placa
from ticket import emitir_ticket, gerar_numero_ticket_unico

RTSP_URL = os.getenv("RTSP_URL", "rtsp://192.168.0.2:554/onvif1")
PADRAO_PLACA_BR = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
CONFIANCA_MINIMA = 0.5
COOLDOWN_SEGUNDOS = 30

ESTADO_CAMERA = {
    "ativa": False,
    "conectada": False,
    "rtsp_url": RTSP_URL,
    "ultima_placa": None,
    "ultimo_horario": None,
    "ultimo_ticket": None,
    "mensagem": "Monitoramento OCR parado",
}
_thread_monitor: threading.Thread | None = None
_parar_evento = threading.Event()


class CameraStream:
    def __init__(self, url: str):
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        self.sucesso, self.frame = self.cap.read()
        self.rodando = self.cap.isOpened()
        self.lock = threading.Lock()
        if self.rodando:
            threading.Thread(target=self._atualizar, daemon=True).start()

    def _atualizar(self):
        while self.rodando:
            sucesso, frame = self.cap.read()
            with self.lock:
                self.sucesso, self.frame = sucesso, frame

    def ler(self):
        with self.lock:
            return self.sucesso, (self.frame.copy() if self.frame is not None else None)

    def liberar(self):
        self.rodando = False
        self.cap.release()


MAPA_PARA_NUMERO = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8"})
MAPA_PARA_LETRA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B"})


def normalizar_e_validar(texto: str) -> str | None:
    limpo = re.sub(r"[^A-Z0-9]", "", (texto or "").upper())
    if limpo.startswith("BR") and len(limpo) > 7:
        limpo = limpo[2:]

    if len(limpo) < 7:
        return None

    for i in range(len(limpo) - 6):
        trecho = list(limpo[i : i + 7])
        for pos in (0, 1, 2):
            trecho[pos] = trecho[pos].translate(MAPA_PARA_LETRA)
        for pos in (3, 5, 6):
            trecho[pos] = trecho[pos].translate(MAPA_PARA_NUMERO)
        candidata = "".join(trecho)
        if PADRAO_PLACA_BR.match(candidata):
            return candidata
    return None


def detectar_placas_no_frame(frame, leitor_ocr, confianca_min: float = 0.25) -> list[dict]:
    cinza = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resultados_ocr = leitor_ocr.readtext(
        cinza,
        allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    )
    placas_encontradas = []

    for bbox, texto_bruto, confianca in resultados_ocr:
        if confianca < confianca_min:
            continue
        placa = normalizar_e_validar(texto_bruto)
        if placa:
            bbox_original = [[int(x), int(y)] for x, y in bbox]
            placas_encontradas.append({
                "placa": placa,
                "confianca": float(confianca),
                "bbox": bbox_original,
            })
    return placas_encontradas

def processar_placa_detectada(placa: str) -> dict:
    placa_limpa = validar_placa(placa)
    numero_ticket = gerar_numero_ticket_unico()
    sessao = cadastrar_entrada(ticket_id=numero_ticket, placa=placa_limpa)
    dados_pdf = emitir_ticket(placa=placa_limpa, numero_ticket=numero_ticket)
    agora_str = datetime.now().strftime("%H:%M:%S")
    ESTADO_CAMERA.update({
        "ultima_placa": placa_limpa,
        "ultimo_horario": agora_str,
        "ultimo_ticket": numero_ticket,
        "mensagem": f"Placa {placa_limpa} registrada às {agora_str}",
    })
    return {**sessao, **dados_pdf}


def obter_status_camera() -> dict:
    return dict(ESTADO_CAMERA)


def _loop_background():
    try:
        import easyocr
    except ImportError:
        ESTADO_CAMERA.update({
            "ativa": False,
            "conectada": False,
            "mensagem": "EasyOCR não instalado no ambiente virtual",
        })
        return

    ESTADO_CAMERA["mensagem"] = "Carregando modelo EasyOCR e conectando RTSP..."
    leitor = easyocr.Reader(["pt", "en"], gpu=False)
    camera = CameraStream(RTSP_URL)

    if not camera.rodando:
        ESTADO_CAMERA.update({
            "ativa": False,
            "conectada": False,
            "mensagem": f"Sem sinal RTSP ({RTSP_URL})",
        })
        return

    ESTADO_CAMERA.update({
        "ativa": True,
        "conectada": True,
        "mensagem": "Câmera RTSP conectada · Lendo placas",
    })

    ultimas_vistas: dict[str, float] = {}
    ultimo_ocr = 0.0

    try:
        while not _parar_evento.is_set():
            sucesso, frame = camera.ler()
            if not sucesso or frame is None:
                time.sleep(0.05)
                continue

            agora = time.time()
            if agora - ultimo_ocr >= 1.0:
                ultimo_ocr = agora
                deteccoes = detectar_placas_no_frame(frame, leitor)
                for item in deteccoes:
                    placa = item["placa"]
                    if agora - ultimas_vistas.get(placa, 0) > COOLDOWN_SEGUNDOS:
                        ultimas_vistas[placa] = agora
                        try:
                            processar_placa_detectada(placa)
                        except ValueError:
                            pass
    finally:
        camera.liberar()
        ESTADO_CAMERA.update({
            "ativa": False,
            "conectada": False,
            "mensagem": "Monitoramento OCR parado",
        })


def iniciar_camera_background() -> dict:
    global _thread_monitor
    if _thread_monitor and _thread_monitor.is_alive():
        return obter_status_camera()
    _parar_evento.clear()
    ESTADO_CAMERA["ativa"] = True
    ESTADO_CAMERA["mensagem"] = "Iniciando thread da câmera..."
    _thread_monitor = threading.Thread(target=_loop_background, daemon=True)
    _thread_monitor.start()
    return obter_status_camera()


def parar_camera_background() -> dict:
    _parar_evento.set()
    ESTADO_CAMERA["ativa"] = False
    ESTADO_CAMERA["conectada"] = False
    ESTADO_CAMERA["mensagem"] = "Monitoramento OCR parado"
    return obter_status_camera()


def iniciar_monitoramento():
    import easyocr

    leitor = easyocr.Reader(["pt", "en"], gpu=False)
    camera = CameraStream(RTSP_URL)

    if not camera.rodando:
        raise SystemExit("Erro: não foi possível conectar à câmera RTSP.")

    ultimas_vistas: dict[str, float] = {}
    ultimas_deteccoes: list[dict] = []
    ultimo_ocr = 0.0

    try:
        while True:
            sucesso, frame = camera.ler()
            if not sucesso or frame is None:
                time.sleep(0.05)
                continue

            agora = time.time()
            if agora - ultimo_ocr >= 1.0:
                ultimo_ocr = agora
                ultimas_deteccoes = detectar_placas_no_frame(frame, leitor)

                for item in ultimas_deteccoes:
                    placa = item["placa"]
                    if agora - ultimas_vistas.get(placa, 0) > COOLDOWN_SEGUNDOS:
                        ultimas_vistas[placa] = agora
                        try:
                            processar_placa_detectada(placa)
                        except ValueError:
                            pass

            for item in ultimas_deteccoes:
                pts = item["bbox"]
                p1, p2 = tuple(pts[0]), tuple(pts[2])
                cv2.rectangle(frame, p1, p2, (0, 255, 0), 2)
                cv2.putText(
                    frame,
                    item["placa"],
                    (p1[0], max(p1[1] - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )

            cv2.imshow("AutoPark - Reconhecimento de Placas", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.liberar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    iniciar_monitoramento()
