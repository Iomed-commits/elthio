CREATE TABLE IF NOT EXISTS safety_scores (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email       text NOT NULL,
  score       integer NOT NULL,
  band        text,
  medications jsonb DEFAULT '[]',
  supplements jsonb DEFAULT '[]',
  checked_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_safety_scores_email
  ON safety_scores(email);
CREATE INDEX IF NOT EXISTS idx_safety_scores_checked_at
  ON safety_scores(checked_at DESC);
