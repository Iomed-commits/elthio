-- Run once in Supabase: Dashboard → SQL → New query → Run
-- Stores Med Check session snapshots for returning-user context.
-- Backend writes via service role (bypasses RLS). No public/anon access.

CREATE TABLE IF NOT EXISTS public.conversation_memory (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email            text NOT NULL,
  session_date     timestamptz DEFAULT now(),
  medications      jsonb DEFAULT '[]',
  supplements      jsonb DEFAULT '[]',
  safety_score     integer,
  critical_count   integer DEFAULT 0,
  high_count       integer DEFAULT 0,
  moderate_count   integer DEFAULT 0,
  top_interactions jsonb DEFAULT '[]',
  synergies_found  jsonb DEFAULT '[]',
  resolved_flags   jsonb DEFAULT '[]',
  summary          text,
  CONSTRAINT conversation_memory_email_date
    UNIQUE (email, session_date)
);

CREATE INDEX IF NOT EXISTS idx_conv_memory_email
  ON public.conversation_memory(email);
CREATE INDEX IF NOT EXISTS idx_conv_memory_date
  ON public.conversation_memory(session_date DESC);

ALTER TABLE public.conversation_memory ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.conversation_memory FROM anon, authenticated;
