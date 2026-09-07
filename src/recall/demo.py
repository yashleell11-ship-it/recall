"""Sample cards so the app is usable before any API key exists.

This is placeholder content: correct, but not from the user's actual syllabus.
Replace it by ingesting real course PDFs — `recall demo --clear` removes it.
"""

SAMPLE_SOURCE = "sample-data (not from your syllabus)"

# (topic_code, kind, question, answer, cloze_text)
SAMPLE_CARDS: list[tuple[str, str, str, str, str | None]] = [
    ("MTH165", "qa", "What two conditions does Rolle's theorem require on [a, b]?",
     "Continuous on [a, b] and differentiable on (a, b), with f(a) = f(b)", None),
    ("MTH165", "cloze", "Derivative of sin x", "cos x",
     "The derivative of sin x with respect to x is {{c1::cos x}}."),
    ("MTH165", "qa", "When is a square matrix invertible?",
     "Exactly when its determinant is non-zero", None),
    ("MTH165", "cloze", "Rank-nullity theorem", "rank(A) + nullity(A) = n",
     "For an m x n matrix A, {{c1::rank(A) + nullity(A) = n}}."),
    ("MTH165", "qa", "What does L'Hopital's rule apply to?",
     "Limits of indeterminate form 0/0 or infinity/infinity", None),

    ("CSE111", "qa", "What does the sizeof operator return for an array in C?",
     "The total size in bytes of the whole array", None),
    ("CSE111", "cloze", "Pointer arithmetic scaling", "the size of the pointed-to type",
     "Adding 1 to a pointer advances it by {{c1::the size of the pointed-to type}}."),
    ("CSE111", "qa", "What is the value of an uninitialised local variable in C?",
     "Indeterminate; reading it is undefined behaviour", None),
    ("CSE111", "qa", "Which C storage class keeps a local variable alive between calls?",
     "static", None),
    ("CSE111", "cloze", "String terminator in C", "a null byte",
     "A C string is terminated by {{c1::a null byte}}."),

    ("INT108", "qa", "What is the time complexity of binary search?",
     "O(log n)", None),
    ("INT108", "cloze", "Stack discipline", "last in, first out",
     "A stack removes elements in {{c1::last in, first out}} order."),
    ("INT108", "qa", "Which traversal of a binary search tree yields sorted order?",
     "In-order traversal", None),
    ("INT108", "qa", "What is the worst-case time complexity of quicksort?",
     "O(n^2)", None),

    ("INT335", "qa", "Which Linux command changes file permissions?",
     "chmod", None),
    ("INT335", "cloze", "Process identifier", "PID",
     "Every running Linux process is identified by its {{c1::PID}}."),
    ("INT335", "qa", "What does the shell operator 2> redirect?",
     "Standard error", None),
    ("INT335", "qa", "What permission value does chmod 755 grant the owner?",
     "Read, write and execute", None),

    ("CSE326", "qa", "Which HTML element groups the navigation links of a page?",
     "<nav>", None),
    ("CSE326", "cloze", "Alt attribute", "screen readers and when the image fails to load",
     "The alt attribute on an image is used by {{c1::screen readers and when the "
     "image fails to load}}."),
    ("CSE326", "qa", "What is the difference between a block and an inline element?",
     "A block element starts on a new line and fills the width; inline does not", None),
    ("CSE326", "qa", "Which attribute associates a label with a form control?",
     "for, matching the control's id", None),
]


def seed_demo(conn, user_id: int = 1) -> int:
    """Insert sample cards as ACTIVE so they are immediately reviewable."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        "SELECT id FROM sources WHERE user_id = ? AND sha256 = 'demo-seed'", (user_id,)
    ).fetchone()
    if row:
        return 0

    topics = {r["code"]: r["id"] for r in conn.execute(
        "SELECT id, code FROM topics WHERE user_id = ?", (user_id,)).fetchall()}
    first_topic = next(iter(topics.values()))
    cur = conn.execute(
        "INSERT INTO sources (user_id, topic_id, filename, kind, sha256, added_at)"
        " VALUES (?,?,?,?,?,?)",
        (user_id, first_topic, SAMPLE_SOURCE, "demo", "demo-seed", now),
    )
    source_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO chunks (source_id, ordinal, text, page_ref) VALUES (?,?,?,?)",
        (source_id, 0, "Sample material.", "p1"),
    )
    chunk_id = cur.lastrowid

    inserted = 0
    for i, (code, kind, question, answer, cloze) in enumerate(SAMPLE_CARDS):
        if code not in topics:
            continue
        conn.execute(
            "INSERT INTO cards (chunk_id, topic_id, kind, question, answer,"
            " cloze_text, arm, state, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (chunk_id, topics[code], kind, question, answer, cloze,
             "learned" if i % 2 else "baseline", "active", now),
        )
        inserted += 1
    conn.commit()
    return inserted


def clear_demo(conn, user_id: int = 1) -> int:
    row = conn.execute(
        "SELECT id FROM sources WHERE user_id = ? AND sha256 = 'demo-seed'", (user_id,)
    ).fetchone()
    if not row:
        return 0
    chunk_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM chunks WHERE source_id = ?", (row["id"],)).fetchall()]
    placeholders = ",".join("?" for _ in chunk_ids) or "NULL"
    card_ids = [r["id"] for r in conn.execute(
        f"SELECT id FROM cards WHERE chunk_id IN ({placeholders})", chunk_ids
    ).fetchall()]
    if card_ids:
        cp = ",".join("?" for _ in card_ids)
        conn.execute(f"DELETE FROM reviews WHERE card_id IN ({cp})", card_ids)
        conn.execute(f"DELETE FROM card_state WHERE card_id IN ({cp})", card_ids)
        conn.execute(f"DELETE FROM cards WHERE id IN ({cp})", card_ids)
    conn.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", chunk_ids)
    conn.execute("DELETE FROM sources WHERE id = ?", (row["id"],))
    conn.commit()
    return len(card_ids)
