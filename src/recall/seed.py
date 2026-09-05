"""Topic seeding for the LPU Semester-1 registry.

Idempotent and rename-aware: a database created with the earlier ad-hoc codes
(MATHS, HTML) has its rows renamed in place, so every card that pointed at the
old topic keeps pointing at the same topic id under its real LPU code.
"""

import json
import sqlite3

from recall.lpu import LEGACY_RENAMES, SUBJECTS


def seed_topics(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    renamed, created, refreshed = [], [], []
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
        })
        row = conn.execute(
            "SELECT id FROM topics WHERE user_id = ? AND code = ?", (user_id, code)
        ).fetchone()
        if row:
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
    return {"renamed": renamed, "created": created, "refreshed": refreshed}
