-- Run once in Supabase: Dashboard → SQL → New query → Run
-- Stores Safety Score snapshots when user saves email on Med Check.
-- Backend writes via service role (bypasses RLS). No public/anon access.

CREATE TABLE IF NOT EXISTS public.safety_scores (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email       text NOT NULL,
  score       integer NOT NULL,
  band        text,
  medications jsonb DEFAULT '[]',
  supplements jsonb DEFAULT '[]',
  checked_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_safety_scores_email
  ON public.safety_scores(email);
CREATE INDEX IF NOT EXISTS idx_safety_scores_checked_at
  ON public.safety_scores(checked_at DESC);

-- Fix "RLS Disabled in Public" — block anon/authenticated PostgREST access.
-- Service role (Railway backend) bypasses RLS and can still insert/select.
ALTER TABLE public.safety_scores ENABLE ROW LEVEL SECURITY;

-- Revoke direct API access from browser clients (backend uses service role only)
REVOKE ALL ON public.safety_scores FROM anon, authenticated;
