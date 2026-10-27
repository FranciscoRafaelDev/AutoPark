import json
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Importa a função geradora de ticket do seu outro arquivo
# (Se o arquivo for main.py, use: from main import emitir_ticket)
from gerador_ticket import emitir_ticket
from datetime import datetime
from banco_estacionamento import cadastrar_entrada

ARQUIVO = Path(__file__).parent / "dados.json"


class MonitorJson(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        # Guarda histórico do que já foi emitido para evitar tickets duplicados
        self.itens_processados = set()
        self.ultimo_registro_processado = None

    def extrair_placa(self, item) -> str:
        """Extrai o valor da placa suportando string direta ou dicionário."""
        if isinstance(item, dict):
            return item.get("placa") or item.get("Placa") or "NÃO INFORMADA"
        if isinstance(item, str):
            return item
        return "NÃO INFORMADA"

    def processar_arquivo(self, caminho):
        arquivo_alterado = Path(caminho)

        if arquivo_alterado.resolve() != ARQUIVO.resolve():
            return

        # Pausa para o arquivo terminar de ser gravado no disco
        time.sleep(0.2)

        try:
            with ARQUIVO.open("r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)

            # Caso 1: O JSON é uma lista acumulada de veículos
            if isinstance(dados, list):
                for index, item in enumerate(dados):
                    # Cria um identificador único para cada entrada da lista
                    item_id = item.get("id") if isinstance(item, dict) and "id" in item else f"{index}_{item!s}"
                    
                    if item_id not in self.itens_processados:
                        placa = self.extrair_placa(item)
                        print(f"\n[+] Novo registro detectado: Placa {placa}")

                        ticket_id = emitir_ticket(placa=placa)

                        if ticket_id:
                            cadastrar_entrada(
    
                                ticket_id=ticket_id,
                                placa=placa,
                                data_hora_entrada=datetime.now().isoformat(
                                    timespec="seconds"
                                )
                             )

                            print(f"[OK] Entrada registrada: {placa}")
                            self.itens_processados.add(item_id)
                        else:
                            print("[ERRO] Ticket não foi confirmado para impressão.")

            # Caso 2: O JSON contém apenas o último veículo recebido
            else:
                if dados != self.ultimo_registro_processado:
                    placa = self.extrair_placa(dados)
                    print(f"\n[+] Novo registro detectado: Placa {placa}")
                    emitir_ticket(placa=placa)
                    self.ultimo_registro_processado = dados

        except (json.JSONDecodeError, OSError) as erro:
            print(f"[!] Erro ao tentar ler o JSON: {erro}")

    def on_modified(self, event):
        if not event.is_directory:
            self.processar_arquivo(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self.processar_arquivo(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.processar_arquivo(event.dest_path)


if __name__ == "__main__":
    pasta = str(ARQUIVO.parent)

    monitor = MonitorJson()
    observador = Observer()

    observador.schedule(monitor, pasta, recursive=False)
    observador.start()

    print(f"Monitorando entradas em: {ARQUIVO}")
    print("Pronto para emitir tickets automaticamente. Pressione CTRL+C para parar.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando monitoramento...")
    finally:
        observador.stop()
        observador.join()