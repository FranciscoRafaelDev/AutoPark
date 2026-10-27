import os

# Configura o RTSP para utilizar UDP e reduz o buffer de atraso
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
import cv2

RTSP_URL = os.getenv("RTSP_URL", "rtsp://192.168.0.2:554/onvif1")
ARQUIVO_SAIDA = Path(__file__).parent / "placas_registradas.json"
PADRAO_PLACA_BR = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
CONFIANCA_MINIMA = 0.5
COOLDOWN_SEGUNDOS = 30


class CameraStream:
    """Lê os quadros continuamente em segundo plano para não perder pacotes UDP/HEVC."""
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


def normalizar_e_validar(texto: str) -> str | None:
    limpo = re.sub(r"[^A-Z0-9]", "", texto.upper())
    return limpo if PADRAO_PLACA_BR.match(limpo) else None


def salvar_placa_json(placa: str, caminho: Path = ARQUIVO_SAIDA) -> dict:
    registros = []
    if caminho.exists():
        try:
            registros = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            registros = []

    novo_registro = {
        "nome": f"carro{len(registros) + 1}",
        "placa": placa,
        "horario": datetime.now().isoformat(timespec="seconds"),
    }
    registros.append(novo_registro)
    caminho.write_text(json.dumps(registros, indent=2, ensure_ascii=False), encoding="utf-8")
    return novo_registro


def detectar_placas_no_frame(frame, leitor_ocr, confianca_min: float = CONFIANCA_MINIMA) -> list[dict]:
    # Reduz pela metade para o OCR rodar mais rápido na CPU
    pequeno = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    cinza = cv2.equalizeHist(cv2.cvtColor(pequeno, cv2.COLOR_BGR2GRAY))
    resultados_ocr = leitor_ocr.readtext(cinza)
    placas_encontradas = []

    for bbox, texto_bruto, confianca in resultados_ocr:
        if confianca < confianca_min:
            continue
        placa = normalizar_e_validar(texto_bruto)
        if placa:
            # Multiplica por 2 para voltar às coordenadas originais do vídeo
            bbox_original = [[int(x * 2), int(y * 2)] for x, y in bbox]
            placas_encontradas.append({
                "placa": placa,
                "confianca": float(confianca),
                "bbox": bbox_original,
            })
    return placas_encontradas


def iniciar_monitoramento():
    import easyocr

    if not ARQUIVO_SAIDA.exists():
        ARQUIVO_SAIDA.write_text("[]", encoding="utf-8")

    leitor = easyocr.Reader(["pt", "en"], gpu=False)
    camera = CameraStream(RTSP_URL)

    if not camera.rodando:
        print("Erro: não foi possível conectar à câmera.")
        raise SystemExit(1)

    print("Câmera conectada com sucesso! Monitorando placas...")

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
            # Executa o OCR no máximo 1 vez por segundo
            if agora - ultimo_ocr >= 1.0:
                ultimo_ocr = agora
                ultimas_deteccoes = detectar_placas_no_frame(frame, leitor)

                for item in ultimas_deteccoes:
                    placa = item["placa"]
                    if agora - ultimas_vistas.get(placa, 0) > COOLDOWN_SEGUNDOS:
                        ultimas_vistas[placa] = agora
                        registro = salvar_placa_json(placa)
                        print(f"Registrado: {registro} (confiança: {item['confianca']:.2f})")

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

            cv2.imshow("Jortan JT-8178 - Reconhecimento de Placas", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.liberar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    iniciar_monitoramento()