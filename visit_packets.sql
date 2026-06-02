-- Run once in Supabase: Dashboard → SQL → New query → Run
-- Stores patient Visit Packet snapshots (JSON) for signed-in users.

create table if not exists public.visit_packets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  snapshot jsonb not null,
  patient_name text,
  visit_date text,
  created_at timestamptz not null default now()
);

create index if not exists visit_packets_user_created_idx
  on public.visit_packets (user_id, created_at desc);

alter table public.visit_packets enable row level security;

drop policy if exists visit_packets_insert_own on public.visit_packets;
create policy visit_packets_insert_own on public.visit_packets
  for insert to authenticated
  with check (auth.uid() = user_id);

drop policy if exists visit_packets_select_own on public.visit_packets;
create policy visit_packets_select_own on public.visit_packets
  for select to authenticated
  using (auth.uid() = user_id);
