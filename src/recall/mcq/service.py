"""Yash Made Test service: draw an attempt, reveal one answer, score it.

Every function takes the connection first and `user_id` second, like
`recall.testmode.service`, and raises `LookupError` for "no such thing" (404),
`ValueError` for "that is not a legal move" (422) and `McqConflict` for "legal,
but not now" (409). The routes translate; nothing here knows about HTTP.

**The shuffle is stored, never recomputed.** An attempt draws its questions
once and shuffles each question's four options once, and both results live on
the attempt row. `option_orders_json[i]` is a permutation of 0..3 where
`order[shown] = stored`, so:

    shown_options  = [stored_options[j] for j in order]
    stored_choice  = order[chosen]
    correct_index  = order.index(stored_correct)

Everything on the wire — `chosen`, `correct_index` — is a position in the
SHOWN order, which is the only order the client has ever seen. Recomputing a
shuffle would make an attempt ungradable the moment the seed changed.

**Unanswered scores zero and still counts.** "Finish & see score" halfway
through is allowed; `total` stays the number of questions drawn, so 12/30 after
twelve questions reads as 12/30 and not as 12/12. Nothing here touches the
scheduler: these are not cards.
"""

import json
import random
import sqlite3
from datetime import datetime, timezone

from recall.api.scheduling import iso, utc_now
from recall.mcq.registry import LENGTHS, MCQ_UNITS

N_OPTIONS = 4

#: Columns of one bank question, in the order the shaping helpers expect.
_Q_COLUMNS = ("id, topic, kind, question, options_json, correct, explain,"
              " why_wrong_json")


class McqConflict(Exception):
    """A move that is legal in general but not now.

    Answering a position that already has an answer, or touching a submitted
    attempt. Separate from ValueError because the HTTP answer differs: 409
    ("you already did that") rather than 422 ("that was never valid"), and the
    client shows the recorded answer instead of an error.
    """


def canonical_units(units) -> list[int]:
    """The selection's identity: sorted, deduplicated integers.

    Units [2, 1] and [1, 2] are one selection, so they must produce one
    `units_json` — otherwise they would be two different leaderboards for the
    same sitting. Canonicalised here, once, and used for the stored column,
    the leaderboard lookup and the wire shape alike.
    """
    try:
        return sorted({int(u) for u in units})
    except (TypeError, ValueError) as exc:
        raise ValueError("units must be a list of unit numbers") from exc


def _length_key(length) -> str:
    """The `length` column: '30', '60' or 'full'."""
    return "full" if length == "full" else str(int(length))


def _length_out(stored: str):
    """The stored length back on the wire as 30 | 60 | "full"."""
    return stored if stored == "full" else int(stored)


def _validate_selection(subject_code: str, units, length) -> tuple[list[int], str]:
    info = MCQ_UNITS.get(subject_code)
    if info is None:
        known = ", ".join(sorted(MCQ_UNITS)) or "none"
        raise ValueError(f"no subject {subject_code!r}; the bank covers {known}")
    if length not in LENGTHS:
        printable = ", ".join(repr(x) for x in LENGTHS)
        raise ValueError(f"length must be one of {printable}, got {length!r}")
    cleaned = canonical_units(units)
    if not cleaned:
        raise ValueError("choose at least one unit")
    bad = [u for u in cleaned if u not in info["units"]]
    if bad:
        have = ", ".join(str(u) for u in sorted(info["units"]))
        raise ValueError(
            f"{subject_code} has units {have}; got "
            f"{', '.join(str(u) for u in bad)}")
    return cleaned, _length_key(length)


def list_subjects(conn) -> list[dict]:
    """Every subject in the registry, each unit with its live question count.

    Driven by MCQ_UNITS rather than by what is in the table, so a unit nobody
    has written questions for yet appears with `count: 0` — "waiting for
    material" is information, and a unit that silently vanished from the picker
    would look like a unit that does not exist.
    """
    out = []
    for code, info in MCQ_UNITS.items():
        counts = {
            row["unit"]: row["n"]
            for row in conn.execute(
                "SELECT unit, COUNT(*) AS n FROM mcq_questions"
                " WHERE subject_code = ? AND active = 1 GROUP BY unit", (code,))
        }
        out.append({
            "subject_code": code,
            "label": info["label"],
            "units": [{"unit": unit, "label": label, "count": counts.get(unit, 0)}
                      for unit, label in sorted(info["units"].items())],
            "lengths": list(LENGTHS),
        })
    return out


def _attempt_row(conn, user_id: int, attempt_id: int):
    """The attempt, or LookupError.

    `user_id` in the WHERE clause is the whole isolation story for this
    feature: somebody else's attempt is missing, in exactly the same words as
    an id that never existed. Answering the two differently would turn this
    route into an oracle for how many attempts other accounts have sat.
    """
    row = conn.execute(
        "SELECT * FROM mcq_attempts WHERE id = ? AND user_id = ?",
        (attempt_id, user_id)).fetchone()
    if row is None:
        raise LookupError(f"no attempt {attempt_id}")
    return row


def _questions_by_id(conn, ids: list[int]) -> dict[int, dict]:
    """The drawn questions, retired ones included.

    `active` is deliberately not filtered here: an attempt that already drew a
    question must stay readable and gradable after that question is retired
    from the bank. `active` gates the DRAW, not the replay.
    """
    if not ids:
        return {}
    holes = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT {_Q_COLUMNS} FROM mcq_questions WHERE id IN ({holes})",
        tuple(ids)).fetchall()
    return {row["id"]: dict(row) for row in rows}


def _shown_options(question: dict, order: list[int]) -> list[str]:
    stored = json.loads(question["options_json"])
    return [stored[j] for j in order]


def _shown_correct(question: dict, order: list[int]) -> int:
    return order.index(int(question["correct"]))


def _why_wrong(question: dict, order: list[int], chosen: int) -> str:
    """The note for the option that was picked; "" when it was the right one.

    Indexed by the STORED position the shown choice maps to, which is why the
    permutation has to be stored rather than reapplied: the notes are written
    against the options as they sit in the JSON file.
    """
    notes = json.loads(question["why_wrong_json"])
    return notes[order[chosen]]


def _answer_rows(conn, attempt_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT position, chosen, is_correct FROM mcq_answers"
        " WHERE attempt_id = ? ORDER BY id", (attempt_id,)).fetchall()


def _feedback_by_position(conn, attempt_id: int, ids: list[int],
                          orders: list[list[int]],
                          questions: dict[int, dict]) -> dict[int, dict]:
    """Every recorded answer as an McqFeedback, keyed by position.

    `answered` and `correct_so_far` are the running totals AS OF that answer,
    rebuilt by walking the answers in the order they were recorded (id order).
    A resumed attempt therefore shows the same numbers the reveal showed at the
    time, rather than today's totals stamped onto yesterday's clicks.
    """
    out: dict[int, dict] = {}
    answered = correct_so_far = 0
    for row in _answer_rows(conn, attempt_id):
        position = row["position"]
        answered += 1
        correct_so_far += 1 if row["is_correct"] else 0
        question = questions.get(ids[position - 1])
        if question is None:          # a question row that vanished entirely
            continue
        order = orders[position - 1]
        chosen = row["chosen"]
        out[position] = {
            "position": position,
            "chosen": chosen,
            "correct_index": _shown_correct(question, order),
            "is_correct": bool(row["is_correct"]),
            "explain": question["explain"],
            "why_wrong": _why_wrong(question, order, chosen),
            "answered": answered,
            "correct_so_far": correct_so_far,
        }
    return out


def _attempt_shape(conn, row) -> dict:
    ids = json.loads(row["question_ids_json"])
    orders = json.loads(row["option_orders_json"])
    questions = _questions_by_id(conn, ids)
    feedback = _feedback_by_position(conn, row["id"], ids, orders, questions)

    out_questions = []
    for position, (qid, order) in enumerate(zip(ids, orders), start=1):
        question = questions.get(qid)
        if question is None:
            continue
        out_questions.append({
            "position": position,
            "topic": question["topic"],
            "kind": question["kind"],
            "question": question["question"],
            "options": _shown_options(question, order),
            "answer": feedback.get(position),
        })
    return {
        "attempt_id": row["id"],
        "subject_code": row["subject_code"],
        "units": json.loads(row["units_json"]),
        "length": _length_out(row["length"]),
        "total": row["total"],
        "started_at": row["started_at"],
        "submitted_at": row["submitted_at"],
        "questions": out_questions,
    }


def create_attempt(conn, user_id: int, subject_code: str, units, length,
                   rng: random.Random | None = None) -> dict:
    """Draw a fresh sitting: `min(length, available)` questions, all shuffled.

    `rng` exists so a test can pass `random.Random(seed)` and get a draw it can
    reason about. Nothing else passes it: two sittings looking different is the
    point of the feature, and an attempt that could be predicted would make the
    leaderboard a lie.
    """
    rng = rng or random.Random()
    cleaned, length_key = _validate_selection(subject_code, units, length)

    holes = ",".join("?" for _ in cleaned)
    rows = conn.execute(
        f"SELECT id FROM mcq_questions WHERE subject_code = ? AND active = 1"
        f" AND unit IN ({holes}) ORDER BY id",
        (subject_code, *cleaned)).fetchall()
    if not rows:
        units_text = ", ".join(str(u) for u in cleaned)
        raise ValueError(
            f"{subject_code} unit{'s' if len(cleaned) > 1 else ''} {units_text}"
            " have no questions yet")

    available = [row["id"] for row in rows]
    want = len(available) if length == "full" else min(int(length), len(available))
    drawn = rng.sample(available, want)
    orders = []
    for _ in drawn:
        order = list(range(N_OPTIONS))
        rng.shuffle(order)
        orders.append(order)

    cur = conn.execute(
        "INSERT INTO mcq_attempts (user_id, subject_code, units_json, length,"
        " question_ids_json, option_orders_json, total, started_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (user_id, subject_code, json.dumps(cleaned), length_key,
         json.dumps(drawn), json.dumps(orders), len(drawn), iso(utc_now())))
    conn.commit()
    return get_attempt(conn, user_id, int(cur.lastrowid))


def get_attempt(conn, user_id: int, attempt_id: int) -> dict:
    """The attempt as it stands, recorded reveals included — this is resuming."""
    return _attempt_shape(conn, _attempt_row(conn, user_id, attempt_id))


def answer_attempt(conn, user_id: int, attempt_id: int, position: int,
                   chosen: int) -> dict:
    """Record one answer and reveal it. The first click is the answer.

    A second answer to the same position is refused, never overwritten: the
    reveal already told the student what the right option was, so a second
    click is either a double-tap or a retry, and both of those must not be able
    to turn a wrong answer into a right one. `UNIQUE(attempt_id, position)`
    makes that true even for two requests in flight at once — the loser catches
    the IntegrityError here and gets the same 409 as a sequential retry.
    """
    row = _attempt_row(conn, user_id, attempt_id)
    if row["submitted_at"] is not None:
        raise McqConflict(f"attempt {attempt_id} is already submitted")

    ids = json.loads(row["question_ids_json"])
    orders = json.loads(row["option_orders_json"])
    if not isinstance(position, int) or not 1 <= position <= len(ids):
        raise ValueError(
            f"position must be 1-{len(ids)} for this attempt, got {position!r}")
    if not isinstance(chosen, int) or not 0 <= chosen < N_OPTIONS:
        raise ValueError(f"chosen must be 0-{N_OPTIONS - 1}, got {chosen!r}")

    question_id = ids[position - 1]
    question = _questions_by_id(conn, [question_id]).get(question_id)
    if question is None:
        raise LookupError(f"attempt {attempt_id} question {position} is missing")

    order = orders[position - 1]
    is_correct = order[chosen] == int(question["correct"])
    try:
        conn.execute(
            "INSERT INTO mcq_answers (attempt_id, position, question_id, chosen,"
            " is_correct, answered_at) VALUES (?,?,?,?,?,?)",
            (attempt_id, position, question_id, chosen, 1 if is_correct else 0,
             iso(utc_now())))
    except sqlite3.IntegrityError as exc:
        raise McqConflict(
            f"question {position} of attempt {attempt_id} is already answered"
        ) from exc
    conn.commit()

    totals = conn.execute(
        "SELECT COUNT(*) AS answered, COALESCE(SUM(is_correct), 0) AS correct"
        " FROM mcq_answers WHERE attempt_id = ?", (attempt_id,)).fetchone()
    return {
        "position": position,
        "chosen": chosen,
        "correct_index": _shown_correct(question, order),
        "is_correct": is_correct,
        "explain": question["explain"],
        "why_wrong": _why_wrong(question, order, chosen),
        "answered": totals["answered"],
        "correct_so_far": totals["correct"],
    }


def submit_attempt(conn, user_id: int, attempt_id: int) -> dict:
    """Close the attempt and score it. Unanswered questions score zero.

    Claiming the attempt is one guarded UPDATE, the same idiom as
    `testmode.service.submit_test`: reading `submitted_at` and then writing it
    would let a double tap over a slow connection have both requests decide
    they were first, and stamp two different durations on one sitting. Exactly
    one sees rowcount 1; the loser reads back what the winner stored. The score
    itself cannot differ between them — answering is refused once submitted —
    but the duration and the submission time can, and a result screen that
    disagrees with the history list is the bug this prevents.
    """
    row = _attempt_row(conn, user_id, attempt_id)
    ids = json.loads(row["question_ids_json"])
    orders = json.loads(row["option_orders_json"])
    questions = _questions_by_id(conn, ids)
    answers = {r["position"]: r for r in _answer_rows(conn, attempt_id)}

    total = row["total"]
    answered = len(answers)
    score = sum(1 for r in answers.values() if r["is_correct"])

    started = row["started_at"]
    duration_s = max(0, int((utc_now() - _parse(started)).total_seconds()))
    submitted_at = row["submitted_at"]

    claimed = False
    if submitted_at is None:
        now = iso(utc_now())
        claimed = conn.execute(
            "UPDATE mcq_attempts SET submitted_at = ?, duration_s = ?, score = ?"
            " WHERE id = ? AND submitted_at IS NULL",
            (now, duration_s, score, attempt_id)).rowcount == 1
        conn.commit()
        if claimed:
            submitted_at = now
    if not claimed:
        settled = _attempt_row(conn, user_id, attempt_id)
        score = settled["score"] if settled["score"] is not None else score
        duration_s = settled["duration_s"] or 0
        submitted_at = settled["submitted_at"]

    # by_topic covers every question DRAWN, not every question answered: a
    # topic you skipped entirely scored 0 out of its real count, and reporting
    # it as 0/0 (or omitting it) would hide exactly the gap worth seeing.
    by_topic: dict[str, dict] = {}
    missed: list[dict] = []
    for position, (qid, order) in enumerate(zip(ids, orders), start=1):
        question = questions.get(qid)
        if question is None:
            continue
        bucket = by_topic.setdefault(
            question["topic"], {"topic": question["topic"], "correct": 0,
                                "total": 0})
        bucket["total"] += 1
        answer = answers.get(position)
        if answer is not None and answer["is_correct"]:
            bucket["correct"] += 1
            continue
        chosen = answer["chosen"] if answer is not None else None
        missed.append({
            "position": position,
            "topic": question["topic"],
            "question": question["question"],
            "options": _shown_options(question, order),
            "chosen": chosen,
            "correct_index": _shown_correct(question, order),
            "explain": question["explain"],
            # Nothing was picked, so there is no wrong option to explain. The
            # teaching for an unanswered question is `explain`.
            "why_wrong": ("" if chosen is None
                          else _why_wrong(question, order, chosen)),
        })

    return {
        "attempt_id": row["id"],
        "score": score,
        "total": total,
        "answered": answered,
        "percent": round(100 * score / total) if total else 0,
        "duration_s": duration_s,
        "by_topic": [by_topic[t] for t in sorted(by_topic)],
        "missed": missed,
        # A sitting nobody answered is not a leaderboard entry, so it is not
        # given a position on one.
        "rank": (_rank_of(conn, user_id, row["subject_code"],
                          json.loads(row["units_json"]), row["length"])
                 if answered else None),
    }


def abandon_attempt(conn, user_id: int, attempt_id: int) -> None:
    """Throw away an open attempt. A submitted one is a result, not clutter.

    Deletes the answers explicitly in the same transaction: `mcq_answers` has
    no ON DELETE CASCADE (SQLite would need the pragma and this schema does not
    rely on it), so leaving them would orphan rows for a later query to trip
    over.
    """
    row = _attempt_row(conn, user_id, attempt_id)
    if row["submitted_at"] is not None:
        raise McqConflict(
            f"attempt {attempt_id} has been submitted; it cannot be discarded")
    conn.execute("DELETE FROM mcq_answers WHERE attempt_id = ?", (attempt_id,))
    conn.execute("DELETE FROM mcq_attempts WHERE id = ?", (attempt_id,))
    conn.commit()


def list_attempts(conn, user_id: int) -> list[dict]:
    """This user's sittings, newest first. `score` is null while one is open."""
    rows = conn.execute(
        "SELECT a.id, a.subject_code, a.units_json, a.length, a.total, a.score,"
        " a.started_at, a.submitted_at, a.duration_s,"
        " (SELECT COUNT(*) FROM mcq_answers ans WHERE ans.attempt_id = a.id)"
        "   AS answered"
        " FROM mcq_attempts a WHERE a.user_id = ?"
        " ORDER BY a.started_at DESC, a.id DESC", (user_id,)).fetchall()
    return [{
        "id": r["id"],
        "subject_code": r["subject_code"],
        "units": json.loads(r["units_json"]),
        "length": _length_out(r["length"]),
        "total": r["total"],
        "answered": r["answered"],
        "score": r["score"],
        "started_at": r["started_at"],
        "submitted_at": r["submitted_at"],
        "duration_s": r["duration_s"],
    } for r in rows]


def leaderboard(conn, subject_code: str, units, length,
                limit: int = 25) -> list[dict]:
    """Each user's best submitted attempt for EXACTLY this selection.

    Exactly: same subject, same canonical units, same length. Units [1] and
    [1, 2] are different boards on purpose — they are different papers, and
    mixing them would rank a twelve-question sitting against a twenty-four
    question one. `canonical_units` is what makes [2, 1] and [1, 2] the same
    board rather than two.

    This is the front door: a user naming a selection, so the selection is
    validated against the registry before it is looked up. Ranking an attempt
    that already exists goes through `_board_rows` instead — see the note
    there.

    This is the one cross-user read in the feature, and it is the feature: a
    leaderboard that showed you only yourself would be a history page.
    """
    cleaned, length_key = _validate_selection(subject_code, units, length)
    return _board_rows(conn, subject_code, cleaned, length_key, limit)


def _board_rows(conn, subject_code: str, units: list[int], length_key: str,
                limit: int | None = 25) -> list[dict]:
    """The board for a selection that is already canonical and already legal.

    Split from `leaderboard` so that ranking a STORED attempt never re-checks
    its selection against the registry. MCQ_UNITS is code: units get written,
    renamed and dropped as the course material is, and an attempt drawn before
    such an edit must still submit afterwards. Validating here made
    `submit_attempt` raise ValueError out of a route that only translates
    LookupError, so removing one unit from the registry turned every open
    attempt covering it into a 500 with the sitting unrecoverable.

    Ordered by percent, then by the shorter sitting, then by who got there
    first. Best-per-user is picked in Python from that same ordering, so the
    row shown is by definition the one that would have ranked highest anyway —
    one rule, not two that can disagree.
    """
    rows = conn.execute(
        "SELECT a.user_id, u.name, a.score, a.total, a.duration_s,"
        " a.submitted_at FROM mcq_attempts a JOIN users u ON u.id = a.user_id"
        " WHERE a.subject_code = ? AND a.units_json = ? AND a.length = ?"
        " AND a.submitted_at IS NOT NULL",
        (subject_code, json.dumps(units), length_key)).fetchall()

    entries = []
    for r in rows:
        total = r["total"] or 0
        score = r["score"] or 0
        entries.append({
            "user_id": r["user_id"],
            "name": r["name"],
            "score": score,
            "total": total,
            "percent": round(100 * score / total) if total else 0,
            "duration_s": r["duration_s"] or 0,
            "submitted_at": r["submitted_at"],
        })
    entries.sort(key=lambda e: (-e["percent"], e["duration_s"],
                                e["submitted_at"] or ""))

    best: list[dict] = []
    seen: set[int] = set()
    for entry in entries:
        if entry["user_id"] in seen:
            continue
        seen.add(entry["user_id"])
        best.append(entry)
    return best[:limit] if limit is not None else best


def _rank_of(conn, user_id: int, subject_code: str, units, length_key: str):
    """Where this user's row sits on the board for this selection.

    Takes the attempt's own stored `units_json` and `length` — a selection
    that exists, therefore one that was legal when it was drawn — and goes
    straight to `_board_rows`. It must not re-validate: see the note there.

    The board is best-per-user, so this is the position of the user's best
    submitted attempt — which is the attempt just submitted whenever it was
    their best, and otherwise the better one they already had. `of` is how many
    people are on the board, not how many attempts exist.
    """
    rows = _board_rows(conn, subject_code, canonical_units(units), length_key,
                       limit=None)
    for position, row in enumerate(rows, start=1):
        if row["user_id"] == user_id:
            return {"position": position, "of": len(rows)}
    return None


def _parse(stamp: str) -> datetime:
    """A stored ISO timestamp back as an aware datetime, tolerating junk.

    Naive stamps are read as UTC: every writer in the app is aware, so a naive
    one is an old row, and guessing local time on a server would make a
    duration wrong by hours rather than by nothing.
    """
    try:
        parsed = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return utc_now()
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


__all__ = ["McqConflict", "abandon_attempt", "answer_attempt",
           "canonical_units", "create_attempt", "get_attempt", "leaderboard",
           "list_attempts", "list_subjects", "submit_attempt"]
