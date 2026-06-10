-- Elthio pgvector — interaction rule embeddings
-- Run once in Supabase SQL Editor before: python vector_search.py --index

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.interaction_embeddings (
  id          text PRIMARY KEY,
  rule_data   jsonb NOT NULL,
  rule_type   text,
  severity    text,
  is_synergy  boolean DEFAULT false,
  embedding   vector(1536),
  created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_interaction_embeddings_type
  ON public.interaction_embeddings(rule_type);

ALTER TABLE public.interaction_embeddings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.interaction_embeddings FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.match_interactions(
  query_embedding vector(1536),
  match_threshold float,
  match_count int,
  filter_type text DEFAULT NULL
)
RETURNS TABLE (
  id text,
  rule_data jsonb,
  rule_type text,
  severity text,
  is_synergy boolean,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    ie.id,
    ie.rule_data,
    ie.rule_type,
    ie.severity,
    ie.is_synergy,
    1 - (ie.embedding <=> query_embedding) AS similarity
  FROM public.interaction_embeddings ie
  WHERE 1 - (ie.embedding <=> query_embedding) > match_threshold
    AND (filter_type IS NULL OR ie.rule_type = filter_type)
  ORDER BY ie.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
