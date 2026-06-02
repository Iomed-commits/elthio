-- Optional: cloud-synced meds & supplements for Separation Coach (signed-in users).
-- Run in Supabase SQL editor once.

create table if not exists public.medications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  dose text,
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists public.supplements (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  brand text,
  ingredients text,
  created_at timestamptz not null default now()
);

create index if not exists medications_user_idx on public.medications (user_id);
create index if not exists supplements_user_idx on public.supplements (user_id);

alter table public.medications enable row level security;
alter table public.supplements enable row level security;

drop policy if exists medications_own on public.medications;
create policy medications_own on public.medications
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists supplements_own on public.supplements;
create policy supplements_own on public.supplements
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
