create table if not exists public.vagas (
    codigo text primary key,
    setor text not null check (char_length(setor) between 1 and 10),
    ocupada boolean not null default false,
    criado_em timestamptz not null default now()
);

create table if not exists public.veiculos (
    placa text primary key check (placa ~ '^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$'),
    responsavel_nome text,
    responsavel_telefone text,
    criado_em timestamptz not null default now()
);

create table if not exists public.sessoes (
    ticket_id text primary key,
    placa text not null references public.veiculos(placa) on update cascade on delete restrict,
    vaga_codigo text references public.vagas(codigo) on update cascade on delete set null,
    entrada timestamptz not null default now(),
    saida timestamptz,
    status text not null default 'ESTACIONADO'
        check (status in ('ESTACIONADO', 'FINALIZADO', 'CANCELADO')),
    valor_total numeric(10, 2) check (valor_total is null or valor_total >= 0),
    operador_id uuid references auth.users(id) on delete set null,
    constraint chk_saida_apos_entrada check (saida is null or saida >= entrada)
);

create unique index if not exists idx_unica_sessao_aberta_por_placa
    on public.sessoes (placa)
    where (status = 'ESTACIONADO');

create index if not exists idx_sessoes_status_entrada
    on public.sessoes (status, entrada desc);

create table if not exists public.pagamentos (
    id uuid primary key default gen_random_uuid(),
    ticket_id text not null unique references public.sessoes(ticket_id) on delete restrict,
    metodo text not null check (metodo in ('PIX', 'CARTAO', 'DINHEIRO')),
    valor numeric(10, 2) not null check (valor >= 0),
    pago_em timestamptz not null default now(),
    operador_id uuid references auth.users(id) on delete set null
);

create index if not exists idx_pagamentos_pago_em
    on public.pagamentos (pago_em desc);

alter table public.vagas enable row level security;
alter table public.veiculos enable row level security;
alter table public.sessoes enable row level security;
alter table public.pagamentos enable row level security;

create policy "operadores_leem_vagas"
    on public.vagas for select
    to authenticated
    using (auth.uid() is not null);

create policy "operadores_gerenciam_vagas"
    on public.vagas for all
    to authenticated
    using (auth.uid() is not null)
    with check (auth.uid() is not null);

create policy "operadores_gerenciam_veiculos"
    on public.veiculos for all
    to authenticated
    using (auth.uid() is not null)
    with check (auth.uid() is not null);

create policy "operadores_gerenciam_sessoes"
    on public.sessoes for all
    to authenticated
    using (auth.uid() is not null)
    with check (auth.uid() is not null);

create policy "operadores_gerenciam_pagamentos"
    on public.pagamentos for all
    to authenticated
    using (auth.uid() is not null)
    with check (auth.uid() is not null);

insert into public.vagas (codigo, setor, ocupada) values
    ('A-01', 'A', false), ('A-02', 'A', false), ('A-03', 'A', false), ('A-04', 'A', false),
    ('A-05', 'A', false), ('B-01', 'B', false), ('B-02', 'B', false), ('B-03', 'B', false),
    ('B-04', 'B', false), ('C-01', 'C', false), ('C-02', 'C', false), ('C-03', 'C', false)
on conflict (codigo) do nothing;
