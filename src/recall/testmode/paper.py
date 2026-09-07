"""Sit a real paper for a subject, whether or not the deck can cover it.

Test mode assembles a paper out of cards you already have. That is the right
default and it has one failure: on a subject you have not uploaded anything
for, it produces "This paper has no questions", which is exactly what the
owner saw the first time he tried it.

This closes that. Given a subject and a paper kind, it works out which units
the real LPU paper draws from, checks what the deck actually holds for each
of those units, generates only what is missing, and then hands off to the
ordinary assembly path.

The generated questions are not a throwaway document. They are cards: they
enter the deck, the paper is assembled from them by the same exact subset-sum
that prices every other paper, and answering them records real reviews that
move the scheduler. A paper you sit here is a paper you have also studied.
"""

from dataclasses import dataclass

from recall.config import Config
from recall.generate.knowledge import (
    MAX_CARDS_PER_CALL,
    generate_for_unit,
    knowledge_sha,
)
from recall.testmode.service import KINDS
from recall.verify.dedupe import embed_texts

#: Roughly what one card is worth once the marks rule has priced it. Cards run
#: 1, 2 or 5 marks; a realistic deck skews short, so this is deliberately near
#: the bottom of that range — overshooting the card count is cheap and being
#: short means the paper cannot be built at all.
_AVG_MARKS_PER_CARD = 1.6

#: Never generate more than this per unit in one paper request, however big the
#: paper. A 100-mark ETE across six units is already ~10 cards a unit.
_MAX_PER_UNIT = MAX_CARDS_PER_CALL


def units_for(kind: str, unit_count: int) -> list[int]:
    """The 0-based unit indices a paper of this kind draws from.

    - ``mte40``: units 1-3. The mid-term covers the first half only; that is a
      university rule, not a heuristic.
    - ``class30``: units 1-2, matching the first class test.
    - ``endterm100`` / ``fullday``: everything.
    """
    if unit_count <= 0:
        return []
    if kind == "mte40":
        return list(range(min(3, unit_count)))
    if kind == "class30":
        return list(range(min(2, unit_count)))
    return list(range(unit_count))


@dataclass(frozen=True)
class CoverageResult:
    generated: int
    rejected: int
    cost_usd: float
    units_touched: list[int]
    already_covered: bool


def cards_needed_per_unit(kind: str, n_units: int) -> int:
    target = KINDS[kind][0]
    if target is None or n_units == 0:      # fullday: whatever exists is the paper
        return 0
    return max(1, round(target / _AVG_MARKS_PER_CARD / n_units))


def _active_per_unit(conn, user_id: int, topic_id: int) -> dict[int, int]:
    """Active cards this topic holds, counted per unit.

    A unit is knowable only for knowledge-mode cards, whose chunk ordinal IS
    the unit index. Cards from an uploaded PDF are tagged by page, and a page
    does not map to a unit — so they are not counted here. They still reach
    the paper through normal assembly; they just cannot prove a unit is
    covered.
    """
    rows = conn.execute(
        "SELECT ch.ordinal AS unit, COUNT(*) AS n"
        " FROM cards c"
        " JOIN chunks ch ON ch.id = c.chunk_id"
        " JOIN sources s ON s.id = ch.source_id"
        " WHERE c.topic_id = ? AND c.state = 'active'"
        "   AND s.user_id = ? AND s.sha256 = ?"
        " GROUP BY ch.ordinal",
        (topic_id, user_id, knowledge_sha(topic_id)),
    ).fetchall()
    return {r["unit"]: r["n"] for r in rows}


def ensure_coverage(conn, cfg: Config, client, *, user_id: int, topic_id: int,
                    topic_code: str, full_name: str, exam_format: str,
                    units: list[str], kind: str,
                    only_units: list[int] | None = None,
                    embed=embed_texts) -> CoverageResult:
    """Generate whatever the paper needs and the deck does not have.

    Only the shortfall is generated: a unit already carrying enough cards
    costs nothing, so sitting the same paper twice does not pay twice.

    `only_units` overrides the paper kind's own plan with an explicit list of
    0-based unit indices — "we did units 2 and 3 in class, examine me on
    those". Given one, the marks target is spread across just those units, so
    asking for one unit gets a paper's worth of that unit rather than a sixth
    of one.
    """
    plan = units_for(kind, len(units)) if only_units is None else list(only_units)
    if not plan:
        return CoverageResult(0, 0, 0.0, [], already_covered=True)

    want = cards_needed_per_unit(kind, len(plan))
    have = _active_per_unit(conn, user_id, topic_id)

    generated = rejected = 0
    cost = 0.0
    touched: list[int] = []
    for unit_index in plan:
        missing = want - have.get(unit_index, 0)
        if missing <= 0:
            continue
        result = generate_for_unit(
            conn, cfg, client, user_id=user_id, topic_id=topic_id,
            topic_code=topic_code, full_name=full_name,
            exam_format=exam_format, unit_index=unit_index,
            unit_name=units[unit_index], n=min(missing, _MAX_PER_UNIT),
            # Active, not pending: see generate_for_unit's `state` docstring.
            # A paper you explicitly asked to sit is a stricter review than
            # the approval queue, and pending cards would leave it empty.
            state="active", embed=embed,
        )
        generated += result.accepted
        rejected += result.rejected
        cost += result.cost_usd
        touched.append(unit_index)

    return CoverageResult(generated, rejected, cost, touched,
                          already_covered=not touched)
