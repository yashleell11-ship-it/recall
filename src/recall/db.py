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
    conn.commit()
