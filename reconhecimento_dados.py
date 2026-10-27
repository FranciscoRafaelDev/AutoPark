import json
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from gerador_ticket import emitir_ticket


ARQUIVO = Path(__file__).parent / "dados.json"


class MonitorJson(FileSystemEventHandler):

    def __init__(self):
        super().__init__()

        # Guarda os registros já processados durante esta execução.
        self.itens_processados = set()

        # Evita que eventos simultâneos processem o arquivo juntos.
        self.lock_processamento = __import__("threading").Lock()

        # Na inicialização, registra os dados existentes sem gerar tickets.
        self.inicializar_historico()

    def extrair_placa(self, item):
        if isinstance(item, dict):
            return item.get("placa") or item.get("Placa")

        if isinstance(item, str):
            return item

        return None

    def obter_id(self, item):
        """
        Usa o horário e a placa como identificador.
        Assim, veículos diferentes podem ter a mesma placa
        em entradas diferentes.
        """
        if not isinstance(item, dict):
            return str(item)

        return (
            item.get("id"),
            item.get("placa") or item.get("Placa"),
            item.get("horario") or item.get("data_hora"),
            item.get("nome"),
        )

    def ler_dados(self):
        try:
            with ARQUIVO.open("r", encoding="utf-8") as arquivo:
                return json.load(arquivo)

        except (json.JSONDecodeError, OSError) as erro:
            print(f"[!] Não foi possível ler dados.json: {erro}")
            return None

    def inicializar_historico(self):
        """
        Registra os dados existentes antes de começar a monitorar.
        Os registros antigos não geram tickets novamente.
        """
        dados = self.ler_dados()

        if isinstance(dados, list):
            for item in dados:
                self.itens_processados.add(self.obter_id(item))

        elif isinstance(dados, dict):
            self.itens_processados.add(self.obter_id(dados))

        print(
            f"[i] Histórico inicial carregado: "
            f"{len(self.itens_processados)} registro(s)."
        )

    def processar_arquivo(self, caminho):
        if Path(caminho).resolve() != ARQUIVO.resolve():
            return

        with self.lock_processamento:
            # Aguarda brevemente a gravação do arquivo.
            time.sleep(0.2)

            dados = self.ler_dados()

            if dados is None:
                return

            if isinstance(dados, dict):
                registros = [dados]
            elif isinstance(dados, list):
                registros = dados
            else:
                print("[!] Formato inesperado em dados.json.")
                return

            for item in registros:
                item_id = self.obter_id(item)

                if item_id in self.itens_processados:
                    continue

                placa = self.extrair_placa(item)

                if not placa:
                    print("[!] Registro ignorado: placa não informada.")
                    continue

                print(f"[+] Nova entrada detectada: {placa}")

                try:
                    resultado = emitir_ticket(placa=placa)

                    # Considera processado somente se a emissão
                    # não indicar falha explicitamente.
                    if resultado is not None and resultado is not False:
                        self.itens_processados.add(item_id)
                        print(f"[OK] Ticket processado para {placa}")
                    else:
                        print(
                            f"[!] Emissão não confirmada para {placa}. "
                            "O registro poderá ser tentado novamente."
                        )

                except Exception as erro:
                    print(
                        f"[!] Erro ao emitir ticket para {placa}: {erro}"
                    )

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
    observador = Observer()
    monitor = MonitorJson()

    observador.schedule(
        monitor,
        str(ARQUIVO.parent),
        recursive=False,
    )

    observador.start()

    print(f"[i] Monitorando: {ARQUIVO}")
    print("[i] Aguardando novas entradas. CTRL+C para encerrar.")

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[i] Encerrando monitoramento...")

    finally:
        observador.stop()
        observador.join()
