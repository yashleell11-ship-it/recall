"""Shared FastAPI dependencies: the DB connection and the authenticated user.

One copy, not three near-duplicates. `app.py`, `teach_routes.py` and
`tests_routes.py` each used to carry their own `get_conn` (the docstrings on
the old copies explained this as avoiding a circular import with `app.py`,
since `app.py` includes those routers) — collecting it here, with no
dependency on `app.py`, removes the reason that split existed.

Timestamps here follow the same convention as `recall.api.scheduling`:
timezone-aware ISO-8601 strings, which sort lexicographically, so a plain
`expires_at <= ?` in SQL is a valid ordering.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException

from recall.db import connect

SESSION_COOKIE = "recall_session"
#: How long a login lasts before it has to be done again. Fixed, not sliding:
#: refreshing this on every request would turn every read in the app — the
#: queue, the stats, every card — into a database write.
SESSION_TTL_DAYS = 10


def get_conn():
    conn = connect(os.environ.get("RECALL_DB", "recall.db"))
    try:
        yield conn
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_session(conn, user_id: int) -> str:
    """Mint a session, returning the raw token to put in the cookie.

    Only the SHA-256 hash is ever written to sqlite — a copy of the DB file
    (backup, misconfigured volume) never carries a value that alone lets
    someone impersonate a user; you'd also need the cookie bytes.
    """
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=SESSION_TTL_DAYS)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at)"
        " VALUES (?,?,?,?)",
        (hash_token(raw), user_id, now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    return raw


def get_current_user(
    conn=Depends(get_conn),
    recall_session: str | None = Cookie(default=None),
) -> int:
    """Resolves the session cookie to a user id, or 401s.

    Returns a plain int, not a row/object: every service function this
    threads into (`scheduling.*`, `testmode.service.*`, `pipeline.*`) already
    takes `user_id: int`, so this is a drop-in replacement for the module
    constants it's replacing, not a refactor of the layer underneath it.
    """
    if recall_session is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    row = conn.execute(
        "SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
        (hash_token(recall_session), _now_iso()),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="session expired or invalid")
    return row["user_id"]
