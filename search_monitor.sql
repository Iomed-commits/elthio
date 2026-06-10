-- Elthio — Search-based price monitor schema
-- Run in Supabase SQL Editor

DROP TABLE IF EXISTS monitor_urls;

CREATE TABLE IF NOT EXISTS tracked_supplements (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL UNIQUE,
  search_terms  jsonb NOT NULL DEFAULT '[]',
  forms         jsonb NOT NULL DEFAULT '[]',
  min_dose      text,
  category      text DEFAULT 'general',
  active        boolean DEFAULT true,
  created_at    timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS retailers (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name            text NOT NULL UNIQUE,
  display_name    text NOT NULL,
  source_type     text NOT NULL DEFAULT 'scrape',
  search_url      text,
  api_endpoint    text,
  affiliate_tag   text,
  active          boolean DEFAULT true,
  priority        integer DEFAULT 5,
  notes           text
);

ALTER TABLE product_prices
  ADD COLUMN IF NOT EXISTS search_query text,
  ADD COLUMN IF NOT EXISTS rank_in_results integer;

CREATE INDEX IF NOT EXISTS idx_tracked_supps_name
  ON tracked_supplements(name);
CREATE INDEX IF NOT EXISTS idx_retailers_name
  ON retailers(name);
CREATE INDEX IF NOT EXISTS idx_product_prices_supp_retailer
  ON product_prices(supplement_name, retailer);

INSERT INTO tracked_supplements (name, search_terms, forms, min_dose, category)
VALUES
  ('magnesium glycinate',
   '["magnesium glycinate", "magnesium bisglycinate", "magnesium bis-glycinate"]',
   '["glycinate", "bisglycinate", "bis-glycinate"]',
   '200mg', 'minerals'),
  ('vitamin d3',
   '["vitamin d3", "vitamin d-3", "cholecalciferol", "vitamin d 5000 iu"]',
   '["cholecalciferol"]',
   '1000 IU', 'vitamins'),
  ('coq10 ubiquinol',
   '["coq10 ubiquinol", "ubiquinol coq10", "coenzyme q10 ubiquinol"]',
   '["ubiquinol"]',
   '100mg', 'antioxidants'),
  ('coq10 ubiquinone',
   '["coq10", "coenzyme q10", "ubiquinone coq10"]',
   '["ubiquinone"]',
   '100mg', 'antioxidants'),
  ('omega-3 fish oil',
   '["omega-3 fish oil", "omega 3 epa dha", "fish oil epa dha", "ultra omega-3"]',
   '["triglyceride", "ethyl ester", "re-esterified"]',
   '1000mg', 'fatty acids'),
  ('vitamin k2 mk7',
   '["vitamin k2 mk7", "vitamin k2 mk-7", "menaquinone-7", "mk7"]',
   '["mk7", "mk-7", "menaquinone-7"]',
   '100mcg', 'vitamins'),
  ('vitamin c',
   '["vitamin c 1000mg", "ascorbic acid 1000mg", "buffered vitamin c", "liposomal vitamin c"]',
   '["ascorbic acid", "buffered", "liposomal", "calcium ascorbate"]',
   '500mg', 'vitamins'),
  ('zinc picolinate',
   '["zinc picolinate", "zinc picolinate 30mg", "zinc picolinate 50mg"]',
   '["picolinate"]',
   '15mg', 'minerals'),
  ('magnesium malate',
   '["magnesium malate", "magnesium malate 1000mg"]',
   '["malate"]',
   '200mg', 'minerals'),
  ('vitamin b12 methylcobalamin',
   '["methylcobalamin b12", "vitamin b12 methylcobalamin", "methyl b12"]',
   '["methylcobalamin", "methyl"]',
   '1000mcg', 'vitamins'),
  ('ashwagandha ksm-66',
   '["ashwagandha ksm-66", "ksm-66 ashwagandha", "ashwagandha extract ksm66"]',
   '["ksm-66", "ksm66"]',
   '300mg', 'adaptogens'),
  ('berberine',
   '["berberine hcl", "berberine hydrochloride", "berberine 500mg"]',
   '["hcl", "hydrochloride"]',
   '500mg', 'metabolic'),
  ('nac n-acetyl cysteine',
   '["nac n-acetyl cysteine", "n-acetyl-l-cysteine", "nac 600mg"]',
   '["n-acetyl-l-cysteine"]',
   '600mg', 'antioxidants'),
  ('alpha lipoic acid',
   '["alpha lipoic acid", "r-alpha lipoic acid", "r-ala", "ala 600mg"]',
   '["r-ala", "r-alpha", "racemic"]',
   '300mg', 'antioxidants'),
  ('vitamin d3 k2',
   '["vitamin d3 k2", "vitamin d3 with k2", "d3 k2 combo"]',
   '["cholecalciferol", "mk7"]',
   NULL, 'vitamins'),
  ('probiotics',
   '["probiotics 50 billion", "probiotics 100 billion", "multi-strain probiotic"]',
   '["lactobacillus", "bifidobacterium"]',
   '10 billion CFU', 'digestive'),
  ('turmeric curcumin',
   '["turmeric curcumin", "curcumin with bioperine", "turmeric extract 95%"]',
   '["curcuminoids", "bcm-95", "meriva", "with bioperine"]',
   '500mg', 'anti-inflammatory'),
  ('lion''s mane mushroom',
   '["lion''s mane mushroom", "hericium erinaceus", "lion''s mane extract"]',
   '["extract", "dual extract", "fruiting body"]',
   '500mg', 'nootropics'),
  ('resveratrol',
   '["resveratrol", "trans-resveratrol", "resveratrol 500mg"]',
   '["trans-resveratrol"]',
   '200mg', 'antioxidants'),
  ('fish oil high dha',
   '["high dha fish oil", "dha fish oil", "algae dha"]',
   '["high dha", "algae-based"]',
   '500mg DHA', 'fatty acids')
ON CONFLICT (name) DO NOTHING;

INSERT INTO retailers
  (name, display_name, source_type, search_url, affiliate_tag, active, priority, notes)
VALUES
  ('iherb', 'iHerb', 'scrape',
   'https://www.iherb.com/search?kw={query}&sr=contains&p=1',
   '?rcode=ELTHIO', true, 1,
   'Apply at iherb.com/info/affiliate-program for API access'),
  ('life_extension', 'Life Extension', 'scrape',
   'https://www.lifeextension.com/search#q={query}&t=product',
   '?source=elthio', true, 2,
   'Clean HTML, reliable scraping'),
  ('thorne', 'Thorne', 'scrape',
   'https://www.thorne.com/search#q={query}',
   '?affId=ELTHIO', true, 3,
   'Apply at thorne.com/affiliate for API access'),
  ('vitacost', 'Vitacost', 'scrape',
   'https://www.vitacost.com/search?t={query}&w=category',
   '?affId=ELTHIO', true, 4,
   'Good generic brand prices'),
  ('pure_encapsulations', 'Pure Encapsulations', 'scrape',
   'https://www.pureencapsulationspro.com/search?q={query}',
   '?ref=elthio', true, 5,
   'Professional grade, clean formulas'),
  ('amazon', 'Amazon', 'api_pending',
   NULL, '?tag=elthio-20', false, 6,
   'Requires Amazon Product Advertising API — apply at affiliate-program.amazon.com')
ON CONFLICT (name) DO UPDATE SET
  notes = EXCLUDED.notes,
  affiliate_tag = EXCLUDED.affiliate_tag;

-- RLS: price monitor tables are backend-only (price_monitor.py uses service role).
-- Enables RLS to clear Supabase "RLS Disabled in Public" warnings.
-- Service role bypasses RLS; anon/authenticated cannot read or write via PostgREST.
ALTER TABLE public.retailers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tracked_supplements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_prices ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.retailers FROM anon, authenticated;
REVOKE ALL ON public.tracked_supplements FROM anon, authenticated;
REVOKE ALL ON public.product_prices FROM anon, authenticated;
