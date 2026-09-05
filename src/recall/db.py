import sqlite3
from importlib import resources


def connect(db_path: str) -> sqlite3.Connection:
    # check_same_thread=False because FastAPI runs a sync dependency's setup and
    # its teardown on DIFFERENT threadpool threads, so the connection is opened in
    # one thread and closed in another. Safe here: every request gets its own
    # connection and uses it sequentially, so no connection is ever shared between
    # concurrent threads. Without this, a page that fires several requests at once
    # 500s on most of them.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    # Repair BEFORE the schema script: a table whose foreign key dangles at a
    # dropped table makes even CREATE INDEX IF NOT EXISTS fail, because SQLite
    # re-parses the referencing table's definition on the way.
    _repair_dangling_test_questions(conn)
    sql = resources.files("recall").joinpath("schema.sql").read_text()
    conn.executescript(sql)
    _migrate(conn)
    conn.commit()


def _repair_dangling_test_questions(conn: sqlite3.Connection) -> None:
    """Fix databases the earlier, wrong-order tests rebuild damaged.

    That migration renamed the OLD tests table away, which rewrote
    test_questions' foreign key to "tests_old" — then dropped tests_old.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='test_questions'"
    ).fetchone()
    if not (row and "tests_old" in (row["sql"] or "")):
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("""CREATE TABLE test_questions_new (
          id        INTEGER PRIMARY KEY,
          test_id   INTEGER NOT NULL REFERENCES tests(id),
          card_id   INTEGER NOT NULL REFERENCES cards(id),
          ordinal   INTEGER NOT NULL,
          marks     INTEGER NOT NULL,
          verdict   TEXT CHECK (verdict IN ('correct','partial','wrong','skipped')),
          seconds   INTEGER,
          UNIQUE(test_id, ordinal)
        )""")
        conn.execute("INSERT INTO test_questions_new SELECT * FROM test_questions")
        conn.execute("DROP TABLE test_questions")
        conn.execute("ALTER TABLE test_questions_new RENAME TO test_questions")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_test_questions_test ON test_questions(test_id)"
        )
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a pre-existing database up to the current schema.

    schema.sql is CREATE IF NOT EXISTS, so it never alters live tables; the
    deltas that need real migration live here, each one idempotent.
    """
    # topics.meta (2026-09-05, LPU subject metadata)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(topics)").fetchall()}
    if cols and "meta" not in cols:
        conn.execute("ALTER TABLE topics ADD COLUMN meta TEXT")

    # tests.kind CHECK gained 'mte40'. SQLite cannot alter a CHECK, so rebuild —
    # and the ORDER MATTERS: renaming the OLD table away rewrites every foreign
    # key that pointed at it (test_questions ended up referencing "tests_old"),
    # so the new table is built under a temp name and renamed INTO place last,
    # per the documented 12-step recipe.
    _TESTS_DDL = """(
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
                )"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tests'"
    ).fetchone()
    if row and "mte40" not in (row["sql"] or ""):
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute(f"CREATE TABLE tests_new {_TESTS_DDL}")
            conn.execute("INSERT INTO tests_new SELECT * FROM tests")
            conn.execute("DROP TABLE tests")
            conn.execute("ALTER TABLE tests_new RENAME TO tests")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tests_user ON tests(user_id, started_at)"
            )
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
