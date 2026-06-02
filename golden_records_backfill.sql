-- Run once in Supabase SQL Editor after golden_records_fix.sql
-- Fills product_name, brand, etc. from the record jsonb column (and backfills old rows)

UPDATE public.golden_records
SET
  product_name = COALESCE(product_name, record->>'product_name'),
  brand = COALESCE(brand, record->>'brand'),
  upc = COALESCE(upc, record->>'upc'),
  dsld_id = COALESCE(dsld_id, record->>'dsld_id'),
  overall_status = COALESCE(overall_status, record->>'overall_status'),
  source_url = COALESCE(source_url, record->>'source_url')
WHERE record IS NOT NULL;
