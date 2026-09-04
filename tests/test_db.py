import sqlite3

import pytest

from recall.db import connect, init_db


def test_init_db_creates_all_tables(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in rows}
    assert {
        "users", "settings", "topics", "sources", "chunks",
        "cards", "gen_runs", "reviews", "card_state", "fit_runs",
    } <= names


def test_init_db_is_idempotent(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    init_db(conn)


def test_rows_are_dict_like(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    conn.execute("INSERT INTO users (name) VALUES ('yash')")
    row = conn.execute("SELECT id, name FROM users").fetchone()
    assert row["name"] == "yash"


def test_foreign_keys_enforced(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO topics (user_id, code, label) VALUES (999,'X','X')")
