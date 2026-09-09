"""Reading a stored lesson. Two GETs, both pure reads.

Lessons are written offline by `recall lessons <TOPIC> --unit N` because each
one takes a minute or two and costs money against a $1.00 daily cap with no
resume path. Until now there was no way to READ one short of
`docker exec ... python -m recall.cli lesson-show` over SSH, which is the same
mistake `card_explanations` made from the other end: the one teaching feature
that shipped has zero rows because it sits behind a button nobody presses.

**Nothing here spends money and nothing here writes.** No `Depends(get_llm)`,
no `DeepSeekClient` import, no `conn.commit()`, no view counter, no cache row.
That is load-bearing rather than incidental: `web/lib/resources.ts::prefetchFor`
fires on route *intent*, so a paid GET on this path would bill the owner for a
hover.

The two shaping functions live beside the routes rather than in
`recall.teach.lessons` — that module owns the WRITING pipeline (prompts, gates,
re-derivation) and is imported by the CLI; the read-side shaping is only ever
wanted by these two routes. What is emphatically NOT duplicated is the lookup
itself: `lesson_page` calls `latest_lesson`, and `lesson_index` reproduces its
selection rule (same synthetic source, same `unit_key` match, same
`ORDER BY l.id DESC` first-match-wins) so the index and the reader can never
disagree about which lesson is the current one for a unit.
"""

import json

from fastapi import APIRouter, Depends, HTTPException

from recall.api.deps import get_conn, get_current_user
from recall.generate.knowledge import knowledge_sha, topic_units
from recall.lpu import unit_key
from recall.teach.lessons import latest_lesson

router = APIRouter()


def _meta(meta_json: str | None) -> dict:
    """topics.meta as a dict, tolerating null and junk exactly as topic_units does."""
    if not meta_json:
        return {}
    try:
        meta = json.loads(meta_json)
    except json.JSONDecodeError:
        return {}
    return meta if isinstance(meta, dict) else {}


def _full_name(row) -> str:
    return str(_meta(row["meta"]).get("full_name") or row["label"] or row["code"])


def _notes(raw: str | None) -> list[str]:
    """`lessons.notes` as a list of sentences.

    Split here, once, rather than in the client: the notes are plain prose
    separated by newlines and a browser that string-splits prose is one
    `\\n` away from showing half a sentence as a bullet.
    """
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _counts(body: dict) -> tuple[int, int]:
    """(sections carrying a quote, sections) — the coverage meter's two numbers.

    This is NOT a re-verification and deliberately does not call
    `check_grounding`. `drop_bad_citations` already removed every quote Python
    could not find verbatim before the lesson was stored, so a stored quote is
    by construction one that passed. Counting them is honest and free;
    re-checking them would need the corpus on a read path and would become a
    second, drifting definition of "verified".
    """
    sections = [s for s in (body.get("sections") or []) if isinstance(s, dict)]
    cited = sum(1 for s in sections if str(s.get("quote") or "").strip())
    return cited, len(sections)


def lesson_index(conn, user_id: int) -> list[dict]:
    """Which syllabus units have a written lesson, per subject.

    One row per unit of every topic that carries LPU metadata with units —
    including the units with nothing written, because "MTH165 unit 4 has
    nothing" is information a student wants and an index that only lists what
    exists cannot say it. Topics with no `meta.units` are omitted entirely:
    nothing can be written for them.

    Ownership (L1): `cards` and `chunks` carry no user_id, so a lesson's owner
    is reachable only by joining out to `sources.user_id` or `topics.user_id`.
    Both are applied here, as two independent gates on the same request — a
    lesson appears only if the topic AND the synthetic source behind its chunk
    both belong to the caller. `s.user_id` is the load-bearing one, since the
    chunk is what the lesson actually points at.

    A stored lesson whose unit name matches no CURRENT syllabus unit is
    dropped, not relabelled: that is what a lesson written before the syllabus
    was edited looks like, and quietly filing it under a neighbouring unit is
    the `_unit_chunk_id` ordinal bug arriving from the index side.
    """
    rows = conn.execute(
        "SELECT t.id AS topic_id, l.id AS lesson_id, l.status, l.created_at,"
        " ch.text AS unit, s.sha256"
        " FROM lessons l"
        " JOIN chunks ch ON ch.id = l.chunk_id"
        " JOIN sources s ON s.id = ch.source_id"
        " JOIN topics t ON t.id = l.topic_id"
        " WHERE s.user_id = ? AND t.user_id = ?"
        " ORDER BY l.id DESC",
        (user_id, user_id),
    ).fetchall()

    # Newest first, first match wins — `latest_lesson`'s rule, with its
    # normaliser and its restriction to the topic's synthetic knowledge source.
    newest: dict[tuple[int, str], dict] = {}
    for r in rows:
        if r["sha256"] != knowledge_sha(r["topic_id"]):
            continue
        key = (r["topic_id"], unit_key(r["unit"]))
        newest.setdefault(key, {"id": r["lesson_id"], "status": r["status"],
                                "created_at": r["created_at"]})

    out: list[dict] = []
    topics = conn.execute(
        "SELECT id, code, label, meta FROM topics WHERE user_id = ? ORDER BY code",
        (user_id,),
    ).fetchall()
    for t in topics:
        units = topic_units(t["meta"])
        if not units:
            continue
        entries = [{"number": i, "name": name,
                    "lesson": newest.get((t["id"], unit_key(name)))}
                   for i, name in enumerate(units, 1)]
        out.append({
            "topic_code": t["code"],
            "full_name": _full_name(t),
            "written": sum(1 for e in entries if e["lesson"] is not None),
            "units": entries,
        })
    return out


def lesson_page(conn, user_id: int, topic_code: str, unit_number: int) -> dict:
    """One unit's lesson, or the unit with `lesson: null`.

    `unit_number` is 1-based — the number a student reads off a timetable.

    Raises LookupError for a topic that is not yours (which is the same 404 as
    a topic that does not exist: answering those two differently would turn
    this route into an oracle for what other accounts have), and ValueError for
    a topic with no syllabus units or a unit past the end of one.

    A unit with nothing written is a 200 with `lesson: null`, not a 404. It is
    a state, not an error — it mirrors `latest_lesson` returning None — and the
    client needs `unit_name` in hand to print the exact CLI command in its
    empty state, which a 404 body cannot carry.
    """
    row = conn.execute(
        "SELECT id, code, label, meta FROM topics WHERE user_id = ? AND code = ?",
        (user_id, topic_code),
    ).fetchone()
    if row is None:
        raise LookupError(f"no topic {topic_code!r}")
    units = topic_units(row["meta"])
    if not units:
        raise ValueError(f"{topic_code} has no syllabus units on record")
    if not 1 <= unit_number <= len(units):
        raise ValueError(f"{topic_code} has {len(units)} units;"
                         f" there is no unit {unit_number}")

    unit_name = units[unit_number - 1]
    got = latest_lesson(conn, user_id, row["id"], unit_name)
    lesson = None
    if got is not None:
        cited, total = _counts(got["body"])
        lesson = {
            "id": got["id"],
            "status": got["status"],
            "notes": _notes(got["notes"]),
            "created_at": got["created_at"],
            "cited_sections": cited,
            "section_count": total,
            "body": got["body"],
        }
    return {
        "topic_code": row["code"],
        "full_name": _full_name(row),
        "unit_number": unit_number,
        "unit_name": unit_name,
        "lesson": lesson,
    }


@router.get("/api/teach/lessons")
def lessons_index(user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
    """Which units have a written lesson. Reads rows; never a paid call — the
    web client prefetches this on route intent."""
    return lesson_index(conn, user_id)


@router.get("/api/teach/lessons/{topic_code}/{unit}")
def lessons_read(topic_code: str, unit: int,
                 user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
    """One stored lesson, or the unit with `lesson: null`. Never a paid call."""
    try:
        return lesson_page(conn, user_id, topic_code, unit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
