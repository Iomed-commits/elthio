-- Run this in Supabase: Dashboard → SQL → New query → Run
-- Enables cloud Golden Records when you audit while signed in.

create table if not exists public.golden_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  record jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists golden_records_user_created_idx
  on public.golden_records (user_id, created_at desc);

alter table public.golden_records enable row level security;

drop policy if exists golden_records_insert_own on public.golden_records;
create policy golden_records_insert_own on public.golden_records
  for insert to authenticated
  with check (auth.uid() = user_id);

drop policy if exists golden_records_select_own on public.golden_records;
create policy golden_records_select_own on public.golden_records
  for select to authenticated
  using (auth.uid() = user_id);
