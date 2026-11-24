alter table if exists public.veiculos
  add column if not exists marca text,
  add column if not exists modelo text;

create table if not exists public.configuracoes_tarifa (
  id integer primary key default 1 check (id = 1),
  modo_cobranca text not null default 'TEMPO' check (modo_cobranca in ('TEMPO', 'FIXO')),
  valor_hora numeric(10, 2) not null default 10.00,
  valor_fixo numeric(10, 2) not null default 20.00,
  atualizado_em timestamptz not null default now()
);

insert into public.configuracoes_tarifa (id, modo_cobranca, valor_hora, valor_fixo)
values (1, 'TEMPO', 10.00, 20.00)
on conflict (id) do nothing;

alter table public.configuracoes_tarifa enable row level security;

drop policy if exists "autenticados_leem_tarifa" on public.configuracoes_tarifa;
create policy "autenticados_leem_tarifa"
  on public.configuracoes_tarifa
  for select
  to authenticated
  using (true);

drop policy if exists "admin_atualiza_tarifa" on public.configuracoes_tarifa;
create policy "admin_atualiza_tarifa"
  on public.configuracoes_tarifa
  for update
  to authenticated
  using (public.eh_admin())
  with check (public.eh_admin());
