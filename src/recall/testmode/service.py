"""Test mode service: assemble a paper, record verdicts, feed the result back.

Every function takes the connection first, like recall.api.scheduling, and raises
LookupError for "no such thing" (404) and ValueError for "that is not a legal
move" (422). The routes translate; nothing here knows about HTTP.

The scheduler is not reimplemented here. Submitting a paper calls the same
record_review the daily queue calls, so a wrong answer on a test moves stability
and difficulty exactly as a wrong answer in review does.
"""

from recall.api.scheduling import iso, record_review, utc_now
from recall.generate.knowledge import knowledge_sha, unit_chunk_ids, unit_key
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


def _units_of(row) -> list[int] | None:
    """The unit scope stored on a test row, or None for a whole-subject paper.

    Tolerant of a row from a database that predates the column, and of junk in
    it: a paper whose scope cannot be read is reported as unscoped rather than
    crashing the screen that lists it.
    """
    import json as _json

    try:
        raw = row["units_json"]
    except (KeyError, IndexError):
        return None
    if not raw:
        return None
    try:
        value = _json.loads(raw)
    except _json.JSONDecodeError:
        return None
    return [int(u) for u in value] if isinstance(value, list) else None


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


def _candidates(conn, user_id: int, topic_code: str | None,
                topic_id: int | None = None,
                unit_names: list[str] | None = None) -> list[CandidateCard]:
    """Active cards a paper may draw from, optionally narrowed to units.

    `unit_names` names the units to include — names, not indices, because a
    unit's identity has to survive the syllabus being edited. Narrowing is
    only
    possible for knowledge-mode cards: their chunk is the per-unit chunk of
    the topic's synthetic knowledge source, and its `ordinal` IS the unit
    index (see recall.generate.knowledge._unit_chunk_id). A card from an
    uploaded PDF is chunked by PAGE, and a page does not map to a syllabus
    unit — so an upload card cannot honestly be claimed for unit 3, and a
    unit-scoped paper leaves it out rather than guessing. The caller says so
    on screen; silently mixing in cards from unknown units would break the
    one promise a unit paper makes.

    `t.user_id = ?` is load-bearing and not redundant with the topic filter:
    `cards` and `chunks` carry no owner of their own, so every query that
    reaches them has to arrive through `topics` (or `sources`) to stay inside
    one account.
    """
    clause = " AND t.code = ?" if topic_code else ""
    args: tuple = (topic_code,) if topic_code else ()

    if unit_names is not None:
        if topic_id is None:
            raise ValueError("a unit-scoped paper needs a topic")
        if not unit_names:
            return []
        # Resolved to chunk ids through knowledge.unit_chunk_ids — the ONE
        # place that answers "which chunk is this unit" — rather than matched
        # in SQL. Doing it in SQL meant two normalisations, `unit_key` here
        # and `lower(trim(...))` there, and they disagreed the moment a unit
        # name carried a double space. Two implementations of one rule is the
        # bug this whole change exists to remove.
        #
        # Names, never ordinals: an ordinal is a position and a syllabus is
        # editable, so a stored ordinal stops meaning what it did the moment
        # a unit is inserted, reordered or dropped.
        source = conn.execute(
            "SELECT id FROM sources WHERE user_id = ? AND sha256 = ?",
            (user_id, knowledge_sha(topic_id))).fetchone()
        if source is None:
            return []                     # nothing generated for this subject
        by_name = unit_chunk_ids(conn, source["id"])
        wanted = [by_name[k] for k in (unit_key(n) for n in unit_names)
                  if k in by_name]
        if not wanted:
            return []                     # those units hold no cards yet
        holes = ",".join("?" for _ in wanted)
        clause += f" AND c.chunk_id IN ({holes})"
        args = (*args, *wanted)

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


def _clean_units(units: list[int], syllabus: list[str],
                 topic_code: str) -> list[int]:
    """Deduplicated, sorted, and every index checked against the real syllabus.

    Out-of-range is refused rather than clamped or dropped: asking for unit 9
    of a six-unit course is a mistake somewhere, and a paper that silently
    came back covering unit 6 instead would hide it.
    """
    if not syllabus:
        raise ValueError(
            f"{topic_code} has no syllabus units recorded, so a paper cannot "
            "be scoped to one")
    cleaned = sorted({int(u) for u in units})
    if not cleaned:
        raise ValueError("choose at least one unit")
    bad = [u for u in cleaned if not 0 <= u < len(syllabus)]
    if bad:
        # Quote the indices as GIVEN. This function is reached only from the
        # 0-based route, so translating them to unit numbers here told the
        # caller "no unit 10" about an index they had written as 9.
        raise ValueError(
            f"{topic_code} has {len(syllabus)} units, so its unit indices run "
            f"0-{len(syllabus) - 1}; got {', '.join(str(u) for u in bad)}")
    return cleaned


def create_test(conn, user_id: int, kind: str,
                topic_code: str | None = None,
                units: list[int] | None = None) -> dict:
    """Assemble a paper.

    `units` is a list of 0-based syllabus unit indices — "we did units 2 and 3
    in class, examine me on those". It narrows the draw to cards whose unit is
    actually known (see `_candidates`), and requires a subject: "unit 3" means
    nothing across five different courses that each have one.
    """
    import json as _json

    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if units is not None and topic_code is None:
        raise ValueError("choosing units needs a subject to choose them from")

    topic_id = None
    chosen_names: list[str] | None = None
    if topic_code is not None:
        row = conn.execute(
            "SELECT id, meta FROM topics WHERE user_id = ? AND code = ?",
            (user_id, topic_code)).fetchone()
        if row is None:
            raise LookupError(f"no topic {topic_code!r}")
        topic_id = row["id"]
        meta = _json.loads(row["meta"]) if row["meta"] else {}
        # Subjects without a mid-term at LPU must not offer one here: sitting a
        # paper the university will never set is practice for nothing.
        if kind == "mte40" and meta.get("mte_exists") is False:
            raise ValueError(
                f"{topic_code} has no MTE at LPU "
                f"({meta.get('ca_policy', 'CA/ETE only')})"
            )
        syllabus = meta.get("units") or []
        if units is not None:
            units = _clean_units(units, syllabus, topic_code)
            chosen_names = [syllabus[u] for u in units]

    target, time_limit_s = KINDS[kind]
    paper = assemble(
        _candidates(conn, user_id, topic_code, topic_id, chosen_names),
        target, now=utc_now())

    cur = conn.execute(
        "INSERT INTO tests (user_id, kind, topic_id, target_marks, total_marks,"
        " time_limit_s, started_at, units_json) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, kind, topic_id, paper.target_marks, paper.total_marks,
         time_limit_s, iso(utc_now()),
         _json.dumps(units) if units is not None else None),
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
            "units": _units_of(test),
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
        "SELECT t.id, t.kind, t.started_at, t.submitted_at, t.obtained_marks,"
        " t.total_marks, t.duration_s, t.units_json, tp.code AS topic_code"
        " FROM tests t LEFT JOIN topics tp ON tp.id = t.topic_id"
        " WHERE t.user_id = ? ORDER BY t.started_at DESC, t.id DESC",
        (user_id,)).fetchall()
    out = []
    for r in rows:
        row = dict(r)
        row["units"] = _units_of(r)
        row.pop("units_json", None)
        out.append(row)
    return out


def abandon_test(conn, user_id: int, test_id: int) -> None:
    """Close an open paper without sitting it.

    Only ever touches an unsubmitted test: `submit_test` is the one place a
    paper's answers turn into reviews, and nothing before that point has
    written anything the scheduler has seen — record_answer only fills in
    `test_questions.verdict`. So deleting an open test deletes work that was
    never real yet, and a submitted one is refused rather than silently
    losing a graded result.

    `test_questions` has no ON DELETE CASCADE (SQLite does not enforce
    foreign keys by default and this schema does not turn that pragma on),
    so its rows are deleted explicitly, in the same transaction as the
    `tests` row, rather than left orphaned for a later query to trip over.
    """
    test = _test_row(conn, user_id, test_id)
    if test["submitted_at"] is not None:
        raise ValueError("cannot close a paper that has already been submitted")
    conn.execute("DELETE FROM test_questions WHERE test_id = ?", (test_id,))
    conn.execute("DELETE FROM tests WHERE id = ?", (test_id,))
    conn.commit()


__all__ = ["KINDS", "VERDICTS", "GRADE_FOR_VERDICT", "create_test", "get_test",
           "record_answer", "submit_test", "list_tests", "abandon_test"]
