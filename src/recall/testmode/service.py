"""Test mode service: assemble a paper, record verdicts, feed the result back.

Every function takes the connection first, like recall.api.scheduling, and raises
LookupError for "no such thing" (404) and ValueError for "that is not a legal
move" (422). The routes translate; nothing here knows about HTTP.

The scheduler is not reimplemented here. Submitting a paper calls the same
record_review the daily queue calls, so a wrong answer on a test moves stability
and difficulty exactly as a wrong answer in review does.
"""

from recall.api.scheduling import iso, record_review, utc_now
from recall.testmode.assembly import CandidateCard, assemble, shortfall_note
from recall.testmode.marks import PARTIAL_MIN_MARKS, marks_for_card

# kind -> (target marks, time limit in seconds). fullday has neither: it is every
# active card, sat over as many sittings as it takes.
KINDS: dict[str, tuple[int | None, int | None]] = {
    "class30": (30, 45 * 60),
    # LPU MTE: covers units 1-3, paper marked out of 40 (scaled to the course's
    # MTE weight afterwards), 90 minutes.
    "mte40": (40, 90 * 60),
    "endterm100": (100, 180 * 60),
    "fullday": (None, None),
}

VERDICTS = ("correct", "partial", "wrong", "skipped")

# Grade 4 ("easy") is never inferred: easy is a claim only the person reviewing
# can make, and a test does not ask. Skipped maps to nothing at all — not
# attempting a question is not evidence about memory.
GRADE_FOR_VERDICT = {"wrong": 1, "partial": 2, "correct": 3}

_SCORE_FRACTION = {"correct": 1.0, "partial": 0.5, "wrong": 0.0, "skipped": 0.0}

_QUESTION_SQL = (
    "SELECT q.ordinal, q.card_id, q.marks, q.verdict, q.seconds,"
    " c.kind, c.question, c.answer, c.cloze_text, c.detail, c.origin,"
    " t.code AS topic_code, ch.page_ref"
    " FROM test_questions q"
    " JOIN cards c ON c.id = q.card_id"
    " JOIN topics t ON t.id = c.topic_id"
    " JOIN chunks ch ON ch.id = c.chunk_id"
    " WHERE q.test_id = ? ORDER BY q.ordinal"
)


def _question(row) -> dict:
    return {"ordinal": row["ordinal"], "card_id": row["card_id"],
            "kind": row["kind"], "question": row["question"],
            "answer": row["answer"], "cloze_text": row["cloze_text"],
            "detail": row["detail"], "origin": row["origin"],
            "marks": row["marks"], "topic_code": row["topic_code"],
            "page_ref": row["page_ref"], "verdict": row["verdict"]}


def _score(row) -> float:
    return row["marks"] * _SCORE_FRACTION.get(row["verdict"] or "skipped", 0.0)


def _test_row(conn, user_id: int, test_id: int):
    row = conn.execute(
        "SELECT t.*, tp.code AS topic_code FROM tests t"
        " LEFT JOIN topics tp ON tp.id = t.topic_id"
        " WHERE t.id = ? AND t.user_id = ?", (test_id, user_id)
    ).fetchone()
    if row is None:
        raise LookupError(f"no test {test_id}")
    return row


def _candidates(conn, user_id: int, topic_code: str | None) -> list[CandidateCard]:
    clause = " AND t.code = ?" if topic_code else ""
    args: tuple = (topic_code,) if topic_code else ()
    rows = conn.execute(
        "SELECT c.id, c.kind, c.answer, t.code AS topic_code,"
        " cs.stability, cs.difficulty, cs.due_at"
        " FROM cards c"
        " JOIN topics t ON t.id = c.topic_id"
        " JOIN chunks ch ON ch.id = c.chunk_id"
        " LEFT JOIN card_state cs ON cs.card_id = c.id AND cs.user_id = ?"
        f" WHERE c.state = 'active' AND t.user_id = ?{clause}"
        " ORDER BY c.id",
        (user_id, user_id, *args),
    ).fetchall()
    return [CandidateCard(card_id=r["id"], topic_code=r["topic_code"],
                          marks=marks_for_card(r["kind"], r["answer"]),
                          stability=r["stability"], difficulty=r["difficulty"],
                          due_at=r["due_at"])
            for r in rows]


def create_test(conn, user_id: int, kind: str,
                topic_code: str | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    topic_id = None
    if topic_code is not None:
        row = conn.execute(
            "SELECT id, meta FROM topics WHERE user_id = ? AND code = ?",
            (user_id, topic_code)).fetchone()
        if row is None:
            raise LookupError(f"no topic {topic_code!r}")
        topic_id = row["id"]
        # Subjects without a mid-term at LPU must not offer one here: sitting a
        # paper the university will never set is practice for nothing.
        if kind == "mte40" and row["meta"]:
            import json as _json

            meta = _json.loads(row["meta"])
            if meta.get("mte_exists") is False:
                raise ValueError(
                    f"{topic_code} has no MTE at LPU "
                    f"({meta.get('ca_policy', 'CA/ETE only')})"
                )

    target, time_limit_s = KINDS[kind]
    paper = assemble(_candidates(conn, user_id, topic_code), target, now=utc_now())

    cur = conn.execute(
        "INSERT INTO tests (user_id, kind, topic_id, target_marks, total_marks,"
        " time_limit_s, started_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, kind, topic_id, paper.target_marks, paper.total_marks,
         time_limit_s, iso(utc_now())),
    )
    test_id = int(cur.lastrowid)
    for ordinal, card in enumerate(paper.cards, start=1):
        conn.execute(
            "INSERT INTO test_questions (test_id, card_id, ordinal, marks)"
            " VALUES (?,?,?,?)", (test_id, card.card_id, ordinal, card.marks))
    conn.commit()
    return get_test(conn, user_id, test_id)


def get_test(conn, user_id: int, test_id: int) -> dict:
    """The paper as it stands, verdicts included — this is what resuming reads."""
    test = _test_row(conn, user_id, test_id)
    rows = conn.execute(_QUESTION_SQL, (test_id,)).fetchall()
    note = shortfall_note(test["total_marks"], test["target_marks"], len(rows))
    return {"test_id": test["id"], "kind": test["kind"],
            "topic_code": test["topic_code"],
            "target_marks": test["target_marks"],
            "total_marks": test["total_marks"],
            "time_limit_s": test["time_limit_s"],
            "started_at": test["started_at"],
            "submitted_at": test["submitted_at"],
            "obtained_marks": test["obtained_marks"],
            "short": note is not None, "note": note,
            "questions": [_question(r) for r in rows]}


def record_answer(conn, user_id: int, test_id: int, ordinal: int, verdict: str,
                  seconds: int = 0) -> dict:
    test = _test_row(conn, user_id, test_id)
    if test["submitted_at"] is not None:
        raise ValueError("test already submitted")
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
    if seconds is not None and seconds < 0:
        raise ValueError("seconds must not be negative")

    row = conn.execute(
        "SELECT marks FROM test_questions WHERE test_id = ? AND ordinal = ?",
        (test_id, ordinal)).fetchone()
    if row is None:
        raise LookupError(f"test {test_id} has no question {ordinal}")
    if verdict == "partial" and row["marks"] < PARTIAL_MIN_MARKS:
        raise ValueError(
            f"partial needs a question worth {PARTIAL_MIN_MARKS} marks or more;"
            f" question {ordinal} is worth {row['marks']}")

    conn.execute(
        "UPDATE test_questions SET verdict = ?, seconds = ?"
        " WHERE test_id = ? AND ordinal = ?",
        (verdict, seconds, test_id, ordinal))
    conn.commit()
    return {"ok": True}


def submit_test(conn, user_id: int, test_id: int) -> dict:
    test = _test_row(conn, user_id, test_id)
    rows = conn.execute(_QUESTION_SQL, (test_id,)).fetchall()

    obtained = sum(_score(r) for r in rows)
    # Time spent answering, not wall clock: a fullday paper is meant to be put
    # down and picked up again, and the days in between are not the exam.
    duration_s = sum(r["seconds"] or 0 for r in rows)

    # Claiming the paper and storing its result is one guarded UPDATE. Reading
    # submitted_at and then writing it would let two submits arriving together
    # -- a double tap on the button over a slow connection -- both decide they
    # were first and record the whole paper's reviews twice. Exactly one of them
    # sees rowcount 1; the other reads back what the winner wrote.
    claimed = False
    if test["submitted_at"] is None:
        claimed = conn.execute(
            "UPDATE tests SET submitted_at = ?, duration_s = ?, obtained_marks = ?"
            " WHERE id = ? AND submitted_at IS NULL",
            (iso(utc_now()), duration_s, obtained, test_id)).rowcount == 1
        conn.commit()

    if claimed:
        for row in rows:
            grade = GRADE_FOR_VERDICT.get(row["verdict"])
            if grade is not None:
                record_review(conn, user_id, row["card_id"], grade)
    else:
        # Re-submitting shows the paper again; it does not re-grade it and must
        # not record a second round of reviews.
        settled = _test_row(conn, user_id, test_id)
        obtained = settled["obtained_marks"] or 0.0
        duration_s = settled["duration_s"] or 0

    total = test["total_marks"]
    by_topic: dict[str, dict] = {}
    for row in rows:
        bucket = by_topic.setdefault(row["topic_code"],
                                     {"topic_code": row["topic_code"],
                                      "obtained": 0.0, "total": 0})
        bucket["obtained"] += _score(row)
        bucket["total"] += row["marks"]

    return {
        "test_id": test["id"],
        "obtained_marks": obtained,
        "total_marks": total,
        "percent": round(100.0 * obtained / total, 1) if total else 0.0,
        "duration_s": duration_s,
        "by_topic": [by_topic[code] for code in sorted(by_topic)],
        "wrong": [_question(r) for r in rows if r["verdict"] == "wrong"],
        "partial": [_question(r) for r in rows if r["verdict"] == "partial"],
    }


def list_tests(conn, user_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, kind, started_at, obtained_marks, total_marks, duration_s"
        " FROM tests WHERE user_id = ? ORDER BY started_at DESC, id DESC",
        (user_id,)).fetchall()
    return [dict(r) for r in rows]


__all__ = ["KINDS", "VERDICTS", "GRADE_FOR_VERDICT", "create_test", "get_test",
           "record_answer", "submit_test", "list_tests"]
