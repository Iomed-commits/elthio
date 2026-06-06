-- Run in Supabase SQL Editor before using Save My Stack

CREATE TABLE IF NOT EXISTS saved_stacks (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL,
  medications   jsonb NOT NULL DEFAULT '[]',
  supplements   jsonb NOT NULL DEFAULT '[]',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  last_checked  timestamptz,
  check_count   integer NOT NULL DEFAULT 0,
  CONSTRAINT saved_stacks_email_unique UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS stack_checks (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email           text NOT NULL,
  medications     jsonb NOT NULL DEFAULT '[]',
  supplements     jsonb NOT NULL DEFAULT '[]',
  interaction_ids jsonb NOT NULL DEFAULT '[]',
  severity_counts jsonb NOT NULL DEFAULT '{}',
  checked_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_stacks_email ON saved_stacks(email);
CREATE INDEX IF NOT EXISTS idx_stack_checks_email ON stack_checks(email);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS saved_stacks_updated_at ON saved_stacks;
CREATE TRIGGER saved_stacks_updated_at
  BEFORE UPDATE ON saved_stacks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
