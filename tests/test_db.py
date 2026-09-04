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


def test_connection_can_be_closed_from_another_thread(tmp_path):
    """Reproduces the exact failure: FastAPI opens a sync dependency's connection
    on one threadpool thread and closes it on another."""
    import threading

    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    errors: list[Exception] = []

    def close_it():
        try:
            conn.close()
        except Exception as exc:  # noqa: BLE001 - the assertion is the point
            errors.append(exc)

    t = threading.Thread(target=close_it)
    t.start()
    t.join()
    assert errors == [], f"connection could not be closed cross-thread: {errors}"


def test_query_works_from_another_thread(tmp_path):
    import threading

    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    out: list[int] = []

    def query():
        out.append(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])

    t = threading.Thread(target=query)
    t.start()
    t.join()
    assert out == [0]
