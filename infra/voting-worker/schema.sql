-- canvas-toolbox voting system D1 database schema

CREATE TABLE IF NOT EXISTS votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feature_id TEXT NOT NULL,
  user_hash TEXT NOT NULL,
  source TEXT DEFAULT 'cli',  -- 'cli' | 'web' | 'agent'
  voted_at TEXT NOT NULL,     -- ISO 8601 timestamp
  UNIQUE(feature_id, user_hash)  -- One vote per user per feature
);

-- Index for fast vote count queries
CREATE INDEX IF NOT EXISTS idx_feature_id ON votes(feature_id);

-- Index for analytics (if needed later)
CREATE INDEX IF NOT EXISTS idx_voted_at ON votes(voted_at);
