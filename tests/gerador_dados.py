import json
import random
import string
import time
from datetime import datetime
from pathlib import Path

# Aponta para o arquivo 'dados.json' na mesma pasta deste script
ARQUIVO_JSON = Path(__file__).resolve().parent / "dados.json"

# Intervalo entre novos registros (em segundos)
INTERVALO_SEGUNDOS = 60


def gerar_placa_aleatoria() -> str:
    """Gera uma placa válida alternando entre padrão Mercosul (ABC1D23) e Cinza (ABC1234)."""
    letras = string.ascii_uppercase
    digitos = string.digits

    if random.choice([True, False]):
        # Padrão Mercosul: 3 letras + 1 dígito + 1 letra + 2 dígitos
        return f"{random.choice(letras)}{random.choice(letras)}{random.choice(letras)}{random.choice(digitos)}{random.choice(letras)}{random.choice(digitos)}{random.choice(digitos)}"
    else:
        # Padrão tradicional: 3 letras + 4 dígitos
        return f"{random.choice(letras)}{random.choice(letras)}{random.choice(letras)}{random.choice(digitos)}{random.choice(digitos)}{random.choice(digitos)}{random.choice(digitos)}"


def carregar_dados_existentes() -> list:
    """Lê o arquivo JSON atual se já existir; caso contrário, inicia com uma lista vazia."""
    if ARQUIVO_JSON.exists():
        try:
            with ARQUIVO_JSON.open("r", encoding="utf-8") as f:
                conteudo = json.load(f)
                return conteudo if isinstance(conteudo, list) else [conteudo]
        except (json.JSONDecodeError, OSError):
            return []
    return []


def salvar_dados(dados: list):
    """Salva a lista completa com indentação formatada."""
    with ARQUIVO_JSON.open("w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


def iniciar_simulacao():
    print("Iniciando gerador de testes...")
    print(f"Destino: {ARQUIVO_JSON}")
    print(f"Intervalo: {INTERVALO_SEGUNDOS} segundos por placa.")
    print("Pressione CTRL+C para parar a qualquer momento.\n")

    lista_veiculos = carregar_dados_existentes()

    try:
        while True:
            nova_placa = gerar_placa_aleatoria()
            novo_registro = {
                "id": len(lista_veiculos) + 1,
                "placa": nova_placa,
                "horario_entrada": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            lista_veiculos.append(novo_registro)
            salvar_dados(lista_veiculos)

            print(f"[{novo_registro['horario_entrada']}] Nova placa gerada: {nova_placa} (Total: {len(lista_veiculos)})")
            print(f"Aguardando {INTERVALO_SEGUNDOS}s para o próximo envio...\n")

            time.sleep(INTERVALO_SEGUNDOS)

    except KeyboardInterrupt:
        print("\nGerador de testes encerrado.")


if __name__ == "__main__":
    iniciar_simulacao()