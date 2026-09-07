"""Service layer: ties the FSRS model to the database.

Timestamps are stored as timezone-aware ISO-8601 strings throughout, which sort
lexicographically, so plain string comparison is a valid ordering and
substr(ts, 1, 10) is a valid date bucket.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from recall.schedule import fit, fsrs

SCHEDULER_VERSION = "fsrs-4.5"
_AGAIN_DELAY_MINUTES = 10

# A card you have forgotten this many times is not being learned by repetition;
# it needs to be understood. Anki suspends leeches; we surface them instead,
# because the teaching endpoint can actually explain them.
LEECH_THRESHOLD = 8


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


@dataclass(frozen=True)
class ReviewOutcome:
    card_id: int
    interval_days: float
    due_at: str
    stability: float
    difficulty: float
    predicted_r: float | None


def get_settings(conn, user_id: int) -> dict:
    row = conn.execute(
        "SELECT new_cards_per_day, daily_review_cap, desired_retention"
        " FROM settings WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        conn.execute("INSERT INTO settings (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return {"new_cards_per_day": 15, "daily_review_cap": 120,
                "desired_retention": 0.90}
    return dict(row)


def update_settings(conn, user_id: int, changes: dict) -> dict:
    allowed = {"new_cards_per_day", "daily_review_cap", "desired_retention"}
    fields = {k: v for k, v in changes.items() if k in allowed and v is not None}
    if fields:
        get_settings(conn, user_id)  # ensure the row exists
        assignments = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE settings SET {assignments} WHERE user_id = ?",
                     (*fields.values(), user_id))
        conn.commit()
    return get_settings(conn, user_id)


def new_cards_introduced_today(conn, user_id: int) -> int:
    """A card counts as introduced today if its FIRST review happened today."""
    today = iso(utc_now())[:10]
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM ("
        "  SELECT card_id, MIN(reviewed_at) AS first_seen FROM reviews"
        "  WHERE user_id = ? GROUP BY card_id"
        ") WHERE substr(first_seen, 1, 10) = ?",
        (user_id, today),
    ).fetchone()
    return row["n"]


def build_queue(conn, user_id: int, topic_code: str | None = None,
                limit: int | None = None) -> dict:
    settings = get_settings(conn, user_id)
    now = iso(utc_now())
    topic_clause = " AND t.code = ?" if topic_code else ""
    topic_args: tuple = (topic_code,) if topic_code else ()

    due_rows = conn.execute(
        "SELECT c.id, c.kind, c.question, c.answer, c.cloze_text, c.origin,"
        " t.code AS topic_code,"
        " ch.page_ref, cs.due_at, cs.stability, cs.difficulty, cs.lapses,"
        " (SELECT MAX(reviewed_at) FROM reviews r"
        "  WHERE r.card_id = c.id AND r.user_id = cs.user_id) AS last_reviewed_at"
        " FROM cards c"
        " JOIN card_state cs ON cs.card_id = c.id AND cs.user_id = ?"
        " JOIN topics t ON t.id = c.topic_id"
        " JOIN chunks ch ON ch.id = c.chunk_id"
        " WHERE c.state = 'active' AND cs.due_at <= ?"
        f" AND t.user_id = ?{topic_clause}"
        " ORDER BY cs.due_at ASC",
        (user_id, now, user_id, *topic_args),
    ).fetchall()

    new_budget = max(0, settings["new_cards_per_day"]
                     - new_cards_introduced_today(conn, user_id))
    # t.user_id is load-bearing, not decoration: the only other user-bound
    # predicate here is "this user has no card_state row for it", and ANOTHER
    # user's untouched card satisfies that perfectly. Without this filter the
    # new-card queue serves other people's cards, question and answer text and
    # all. The due half above is safe for a different reason — it INNER JOINs
    # card_state on this user, so it can only ever return cards they have
    # personally studied.
    new_rows = conn.execute(
        "SELECT c.id, c.kind, c.question, c.answer, c.cloze_text, c.origin,"
        " t.code AS topic_code, ch.page_ref"
        " FROM cards c"
        " JOIN topics t ON t.id = c.topic_id"
        " JOIN chunks ch ON ch.id = c.chunk_id"
        " LEFT JOIN card_state cs ON cs.card_id = c.id AND cs.user_id = ?"
        " WHERE c.state = 'active' AND cs.card_id IS NULL"
        f" AND t.user_id = ?{topic_clause}"
        " ORDER BY c.id ASC LIMIT ?",
        (user_id, user_id, *topic_args, new_budget),
    ).fetchall()

    def card(row, is_new: bool) -> dict:
        # Memory state travels with the card so the client can price each grade
        # button exactly, instead of estimating what the next interval will be.
        keys = row.keys()
        stability = None if is_new else row["stability"]
        difficulty = None if is_new else row["difficulty"]
        lapses = 0 if is_new else (row["lapses"] if "lapses" in keys else 0)
        elapsed = 0.0
        if not is_new and "last_reviewed_at" in keys and row["last_reviewed_at"]:
            elapsed = max(
                0.0,
                (utc_now() - datetime.fromisoformat(row["last_reviewed_at"]))
                .total_seconds() / 86400.0,
            )
        return {"id": row["id"], "kind": row["kind"], "question": row["question"],
                "answer": row["answer"], "cloze_text": row["cloze_text"],
                "origin": row["origin"],
                "topic_code": row["topic_code"], "page_ref": row["page_ref"],
                "is_new": is_new, "stability": stability, "difficulty": difficulty,
                "elapsed_days": round(elapsed, 4),
                "lapses": lapses, "is_leech": lapses >= LEECH_THRESHOLD}

    cards = [card(r, False) for r in due_rows] + [card(r, True) for r in new_rows]
    cap = min(settings["daily_review_cap"], limit or settings["daily_review_cap"])
    cap_reached = len(cards) > cap
    return {
        "cards": cards[:cap],
        "due_remaining": max(0, len(due_rows) - cap),
        "new_remaining": max(0, new_budget - len(new_rows)),
        "cap_reached": cap_reached,
    }


def _last_reviewed_at(conn, card_id: int, user_id: int) -> str | None:
    row = conn.execute(
        "SELECT MAX(reviewed_at) AS m FROM reviews WHERE card_id = ? AND user_id = ?",
        (card_id, user_id),
    ).fetchone()
    return row["m"]


def record_review(conn, user_id: int, card_id: int, grade: int) -> ReviewOutcome:
    if grade not in (1, 2, 3, 4):
        raise ValueError("grade must be 1, 2, 3 or 4")
    # Joined through topics: a card id on its own is not proof of ownership,
    # and without this any signed-in user could record reviews against — and
    # so schedule themselves through — someone else's deck.
    exists = conn.execute(
        "SELECT c.id, c.state FROM cards c JOIN topics t ON t.id = c.topic_id"
        " WHERE c.id = ? AND t.user_id = ?", (card_id, user_id)
    ).fetchone()
    if exists is None:
        raise LookupError(f"no card {card_id}")

    settings = get_settings(conn, user_id)
    params = fit.load_latest_params(conn)
    now = utc_now()
    state_row = conn.execute(
        "SELECT stability, difficulty, reps, lapses FROM card_state"
        " WHERE card_id = ? AND user_id = ?", (card_id, user_id)
    ).fetchone()

    if state_row is None:
        elapsed_days = 0.0
        predicted_r = None
        state = fsrs.initial_state(grade, params)
        reps, lapses = 1, (1 if grade == 1 else 0)
    else:
        last = _last_reviewed_at(conn, card_id, user_id)
        elapsed_days = 0.0
        if last:
            elapsed_days = max(
                0.0, (now - datetime.fromisoformat(last)).total_seconds() / 86400.0
            )
        predicted_r = fsrs.retrievability(elapsed_days, state_row["stability"])
        state = fsrs.next_state(
            fsrs.MemoryState(state_row["stability"], state_row["difficulty"]),
            grade, elapsed_days, params,
        )
        reps = state_row["reps"] + 1
        lapses = state_row["lapses"] + (1 if grade == 1 else 0)

    if grade == 1:
        due = now + timedelta(minutes=_AGAIN_DELAY_MINUTES)
        interval = _AGAIN_DELAY_MINUTES / (60 * 24)
    else:
        interval = fsrs.interval_days(state.stability, settings["desired_retention"])
        due = now + timedelta(days=max(1.0, round(interval)))

    conn.execute(
        "INSERT INTO reviews (card_id, user_id, reviewed_at, grade, elapsed_days,"
        " predicted_r, scheduler_version) VALUES (?,?,?,?,?,?,?)",
        (card_id, user_id, iso(now), grade, elapsed_days, predicted_r,
         SCHEDULER_VERSION),
    )
    conn.execute(
        "INSERT INTO card_state (card_id, user_id, stability, difficulty, due_at,"
        " reps, lapses) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(card_id, user_id) DO UPDATE SET"
        " stability=excluded.stability, difficulty=excluded.difficulty,"
        " due_at=excluded.due_at, reps=excluded.reps, lapses=excluded.lapses",
        (card_id, user_id, state.stability, state.difficulty, iso(due), reps, lapses),
    )
    conn.commit()
    return ReviewOutcome(card_id, interval, iso(due), state.stability,
                         state.difficulty, predicted_r)


def topic_summary(conn, user_id: int) -> list[dict]:
    import json

    now = iso(utc_now())
    rows = conn.execute(
        "SELECT t.id, t.code, t.label, t.meta,"
        " SUM(CASE WHEN c.state='active' AND cs.due_at IS NOT NULL"
        "          AND cs.due_at <= ? THEN 1 ELSE 0 END) AS due,"
        " SUM(CASE WHEN c.state='active' AND cs.card_id IS NULL THEN 1 ELSE 0 END)"
        "     AS new,"
        " SUM(CASE WHEN c.state='active' THEN 1 ELSE 0 END) AS active,"
        " SUM(CASE WHEN c.state='pending' THEN 1 ELSE 0 END) AS pending"
        " FROM topics t"
        " LEFT JOIN cards c ON c.topic_id = t.id"
        " LEFT JOIN card_state cs ON cs.card_id = c.id AND cs.user_id = ?"
        " WHERE t.user_id = ? GROUP BY t.id ORDER BY t.code",
        (now, user_id, user_id),
    ).fetchall()
    out = []
    for r in rows:
        item = {k: (r[k] or 0) if k in ("due", "new", "active", "pending") else r[k]
                for k in ("id", "code", "label", "due", "new", "active", "pending")}
        item["meta"] = json.loads(r["meta"]) if r["meta"] else None
        out.append(item)
    return out


def stats(conn, user_id: int) -> dict:
    today = iso(utc_now())[:10]
    today_row = conn.execute(
        "SELECT COUNT(*) AS reviewed,"
        " SUM(CASE WHEN grade = 1 THEN 1 ELSE 0 END) AS again"
        " FROM reviews WHERE user_id = ? AND substr(reviewed_at, 1, 10) = ?",
        (user_id, today),
    ).fetchone()
    days = conn.execute(
        "SELECT substr(reviewed_at, 1, 10) AS date, COUNT(*) AS count"
        " FROM reviews WHERE user_id = ? GROUP BY date ORDER BY date DESC LIMIT 14",
        (user_id,),
    ).fetchall()
    totals = conn.execute(
        "SELECT SUM(CASE WHEN c.state='active' THEN 1 ELSE 0 END) AS active,"
        " SUM(CASE WHEN c.state='pending' THEN 1 ELSE 0 END) AS pending"
        " FROM cards c JOIN topics t ON t.id = c.topic_id WHERE t.user_id = ?",
        (user_id,),
    ).fetchone()
    sources = conn.execute(
        "SELECT COUNT(*) AS n FROM sources WHERE user_id = ?", (user_id,)
    ).fetchone()["n"]
    leeches = conn.execute(
        "SELECT COUNT(*) AS n FROM card_state cs JOIN cards c ON c.id = cs.card_id"
        " WHERE cs.user_id = ? AND cs.lapses >= ? AND c.state = 'active'",
        (user_id, LEECH_THRESHOLD),
    ).fetchone()["n"]

    streak, cursor = 0, utc_now()
    seen = {r["date"] for r in days}
    while iso(cursor)[:10] in seen:
        streak += 1
        cursor -= timedelta(days=1)

    return {
        "today": {"reviewed": today_row["reviewed"] or 0,
                  "again": today_row["again"] or 0,
                  "streak": streak},
        "by_topic": topic_summary(conn, user_id),
        "last_14_days": [{"date": r["date"], "count": r["count"]}
                         for r in reversed(days)],
        "totals": {"active": totals["active"] or 0,
                   "pending": totals["pending"] or 0,
                   "sources": sources,
                   "leeches": leeches},
    }
