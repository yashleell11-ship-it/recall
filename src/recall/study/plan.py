"""What to study next, per subject.

The dashboard could already tell you that forty-one cards were due. It could
not tell you what to *do*, which is the difference between a report and a
teacher. This is the smallest honest version of the second one: for each
subject, the single next action, and the evidence behind it.

Nothing here is new arithmetic. Weakness is `assembly.weakness`, the tuned score
the paper builder already ranks by; the per-unit rollup is the shape
`paper._active_marks_per_unit` already uses; the paper-coverage rule is
`paper.units_for`. A second opinion about what "weak" means, computed
differently in a second place, is the drift this codebase keeps paying for.

**What this can and cannot see.** A unit is knowable only for knowledge-mode
cards, whose chunk carries the unit's name. Cards from an uploaded PDF are
chunked by page and a page maps to no unit, so they count toward the subject and
are invisible per unit. That is reported as `units_cover`, not hidden: a "unit 4
is your weakest" drawn from three of a subject's forty cards is a guess wearing
a fact's clothing.
"""

from dataclasses import dataclass

from recall.api.scheduling import topic_summary, utc_now
from recall.generate.knowledge import knowledge_sha, unit_key
from recall.testmode.assembly import CandidateCard, weakness

#: Below this, a unit is worth being sent back to rather than tested on. Chosen
#: to sit just under the midpoint of `weakness`'s 0..1 range, so a deck of
#: never-reviewed cards — which score exactly 0.5 weakness, i.e. 0.5 mastery —
#: does not read as "weak" merely for being new.
_WEAK_BELOW = 0.5

#: A unit holding fewer active cards than this cannot support a paper, so the
#: honest advice is to write more rather than to sit one.
_THIN_UNIT = 4


@dataclass(frozen=True)
class UnitHealth:
    """One syllabus unit, as the deck actually stands."""

    index: int          #: 0-based, into the subject's unit list
    name: str
    active: int         #: knowledge cards in rotation for this unit
    due: int
    mastery: float      #: 1 - mean weakness, 0..1; 0.5 for never-reviewed


def unit_health(conn, user_id: int, topic_id: int,
                units: list[str]) -> list[UnitHealth]:
    """Per-unit standing for one subject, in syllabus order.

    Units with nothing generated come back with `active = 0` rather than being
    omitted — "this unit is empty" is the most actionable thing the plan can
    say, and dropping the row would hide it.
    """
    rows = conn.execute(
        "SELECT ch.text AS unit_name, cs.stability, cs.difficulty, cs.due_at"
        " FROM cards c"
        " JOIN chunks ch ON ch.id = c.chunk_id"
        " JOIN sources s ON s.id = ch.source_id"
        " LEFT JOIN card_state cs ON cs.card_id = c.id AND cs.user_id = ?"
        " WHERE c.topic_id = ? AND c.state = 'active'"
        "   AND s.user_id = ? AND s.sha256 = ?",
        (user_id, topic_id, user_id, knowledge_sha(topic_id)),
    ).fetchall()

    now = utc_now()
    now_iso = now.isoformat()
    buckets: dict[str, list] = {}
    for r in rows:
        buckets.setdefault(unit_key(r["unit_name"]), []).append(r)

    out = []
    for i, name in enumerate(units):
        held = buckets.get(unit_key(name), [])
        # A throwaway CandidateCard so weakness is computed by the one function
        # that defines it, rather than by a copy of its formula living here.
        scores = [weakness(CandidateCard(0, "", 1, stability=r["stability"],
                                         difficulty=r["difficulty"],
                                         due_at=r["due_at"]), now)
                  for r in held]
        mastery = 1.0 - (sum(scores) / len(scores)) if scores else 0.0
        due = sum(1 for r in held
                  if r["due_at"] is not None and r["due_at"] <= now_iso)
        out.append(UnitHealth(index=i, name=name, active=len(held), due=due,
                              mastery=round(mastery, 3)))
    return out


def _advise(due: int, new: int, units: list[UnitHealth], active: int,
            units_cover: int) -> tuple[dict, str]:
    """The single next action for one subject, and the sentence for it.

    A ladder, not a score. Each rung is a thing you can press, and the first one
    that applies wins — a recommendation that offers three options is the report
    this was meant to replace.

    The order is load-bearing. Cards you already have and have not met outrank
    writing new ones: an early draft put the empty-unit rung above `new`, and on
    a subject built entirely from uploaded PDFs — where no card belongs to any
    unit, so every unit reads as empty — it told you to write questions while
    twelve unmet cards sat in the deck.
    """
    if active == 0:
        return ({"kind": "generate", "unit": 1},
                "nothing here yet — write some questions for unit 1")

    if due:
        return ({"kind": "review", "unit": None},
                f"{due} due — review before anything else")

    if new:
        return ({"kind": "review", "unit": None},
                f"{new} you have never seen — meet them first")

    # Everything below reasons per unit, which is only possible for cards whose
    # unit is known. On a subject whose deck is entirely uploads there is
    # nothing honest to say at unit level, so it says nothing rather than
    # calling every unit empty.
    if units_cover == 0:
        return ({"kind": "clear", "unit": None},
                "nothing due — no unit-level view on this subject yet")

    empty = [u for u in units if u.active == 0]
    if empty:
        u = empty[0]
        return ({"kind": "generate", "unit": u.index + 1},
                f"unit {u.index + 1} is empty — write questions for it")

    graded = [u for u in units if u.active]
    weakest = min(graded, key=lambda u: (u.mastery, u.index)) if graded else None
    if weakest is not None and weakest.mastery < _WEAK_BELOW:
        n = weakest.index + 1
        if weakest.active < _THIN_UNIT:
            return ({"kind": "generate", "unit": n},
                    f"unit {n} is your weakest and thin — write more for it")
        return ({"kind": "sit", "unit": n},
                f"unit {n} is your weakest — sit a test on it")

    return ({"kind": "clear", "unit": None}, "nothing pressing — you are ahead")


def study_plan(conn, user_id: int) -> list[dict]:
    """One entry per subject, in the order `topic_summary` returns them.

    Ownership travels through `topics.user_id` (in `topic_summary`) and
    `sources.user_id` (in `unit_health`). `cards` and `chunks` carry no owner of
    their own, so a query that reaches them by any other route is a leak.
    """
    out = []
    for topic in topic_summary(conn, user_id):
        meta = topic.get("meta") or {}
        units = meta.get("units") or []
        health = unit_health(conn, user_id, topic["id"], units)
        attributable = sum(u.active for u in health)
        action, advice = _advise(topic["due"], topic["new"], health,
                                 topic["active"], attributable)
        weakest = min((u for u in health if u.active),
                      key=lambda u: (u.mastery, u.index), default=None)
        out.append({
            "topic_code": topic["code"],
            "due": topic["due"],
            "new": topic["new"],
            "active": topic["active"],
            # How much of this subject the per-unit view actually accounts for.
            # Upload cards are chunked by page and belong to no unit, so on a
            # subject built from PDFs this is small and the unit advice below is
            # correspondingly narrow. Said out loud rather than papered over.
            "units_cover": attributable,
            "weakest_unit": (weakest.index + 1) if weakest else None,
            "units": [{"number": u.index + 1, "name": u.name, "active": u.active,
                       "due": u.due, "mastery": u.mastery} for u in health],
            "action": action,
            "advice": advice,
        })
    return out


__all__ = ["UnitHealth", "study_plan", "unit_health"]
