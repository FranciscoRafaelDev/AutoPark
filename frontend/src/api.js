const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function requisitar(caminho, opcoes = {}) {
  const resposta = await fetch(`${API_BASE}${caminho}`, {
    headers: { 'Content-Type': 'application/json', ...(opcoes.headers || {}) },
    ...opcoes,
  });
  if (!resposta.ok) {
    const erro = await resposta.json().catch(() => ({}));
    throw new Error(erro.detail || `Erro HTTP ${resposta.status}`);
  }
  return resposta.json();
}

export const api = {
  urlBase: API_BASE,
  obterPainel: async () => {
    const [resumo, ativos, vagas, tickets, pagamentos] = await Promise.all([
      requisitar('/api/resumo'),
      requisitar('/api/estacionamento/ativos'),
      requisitar('/api/vagas'),
      requisitar('/api/tickets'),
      requisitar('/api/pagamentos'),
    ]);
    return { resumo, ativos, vagas, tickets, pagamentos };
  },
  registrarEntrada: (dados) =>
    requisitar('/api/estacionamento/entrada', {
      method: 'POST',
      body: JSON.stringify(dados),
    }),
  registrarSaida: (dados) =>
    requisitar('/api/estacionamento/saida', {
      method: 'POST',
      body: JSON.stringify(dados),
    }),
  iniciarCamera: () =>
    requisitar('/api/camera/iniciar', { method: 'POST' }),
  pararCamera: () =>
    requisitar('/api/camera/parar', { method: 'POST' }),
  simularLeituraOcr: (placa) =>
    requisitar('/api/camera/simular-deteccao', {
      method: 'POST',
      body: JSON.stringify({ placa }),
    }),
  urlPdfTicket: (ticketId) => `${API_BASE}/api/tickets/${ticketId}/pdf`,
};
