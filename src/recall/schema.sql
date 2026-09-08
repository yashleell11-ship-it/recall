PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  email         TEXT,
  password_hash TEXT,
  created_at    TEXT
);
-- The unique index on email is created in db.py's _migrate(), not here: this
-- script runs (via executescript) BEFORE _migrate() adds the email column to
-- a pre-existing users table, and CREATE TABLE IF NOT EXISTS is a no-op on a
-- table that already exists — so an index statement here would fail with
-- "no such column: email" on any database older than this change.

-- Open registration: one row per logged-in session, looked up by the hash of
-- the opaque token in the "recall_session" cookie — the raw token is never
-- stored, so a copy of this database alone can't be used to impersonate
-- anyone. DB-backed rather than JWT: revocation (logout, killing an abusive
-- account) is a DELETE, and there's no signing secret to protect or rotate.
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

-- Per-user, per-day DeepSeek spend, so open registration can't run up the
-- shared API budget: one row summed and checked before any generation call,
-- upload-grounded or knowledge-mode alike.
CREATE TABLE IF NOT EXISTS usage_daily (
  user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day      TEXT NOT NULL,  -- YYYY-MM-DD, UTC
  cost_usd REAL NOT NULL DEFAULT 0.0,
  PRIMARY KEY (user_id, day)
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
  created_at    TEXT NOT NULL,
  -- 'upload'    = grounded in a verbatim quote from a file you uploaded.
  -- 'knowledge' = written from the model's own knowledge of a syllabus unit,
  --               with no source to check it against. The UI must say which,
  --               because the two carry very different warranties.
  origin        TEXT NOT NULL DEFAULT 'upload'
                CHECK (origin IN ('upload','knowledge')),
  -- The full explanation, shown AFTER the answer is revealed.
  --
  -- Deliberately not part of `answer`: answer is the retrieval target you
  -- must produce cold, and testmode/marks.py prices a question by its answer's
  -- word count (<=4 words -> 1 mark, <=12 -> 2, longer -> 5). Fattening
  -- `answer` with detail would silently make every card a 5-marker and turn a
  -- 40-mark MTE into eight questions. Detail lives here, where depth costs
  -- nothing: it is read after retrieval has already been attempted.
  detail        TEXT
);
CREATE INDEX IF NOT EXISTS idx_cards_state ON cards(state);
CREATE INDEX IF NOT EXISTS idx_cards_topic ON cards(topic_id);
-- idx_cards_origin is created in db.py's _migrate(), for the same reason as
-- idx_users_email: this script runs before the ALTER that adds the column to
-- a pre-existing table, and indexing a column that is not there yet fails.

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
  obtained_marks REAL,
  -- Which syllabus units the paper was scoped to: a JSON array of 0-based
  -- indices, or NULL for a paper drawn from the whole subject.
  units_json     TEXT
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
-- "Was this card asked recently, and how did it go?" — the lookup that keeps a
-- new paper from repeating the paper you sat yesterday. Without it that is a
-- full scan of every question ever asked, once per candidate card.
CREATE INDEX IF NOT EXISTS idx_test_questions_card ON test_questions(card_id);

-- Which syllabus units a source serves, for corpus material collected against
-- a course rather than uploaded blind.
--
-- The manifest maps files to unit NUMBERS. Numbers are positions and a
-- syllabus is editable, so the number is resolved to a NAME at load time and
-- the name is what is stored — the same rule chunks, cards and lessons already
-- follow. A corpus mapped by ordinal would silently re-point at a different
-- unit the first time one was inserted.
--
-- OWNERSHIP: source_id -> sources.user_id.
CREATE TABLE IF NOT EXISTS source_units (
  source_id INTEGER NOT NULL REFERENCES sources(id),
  unit_name TEXT NOT NULL,
  unit_key  TEXT NOT NULL,
  PRIMARY KEY (source_id, unit_key)
);
CREATE INDEX IF NOT EXISTS idx_source_units_key ON source_units(unit_key);

-- Teaching: a written lesson for one syllabus unit.
--
-- OWNERSHIP: `chunk_id` -> chunks -> sources.user_id. There is no user_id
-- column here for the same reason cards has none: the owner is reachable, and
-- adding a second answer to "whose is this" is how the two drift apart. Every
-- read below joins sources and filters on it.
--
-- IDENTITY: the unit CHUNK, never a unit name or an index. seed.py's
-- _follow_renamed_units rewrites chunks.text in place for a declared rename
-- and never changes chunks.id, so a lesson follows its unit across a rename
-- with no code and no second rename mechanism to forget.
--
-- No CHECK constraint on any column: this table will acquire inbound foreign
-- keys, and a later rebuild to alter a CHECK is what left test_questions
-- pointing at tests_old. `status` is validated in Python.
CREATE TABLE IF NOT EXISTS lessons (
  id          INTEGER PRIMARY KEY,
  chunk_id    INTEGER NOT NULL REFERENCES chunks(id),
  topic_id    INTEGER NOT NULL REFERENCES topics(id),
  body_json   TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'draft',
  notes       TEXT,
  model       TEXT NOT NULL,
  cost_usd    REAL NOT NULL DEFAULT 0.0,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lessons_chunk ON lessons(chunk_id, id);

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
