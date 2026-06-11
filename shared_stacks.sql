-- Run once in Supabase: Dashboard → SQL → New query → Run
-- Public shareable supplement stacks (backend writes via service role).

CREATE TABLE IF NOT EXISTS public.shared_stacks (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            text NOT NULL UNIQUE,
  email           text,
  medications     jsonb NOT NULL DEFAULT '[]',
  supplements     jsonb NOT NULL DEFAULT '[]',
  safety_score    integer,
  safety_band     text,
  interactions    jsonb NOT NULL DEFAULT '[]',
  synergies       jsonb NOT NULL DEFAULT '[]',
  near_misses     jsonb NOT NULL DEFAULT '[]',
  title           text DEFAULT 'My Supplement Stack',
  note            text,
  view_count      integer DEFAULT 0,
  created_at      timestamptz DEFAULT now(),
  expires_at      timestamptz DEFAULT (now() + interval '90 days')
);

CREATE INDEX IF NOT EXISTS idx_shared_stacks_slug
  ON public.shared_stacks(slug);
CREATE INDEX IF NOT EXISTS idx_shared_stacks_email
  ON public.shared_stacks(email);

CREATE OR REPLACE FUNCTION increment_view_count(stack_slug text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  UPDATE shared_stacks
  SET view_count = view_count + 1
  WHERE slug = stack_slug;
END;
$$;

ALTER TABLE public.shared_stacks ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.shared_stacks FROM anon, authenticated;
