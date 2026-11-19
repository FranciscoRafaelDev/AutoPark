import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api.js';

const estadoInicial = {
  resumo: {
    capacidade: 12,
    estacionados_agora: 0,
    entradas_hoje: 0,
    saidas_hoje: 0,
    faturamento_hoje: null,
    banco_ativo: 'Supabase (PostgreSQL)',
    camera: {
      ativa: false,
      conectada: false,
      ultima_placa: null,
      ultimo_horario: null,
      mensagem: 'Inativa',
    },
  },
  vagas: [],
  ativos: [],
  tickets: [],
  pagamentos: [],
};

const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const dateLabel = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'full' }).format(new Date());

function formatTime(isoOrTime) {
  if (!isoOrTime) return '—';
  if (isoOrTime.length <= 8) return isoOrTime;
  const d = new Date(isoOrTime);
  return Number.isNaN(d.getTime()) ? isoOrTime : d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function extrairHora(isoOrTime) {
  if (!isoOrTime) return null;
  if (isoOrTime.length <= 8 && isoOrTime.includes(':')) {
    const h = parseInt(isoOrTime.split(':')[0], 10);
    return Number.isNaN(h) ? null : h;
  }
  const d = new Date(isoOrTime);
  return Number.isNaN(d.getTime()) ? null : d.getHours();
}

function calcularFinanceiro(tickets, pagamentos, ativos, resumo) {
  const totalFaturado = pagamentos.reduce((acc, p) => acc + Number(p.valor || 0), 0);
  const receitaEmAberto = ativos.reduce((acc, a) => acc + Number(a.valor_parcial || 0), 0);
  const ticketMedio = pagamentos.length ? totalFaturado / pagamentos.length : 0;
  const taxaOcupacao = Math.min(100, Math.round((ativos.length / Math.max(1, resumo.capacidade)) * 100));

  const metodosBase = ['PIX', 'CARTAO', 'DINHEIRO'];
  const porMetodo = metodosBase.map(metodo => {
    const itens = pagamentos.filter(p => (p.metodo || '').toUpperCase() === metodo);
    const total = itens.reduce((acc, p) => acc + Number(p.valor || 0), 0);
    const percentual = totalFaturado > 0 ? Math.round((total / totalFaturado) * 100) : 0;
    return { metodo, quantidade: itens.length, total, percentual };
  });

  const contagemHoras = Array.from({ length: 24 }, (_, hora) => ({ hora, quantidade: 0 }));
  tickets.forEach(t => {
    const h = extrairHora(t.entrada);
    if (h !== null && h >= 0 && h < 24) {
      contagemHoras[h].quantidade += 1;
    }
  });

  const horasExibidas = contagemHoras.filter(
    item => (item.hora >= 7 && item.hora <= 22) || item.quantidade > 0
  );
  const maxEntradas = Math.max(1, ...horasExibidas.map(h => h.quantidade));
  const pico = horasExibidas.reduce(
    (melhor, atual) => (atual.quantidade > melhor.quantidade ? atual : melhor),
    { hora: null, quantidade: 0 }
  );

  const horarioPicoLabel =
    pico.quantidade > 0
      ? `${String(pico.hora).padStart(2, '0')}h - ${String((pico.hora + 1) % 24).padStart(2, '0')}h`
      : 'Sem dados';

  return {
    totalFaturado,
    receitaEmAberto,
    ticketMedio,
    taxaOcupacao,
    porMetodo,
    horasExibidas,
    maxEntradas,
    pico,
    horarioPicoLabel,
  };
}

const Icons = {
  overview: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="7" height="9" rx="2" /><rect x="14" y="3" width="7" height="5" rx="2" />
      <rect x="14" y="12" width="7" height="9" rx="2" /><rect x="3" y="16" width="7" height="5" rx="2" />
    </svg>
  ),
  vehicles: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 17H3v-5l2.2-5.3A2 2 0 0 1 7.05 5.5h9.9a2 2 0 0 1 1.85 1.2L21 12v5h-2" />
      <circle cx="7.5" cy="17.5" r="2" /><circle cx="16.5" cy="17.5" r="2" /><path d="M9.5 17h5" />
    </svg>
  ),
  camera: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
      <circle cx="12" cy="13" r="3" />
    </svg>
  ),
  spots: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="3" /><path d="M9 17V7h4a3 3 0 0 1 0 6H9" />
    </svg>
  ),
  tickets: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 9a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v1.5a2 2 0 0 0 0 3V15a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1.5a2 2 0 0 0 0-3V9Z" />
      <path d="M9 7v10" strokeDasharray="2 2" />
    </svg>
  ),
  payments: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="5" width="20" height="14" rx="2.5" /><path d="M2 10h20M6 15h4" />
    </svg>
  ),
  revenue: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  ),
  reports: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h5" />
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.6.85 1 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
  entry: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M7 7l10 10M17 7v10H7" /></svg>,
  exit: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M7 17L17 7M7 7h10v10" /></svg>,
  search: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>,
  plus: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>,
  sun: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></svg>,
  moon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>,
};

const pages = [
  ['overview', 'overview', 'Visão geral'],
  ['vehicles', 'vehicles', 'Veículos no pátio'],
  ['camera', 'camera', 'Câmera OCR (Ao vivo)'],
  ['spots', 'spots', 'Mapa de vagas'],
  ['tickets', 'tickets', 'Tickets emitidos'],
  ['payments', 'payments', 'Pagamentos'],
  ['reports', 'revenue', 'Relatório financeiro'],
  ['settings', 'settings', 'Configurações'],
];
const pageTitles = Object.fromEntries(pages.map(([id, , label]) => [id, label]));

function BrandLogo({ size = 'md', subtitle = 'Gestão de estacionamento', theme = 'dark' }) {
  const [imgError, setImgError] = useState(false);
  const src = theme === 'dark' ? '/logo-dark.png' : '/logo.png';

  return (
    <div className={`brand-lockup brand-${size}`}>
      {!imgError ? (
        <div className="brand-img-shell">
          <img src={src} alt="AutoPark" className="brand-logo-img" onError={() => setImgError(true)} />
        </div>
      ) : (
        <div className="brand-vector-fallback" aria-label="AutoPark">
          <div className="brand-wordmark">
            <span className="word-auto">Auto</span>
            <span className="word-park">Park</span>
          </div>
        </div>
      )}
      {subtitle && <div className="brand-sub">{subtitle}</div>}
    </div>
  );
}

function PlateBadge({ plate }) {
  return (
    <span className="plate-badge" title={`Placa ${plate}`}>
      <span className="plate-top">BRASIL</span>
      <strong className="plate-code">{plate}</strong>
    </span>
  );
}

function Login({ onLogin, theme }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const { usuario } = await api.login(email.trim(), password);
      onLogin(usuario);
    } catch (err) {
      setError(err.message || 'Falha ao autenticar.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <BrandLogo size="lg" subtitle="Autenticação via Supabase Auth" theme={theme} />
        </div>
        <div className="login-header">
          <h1>Acesse o terminal operacional</h1>
          <p className="muted">Entre com seu e-mail e senha cadastrados.</p>
        </div>
        <label className="field">
          <span>E-mail</span>
          <input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required />
        </label>
        <label className="field">
          <span>Senha</span>
          <input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required />
        </label>
        {error && <div className="login-error" role="alert">{error}</div>}
        <button type="submit" className="primary-btn login-submit" disabled={loading}>
          {loading ? 'Validando...' : 'Entrar no painel →'}
        </button>
      </form>
    </section>
  );
}

function Card({ label, iconKey, value, hint, accent = 'blue' }) {
  return (
    <article className={`card card-accent-${accent}`}>
      <div className="card-top">
        <span>{label}</span>
        <span className="card-icon">{Icons[iconKey]}</span>
      </div>
      <div className="value">{value}</div>
      <div className="card-foot"><span className="hint">{hint}</span></div>
    </article>
  );
}

function DataTable({ title, subtitle, headers, rows, searchable = true, action }) {
  const [query, setQuery] = useState('');
  const filteredRows = useMemo(() => {
    if (!query.trim()) return rows;
    return rows.filter(row =>
      row.map(c => (typeof c === 'string' || typeof c === 'number' ? c : c?.props?.plate || c?.props?.children || '')).join(' ').toLowerCase().includes(query.toLowerCase())
    );
  }, [rows, query]);

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2 className="section-title">{title}</h2>
          <div className="section-sub">{subtitle}</div>
        </div>
        <div className="section-controls">
          {searchable && (
            <div className="search-wrap">
              <span className="search-icon">{Icons.search}</span>
              <input className="search" placeholder="Filtrar..." type="search" value={query} onChange={e => setQuery(e.target.value)} />
            </div>
          )}
          {action}
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr>{headers.map(h => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>
            {filteredRows.length ? (
              filteredRows.map((row, idx) => (
                <tr key={idx}>{row.map((cell, cIdx) => <td key={cIdx}>{cell}</td>)}</tr>
              ))
            ) : (
              <tr><td className="empty" colSpan={headers.length}>Nenhum registro encontrado.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function App() {
  const [usuario, setUsuario] = useState(null);
  const [verificandoSessao, setVerificandoSessao] = useState(true);
  const [usuariosAdmin, setUsuariosAdmin] = useState([]);
  const [page, setPage] = useState('overview');
  const [theme, setTheme] = useState(() => localStorage.getItem('autopark-theme') || 'dark');
  const [estado, setEstado] = useState(estadoInicial);
  const [apiOnline, setApiOnline] = useState(false);
  const [aviso, setAviso] = useState('');
  const [showNewEntry, setShowNewEntry] = useState(false);
  const [placaInput, setPlacaInput] = useState('');
  const [vagaInput, setVagaInput] = useState('');
  const [placaSimulada, setPlacaSimulada] = useState('BRA2E19');
  const ultimaPlacaConhecida = useRef(null);

  const temPermissao = (modulo) =>
    usuario?.papel === 'admin' || Boolean(usuario?.permissoes?.[modulo]);

  const paginasPermitidas = useMemo(
    () => pages.filter(([id]) => usuario?.papel === 'admin' || Boolean(usuario?.permissoes?.[id])),
    [usuario]
  );

  const { resumo, ativos, vagas, tickets, pagamentos } = estado;

  const financeiro = useMemo(
    () => calcularFinanceiro(tickets, pagamentos, ativos, resumo),
    [tickets, pagamentos, ativos, resumo]
  );

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('autopark-theme', theme);
  }, [theme]);

  useEffect(() => {
    api.me()
      .then(({ usuario: u }) => setUsuario(u))
      .catch(() => setUsuario(null))
      .finally(() => setVerificandoSessao(false));
  }, []);

  useEffect(() => {
    if (!usuario) return;
    const permitido = usuario.papel === 'admin' || Boolean(usuario.permissoes?.[page]);
    if (!permitido && paginasPermitidas.length) {
      setPage(paginasPermitidas[0][0]);
    }
  }, [usuario, page, paginasPermitidas]);

  async function carregarDados() {
    if (!usuario) return;
    try {
      const dados = await api.obterPainel(usuario);
      const cam = dados.resumo?.camera;
      if (cam?.ultima_placa && cam.ultima_placa !== ultimaPlacaConhecida.current) {
        if (ultimaPlacaConhecida.current !== null) {
          setAviso(`Câmera OCR detectou a placa ${cam.ultima_placa} às ${cam.ultimo_horario} (Ticket ${cam.ultimo_ticket}).`);
        }
        ultimaPlacaConhecida.current = cam.ultima_placa;
      }
      setEstado(dados);
      setApiOnline(true);
    } catch (err) {
      if (err.status === 401) {
        setUsuario(null);
      } else {
        setApiOnline(false);
      }
    }
  }

  useEffect(() => {
    if (!usuario) return undefined;
    carregarDados();
    if (usuario.papel === 'admin') {
      api.listarUsuarios().then(setUsuariosAdmin).catch(() => {});
    }
    const timer = setInterval(carregarDados, 3000);
    return () => clearInterval(timer);
  }, [usuario]);

  async function handleRegistrarEntrada(e) {
    e.preventDefault();
    setAviso('');
    try {
      const novo = await api.registrarEntrada({
        placa: placaInput,
        vaga_codigo: vagaInput || null,
      });
      await carregarDados();
      setAviso(`Entrada registrada! Ticket ${novo.ticket_id} emitido.`);
      setPlacaInput('');
      setShowNewEntry(false);
    } catch (err) {
      setAviso(err.message);
    }
  }

  async function handleSaida(ticketId, metodo = 'PIX') {
    setAviso('');
    try {
      await api.registrarSaida({ ticket_id: ticketId, metodo_pagamento: metodo });
      await carregarDados();
      setAviso(`Saída e pagamento (${metodo}) do ticket ${ticketId} confirmados.`);
    } catch (err) {
      setAviso(err.message);
    }
  }

  async function handleToggleCamera() {
    try {
      if (estado.resumo?.camera?.ativa) {
        await api.pararCamera();
      } else {
        await api.iniciarCamera();
      }
      await carregarDados();
    } catch (err) {
      setAviso(err.message);
    }
  }

  async function handleSimularOcr(e) {
    e.preventDefault();
    setAviso('');
    try {
      const res = await api.simularLeituraOcr(placaSimulada);
      await carregarDados();
      setAviso(`Leitura OCR simulada: Placa ${res.placa} registrada com Ticket ${res.ticket_id}!`);
    } catch (err) {
      setAviso(err.message);
    }
  }

  async function handleLogout() {
    await api.logout().catch(() => {});
    setUsuario(null);
    setUsuariosAdmin([]);
    setEstado(estadoInicial);
  }

  async function handleAlternarPermissao(alvo, modulo) {
    const novasPermissoes = {
      ...(alvo.permissoes || {}),
      [modulo]: !alvo.permissoes?.[modulo],
    };
    try {
      const atualizado = await api.atualizarUsuario(alvo.id, {
        papel: alvo.papel,
        ativo: alvo.ativo,
        permissoes: novasPermissoes,
      });
      setUsuariosAdmin(prev => prev.map(u => (u.id === alvo.id ? atualizado : u)));
    } catch (err) {
      setAviso(err.message);
    }
  }

  async function handleAlterarPapel(alvo, novoPapel) {
    try {
      const atualizado = await api.atualizarUsuario(alvo.id, {
        papel: novoPapel,
        ativo: alvo.ativo,
        permissoes: alvo.permissoes || {},
      });
      setUsuariosAdmin(prev => prev.map(u => (u.id === alvo.id ? atualizado : u)));
    } catch (err) {
      setAviso(err.message);
    }
  }

  if (verificandoSessao) {
    return (
      <section className="login-screen">
        <p className="muted">Verificando sessão...</p>
      </section>
    );
  }

  if (!usuario) {
    return <Login theme={theme} onLogin={setUsuario} />;
  }

  const cameraInfo = resumo?.camera || { ativa: false, conectada: false, mensagem: 'Inativa' };
  const occupancyPct = Math.min(100, Math.round((ativos.length / Math.max(1, resumo.capacidade)) * 100));

  const vehicleRows = ativos.map(v => [
    <PlateBadge plate={v.placa} />,
    <span className="mono-chip">{v.ticket_id}</span>,
    <span className="spot-tag">{v.vaga_codigo}</span>,
    <span className="tabular">{formatTime(v.entrada)}</span>,
    <span className="tabular">{v.duracao}</span>,
    <strong className="tabular">{currency.format(v.valor_parcial)}</strong>,
    <div className="row-actions">
      {apiOnline && temPermissao('tickets') && (
        <a className="ghost-btn" href={api.urlPdfTicket(v.ticket_id)} target="_blank" rel="noreferrer">
          PDF 80mm
        </a>
      )}
      <button type="button" className="primary-btn btn-sm" onClick={() => handleSaida(v.ticket_id, 'PIX')}>
        Dar saída (Pix)
      </button>
    </div>,
  ]);

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <BrandLogo size="sm" subtitle="Gestão de estacionamento" theme={theme} />
        </div>
        <div className="nav-label">OPERAÇÃO</div>
        <nav className="nav">
          {paginasPermitidas.map(([id, iconKey, label]) => (
            <button key={id} type="button" className={page === id ? 'active' : ''} onClick={() => setPage(id)}>
              <span className="ico">{Icons[iconKey]}</span>
              <span>{label}</span>
              {id === 'vehicles' && <span className="nav-counter tabular">{ativos.length}</span>}
            </button>
          ))}
        </nav>

        <div className="patio-meter">
          <div className="patio-meter-head">
            <span>Ocupação do pátio</span>
            <strong className="tabular">{ativos.length}/{resumo.capacidade}</strong>
          </div>
          <div className="patio-bar-track">
            <div className="patio-bar-fill" style={{ width: `${occupancyPct}%` }} />
          </div>
          <div className="patio-meter-sub">{Math.max(0, resumo.capacidade - ativos.length)} vagas disponíveis</div>
        </div>

        <div className="side-bottom">
          <span className="status-dot" />
          <span>{usuario.nome} ({usuario.papel})</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">AutoPark Full Stack · Atualização em Tempo Real</div>
            <h1 className="heading">{pageTitles[page]}</h1>
          </div>
          <div className="top-actions">
            {temPermissao('camera') && (
              <button
                type="button"
                className={`camera-chip ${cameraInfo.conectada ? 'cam-online' : cameraInfo.ativa ? 'cam-starting' : 'cam-idle'}`}
                onClick={() => setPage('camera')}
                title={cameraInfo.mensagem}
              >
                <span className="cam-dot" />
                <span>
                  {cameraInfo.conectada
                    ? `Câmera OCR Ativa${cameraInfo.ultima_placa ? ` · Última: ${cameraInfo.ultima_placa}` : ''}`
                    : 'Câmera OCR: Pronta'}
                </span>
              </button>
            )}

            {temPermissao('vehicles') && (
              <button type="button" className="primary-btn btn-sm" onClick={() => setShowNewEntry(true)}>
                <span className="btn-ico">{Icons.plus}</span>
                Nova Entrada
              </button>
            )}
            <button type="button" className="icon-btn" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="Alternar tema">
              {theme === 'dark' ? Icons.sun : Icons.moon}
            </button>
            <div className="date-chip">{dateLabel}</div>
            <button type="button" className="link-button" onClick={handleLogout}>
              Sair
            </button>
          </div>
        </header>

        {aviso && <div className="alert-banner">{aviso}</div>}

        {page === 'overview' && temPermissao('overview') && (
          <>
            <section className="cards">
              <Card label="Veículos no pátio" iconKey="vehicles" value={ativos.length} hint={`${resumo.capacidade - ativos.length} vagas livres`} accent="blue" />
              <Card label="Entradas registradas" iconKey="entry" value={resumo.entradas_hoje} hint="Manual + Câmera OCR" accent="emerald" />
              <Card label="Saídas concluídas" iconKey="exit" value={resumo.saidas_hoje} hint="Baixas no caixa" accent="slate" />
              {resumo.faturamento_hoje !== null && (
                <Card label="Faturamento" iconKey="revenue" value={currency.format(resumo.faturamento_hoje)} hint="Total liquidado" accent="emerald" />
              )}
            </section>
            {temPermissao('vehicles') && (
              <div className="content">
                <DataTable
                  title="Veículos estacionados agora"
                  subtitle="Atualizado automaticamente a cada 3 segundos com leituras da câmera e entradas manuais"
                  headers={['Placa', 'Ticket', 'Vaga', 'Entrada', 'Permanência', 'Parcial', 'Ações']}
                  rows={vehicleRows}
                />
              </div>
            )}
          </>
        )}

        {page === 'vehicles' && temPermissao('vehicles') && (
          <DataTable
            title="Veículos no pátio"
            subtitle="Controle de entradas, impressão de ticket 80mm e saída"
            headers={['Placa', 'Ticket', 'Vaga', 'Entrada', 'Permanência', 'Parcial', 'Ações']}
            rows={vehicleRows}
          />
        )}

        {page === 'camera' && temPermissao('camera') && (
          <section className="section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Monitoramento de Câmera RTSP + EasyOCR</h2>
                <div className="section-sub">Reconhecimento automático de placas Mercosul e antigas integrado ao banco e impressora térmica</div>
              </div>
              {apiOnline && (
                <button type="button" className="primary-btn btn-sm" onClick={handleToggleCamera}>
                  {cameraInfo.ativa ? 'Parar Monitoramento RTSP' : 'Iniciar Monitoramento RTSP'}
                </button>
              )}
            </div>
            <div className="report-grid">
              <div className="report-item">
                <span>Status da Câmera</span>
                <strong>{cameraInfo.mensagem || 'Aguardando acionamento'}</strong>
              </div>
              <div className="report-item">
                <span>Última Placa Reconhecida</span>
                <div>{cameraInfo.ultima_placa ? <PlateBadge plate={cameraInfo.ultima_placa} /> : <strong>Nenhuma ainda</strong>}</div>
              </div>
              <div className="report-item">
                <span>Horário / Ticket Gerado</span>
                <strong className="tabular">
                  {cameraInfo.ultimo_horario ? `${cameraInfo.ultimo_horario} · #${cameraInfo.ultimo_ticket}` : '—'}
                </strong>
              </div>
            </div>

            <form className="ocr-sim-box" onSubmit={handleSimularOcr}>
              <div>
                <strong>Testar fluxo completo da câmera (sem precisar da câmera RTSP física ligada)</strong>
                <p className="muted">Dispara exatamente a função <code>processar_placa_detectada()</code> do <code>camera.py</code>, alocando vaga no Supabase e gerando o PDF térmico 80mm.</p>
              </div>
              <div className="ocr-sim-controls">
                <input
                  className="control"
                  value={placaSimulada}
                  onChange={e => setPlacaSimulada(e.target.value.toUpperCase())}
                  placeholder="Placa (ex.: BRA2E19)"
                  maxLength={8}
                  required
                />
                <button type="submit" className="primary-btn btn-sm">
                  Simular Detecção OCR
                </button>
              </div>
            </form>
          </section>
        )}

        {page === 'spots' && temPermissao('spots') && (
          <section className="section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Mapa de vagas por setor</h2>
                <div className="section-sub">Status de ocupação sincronizado com as entradas e saídas</div>
              </div>
            </div>
            <div className="report-grid">
              {vagas.map(v => (
                <div className="report-item" key={v.codigo}>
                  <span>Setor {v.setor} · Vaga <strong>{v.codigo}</strong></span>
                  <span className={`pill ${v.ocupada ? 'pill-blue' : 'pill-active'}`}>
                    {v.ocupada ? 'Ocupada' : 'Livre'}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {page === 'tickets' && temPermissao('tickets') && (
          <DataTable
            title="Histórico de tickets emitidos"
            subtitle="Cada entrada gera um PDF térmico de 80mm com código de barras Code128"
            headers={['Ticket ID', 'Placa', 'Vaga', 'Entrada', 'Status', 'PDF']}
            rows={tickets.map(t => [
              <span className="mono-chip">{t.ticket_id}</span>,
              <PlateBadge plate={t.placa} />,
              t.vaga_codigo || 'Pátio',
              formatTime(t.entrada),
              <span className="pill pill-active">{t.status}</span>,
              apiOnline ? <a className="ghost-btn" href={api.urlPdfTicket(t.ticket_id)} target="_blank" rel="noreferrer">Abrir PDF</a> : '—',
            ])}
          />
        )}

        {page === 'payments' && temPermissao('payments') && (
          <DataTable
            title="Pagamentos registrados"
            subtitle="Baixas de sessões gravadas na tabela pagamentos"
            headers={['Ticket', 'Placa', 'Método', 'Valor', 'Horário']}
            rows={pagamentos.map(p => [
              <span className="mono-chip">{p.ticket_id}</span>,
              <PlateBadge plate={p.placa} />,
              <span className="method-pill method-pix">{p.metodo}</span>,
              <strong className="tabular">{currency.format(p.valor)}</strong>,
              formatTime(p.pago_em),
            ])}
          />
        )}

        {page === 'reports' && temPermissao('reports') && (
          <div className="finance-stack">
            <section className="cards">
              <Card
                label="Faturamento liquidado"
                iconKey="revenue"
                value={currency.format(financeiro.totalFaturado)}
                hint={`${pagamentos.length} pagamento(s) confirmado(s)`}
                accent="emerald"
              />
              <Card
                label="Receita em aberto"
                iconKey="payments"
                value={currency.format(financeiro.receitaEmAberto)}
                hint={`${ativos.length} veículo(s) no pátio`}
                accent="blue"
              />
              <Card
                label="Ticket médio"
                iconKey="tickets"
                value={currency.format(financeiro.ticketMedio)}
                hint="Média por saída finalizada"
                accent="slate"
              />
              <Card
                label="Horário de pico"
                iconKey="overview"
                value={financeiro.horarioPicoLabel}
                hint={
                  financeiro.pico.quantidade > 0
                    ? `${financeiro.pico.quantidade} entrada(s) no pico`
                    : 'Aguardando entradas'
                }
                accent="blue"
              />
            </section>

            <div className="finance-grid">
              <section className="section">
                <div className="section-head">
                  <div>
                    <h2 className="section-title">Faturamento por método de pagamento</h2>
                    <div className="section-sub">Distribuição dos valores liquidados no caixa</div>
                  </div>
                </div>
                <div className="method-bars">
                  {financeiro.porMetodo.map(item => (
                    <div className="method-bar-row" key={item.metodo}>
                      <div className="method-bar-meta">
                        <span className="method-pill">{item.metodo}</span>
                        <span className="muted tabular">{item.quantidade} pgto(s) · {item.percentual}%</span>
                        <strong className="tabular">{currency.format(item.total)}</strong>
                      </div>
                      <div className="patio-bar-track">
                        <div className="patio-bar-fill" style={{ width: `${item.percentual}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="section">
                <div className="section-head">
                  <div>
                    <h2 className="section-title">Resumo operacional</h2>
                    <div className="section-sub">{dateLabel}</div>
                  </div>
                  <button type="button" className="primary-btn btn-sm" onClick={() => window.print()}>
                    Imprimir
                  </button>
                </div>
                <div className="report-grid report-grid-2">
                  <div className="report-item"><span>Banco conectado</span><strong>{resumo.banco_ativo}</strong></div>
                  <div className="report-item"><span>Ocupação atual</span><strong className="tabular">{financeiro.taxaOcupacao}%</strong></div>
                  <div className="report-item"><span>Entradas</span><strong className="tabular">{resumo.entradas_hoje}</strong></div>
                  <div className="report-item"><span>Saídas</span><strong className="tabular">{resumo.saidas_hoje}</strong></div>
                </div>
              </section>
            </div>

            <section className="section">
              <div className="section-head">
                <div>
                  <h2 className="section-title">Horários de pico (Entradas por hora)</h2>
                  <div className="section-sub">Volume de acessos calculado automaticamente pelos tickets registrados</div>
                </div>
              </div>
              <div className="peak-chart">
                {financeiro.horasExibidas.map(item => {
                  const altura = item.quantidade > 0
                    ? Math.max(12, Math.round((item.quantidade / financeiro.maxEntradas) * 100))
                    : 4;
                  const ehPico = item.quantidade > 0 && item.quantidade === financeiro.pico.quantidade;
                  return (
                    <div className="peak-col" key={item.hora} title={`${String(item.hora).padStart(2, '0')}h: ${item.quantidade} entrada(s)`}>
                      <span className="peak-count tabular">{item.quantidade > 0 ? item.quantidade : ''}</span>
                      <div className="peak-bar-wrap">
                        <div
                          className={`peak-bar ${ehPico ? 'peak-bar-max' : ''} ${item.quantidade === 0 ? 'peak-bar-empty' : ''}`}
                          style={{ height: `${altura}%` }}
                        />
                      </div>
                      <span className="peak-hour tabular">{String(item.hora).padStart(2, '0')}h</span>
                    </div>
                  );
                })}
              </div>
            </section>
          </div>
        )}

        {page === 'settings' && temPermissao('settings') && (
          <div className="finance-stack">
            <section className="section">
              <div className="section-head">
                <div>
                  <h2 className="section-title">Permissões de usuários</h2>
                  <div className="section-sub">Defina papel e acesso por módulo para cada funcionário</div>
                </div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Usuário</th>
                      <th>Papel</th>
                      {pages.map(([id, , label]) => <th key={id}>{label}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {usuariosAdmin.map(u => (
                      <tr key={u.id}>
                        <td>
                          <strong>{u.nome}</strong>
                          <div className="section-sub">{u.email}</div>
                        </td>
                        <td>
                          <select
                            className="control"
                            value={u.papel}
                            onChange={e => handleAlterarPapel(u, e.target.value)}
                          >
                            <option value="funcionario">Funcionário</option>
                            <option value="admin">Admin</option>
                          </select>
                        </td>
                        {pages.map(([id]) => (
                          <td key={id}>
                            <input
                              type="checkbox"
                              checked={u.papel === 'admin' || Boolean(u.permissoes?.[id])}
                              disabled={u.papel === 'admin'}
                              onChange={() => handleAlternarPermissao(u, id)}
                            />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="section">
              <div className="section-head">
                <div>
                  <h2 className="section-title">Configurações de ambiente</h2>
                  <div className="section-sub">Conexão React → FastAPI → Supabase</div>
                </div>
              </div>
              <div className="report-grid">
                <div className="report-item"><span>Endpoint FastAPI</span><strong>{api.urlBase}</strong></div>
                <div className="report-item"><span>Persistência ativa</span><strong>{resumo.banco_ativo}</strong></div>
                <div className="report-item"><span>Documentação OpenAPI</span><strong><a href={`${api.urlBase}/docs`} target="_blank" rel="noreferrer">/docs</a></strong></div>
              </div>
            </section>
          </div>
        )}
      </main>

      {showNewEntry && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <form className="modal-card" onSubmit={handleRegistrarEntrada}>
            <div className="modal-head">
              <div>
                <h3>Registrar entrada de veículo</h3>
                <p className="muted">Valida a placa, aloca vaga e gera o PDF térmico 80mm.</p>
              </div>
              <button type="button" className="ghost-btn" onClick={() => setShowNewEntry(false)}>Fechar</button>
            </div>
            <label className="field">
              <span>Placa (Mercosul ou antiga)</span>
              <input autoFocus value={placaInput} onChange={e => setPlacaInput(e.target.value.toUpperCase())} placeholder="Ex.: ABC1D23" maxLength={8} required />
            </label>
            <label className="field">
              <span>Vaga (opcional — aloca livre automaticamente)</span>
              <select className="control" value={vagaInput} onChange={e => setVagaInput(e.target.value)}>
                <option value="">Automática (primeira livre)</option>
                {vagas.filter(v => !v.ocupada).map(v => (
                  <option key={v.codigo} value={v.codigo}>{v.codigo} (Setor {v.setor})</option>
                ))}
              </select>
            </label>
            <div className="modal-actions">
              <button type="button" className="ghost-btn" onClick={() => setShowNewEntry(false)}>Cancelar</button>
              <button type="submit" className="primary-btn btn-sm">Emitir ticket</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
