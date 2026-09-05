PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS settings (
  user_id           INTEGER PRIMARY KEY REFERENCES users(id),
  new_cards_per_day INTEGER NOT NULL DEFAULT 15,
  daily_review_cap  INTEGER NOT NULL DEFAULT 120,
  desired_retention REAL    NOT NULL DEFAULT 0.90
);

CREATE TABLE IF NOT EXISTS topics (
  id      INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  code    TEXT NOT NULL,
  label   TEXT NOT NULL,
  meta    TEXT,  -- JSON: full_name, credits, units[], scheme{}, ca_policy, mte_exists, exam_format
  UNIQUE(user_id, code)
);

CREATE TABLE IF NOT EXISTS sources (
  id       INTEGER PRIMARY KEY,
  user_id  INTEGER NOT NULL REFERENCES users(id),
  topic_id INTEGER NOT NULL REFERENCES topics(id),
  filename TEXT NOT NULL,
  kind     TEXT NOT NULL,
  sha256   TEXT NOT NULL,
  added_at TEXT NOT NULL,
  UNIQUE(user_id, sha256)
);

CREATE TABLE IF NOT EXISTS chunks (
  id           INTEGER PRIMARY KEY,
  source_id    INTEGER NOT NULL REFERENCES sources(id),
  ordinal      INTEGER NOT NULL,
  text         TEXT NOT NULL,
  page_ref     TEXT NOT NULL,
  generated_at TEXT,
  UNIQUE(source_id, ordinal)
);

CREATE TABLE IF NOT EXISTS cards (
  id            INTEGER PRIMARY KEY,
  chunk_id      INTEGER NOT NULL REFERENCES chunks(id),
  topic_id      INTEGER NOT NULL REFERENCES topics(id),
  kind          TEXT NOT NULL CHECK (kind IN ('qa','cloze')),
  question      TEXT NOT NULL,
  answer        TEXT NOT NULL,
  cloze_text    TEXT,
  arm           TEXT NOT NULL CHECK (arm IN ('learned','baseline')),
  state         TEXT NOT NULL CHECK (state IN ('pending','active','suspended','rejected')),
  reject_reason TEXT,
  created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_state ON cards(state);
CREATE INDEX IF NOT EXISTS idx_cards_topic ON cards(topic_id);

CREATE TABLE IF NOT EXISTS gen_runs (
  id                INTEGER PRIMARY KEY,
  source_id         INTEGER NOT NULL REFERENCES sources(id),
  ran_at            TEXT NOT NULL,
  model             TEXT NOT NULL,
  prompt_tokens     INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost_estimate     REAL NOT NULL DEFAULT 0.0,
  cards_accepted    INTEGER NOT NULL DEFAULT 0,
  cards_rejected    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reviews (
  id                INTEGER PRIMARY KEY,
  card_id           INTEGER NOT NULL REFERENCES cards(id),
  user_id           INTEGER NOT NULL REFERENCES users(id),
  reviewed_at       TEXT NOT NULL,
  grade             INTEGER NOT NULL CHECK (grade BETWEEN 1 AND 4),
  elapsed_days      REAL NOT NULL,
  predicted_r       REAL,
  scheduler_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_card ON reviews(card_id, reviewed_at);

CREATE TABLE IF NOT EXISTS card_state (
  card_id    INTEGER NOT NULL REFERENCES cards(id),
  user_id    INTEGER NOT NULL REFERENCES users(id),
  stability  REAL NOT NULL,
  difficulty REAL NOT NULL,
  due_at     TEXT NOT NULL,
  reps       INTEGER NOT NULL DEFAULT 0,
  lapses     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (card_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_card_state_due ON card_state(user_id, due_at);

CREATE TABLE IF NOT EXISTS fit_runs (
  id           INTEGER PRIMARY KEY,
  ran_at       TEXT NOT NULL,
  n_reviews    INTEGER NOT NULL,
  params_json  TEXT NOT NULL,
  val_logloss  REAL NOT NULL
);

-- Test mode: sit a paper of a given mark total, then feed the results back into
-- the scheduler so what you got wrong actually comes back sooner.
CREATE TABLE IF NOT EXISTS tests (
  id             INTEGER PRIMARY KEY,
  user_id        INTEGER NOT NULL REFERENCES users(id),
  kind           TEXT NOT NULL CHECK (kind IN ('class30','mte40','endterm100','fullday')),
  topic_id       INTEGER REFERENCES topics(id),
  target_marks   INTEGER NOT NULL,
  total_marks    INTEGER NOT NULL,
  time_limit_s   INTEGER,
  started_at     TEXT NOT NULL,
  submitted_at   TEXT,
  duration_s     INTEGER,
  obtained_marks REAL
);
CREATE INDEX IF NOT EXISTS idx_tests_user ON tests(user_id, started_at);

CREATE TABLE IF NOT EXISTS test_questions (
  id        INTEGER PRIMARY KEY,
  test_id   INTEGER NOT NULL REFERENCES tests(id),
  card_id   INTEGER NOT NULL REFERENCES cards(id),
  ordinal   INTEGER NOT NULL,
  marks     INTEGER NOT NULL,
  verdict   TEXT CHECK (verdict IN ('correct','partial','wrong','skipped')),
  seconds   INTEGER,
  UNIQUE(test_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_test_questions_test ON test_questions(test_id);

-- Teaching: a grounded explanation of a card that was missed. Cached by card
-- because explanations cost money and the same card gets missed repeatedly.
CREATE TABLE IF NOT EXISTS card_explanations (
  id           INTEGER PRIMARY KEY,
  card_id      INTEGER NOT NULL UNIQUE REFERENCES cards(id) ON DELETE CASCADE,
  explanation  TEXT NOT NULL,
  source_quote TEXT NOT NULL,
  model        TEXT NOT NULL,
  created_at   TEXT NOT NULL
);
