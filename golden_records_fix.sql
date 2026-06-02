-- Fixes golden_records schema for Elthio (PGRST204 missing record column)

ALTER TABLE public.golden_records
  ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES auth.users (id) ON DELETE CASCADE;

ALTER TABLE public.golden_records
  ADD COLUMN IF NOT EXISTS record jsonb;

ALTER TABLE public.golden_records
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

UPDATE public.golden_records SET record = '{}'::jsonb WHERE record IS NULL;

ALTER TABLE public.golden_records ALTER COLUMN record SET NOT NULL;

CREATE INDEX IF NOT EXISTS golden_records_user_created_idx
  ON public.golden_records (user_id, created_at DESC);

ALTER TABLE public.golden_records ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS golden_records_insert_own ON public.golden_records;
CREATE POLICY golden_records_insert_own ON public.golden_records
  FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS golden_records_select_own ON public.golden_records;
CREATE POLICY golden_records_select_own ON public.golden_records
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

NOTIFY pgrst, 'reload schema';
