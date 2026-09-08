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
from recall.testmode.marks import marks_for_card
from recall.testmode.service import KINDS
from recall.verify.dedupe import embed_texts

#: Roughly what one card is worth once the marks rule has priced it. Cards run
#: 1, 2 or 5 marks; a realistic deck skews short, so this is deliberately near
#: the bottom of that range — overshooting the card count is cheap and being
#: short means the paper cannot be built at all.
_AVG_MARKS_PER_CARD = 1.6

#: One generation call cannot reliably produce more than this many usable
#: cards, so a unit that needs more gets several calls rather than one
#: impossible one.
_MAX_PER_UNIT = MAX_CARDS_PER_CALL

#: How many generation calls one unit may take in a single paper request.
#: Four rounds of 25 is a hundred cards for one unit — far more than any paper
#: needs, and a hard stop on what one press can spend.
_MAX_ROUNDS_PER_UNIT = 4


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
    """How many cards to ask one generation call for. Still a card count,
    because that is what a prompt can be given; the STOPPING condition is
    marks — see marks_needed_per_unit."""
    target = KINDS[kind][0]
    if target is None or n_units == 0:      # fullday: whatever exists is the paper
        return 0
    return max(1, round(target / _AVG_MARKS_PER_CARD / n_units))


def marks_needed_per_unit(kind: str, n_units: int) -> int:
    """The marks one unit has to contribute for the paper to reach its target.

    This is what generation now works toward. Working toward a CARD count
    assumed every card was worth _AVG_MARKS_PER_CARD, and a deck of
    short-answer cards is worth 1 mark each — which is how a 100-mark end term
    scoped to a single unit came back holding 25 marks and calling itself
    short.
    """
    target = KINDS[kind][0]
    if target is None or n_units == 0:
        return 0
    return -(-target // n_units)            # ceil, so the units cover the target


def _active_marks_per_unit(conn, user_id: int, topic_id: int) -> dict[int, int]:
    """The MARKS this topic already holds, per unit.

    Marks rather than cards, because marks are what a paper is measured in and
    a card is worth 1, 2 or 5 of them depending on how long its answer is.
    Counting cards and assuming an average is how a one-unit end term ended up
    a quarter length: twenty-five short-answer cards is twenty-five marks, not
    the sixty-odd the average predicted.

    A unit is knowable only for knowledge-mode cards, whose chunk ordinal IS
    the unit index. Cards from an uploaded PDF are tagged by page, and a page
    does not map to a unit — so they are not counted here. They still reach
    the paper through normal assembly; they just cannot prove a unit is
    covered.
    """
    rows = conn.execute(
        "SELECT ch.ordinal AS unit, c.kind, c.answer"
        " FROM cards c"
        " JOIN chunks ch ON ch.id = c.chunk_id"
        " JOIN sources s ON s.id = ch.source_id"
        " WHERE c.topic_id = ? AND c.state = 'active'"
        "   AND s.user_id = ? AND s.sha256 = ?",
        (topic_id, user_id, knowledge_sha(topic_id)),
    ).fetchall()
    marks: dict[int, int] = {}
    for r in rows:
        marks[r["unit"]] = marks.get(r["unit"], 0) + marks_for_card(
            r["kind"], r["answer"])
    return marks


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

    per_call = cards_needed_per_unit(kind, len(plan))
    want_marks = marks_needed_per_unit(kind, len(plan))
    have_marks = _active_marks_per_unit(conn, user_id, topic_id)

    generated = rejected = 0
    cost = 0.0
    touched: list[int] = []
    for unit_index in plan:
        held = have_marks.get(unit_index, 0)
        # Several calls, not one: a single completion tops out at
        # MAX_CARDS_PER_CALL, which is 25 marks when the answers are short.
        # A paper scoped to one unit needs the whole target from that unit,
        # so it needs more than one call to get there.
        for _round in range(_MAX_ROUNDS_PER_UNIT):
            if held >= want_marks:
                break
            result = generate_for_unit(
                conn, cfg, client, user_id=user_id, topic_id=topic_id,
                topic_code=topic_code, full_name=full_name,
                exam_format=exam_format, unit_index=unit_index,
                unit_name=units[unit_index],
                n=min(per_call, _MAX_PER_UNIT),
                # Active, not pending: see generate_for_unit's `state`
                # docstring. A paper you explicitly asked to sit is a stricter
                # review than the approval queue, and pending cards would
                # leave it empty.
                state="active", embed=embed,
            )
            generated += result.accepted
            rejected += result.rejected
            cost += result.cost_usd
            if unit_index not in touched:
                touched.append(unit_index)
            # A round that produced nothing will produce nothing next time
            # either — the dedup seed guarantees a second identical batch is
            # dropped — so stop rather than pay for the same refusal again.
            if result.accepted == 0:
                break
            held = _active_marks_per_unit(
                conn, user_id, topic_id).get(unit_index, 0)

    return CoverageResult(generated, rejected, cost, touched,
                          already_covered=not touched)
