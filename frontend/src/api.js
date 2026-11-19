const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function requisitar(caminho, opcoes = {}) {
  const resposta = await fetch(`${API_BASE}${caminho}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(opcoes.headers || {}) },
    ...opcoes,
  });
  if (!resposta.ok) {
    const erro = await resposta.json().catch(() => ({}));
    const err = new Error(erro.detail || `Erro HTTP ${resposta.status}`);
    err.status = resposta.status;
    throw err;
  }
  return resposta.json();
}

export const api = {
  urlBase: API_BASE,
  login: (email, password) =>
    requisitar('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => requisitar('/api/auth/logout', { method: 'POST' }),
  me: () => requisitar('/api/auth/me'),
  listarUsuarios: () => requisitar('/api/admin/usuarios'),
  atualizarUsuario: (userId, dados) =>
    requisitar(`/api/admin/usuarios/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(dados),
    }),
  obterPainel: async (usuario) => {
    const ehAdmin = usuario?.papel === 'admin';
    const perm = usuario?.permissoes || {};
    const pode = (mod) => ehAdmin || Boolean(perm[mod]);

    const [resumo, ativos, vagas, tickets, pagamentos] = await Promise.all([
      pode('overview') ? requisitar('/api/resumo') : Promise.resolve(null),
      pode('vehicles') ? requisitar('/api/estacionamento/ativos') : Promise.resolve([]),
      pode('spots') ? requisitar('/api/vagas') : Promise.resolve([]),
      pode('tickets') ? requisitar('/api/tickets') : Promise.resolve([]),
      pode('payments') ? requisitar('/api/pagamentos') : Promise.resolve([]),
    ]);
    return {
      resumo: resumo || {
        capacidade: 12,
        estacionados_agora: ativos.length,
        entradas_hoje: tickets.length,
        saidas_hoje: 0,
        faturamento_hoje: null,
        banco_ativo: 'Supabase (PostgreSQL)',
        camera: { ativa: false, conectada: false, mensagem: 'Inativa' },
      },
      ativos,
      vagas,
      tickets,
      pagamentos,
    };
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
  iniciarCamera: () => requisitar('/api/camera/iniciar', { method: 'POST' }),
  pararCamera: () => requisitar('/api/camera/parar', { method: 'POST' }),
  simularLeituraOcr: (placa) =>
    requisitar('/api/camera/simular-deteccao', {
      method: 'POST',
      body: JSON.stringify({ placa }),
    }),
  urlPdfTicket: (ticketId) => `${API_BASE}/api/tickets/${ticketId}/pdf`,
};
