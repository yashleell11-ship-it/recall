import json

from recall.db import connect, init_db
from recall.lpu import SUBJECTS
from recall.seed import seed_topics


def fresh(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.commit()
    return conn


def test_seed_creates_all_subjects_with_meta(tmp_path):
    conn = fresh(tmp_path)
    result = seed_topics(conn)
    assert set(result["created"]) == set(SUBJECTS)
    row = conn.execute("SELECT label, meta FROM topics WHERE code='MTH174'").fetchone()
    assert row["label"] == "Engineering Mathematics"
    meta = json.loads(row["meta"])
    assert len(meta["units"]) == 6
    assert meta["scheme"] == {"attendance": 5, "ca": 25, "mte": 20, "ete": 50}
    assert meta["mte_exists"] is True


def test_legacy_codes_are_renamed_in_place_keeping_ids(tmp_path):
    """Cards reference topic ids; a rename must never orphan them."""
    conn = fresh(tmp_path)
    conn.execute("INSERT INTO topics (id, user_id, code, label) VALUES (7, 1, 'MATHS', 'Mathematics')")
    conn.execute("INSERT INTO topics (id, user_id, code, label) VALUES (9, 1, 'HTML', 'HTML')")
    conn.commit()
    result = seed_topics(conn)
    assert "MATHS->MTH174" in result["renamed"]
    assert "HTML->CSE326" in result["renamed"]
    assert conn.execute("SELECT id FROM topics WHERE code='MTH174'").fetchone()["id"] == 7
    assert conn.execute("SELECT id FROM topics WHERE code='CSE326'").fetchone()["id"] == 9
    assert conn.execute("SELECT COUNT(*) n FROM topics WHERE code IN ('MATHS','HTML')").fetchone()["n"] == 0


def test_seed_is_idempotent(tmp_path):
    conn = fresh(tmp_path)
    seed_topics(conn)
    second = seed_topics(conn)
    assert second["created"] == []
    assert set(second["refreshed"]) == set(SUBJECTS)
    assert conn.execute("SELECT COUNT(*) n FROM topics").fetchone()["n"] == len(SUBJECTS)


def test_int108_and_cse326_have_no_mte(tmp_path):
    conn = fresh(tmp_path)
    seed_topics(conn)
    for code in ("INT108", "CSE326"):
        meta = json.loads(conn.execute(
            "SELECT meta FROM topics WHERE code=?", (code,)).fetchone()["meta"])
        assert meta["mte_exists"] is False, code


def test_migration_rebuilds_tests_check_for_mte40(tmp_path):
    """A live database created before the mte40 kind must accept it after init_db."""
    import sqlite3
    conn = connect(str(tmp_path / "old.db"))
    conn.executescript("""
      CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
      INSERT INTO users (id, name) VALUES (1, 'yash');
      CREATE TABLE topics (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
        code TEXT NOT NULL, label TEXT NOT NULL, UNIQUE(user_id, code));
      CREATE TABLE tests (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        kind TEXT NOT NULL CHECK (kind IN ('class30','endterm100','fullday')),
        topic_id INTEGER REFERENCES topics(id),
        target_marks INTEGER NOT NULL, total_marks INTEGER NOT NULL,
        time_limit_s INTEGER, started_at TEXT NOT NULL, submitted_at TEXT,
        duration_s INTEGER, obtained_marks REAL);
      INSERT INTO tests (user_id, kind, target_marks, total_marks, started_at)
        VALUES (1, 'class30', 30, 30, '2026-09-01T00:00:00+00:00');
      CREATE TABLE cards (id INTEGER PRIMARY KEY, state TEXT, topic_id INTEGER, created_at TEXT);
      INSERT INTO cards (id) VALUES (1);
      CREATE TABLE test_questions (
        id INTEGER PRIMARY KEY,
        test_id INTEGER NOT NULL REFERENCES tests(id),
        card_id INTEGER NOT NULL REFERENCES cards(id),
        ordinal INTEGER NOT NULL, marks INTEGER NOT NULL,
        verdict TEXT, seconds INTEGER, UNIQUE(test_id, ordinal));
      INSERT INTO test_questions (test_id, card_id, ordinal, marks)
        VALUES (1, 1, 1, 2);
    """)
    conn.commit()
    with __import__("pytest").raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tests (user_id, kind, target_marks, total_marks,"
                     " started_at) VALUES (1,'mte40',40,40,'2026-09-05T00:00:00+00:00')")
    init_db(conn)
    conn.execute("INSERT INTO tests (user_id, kind, target_marks, total_marks,"
                 " started_at) VALUES (1,'mte40',40,40,'2026-09-05T00:00:00+00:00')")
    rows = conn.execute("SELECT kind FROM tests ORDER BY id").fetchall()
    assert [r["kind"] for r in rows] == ["class30", "mte40"]
    # The referencing table must survive with its FK pointing at the REBUILT
    # tests table — renaming the old table away instead of the new one into
    # place drags the FK to "tests_old" and detonates on the next insert.
    tq_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='test_questions'").fetchone()["sql"]
    assert "tests_old" not in tq_sql
    assert conn.execute("SELECT COUNT(*) n FROM test_questions").fetchone()["n"] == 1
    new_test = conn.execute("SELECT id FROM tests WHERE kind='mte40'").fetchone()["id"]
    conn.execute("INSERT INTO test_questions (test_id, card_id, ordinal, marks)"
                 " VALUES (?, 1, 1, 1)", (new_test,))


def test_repair_pass_fixes_a_database_the_bad_migration_damaged(tmp_path):
    """Databases migrated by the wrong-order rebuild have test_questions
    referencing the dropped tests_old; init_db must repair them."""
    conn = connect(str(tmp_path / "hurt.db"))
    conn.execute("PRAGMA foreign_keys = OFF")  # planting the damaged state
    conn.executescript('''
      CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
      INSERT INTO users (id, name) VALUES (1, 'yash');
      CREATE TABLE topics (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
        code TEXT NOT NULL, label TEXT NOT NULL, UNIQUE(user_id, code));
      CREATE TABLE cards (id INTEGER PRIMARY KEY, state TEXT, topic_id INTEGER, created_at TEXT);
      INSERT INTO cards (id) VALUES (1);
      CREATE TABLE tests (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        kind TEXT NOT NULL CHECK (kind IN ('class30','mte40','endterm100','fullday')),
        topic_id INTEGER, target_marks INTEGER NOT NULL, total_marks INTEGER NOT NULL,
        time_limit_s INTEGER, started_at TEXT NOT NULL, submitted_at TEXT,
        duration_s INTEGER, obtained_marks REAL);
      INSERT INTO tests (user_id, kind, target_marks, total_marks, started_at)
        VALUES (1, 'class30', 30, 30, '2026-09-01T00:00:00+00:00');
      CREATE TABLE test_questions (
        id INTEGER PRIMARY KEY,
        test_id INTEGER NOT NULL REFERENCES "tests_old"(id),
        card_id INTEGER NOT NULL REFERENCES cards(id),
        ordinal INTEGER NOT NULL, marks INTEGER NOT NULL,
        verdict TEXT, seconds INTEGER, UNIQUE(test_id, ordinal));
      INSERT INTO test_questions (test_id, card_id, ordinal, marks)
        VALUES (1, 1, 1, 2);
    ''')
    conn.commit()
    init_db(conn)
    tq_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='test_questions'").fetchone()["sql"]
    assert "tests_old" not in tq_sql
    conn.execute("INSERT INTO tests (user_id, kind, target_marks, total_marks,"
                 " started_at) VALUES (1,'mte40',40,40,'2026-09-05T00:00:00+00:00')")
    conn.execute("INSERT INTO test_questions (test_id, card_id, ordinal, marks)"
                 " VALUES (2, 1, 1, 1)")
    assert conn.execute("SELECT COUNT(*) n FROM test_questions").fetchone()["n"] == 2
