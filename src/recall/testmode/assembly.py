"""Paper assembly: choose which cards go on a test and in what order.

Three things decide whether a paper is worth sitting.

**Coverage.** Marks are shared out across topics in proportion to each topic's
active cards, so one bulky subject cannot swallow the paper.

**Honesty.** Inside a topic the weak cards come first — high difficulty, low
stability, overdue — because those are the ones you cannot yet answer. But every
fourth pick is taken from the strong end instead. A paper made only of your worst
cards is punishment, not assessment, and its score means nothing.

**Exactness.** The fill is greedy and hits the mark target exactly whenever the
deck allows it: a card that would overshoot the remaining budget is stepped over,
not forced in. When the deck genuinely cannot reach the target the paper comes
back short and says so, rather than being padded with repeats.

This module is pure: it takes candidates and returns a selection. No database.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

# Weakness weights. Difficulty dominates because it is the card's own stubborn-
# ness; stability and overdueness say more about the clock than about the card.
_W_DIFFICULTY = 0.5
_W_STABILITY = 0.3
_W_OVERDUE = 0.2

# A never-reviewed card carries no evidence either way, so it sits in the middle
# of the ranking instead of being treated as mastered or as a disaster.
_NEW_CARD_WEAKNESS = 0.5

# Days overdue past which a card is simply "very overdue"; more does not mean more.
_OVERDUE_SATURATION_DAYS = 7.0

# Stability in days at which the stability term bottoms out (10 ** 2 - 1).
_STABILITY_SATURATION_LOG = 2.0

# One in every four picks comes from the strong end of the ranking.
_STRONG_EVERY = 4


@dataclass(frozen=True)
class CandidateCard:
    card_id: int
    topic_code: str
    marks: int
    stability: float | None = None
    difficulty: float | None = None
    due_at: str | None = None


@dataclass(frozen=True)
class Paper:
    cards: tuple[CandidateCard, ...]
    total_marks: int
    target_marks: int
    short: bool
    note: str | None


def weakness(card: CandidateCard, now: datetime) -> float:
    """0 (solid) .. 1 (about to be forgotten). Higher means more worth asking."""
    if card.stability is None or card.difficulty is None:
        return _NEW_CARD_WEAKNESS

    difficulty = (min(10.0, max(1.0, card.difficulty)) - 1.0) / 9.0
    # Log scale: 1 day versus 10 days of stability is a real difference, 100 days
    # versus 1000 is not.
    stability = 1.0 - min(
        1.0,
        math.log10(1.0 + max(0.0, card.stability)) / _STABILITY_SATURATION_LOG,
    )
    overdue = 0.0
    if card.due_at is not None:
        days = (now - datetime.fromisoformat(card.due_at)).total_seconds() / 86400.0
        overdue = min(1.0, max(0.0, days) / _OVERDUE_SATURATION_DAYS)
    return _W_DIFFICULTY * difficulty + _W_STABILITY * stability + _W_OVERDUE * overdue


def _pick_order(cards: list[CandidateCard], now: datetime) -> list[CandidateCard]:
    """Weakest first, but every _STRONG_EVERY-th pick from the strong end."""
    ranked = sorted(cards, key=lambda c: (-weakness(c, now), c.card_id))
    order: list[CandidateCard] = []
    weak, strong = 0, len(ranked) - 1
    while weak <= strong:
        if len(order) % _STRONG_EVERY == _STRONG_EVERY - 1:
            order.append(ranked[strong])
            strong -= 1
        else:
            order.append(ranked[weak])
            weak += 1
    return order


def _topic_quotas(counts: dict[str, int], target: int) -> dict[str, int]:
    """Split target marks across topics by active-card share (largest remainder)."""
    total = sum(counts.values())
    exact = {code: target * n / total for code, n in counts.items()}
    quotas = {code: int(v) for code, v in exact.items()}
    spare = target - sum(quotas.values())
    by_remainder = sorted(counts,
                          key=lambda code: (-(exact[code] - quotas[code]), code))
    for code in by_remainder[:spare]:
        quotas[code] += 1
    return quotas


def _fill(order: list[CandidateCard], budget: int,
          used: set[int]) -> tuple[list[CandidateCard], int]:
    """Take cards in order while they fit. Stepping over an oversized card is what
    makes the total land exactly on the budget instead of near it."""
    picked: list[CandidateCard] = []
    for card in order:
        if budget == 0:
            break
        if card.card_id in used or card.marks > budget:
            continue
        picked.append(card)
        used.add(card.card_id)
        budget -= card.marks
    return picked, budget


def _top_up(orders: dict[str, list[CandidateCard]], used: set[int],
            gap: int) -> tuple[list[CandidateCard], int]:
    """Spend leftover marks round-robin across topics, so topping up a paper does
    not quietly turn it into a single-subject one."""
    picked: list[CandidateCard] = []
    cursors = {code: 0 for code in orders}
    moved = True
    while gap > 0 and moved:
        moved = False
        for code in sorted(orders):
            if gap == 0:
                break
            cards, i = orders[code], cursors[code]
            while i < len(cards):
                card = cards[i]
                i += 1
                # A skipped card can never fit later: the gap only shrinks.
                if card.card_id in used or card.marks > gap:
                    continue
                picked.append(card)
                used.add(card.card_id)
                gap -= card.marks
                moved = True
                break
            cursors[code] = i
    return picked, gap


def _exact_fill(pool: list[CandidateCard], need: int,
                now: datetime) -> list[CandidateCard] | None:
    """The weakest subset of `pool` summing to exactly `need`, or None.

    Marks are small integers and `need` is at most a paper's worth of them, so a
    subset-sum pass over the leftovers is cheap and settles exactness where the
    greedy fill cannot see it.
    """
    # best[sum] = (total weakness, indices into pool)
    best: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, ())}
    for idx, card in enumerate(pool):
        value = weakness(card, now)
        # Descending, over a snapshot, so each card is used at most once.
        for reached in sorted(best, reverse=True):
            total = reached + card.marks
            if total > need:
                continue
            scored = best[reached][0] + value
            if total not in best or scored > best[total][0]:
                best[total] = (scored, best[reached][1] + (idx,))
    if need not in best:
        return None
    return [pool[i] for i in best[need][1]]


def _repair(picked: list[CandidateCard], pool: list[CandidateCard], gap: int,
            now: datetime) -> tuple[list[CandidateCard], int]:
    """Close a small gap by dropping one question and refilling the hole exactly.

    Greedy fill can stall a few marks short on a deck with no 1-mark cards: a gap
    of 1 cannot be paid for out of 2- and 5-mark leftovers. Dropping the question
    we least needed to ask opens a hole those leftovers often fit exactly, which
    is the difference between a 30-mark paper and a 29-mark one. One drop is
    enough for the marks this app issues; if it is not, the paper is short and
    says so rather than quietly missing the target.
    """
    for drop in sorted(picked, key=lambda c: (weakness(c, now), c.card_id)):
        chosen = _exact_fill(pool, gap + drop.marks, now)
        if chosen is not None:
            kept = [c for c in picked if c.card_id != drop.card_id]
            return kept + chosen, 0
    return picked, gap


def shortfall_note(total: int, target: int, count: int) -> str | None:
    """Plain sentence for a paper that could not reach its target, else None."""
    if count == 0:
        return "no active cards to test"
    if total < target:
        return (f"deck reaches only {total} of {target} marks;"
                " the paper is short rather than padded with repeats")
    return None


def assemble(candidates: list[CandidateCard], target_marks: int | None, *,
             now: datetime) -> Paper:
    """Build a paper. target_marks None means every card (a 'fullday' paper)."""
    if target_marks is None:
        cards = _ordered(list(candidates))
        total = sum(c.marks for c in cards)
        return _paper(cards, total, total)

    by_topic: dict[str, list[CandidateCard]] = {}
    for card in candidates:
        by_topic.setdefault(card.topic_code, []).append(card)
    if not by_topic:
        return _paper((), 0, target_marks)

    orders = {code: _pick_order(cards, now) for code, cards in by_topic.items()}
    quotas = _topic_quotas({code: len(c) for code, c in by_topic.items()},
                           target_marks)

    used: set[int] = set()
    picked: list[CandidateCard] = []
    spent = 0
    for code in sorted(orders):
        taken, left = _fill(orders[code], quotas[code], used)
        picked.extend(taken)
        spent += quotas[code] - left

    # Topics that ran out of cards leave marks unspent; other topics can pay for
    # them, which is what keeps the total exact.
    extra, gap = _top_up(orders, used, target_marks - spent)
    picked.extend(extra)
    if gap > 0:
        pool = [c for c in candidates if c.card_id not in used]
        picked, gap = _repair(picked, pool, gap, now)
    total = target_marks - gap

    return _paper(_ordered(picked), total, target_marks)


def _paper(cards: tuple[CandidateCard, ...], total: int, target: int) -> Paper:
    note = shortfall_note(total, target, len(cards))
    return Paper(cards, total, target, note is not None, note)


def _ordered(cards: list[CandidateCard]) -> tuple[CandidateCard, ...]:
    """Sections by topic, short questions first inside a section — a real paper."""
    return tuple(sorted(cards, key=lambda c: (c.topic_code, c.marks, c.card_id)))
