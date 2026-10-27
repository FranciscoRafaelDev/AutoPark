from banco_estacionamento import (
    buscar_ticket,
    registrar_pagamento,
)

ticket_id = input("Digite o número do ticket: ")

registro = buscar_ticket(ticket_id)

if registro is None:
    print("Ticket não encontrado.")

elif registro["status"] == "SAIU":
    print("Este veículo já teve a saída registrada.")

else:
    valor = float(input("Valor pago (R$): "))

    sucesso = registrar_pagamento(
        ticket_id=ticket_id,
        valor_total=valor
    )

    if sucesso:
        print("Pagamento registrado!")
        print("Saída do veículo registrada!")
    else:
        print("Não foi possível registrar a saída.")
