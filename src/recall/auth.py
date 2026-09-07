"""Password hashing and user creation for open registration.

Argon2id (via argon2-cffi) rather than bcrypt/passlib: it's OWASP's current
default recommendation, ships prebuilt wheels for the slim Python image this
project already deploys on, and passlib (the usual bcrypt wrapper) has had
compatibility breaks with recent bcrypt releases.
"""

import sqlite3
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from recall.seed import seed_topics

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def normalize_email(email: str) -> str:
    # SQLite's default collation is case-sensitive; normalize in Python so the
    # rule is visible at the call site rather than hidden in a COLLATE clause.
    return email.strip().lower()


class DuplicateAccount(Exception):
    """A username or email is already taken."""


def create_user(conn: sqlite3.Connection, *, name: str, email: str,
                password: str) -> int:
    """Creates the account, its default settings, and its LPU topic catalog.

    A new signup is only actually usable once it has its own topics to
    upload/study against — this mirrors exactly what `recall init` does for
    the owner's own account.
    """
    email = normalize_email(email)
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at)"
            " VALUES (?,?,?,?)",
            (name, email, hash_password(password),
             datetime.now(timezone.utc).isoformat()),
        )
    except sqlite3.IntegrityError as exc:
        raise DuplicateAccount(str(exc)) from exc
    user_id = cur.lastrowid
    conn.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
    seed_topics(conn, user_id=user_id)
    conn.commit()
    return user_id
