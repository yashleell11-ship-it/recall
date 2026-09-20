"""Put the curated bank into the database. Runs on every boot, idempotently.

Two rules carry the whole design:

**Upsert on `key`, never insert-and-replace.** `mcq_attempts` stores the
question ids it drew, so a question that got a new row id every boot would
orphan every attempt that used it. Editing a typo in the JSON has to fix the
question in place.

**A question removed from the JSON is retired, not deleted**, for the same
reason: `active = 0` keeps it out of future draws while every attempt that
already holds it stays readable and gradable.

Retirement is scoped to the (subject, unit) pairs the files actually cover.
Seeding from a directory that holds only CSE111 unit 1 must not retire unit 2
— the files are the truth about the units they describe and say nothing about
any other.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from recall.mcq.bank import load_bank
from recall.mcq.registry import MCQ_UNITS

_UPSERT = """
INSERT INTO mcq_questions
  (key, subject_code, unit, topic, kind, question, options_json, correct,
   explain, why_wrong_json, active, updated_at)
VALUES (?,?,?,?,?,?,?,?,?,?,1,?)
ON CONFLICT(key) DO UPDATE SET
  subject_code = excluded.subject_code,
  unit         = excluded.unit,
  topic        = excluded.topic,
  kind         = excluded.kind,
  question     = excluded.question,
  options_json = excluded.options_json,
  correct      = excluded.correct,
  explain      = excluded.explain,
  why_wrong_json = excluded.why_wrong_json,
  active       = 1,
  updated_at   = excluded.updated_at
"""


def seed_mcq_bank(conn: sqlite3.Connection,
                  bank_dir: Path | str | None = None) -> dict:
    """Load the bank and reconcile the table with it. Returns counts.

    Idempotent: seeding an unchanged bank twice leaves the same rows and
    reports the same counts. `retired` is the only delta in there — it counts
    rows this run switched off, so it is non-zero exactly once after a
    question is removed from the JSON and zero on every boot after that.
    """
    files = load_bank(bank_dir)
    now = datetime.now(timezone.utc).isoformat()

    questions = 0
    for bank_file in files:
        for q in bank_file.questions:
            conn.execute(_UPSERT, (
                q["key"], q["subject_code"], q["unit"], q["topic"], q["kind"],
                q["question"], json.dumps(q["options"]), q["correct"],
                q["explain"], json.dumps(q["why_wrong"]), now,
            ))
            questions += 1

    # Group by (subject, unit) rather than by file so two files describing the
    # same unit are reconciled together instead of retiring each other.
    covered: dict[tuple[str, int], set[str]] = {}
    for bank_file in files:
        keys = covered.setdefault((bank_file.subject_code, bank_file.unit), set())
        keys.update(q["key"] for q in bank_file.questions)

    retired = 0
    for (subject_code, unit), keys in covered.items():
        if keys:
            holes = ",".join("?" for _ in keys)
            cur = conn.execute(
                "UPDATE mcq_questions SET active = 0, updated_at = ?"
                " WHERE subject_code = ? AND unit = ? AND active = 1"
                f" AND key NOT IN ({holes})",
                (now, subject_code, unit, *sorted(keys)))
        else:
            # A file that lists a unit and no questions retires the unit.
            cur = conn.execute(
                "UPDATE mcq_questions SET active = 0, updated_at = ?"
                " WHERE subject_code = ? AND unit = ? AND active = 1",
                (now, subject_code, unit))
        retired += cur.rowcount

    conn.commit()
    active = conn.execute(
        "SELECT COUNT(*) AS n FROM mcq_questions WHERE active = 1").fetchone()["n"]

    # Questions for a (subject, unit) the registry does not declare are seeded
    # like any other and then reachable by nobody: the picker is driven by
    # MCQ_UNITS and `create_attempt` validates against it, so a file named for
    # the wrong subject, or a unit added to the bank before the registry,
    # disappears without a word. Counted rather than raised on purpose — the
    # container entrypoint runs this under `set -e`, so a raise here would take
    # the whole site down over one mis-named file. This makes it loud instead:
    # the boot line prints it, and it is zero on a bank that is wired up.
    unreachable = sum(
        1 for f in files for q in f.questions
        if q["unit"] not in MCQ_UNITS.get(q["subject_code"], {}).get("units", {}))

    return {"files": len(files), "questions": questions, "retired": retired,
            "active": active, "unreachable": unreachable}


__all__ = ["seed_mcq_bank"]
