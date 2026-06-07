-- Elthio + Biologer — Price Monitor schema
-- Run in Supabase SQL Editor

-- Product prices table (one row per retailer URL)
CREATE TABLE IF NOT EXISTS product_prices (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  supplement_name   text NOT NULL,
  brand             text,
  product_title     text,
  retailer          text NOT NULL,
  price_usd         numeric(8,2),
  serving_size      text,
  servings          integer,
  cost_per_serving  numeric(8,4),
  form              text,
  in_stock          boolean DEFAULT true,
  affiliate_url     text NOT NULL,
  source_type       text NOT NULL DEFAULT 'scraped',
  nih_status        text DEFAULT 'UNVERIFIED',
  nih_confidence    integer DEFAULT 0,
  nih_dsld_id       text,
  last_checked      timestamptz DEFAULT now(),
  created_at        timestamptz DEFAULT now(),
  CONSTRAINT product_prices_url_unique UNIQUE (affiliate_url)
);

-- Monitor list (URLs to check on schedule)
CREATE TABLE IF NOT EXISTS monitor_urls (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  url             text NOT NULL UNIQUE,
  retailer        text NOT NULL,
  supplement_name text NOT NULL,
  source_type     text NOT NULL DEFAULT 'scraped',
  affiliate_tag   text,
  active          boolean DEFAULT true,
  added_at        timestamptz DEFAULT now(),
  last_run        timestamptz,
  last_status     text
);

-- Indexes for fast supplement name search
CREATE INDEX IF NOT EXISTS idx_product_prices_name
  ON product_prices(supplement_name);
CREATE INDEX IF NOT EXISTS idx_product_prices_retailer
  ON product_prices(retailer);
CREATE INDEX IF NOT EXISTS idx_product_prices_nih
  ON product_prices(nih_status);

-- Seed the monitor list with core supplements across retailers
INSERT INTO monitor_urls (url, retailer, supplement_name, source_type, affiliate_tag)
VALUES
  ('https://www.lifeextension.com/vitamins-supplements/item01913/vitamin-d3',
   'life_extension', 'vitamin d3', 'scraped', '?source=elthio'),
  ('https://www.lifeextension.com/vitamins-supplements/item01700/magnesium',
   'life_extension', 'magnesium', 'scraped', '?source=elthio'),
  ('https://www.lifeextension.com/vitamins-supplements/item01327/vitamin-c',
   'life_extension', 'vitamin c', 'scraped', '?source=elthio'),
  ('https://www.lifeextension.com/vitamins-supplements/item01426/coq10',
   'life_extension', 'coq10', 'scraped', '?source=elthio'),
  ('https://www.lifeextension.com/vitamins-supplements/item02121/omega-3',
   'life_extension', 'omega-3', 'scraped', '?source=elthio'),
  ('https://www.iherb.com/pr/now-foods-vitamin-d-3-high-potency-125-mcg-5-000-iu-240-softgels/22335',
   'iherb', 'vitamin d3', 'scraped', '?rcode=ELTHIO'),
  ('https://www.iherb.com/pr/now-foods-magnesium-citrate-180-softgels/745',
   'iherb', 'magnesium', 'scraped', '?rcode=ELTHIO'),
  ('https://www.iherb.com/pr/now-foods-vitamin-c-1000-mg-with-bioflavonoids-100-tablets/471',
   'iherb', 'vitamin c', 'scraped', '?rcode=ELTHIO'),
  ('https://www.iherb.com/pr/now-foods-coq10-100-mg-150-veg-capsules/422',
   'iherb', 'coq10', 'scraped', '?rcode=ELTHIO'),
  ('https://www.iherb.com/pr/now-foods-omega-3-180-epa-120-dha-200-softgels/571',
   'iherb', 'omega-3', 'scraped', '?rcode=ELTHIO')
ON CONFLICT (url) DO NOTHING;
