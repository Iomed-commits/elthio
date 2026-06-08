CREATE TABLE IF NOT EXISTS pharmacy_history (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email       text NOT NULL,
  medications jsonb NOT NULL DEFAULT '[]',
  parsed_at   timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pharmacy_email
  ON pharmacy_history(email);
