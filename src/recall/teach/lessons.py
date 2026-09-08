"""Writing, checking and storing a lesson for one syllabus unit.

Offline by design. A lesson takes one to two minutes to write and costs money,
and the per-user daily cap is $1.00 with no resume path, so this is reached
from `recall lessons`, never from an HTTP request the student is waiting on.
The request path reads rows.

What is checked, in the order it is checked, cheapest first:

1. **Structure** — the shape the prompt asked for, in Python. A lesson missing
   its worked examples is not a lesson.
2. **Notation** — `recall.notation.check_notation`. Free, deterministic, and
   the one rule the owner stated in his own words.
3. **Re-derivation** — one fresh call per worked example, given only the
   question, compared in Python. This is the only check here with real teeth
   against a confidently wrong derivation, and it is honest about its reach:
   it catches wrong ANSWERS. Nothing cheap catches bad teaching.

A lesson that fails 1 or 2 is repaired once and re-checked; a lesson that
fails 3 is stored `status='suspect'` with the mismatch written into `notes`,
because a wrong worked example is exactly the thing a human should look at
rather than have silently deleted.
"""

import json
import re
from dataclasses import dataclass, field

from recall.api.scheduling import iso, utc_now
from recall.generate.knowledge import _synthetic_source_id, _unit_chunk_id
from recall.generate.unit_guidance import guidance_for
from recall.config import Config
from recall.notation import check_notation
from recall.pipeline import _cost
from recall.teach.lesson_prompts import (
    DEFAULT_SHAPE,
    EXAMPLES_PREFACE,
    GUIDANCE_PREFACE,
    LESSON_SYSTEM,
    LESSON_USER,
    REDERIVE_SYSTEM,
    REDERIVE_USER,
    SHAPE_BY_FORMAT,
)

#: How many worked examples a lesson must carry. Two, for the reason
#: unit_guidance gives about its own calibration pair: one cannot show a range,
#: and three starts to read as a problem set rather than a lesson.
_WORKED = 2
_MIN_SECTIONS, _MAX_SECTIONS = 3, 5
_MIN_CHECK = 2


@dataclass
class LessonResult:
    body: dict | None
    status: str                      #: 'draft' | 'suspect' | 'rejected'
    notes: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    lesson_id: int | None = None


def _loads(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def check_structure(body: dict) -> list[str]:
    """The shape the prompt asked for, verified rather than assumed."""
    out: list[str] = []
    if not isinstance(body.get("why"), str) or not body["why"].strip():
        out.append("no 'why': the lesson never says what the unit is for")

    sections = body.get("sections")
    if not isinstance(sections, list) or not (
            _MIN_SECTIONS <= len(sections) <= _MAX_SECTIONS):
        out.append(f"needs {_MIN_SECTIONS}-{_MAX_SECTIONS} sections, "
                   f"got {len(sections) if isinstance(sections, list) else 0}")
    else:
        for i, s in enumerate(sections, 1):
            if not isinstance(s, dict) or not str(s.get("body", "")).strip():
                out.append(f"section {i} has no body")
            elif len(str(s["body"]).split()) < 40:
                out.append(f"section {i} is {len(str(s['body']).split())} words"
                           " — a heading with a sentence under it is not teaching")

    worked = body.get("worked")
    if not isinstance(worked, list) or len(worked) != _WORKED:
        out.append(f"needs exactly {_WORKED} worked examples, "
                   f"got {len(worked) if isinstance(worked, list) else 0}")
    else:
        for i, w in enumerate(worked, 1):
            if not isinstance(w, dict):
                out.append(f"worked example {i} is malformed")
                continue
            steps = w.get("steps")
            if not isinstance(steps, list) or len(steps) < 2:
                out.append(f"worked example {i} has no derivation — the steps "
                           "are the whole point")
            if not str(w.get("answer", "")).strip():
                out.append(f"worked example {i} never reaches an answer")
            if not str(w.get("question", "")).strip():
                out.append(f"worked example {i} has no question")

    check = body.get("check")
    if not isinstance(check, list) or len(check) < _MIN_CHECK:
        out.append(f"needs at least {_MIN_CHECK} check questions")
    return out


def lesson_text(body: dict) -> str:
    """Every word a student would read, for the notation check."""
    parts = [str(body.get("why", ""))]
    for s in body.get("sections") or []:
        if isinstance(s, dict):
            parts += [str(s.get("heading", "")), str(s.get("body", ""))]
    for w in body.get("worked") or []:
        if isinstance(w, dict):
            parts += [str(w.get("question", "")), str(w.get("answer", ""))]
            parts += [str(x) for x in (w.get("steps") or [])]
    for c in body.get("check") or []:
        if isinstance(c, dict):
            parts += [str(c.get("question", "")), str(c.get("answer", "")),
                      str(c.get("why", ""))]
    return "\n".join(parts)


_NUM = re.compile(r"-?\d+(?:\.\d+)?")

#: Typographic forms of the same mathematics. The lesson is REQUIRED by the
#: notation law to write − (U+2212); the re-derivation call, which is told to
#: answer as compactly as possible, writes the ASCII hyphen. Comparing them
#: raw made the two rules fight each other, and the first run flagged
#: e^(−1/6) against e^(-1/6) as a contradiction.
_SAME_CHAR = str.maketrans({
    "\u2212": "-", "\u2013": "-", "\u2014": "-", "\u00d7": "*",
    "\u00f7": "/", "\u2044": "/", "\u2261": "=", "\u2245": "=",
    "\u2248": "=", "\u00a0": " ",
})

#: An answer with no digits and more than this many words is prose, and this
#: comparator has no business judging it.
_PROSE_WORDS = 6

#: How many independent cold solves must AGREE WITH EACH OTHER before their
#: disagreement with the lesson counts against the lesson. Two, because the
#: first run proved one is not enough: a single solve contradicted two
#: worked examples that were, on checking, both correct.
_REDERIVE_VOTES = 2


def _chars(text: str) -> str:
    """Same characters for the same mathematics, spacing untouched."""
    return (text or "").translate(_SAME_CHAR).strip().lower()


def _canon(text: str) -> str:
    """As above, with separators removed, for the containment test."""
    return re.sub(r"[\s,;$]+", "", _chars(text))


def is_adjudicable(claimed: str) -> bool:
    """Can string comparison honestly settle this answer?

    Only where the answer is determinate — a number, an expression, a matrix.
    On a design-thinking paper the answer is a sentence, and two correct
    sentences share almost no characters: the first run compared "They skipped
    Define…" against "Define; a point of view statement" and called the lesson
    suspect, when the two say the same thing.

    A check that cannot adjudicate must say so. Guessing in either direction is
    worse than the honest answer, because a review queue full of non-problems
    is how a check gets switched off, and a green tick nobody earned is how a
    wrong derivation reaches a student.
    """
    a = (claimed or "").strip()
    if not a:
        return False
    return bool(_NUM.search(a)) or len(a.split()) <= _PROSE_WORDS


def answers_agree(claimed: str, fresh: str) -> bool:
    """Do two answers to the same question say the same thing?

    Deliberately generous about form and strict about value: "x = 2" and "2"
    agree, "λ = 3, 5" and "3 and 5" agree, and − and - are the same sign.
    Only called when `is_adjudicable(claimed)`.
    """
    a, b = _canon(claimed), _canon(fresh)
    if not a or not b:
        return False
    if "cannotsolve" in b:
        return False
    if a == b or a in b or b in a:
        return True
    # Fall back to the numbers: same multiset of values, same answer. Signs
    # included — an inverse matrix with every sign flipped is a different
    # matrix, and that is a real defect this caught on the first run.
    #
    # Read off the SPACED text, not the squashed one: squashing turns the
    # comma in "3, 5" into nothing and the two roots into the single number
    # thirty-five.
    na = _NUM.findall(_chars(claimed).replace("^", " "))
    nb = _NUM.findall(_chars(fresh).replace("^", " "))
    if na and sorted(float(x) for x in na) == sorted(float(x) for x in nb):
        return True
    return False


def _rederive(client, cfg: Config, *, topic_code: str, full_name: str,
              unit_name: str, question: str) -> tuple[str, float]:
    resp = client.complete_json(
        REDERIVE_SYSTEM,
        REDERIVE_USER.format(topic_code=topic_code, full_name=full_name,
                             unit_name=unit_name, question=question))
    data = _loads(resp.content) or {}
    return (str(data.get("answer", "")),
            _cost(cfg, resp.prompt_tokens, resp.completion_tokens))


def write_lesson(conn, client, cfg: Config, *, user_id: int, topic_id: int,
                 topic_code: str, meta: dict, unit_number: int,
                 rederive: bool = True) -> LessonResult:
    """Write, check and store one lesson. `unit_number` is 1-based."""
    units = meta.get("units") or []
    if not 1 <= unit_number <= len(units):
        raise ValueError(
            f"{topic_code} has {len(units)} units; there is no unit {unit_number}")
    unit_name = units[unit_number - 1]
    full_name = meta.get("full_name") or topic_code
    shape = SHAPE_BY_FORMAT.get(meta.get("exam_format") or "", DEFAULT_SHAPE)

    guidance = guidance_for(topic_code, unit_number)
    guidance_block = (GUIDANCE_PREFACE.format(guidance=guidance.guidance)
                      if guidance and guidance.guidance else "")
    examples_block = ""
    if guidance and guidance.examples:
        shown = "\n\n".join(
            f"Q: {e.question}\nA: {e.answer}\nWorking: {e.detail}"
            for e in guidance.examples)
        examples_block = EXAMPLES_PREFACE.format(examples=shown)

    user = LESSON_USER.format(
        topic_code=topic_code, full_name=full_name, unit_number=unit_number,
        unit_count=len(units), unit_name=unit_name,
        all_units="; ".join(f"{i + 1}. {u}" for i, u in enumerate(units)),
        shape=shape, guidance=guidance_block, examples=examples_block)

    cost = 0.0
    body: dict | None = None
    complaints: list[str] = []
    for attempt in (1, 2):
        prompt = user if attempt == 1 else (
            user + "\n\nYour previous attempt was rejected for these reasons. "
            "Fix every one and write the lesson again:\n- "
            + "\n- ".join(complaints))
        resp = client.complete_json(LESSON_SYSTEM, prompt)
        cost += _cost(cfg, resp.prompt_tokens, resp.completion_tokens)
        candidate = _loads(resp.content)
        if candidate is None:
            complaints = ["the reply was not valid json"]
            continue
        complaints = check_structure(candidate) + check_notation(
            lesson_text(candidate))
        body = candidate
        if not complaints:
            break

    if body is None or complaints:
        return LessonResult(body, "rejected", complaints, cost)

    status, notes, check_cost = verify_worked(
        client, cfg, body, topic_code=topic_code, full_name=full_name,
        unit_name=unit_name) if rederive else ("draft", [], 0.0)
    cost += check_cost

    source_id = _synthetic_source_id(conn, user_id, topic_id)
    chunk_id = _unit_chunk_id(conn, source_id, unit_number - 1, unit_name)
    cur = conn.execute(
        "INSERT INTO lessons (chunk_id, topic_id, body_json, status, notes,"
        " model, cost_usd, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (chunk_id, topic_id, json.dumps(body, ensure_ascii=False), status,
         "\n".join(notes) or None, cfg.model, cost, iso(utc_now())))
    conn.commit()
    return LessonResult(body, status, notes, cost, int(cur.lastrowid))


def verify_worked(client, cfg: Config, body: dict, *, topic_code: str,
                  full_name: str, unit_name: str) -> tuple[str, list[str], float]:
    """Re-solve every worked example and judge the lesson on the result.

    Split out of `write_lesson` so that re-checking a stored lesson runs the
    SAME check rather than a second copy of it — a second opinion about what
    "verified" means, computed differently in a second place, is the drift this
    codebase keeps paying for.
    """
    notes: list[str] = []
    status = "draft"
    cost = 0.0
    unchecked = 0
    for i, w in enumerate(body["worked"], 1):
        claimed = str(w["answer"])
        if not is_adjudicable(claimed):
            # Not a failure and not a pass. Said out loud, because a lesson
            # nobody could check is a different thing from one that passed.
            unchecked += 1
            notes.append(
                f"worked example {i}: answer is prose, so re-solving it "
                "cannot confirm or contradict it — read this one yourself")
            continue
        # Two independent solves, not one. The first real run flagged both
        # of a lesson's worked examples; checked against numpy, the LESSON
        # was right both times and the single cold solve was wrong — once
        # by an arithmetic slip (k = 5 for k = 4) and once by dropping the
        # sign of det A, returning the exact negative of the true inverse.
        #
        # That is the shape of the problem: the checker is weaker than the
        # thing it checks. The lesson is written with researched guidance
        # and two calibrated examples in front of it; the re-solve gets a
        # bare question. So one disagreement is evidence about the SOLVER,
        # and only two solvers agreeing with each other and disagreeing
        # with the lesson is evidence about the lesson.
        votes = []
        for _ in range(_REDERIVE_VOTES):
            fresh, c = _rederive(client, cfg, topic_code=topic_code,
                                 full_name=full_name, unit_name=unit_name,
                                 question=str(w["question"]))
            cost += c
            votes.append(fresh)
            if answers_agree(claimed, fresh):
                break          # confirmed; a second opinion buys nothing
        else:
            if answers_agree(votes[0], votes[1]):
                status = "suspect"
                notes.append(
                    f"worked example {i}: the lesson answers "
                    f"{claimed[:80]!r}; solved fresh twice it came out "
                    f"{votes[0][:60]!r} and {votes[1][:60]!r}")
            else:
                unchecked += 1
                notes.append(
                    f"worked example {i}: two fresh attempts disagreed with "
                    f"each other ({votes[0][:40]!r} vs {votes[1][:40]!r}), "
                    "so this says the question is hard to solve cold, not "
                    "that the lesson is wrong — read this one yourself")
    if status == "draft" and unchecked:
        status = "unverified"
    return status, notes, cost


def recheck_lesson(conn, client, cfg: Config, *, user_id: int, lesson_id: int,
                   topic_code: str, full_name: str) -> LessonResult:
    """Re-run verification on a STORED lesson, leaving its text alone.

    The check improved after the first three lessons were written, and their
    stored verdicts were left saying the opposite of the truth: two worked
    examples marked `suspect` were confirmed correct against numpy, while the
    single cold solve that accused them was the thing in error.

    Rewriting the lesson to fix its label would have thrown away prose the
    owner was already reading in order to correct a judgement about it. So this
    re-judges instead: same body, same id, new status.

    Ownership arrives through `sources.user_id` — chunks carry no owner.
    """
    row = conn.execute(
        "SELECT l.id, l.body_json, ch.text AS unit"
        " FROM lessons l"
        " JOIN chunks ch ON ch.id = l.chunk_id"
        " JOIN sources s ON s.id = ch.source_id"
        " WHERE l.id = ? AND s.user_id = ?", (lesson_id, user_id)).fetchone()
    if row is None:
        raise LookupError(f"no lesson {lesson_id}")

    body = json.loads(row["body_json"])
    status, notes, cost = verify_worked(
        client, cfg, body, topic_code=topic_code, full_name=full_name,
        unit_name=row["unit"])
    conn.execute(
        "UPDATE lessons SET status = ?, notes = ?, cost_usd = cost_usd + ?"
        " WHERE id = ?",
        (status, "\n".join(notes) or None, cost, lesson_id))
    conn.commit()
    return LessonResult(body, status, notes, cost, lesson_id)


def latest_lesson(conn, user_id: int, topic_id: int, unit_name: str) -> dict | None:
    """The most recent lesson for one unit, or None.

    Joins `sources` and filters `s.user_id` — chunks carry no owner, so this is
    the only thing keeping one account's lessons out of another's.
    """
    from recall.generate.knowledge import knowledge_sha, unit_key

    row = conn.execute(
        "SELECT l.id, l.body_json, l.status, l.notes, l.created_at, ch.text AS unit"
        " FROM lessons l"
        " JOIN chunks ch ON ch.id = l.chunk_id"
        " JOIN sources s ON s.id = ch.source_id"
        " WHERE s.user_id = ? AND s.sha256 = ? AND l.topic_id = ?"
        " ORDER BY l.id DESC", (user_id, knowledge_sha(topic_id), topic_id)
    ).fetchall()
    for r in row:
        if unit_key(r["unit"]) == unit_key(unit_name):
            return {"id": r["id"], "body": json.loads(r["body_json"]),
                    "status": r["status"], "notes": r["notes"],
                    "created_at": r["created_at"], "unit": r["unit"]}
    return None


__all__ = ["LessonResult", "answers_agree", "check_structure",
           "is_adjudicable", "latest_lesson", "recheck_lesson",
           "verify_worked",
           "lesson_text", "write_lesson"]
