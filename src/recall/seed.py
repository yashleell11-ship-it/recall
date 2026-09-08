"""Topic seeding for the LPU Semester-1 registry.

Idempotent and rename-aware: a database created with the earlier ad-hoc codes
(MATHS, HTML) has its rows renamed in place, so every card that pointed at the
old topic keeps pointing at the same topic id under its real LPU code.
"""

import json
import sqlite3

from recall.generate.knowledge import (
    knowledge_sha,
    unit_chunk_ids,
    unit_key,
)
from recall.lpu import (
    DEFAULT_SCHEME_CONFIRMED,
    LEGACY_RENAMES,
    LEGACY_UNIT_RENAMES,
    SUBJECTS,
)



def _follow_renamed_units(conn, user_id: int, topic_id: int,
                          code: str) -> list[str]:
    """Carry a knowledge deck across a unit that was RENAMED.

    A unit's identity is its name (see knowledge._unit_chunk_id), which makes
    insertion, reordering and deletion safe by themselves — the name moves and
    its cards move with it. A rename is the one edit that breaks it: the old
    name vanishes and the cards carrying it match nothing, so they quietly
    stop belonging to any unit.

    Not hypothetical. MTH165's units were corrected from paraphrases to the
    syllabus's own wording after cards had been generated against them,
    stranding sixteen live cards under "Linear Algebra" — a unit that, by
    name, no longer exists.

    The mapping is DECLARED, in lpu.LEGACY_UNIT_RENAMES, never inferred.
    Inferring it from position cannot tell a rename from a restructure, and
    MEC103's six units were replaced by six different ones with the same
    count — a positional rule would have filed one unit's cards under another
    while reporting success. Relabelling a card as the wrong unit is worse
    than leaving it unlabelled, so anything undeclared is left alone: those
    cards stay out of unit papers and remain in whole-subject ones, which is
    what they honestly are.

    Idempotent: once applied, the old name matches nothing and the next boot
    does nothing.
    """
    mapping = LEGACY_UNIT_RENAMES.get(code) or {}
    if not mapping:
        return []
    source = conn.execute(
        "SELECT id FROM sources WHERE user_id = ? AND sha256 = ?",
        (user_id, knowledge_sha(topic_id))).fetchone()
    if source is None:
        return []

    by_name = unit_chunk_ids(conn, source["id"])
    current = [unit_key(u) for u in (SUBJECTS.get(code, {}).get("units") or [])]
    moved = []
    for was, now in mapping.items():
        chunk_id = by_name.get(unit_key(was))
        if chunk_id is None:
            continue                      # nothing was generated under it
        if unit_key(was) in current:
            continue                      # still a real unit; not a rename yet
        try:
            position = current.index(unit_key(now))
        except ValueError:
            continue                      # the new name is not a unit either
        conn.execute(
            "UPDATE chunks SET text = ?, page_ref = ? WHERE id = ?",
            (now, f"Unit {position + 1} · {now}", chunk_id))
        moved.append(f"{was!r} -> {now!r}")
    return moved


def seed_topics(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    renamed, created, refreshed = [], [], []
    relabelled: list[str] = []
    for old, new in LEGACY_RENAMES.items():
        row = conn.execute(
            "SELECT id FROM topics WHERE user_id = ? AND code = ?", (user_id, old)
        ).fetchone()
        clash = conn.execute(
            "SELECT id FROM topics WHERE user_id = ? AND code = ?", (user_id, new)
        ).fetchone()
        if row and not clash:
            conn.execute("UPDATE topics SET code = ? WHERE id = ?", (new, row["id"]))
            renamed.append(f"{old}->{new}")

    for code, info in SUBJECTS.items():
        meta = json.dumps({
            "full_name": info["full_name"],
            "credits": info["credits"],
            "units": info["units"],
            "scheme": info["scheme"],
            "ca_policy": info["ca_policy"],
            "mte_exists": info["mte_exists"],
            "exam_format": info["exam_format"],
            # False only where the weights are a placeholder rather than a
            # sourced fact, so the UI can say so instead of asserting them.
            "scheme_confirmed": info.get("scheme_confirmed",
                                         DEFAULT_SCHEME_CONFIRMED),
        })
        row = conn.execute(
            "SELECT id, meta FROM topics WHERE user_id = ? AND code = ?",
            (user_id, code)
        ).fetchone()
        if row:
            # Before overwriting meta, this is the ONLY moment both the old
            # and the new unit lists exist. A unit that was renamed can be
            # recognised here and nowhere else afterwards.
            moved = _follow_renamed_units(conn, user_id, row["id"], code)
            relabelled.extend(f"{code}: {m}" for m in moved)
            conn.execute("UPDATE topics SET label = ?, meta = ? WHERE id = ?",
                         (info["full_name"], meta, row["id"]))
            refreshed.append(code)
        else:
            conn.execute(
                "INSERT INTO topics (user_id, code, label, meta) VALUES (?,?,?,?)",
                (user_id, code, info["full_name"], meta),
            )
            created.append(code)
    conn.commit()
    return {"renamed": renamed, "created": created,
            "refreshed": refreshed, "relabelled": relabelled}
