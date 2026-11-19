create table if not exists public.perfis_usuarios (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
  nome text not null,
  papel text not null default 'funcionario' check (papel in ('admin', 'funcionario')),
  ativo boolean not null default true,
  permissoes jsonb not null default '{
    "overview": true,
    "vehicles": true,
    "camera": true,
    "spots": true,
    "tickets": true,
    "payments": true,
    "reports": false,
    "settings": false
  }'::jsonb,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create or replace function public.eh_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.perfis_usuarios
    where id = auth.uid()
      and papel = 'admin'
      and ativo = true
  );
$$;

create or replace function public.criar_perfil_novo_usuario()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.perfis_usuarios (id, email, nome)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'nome', split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists trg_criar_perfil_novo_usuario on auth.users;
create trigger trg_criar_perfil_novo_usuario
  after insert on auth.users
  for each row execute function public.criar_perfil_novo_usuario();

alter table public.perfis_usuarios enable row level security;

drop policy if exists "usuario_le_proprio_perfil" on public.perfis_usuarios;
create policy "usuario_le_proprio_perfil"
  on public.perfis_usuarios
  for select
  to authenticated
  using (auth.uid() = id);

drop policy if exists "admin_le_todos_perfis" on public.perfis_usuarios;
create policy "admin_le_todos_perfis"
  on public.perfis_usuarios
  for select
  to authenticated
  using (public.eh_admin());

drop policy if exists "admin_atualiza_perfis" on public.perfis_usuarios;
create policy "admin_atualiza_perfis"
  on public.perfis_usuarios
  for update
  to authenticated
  using (public.eh_admin())
  with check (public.eh_admin());
