-- Elthio affiliate feed cache schema
-- Run in the Supabase dashboard under SQL Editor.
-- Populated by feed_manager.py (run daily via cron / Railway scheduled job).

create table if not exists elthio_products (
  id                   uuid default gen_random_uuid() primary key,
  retailer             text not null,
  retailer_id          text not null,
  brand                text,
  product_name         text,
  supplement_type      text,
  form                 text,
  dose_amount          numeric,
  dose_unit            text,
  servings             integer,
  price                numeric,
  cost_per_serving     numeric,
  cost_per_active_unit numeric,
  form_score           integer,
  dose_adequacy        text,
  value_score          integer,
  image_url            text,
  product_url          text,
  affiliate_url        text,
  in_stock             boolean default true,
  verified             boolean default false,
  verification_type    text,
  last_updated         timestamptz default now(),
  unique (retailer, retailer_id)
);

create index if not exists idx_elthio_products_type
  on elthio_products (supplement_type, value_score desc);

create index if not exists idx_elthio_products_retailer
  on elthio_products (retailer, supplement_type);

create table if not exists elthio_price_history (
  id          uuid default gen_random_uuid() primary key,
  retailer    text not null,
  retailer_id text not null,
  price       numeric not null,
  recorded_at timestamptz default now()
);

create index if not exists idx_price_history_lookup
  on elthio_price_history (retailer, retailer_id, recorded_at desc);
