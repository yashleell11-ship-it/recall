import sqlite3
from importlib import resources


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    sql = resources.files("recall").joinpath("schema.sql").read_text()
    conn.executescript(sql)
    conn.commit()
