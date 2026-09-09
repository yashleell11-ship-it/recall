"""Knowledge mode: cards for a syllabus unit with nothing uploaded.

The upload pipeline's contract is "every card is traceable to a verbatim
quote from something you uploaded". This module deliberately breaks that
contract, on the owner's explicit call, so that a student can study a subject
before they have scanned a single page.

What that costs is stated plainly rather than hidden: `check_grounded` has no
passage to check against and is dropped, and `check_closed_book` — whose only
job is to REJECT cards answerable without the source — is inverted here, so
it is dropped too. What survives is every check that never needed a source:
answerability, atomicity, and semantic dedup.

Because of that, a card written here carries less warranty than an
upload-grounded one — and it is important to be exact about what catches that,
because this docstring used to claim a gate that no longer exists. There is no
approval queue: `pipeline.keep_state` returns 'active' unconditionally, and has
since triage-before-use was removed. A knowledge card goes straight into
rotation like any other.

What actually stands between a wrong card and a wrong memory is therefore the
`no source` mark on screen, review itself — a bad card is graded `again`,
surfaces as a leech, and is suspended with one press — and, where the unit has
course material loaded, a lesson whose every claim is quoted verbatim from it
(see recall.teach.lessons). Naming a gate that is not there is worse than
naming none: it is a promise nobody is keeping.

Every card is written with `origin='knowledge'` so the rest of the app can
tell the two kinds apart and say so on screen.

The FK on `cards.chunk_id` is satisfied by a synthetic source + one chunk per
unit rather than by making the column nullable: seven read paths inner-join
`chunks`, so a null there would silently drop these cards out of the review
queue, test assembly, teaching, the CLI and the Anki export. `demo.py` already
uses this same synthetic-row shape.
"""

import hashlib
import json
import sqlite3

from recall.config import Config
from recall.generate.generate import Candidate, _parse
from recall.generate.prompts import (
    KNOWLEDGE_GENERATE_SYSTEM,
    KNOWLEDGE_GENERATE_USER,
    format_guidance,
)
from recall.generate.unit_guidance import examples_text, guidance_text
# Re-exported: unit identity is normalised in exactly one place, and that
# place has to be a leaf module so unit_guidance can use it too without a
# cycle. Every existing caller imports it from here.
from recall.lpu import unit_key  # noqa: F401
from recall.pipeline import (
    IngestResult,
    _cost,
    _insert_card,
    _now,
    assign_arm,
    keep_state,
)
from recall.verify.dedupe import dedupe, embed_texts
from recall.verify.heuristics import check_answerable, check_atomic
from recall.verify.judges import check_facts

# One request per unit, so ask for a deck's worth rather than a chunk's worth.
DEFAULT_CARDS_PER_UNIT = 12
# A server-side ceiling, not a prompt request: a prompt is a suggestion, and
# this is the thing that actually bounds one press of the button.
MAX_CARDS_PER_CALL = 25

SYNTHETIC_KIND = "knowledge"
SYNTHETIC_FILENAME = "AI knowledge (no upload)"


def knowledge_sha(topic_id: int) -> str:
    """Deterministic, so the per-topic synthetic source is found, not remade."""
    return hashlib.sha256(f"knowledge:{topic_id}".encode()).hexdigest()


def _synthetic_source_id(conn, user_id: int, topic_id: int) -> int:
    sha = knowledge_sha(topic_id)
    row = conn.execute(
        "SELECT id FROM sources WHERE user_id = ? AND sha256 = ?", (user_id, sha)
    ).fetchone()
    if row:
        return row["id"]
    try:
        cur = conn.execute(
            "INSERT INTO sources (user_id, topic_id, filename, kind, sha256, added_at)"
            " VALUES (?,?,?,?,?,?)",
            (user_id, topic_id, SYNTHETIC_FILENAME, SYNTHETIC_KIND, sha, _now()),
        )
    except sqlite3.IntegrityError:
        # Two presses of the button at once; UNIQUE(user_id, sha256) picked a
        # winner and this is the loser reading the winner's row.
        conn.rollback()
        row = conn.execute(
            "SELECT id FROM sources WHERE user_id = ? AND sha256 = ?", (user_id, sha)
        ).fetchone()
        if row is None:
            raise
        return row["id"]
    return cur.lastrowid




def unit_chunk_ids(conn, source_id: int) -> dict[str, int]:
    """Every unit chunk under a knowledge source, keyed by unit name.

    THE one place that answers "which chunk is this unit". Three call sites
    used to work it out independently from the chunk's ORDINAL, and that is
    exactly how they drifted: an ordinal is a position, and a syllabus is
    editable, so position stopped meaning what it did when the cards were
    written.
    """
    return {
        unit_key(r["text"]): r["id"]
        for r in conn.execute(
            "SELECT id, text FROM chunks WHERE source_id = ?", (source_id,))
    }


def _unit_chunk_id(conn, source_id: int, unit_index: int, unit_name: str) -> int:
    """One chunk per unit, identified by the unit's NAME.

    Its text is the unit's name and nothing more: padding it into a
    passage-shaped paragraph would let an intentionally ungrounded card be
    laundered through a grounding check later. That text is now also the
    unit's identity.

    It used to look the chunk up by `ordinal` and return whatever sat there,
    never comparing the name. So the moment a syllabus was edited — a unit
    inserted, reordered, or dropped — every stored ordinal kept pointing at
    its old position while `topics.meta` moved on, and cards written for one
    unit were served under another's name. That is not hypothetical: MEC103's
    unit list was restructured wholesale in this project (its old units 1-3
    were folded into one and its old unit 6 split into three), and CSE111's
    grew a seventh.

    Matching on the name makes reorder and insertion free, and makes a
    DELETED unit degrade honestly: its cards match no current unit, so they
    stay out of unit-scoped papers while remaining in whole-subject ones,
    which is exactly what they still are — real cards about the subject.

    `ordinal` survives as the historical insertion slot and the display
    position. It carries a UNIQUE(source_id, ordinal) constraint, so it
    cannot be shuffled freely on a reorder; nothing reads it as a unit index
    any more, and `page_ref` — which IS printed beside a question — is
    brought back in line whenever the unit's position moves.
    """
    key = unit_key(unit_name)
    page_ref = f"Unit {unit_index + 1} · {unit_name}"

    row = conn.execute(
        "SELECT id, ordinal, page_ref FROM chunks WHERE source_id = ?"
        " AND lower(trim(text)) = lower(trim(?))",
        (source_id, unit_name),
    ).fetchone()
    if row is None:
        # Fall back to a Python-side comparison, which normalises interior
        # whitespace too; SQL's trim() only touches the ends.
        for candidate in conn.execute(
                "SELECT id, ordinal, page_ref, text FROM chunks"
                " WHERE source_id = ?", (source_id,)):
            if unit_key(candidate["text"]) == key:
                row = candidate
                break

    if row is not None:
        # The unit still exists; only its position may have moved. Correct
        # the label that gets printed next to every question from it.
        if row["page_ref"] != page_ref:
            conn.execute("UPDATE chunks SET page_ref = ? WHERE id = ?",
                         (page_ref, row["id"]))
        return row["id"]

    # A unit with no chunk yet. Take the first free slot rather than
    # `unit_index`: after a reorder the slot for this index may be occupied
    # by a unit that has not moved, and UNIQUE(source_id, ordinal) would
    # refuse the insert.
    taken = {r["ordinal"] for r in conn.execute(
        "SELECT ordinal FROM chunks WHERE source_id = ?", (source_id,))}
    slot = unit_index if unit_index not in taken else (
        max(taken) + 1 if taken else unit_index)
    cur = conn.execute(
        "INSERT INTO chunks (source_id, ordinal, text, page_ref) VALUES (?,?,?,?)",
        (source_id, slot, unit_name, page_ref),
    )
    return cur.lastrowid


def generate_knowledge_cards(client, *, topic_code: str, full_name: str,
                             exam_format: str, unit_name: str, unit_number: int,
                             n: int) -> tuple[list[Candidate], int, int]:
    resp = client.complete_json(
        KNOWLEDGE_GENERATE_SYSTEM,
        KNOWLEDGE_GENERATE_USER.format(
            topic_code=topic_code, full_name=full_name,
            format_guidance=format_guidance(exam_format),
            unit_guidance=guidance_text(topic_code, unit_number),
            unit_examples=examples_text(topic_code, unit_number),
            unit_name=unit_name, unit_number=unit_number, n=n,
        ),
    )
    return _parse(resp.content), resp.prompt_tokens, resp.completion_tokens


def topic_units(meta_json: str | None) -> list[str]:
    """The unit list a topic carries, or [] when it has no LPU metadata —
    test fixtures insert topics without it, and so did every database made
    before the subject registry existed."""
    if not meta_json:
        return []
    try:
        meta = json.loads(meta_json)
    except json.JSONDecodeError:
        return []
    units = meta.get("units") if isinstance(meta, dict) else None
    return [u for u in units if isinstance(u, str)] if isinstance(units, list) else []


def generate_for_unit(conn, cfg: Config, client, *, user_id: int, topic_id: int,
                      topic_code: str, full_name: str, exam_format: str,
                      unit_index: int, unit_name: str,
                      n: int = DEFAULT_CARDS_PER_UNIT,
                      state: str | None = None,
                      embed=embed_texts) -> IngestResult:
    """One paid call, then the source-independent gates, then insert.

    `unit_index` is 0-based; the prompt shows the student-facing 1-based
    number.

    `state` overrides where surviving cards land. It defaults to the normal
    rule (knowledge cards wait for approval, because nothing has checked them
    against reality). The one caller that overrides it is the paper builder:
    when you have asked to sit a paper on this unit right now, the cards are
    not entering your rotation unseen — you are about to read every one of
    them and grade yourself on it, which is a stricter look than the approval
    queue gives. Holding them back would just produce an empty paper, which is
    the bug this was built to fix.
    """
    n = max(1, min(n, MAX_CARDS_PER_CALL))
    source_id = _synthetic_source_id(conn, user_id, topic_id)
    chunk_id = _unit_chunk_id(conn, source_id, unit_index, unit_name)
    conn.commit()

    candidates, prompt_tokens, completion_tokens = generate_knowledge_cards(
        client, topic_code=topic_code, full_name=full_name,
        exam_format=exam_format, unit_name=unit_name,
        unit_number=unit_index + 1, n=n,
    )

    accepted = rejected = 0
    survivors: list[Candidate] = []
    for c in candidates:
        # check_grounded and check_closed_book are absent by design — see the
        # module docstring. These two never needed a passage.
        reason = check_answerable(c) or check_atomic(c)
        if reason is None:
            survivors.append(c)
        else:
            _insert_card(conn, chunk_id, topic_id, c, "rejected", reason,
                         "learned", origin="knowledge")
            rejected += 1

    # Seeded with what this unit already holds. Uploaded chunks are generated
    # from exactly once (`generated_at`), but this button can be pressed
    # repeatedly against the same unit, and a fresh completion will happily
    # reproduce cards it already wrote. Without the seed, "generate more" is a
    # duplicate-flooding vector that simply does not exist on the upload path.
    seen = [r["question"] for r in conn.execute(
        "SELECT question FROM cards WHERE topic_id = ? AND chunk_id = ?"
        " AND state != 'rejected'", (topic_id, chunk_id)
    ).fetchall()]

    # The fact check. Upload-grounded cards are verified against their own
    # passage; these have none, and no longer a human reading them either, so
    # this is the only thing that looks at them before they enter the deck.
    # One call for the batch — the cost of the whole check is a fraction of
    # the generation that produced it.
    checked, pt, ct = check_facts(
        client, survivors, topic_code=topic_code, full_name=full_name,
        unit_name=unit_name, unit_number=unit_index + 1,
    )
    prompt_tokens += pt
    completion_tokens += ct
    survivors = []
    for candidate, reason in checked:
        if reason is None:
            survivors.append(candidate)
        else:
            _insert_card(conn, chunk_id, topic_id, candidate, "rejected", reason,
                         "learned", origin="knowledge")
            rejected += 1

    kept, dropped = dedupe(survivors, embed=embed, seed_texts=seen)
    for c, reason in dropped:
        _insert_card(conn, chunk_id, topic_id, c, "rejected", reason, "learned",
                     origin="knowledge")
        rejected += 1
    landing = state or keep_state("knowledge")
    for c in kept:
        _insert_card(conn, chunk_id, topic_id, c, landing, None,
                     assign_arm(accepted), origin="knowledge")
        accepted += 1

    cost = _cost(cfg, prompt_tokens, completion_tokens)
    _record_run(conn, source_id, cfg.model, prompt_tokens, completion_tokens,
                cost, accepted, rejected)
    conn.commit()
    # stopped_early is always False: there is no chunk loop to stop part-way
    # through — one unit is one call, and `n` bounds it up front.
    return IngestResult(source_id, accepted, rejected, cost, False)


def _record_run(conn, source_id: int, model: str, prompt_tokens: int,
                completion_tokens: int, cost: float, accepted: int,
                rejected: int) -> None:
    """Accumulated onto one row per source, matching the upload path — /api/sources
    LEFT JOINs gen_runs without aggregating, so a second row would list the
    source twice with its totals split."""
    existing = conn.execute(
        "SELECT id FROM gen_runs WHERE source_id = ?", (source_id,)
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO gen_runs (source_id, ran_at, model, prompt_tokens,"
            " completion_tokens, cost_estimate, cards_accepted, cards_rejected)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (source_id, _now(), model, prompt_tokens, completion_tokens, cost,
             accepted, rejected),
        )
    else:
        conn.execute(
            "UPDATE gen_runs SET ran_at = ?, model = ?,"
            " prompt_tokens = prompt_tokens + ?,"
            " completion_tokens = completion_tokens + ?,"
            " cost_estimate = cost_estimate + ?,"
            " cards_accepted = cards_accepted + ?,"
            " cards_rejected = cards_rejected + ? WHERE id = ?",
            (_now(), model, prompt_tokens, completion_tokens, cost, accepted,
             rejected, existing["id"]),
        )
