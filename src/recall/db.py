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
    sql = resources.files("recall").joinpath("schema.sql").read_text()
    conn.executescript(sql)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a pre-existing database up to the current schema.

    schema.sql is CREATE IF NOT EXISTS, so it never alters live tables; the
    deltas that need real migration live here, each one idempotent.
    """
    # topics.meta (2026-09-05, LPU subject metadata)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(topics)").fetchall()}
    if cols and "meta" not in cols:
        conn.execute("ALTER TABLE topics ADD COLUMN meta TEXT")

    # tests.kind CHECK gained 'mte40'. SQLite cannot alter a CHECK, so rebuild.
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tests'"
    ).fetchone()
    if row and "mte40" not in (row["sql"] or ""):
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute("ALTER TABLE tests RENAME TO tests_old")
            conn.execute(
                """CREATE TABLE tests (
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
            )
            conn.execute("INSERT INTO tests SELECT * FROM tests_old")
            conn.execute("DROP TABLE tests_old")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tests_user ON tests(user_id, started_at)"
            )
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
