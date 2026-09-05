"""Paper assembly: choose which cards go on a test and in what order.

Three things decide whether a paper is worth sitting.

**Coverage.** Marks are shared out across topics in proportion to each topic's
active cards, so one bulky subject cannot swallow the paper.

**Honesty.** Inside a topic the weak cards come first — high difficulty, low
stability, overdue — because those are the ones you cannot yet answer. But every
fourth pick is taken from the strong end instead. A paper made only of your worst
cards is punishment, not assessment, and its score means nothing.

**Exactness.** The paper hits its mark target exactly whenever any subset of the
deck can. The stratified fill is greedy — a card that would overshoot the
remaining budget is stepped over, not forced in — and when greedy stalls short a
subset-sum finishes the job, swapping out as few of its questions as it can.
When the deck genuinely cannot reach the target the paper comes back short and
says so, rather than being padded with repeats.

This module is pure: it takes candidates and returns a selection. No database.
"""

from __future__ import annotations

import math
from collections.abc import Callable
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


def _prune(deck: list[CandidateCard], target: int,
           score: Callable[[CandidateCard], tuple[int, float]],
           ) -> list[CandidateCard]:
    """Keep only the cards an exact-sum paper could ever want.

    A subset summing to `target` holds at most `target // marks` cards of any one
    mark value, and swapping a lower-scoring card for a higher-scoring one of the
    same value never makes the paper worse. So the best `target // marks` of each
    value are enough, and the search below stays the same size on a deck of
    twenty thousand cards as on a deck of two hundred.
    """
    by_marks: dict[int, list[CandidateCard]] = {}
    for card in deck:
        by_marks.setdefault(card.marks, []).append(card)
    kept: list[CandidateCard] = []
    for marks, cards in sorted(by_marks.items()):
        cards.sort(key=lambda c: (-score(c)[0], -score(c)[1], c.card_id))
        kept.extend(cards[:target // marks])
    return kept


def _subset(deck: list[CandidateCard], target: int,
            score: Callable[[CandidateCard], tuple[int, float]],
            ) -> list[CandidateCard] | None:
    """The highest-scoring subset of `deck` summing to exactly `target`.

    Marks are small integers and a paper is a few dozen of them, so this settles
    exactness outright instead of adding another layer of guessing. Returns None
    when no subset sums to the target at all — arithmetic, not a bug.
    """
    # best[marks so far] = (score, the cards that got there)
    best: dict[int, tuple[tuple[int, float], tuple[CandidateCard, ...]]] = {
        0: ((0, 0.0), ())}
    for card in _prune(deck, target, score):
        kept_here, weak_here = score(card)
        # Descending, over a snapshot: every sum written this pass is above every
        # sum still to be read, so no card is ever used twice.
        for reached in sorted(best, reverse=True):
            total = reached + card.marks
            if total > target:
                continue
            (kept, weak), chosen = best[reached]
            scored = (kept + kept_here, weak + weak_here)
            if total not in best or scored > best[total][0]:
                best[total] = (scored, chosen + (card,))
    if target not in best:
        return None
    return list(best[target][1])


def _anchors(picked: list[CandidateCard], now: datetime) -> list[CandidateCard]:
    """The one question each topic on the greedy paper keeps no matter what."""
    strongest_claim: dict[str, CandidateCard] = {}
    for card in sorted(picked, key=lambda c: (-weakness(c, now), c.card_id)):
        strongest_claim.setdefault(card.topic_code, card)
    return [strongest_claim[code] for code in sorted(strongest_claim)]


def _exact_paper(picked: list[CandidateCard], pool: list[CandidateCard],
                 target: int, now: datetime) -> list[CandidateCard] | None:
    """The greedy paper, adjusted to land exactly on `target`, or None.

    Greedy fill can stall short, and not only by a mark it could pay off: a deck
    of 1,1,5,5 marks fills to 7 against a target of 10 and then no single swap
    reaches it, though 5+5 sits right there.

    Two things have to survive that adjustment. Each topic the greedy paper
    reached keeps its weakest question, anchored, because buying the last mark by
    dropping a subject off the paper is not a trade worth making. Beyond the
    anchors the score keeps as many of the greedy paper's other questions as it
    can, and prefers weak cards to break ties, so the paper that comes back is the
    one it built with the fewest questions swapped out.

    Only if no anchored paper hits the target at all does the search run again
    unanchored: an exact paper that is thin on one topic still beats a short one.
    """
    on_paper = {c.card_id for c in picked}

    def score(card: CandidateCard) -> tuple[int, float]:
        return (1 if card.card_id in on_paper else 0, weakness(card, now))

    deck = picked + pool
    anchors = _anchors(picked, now)
    anchored_marks = sum(c.marks for c in anchors)
    if anchored_marks <= target:
        held = {c.card_id for c in anchors}
        rest = _subset([c for c in deck if c.card_id not in held],
                       target - anchored_marks, score)
        if rest is not None:
            return anchors + rest
    return _subset(deck, target, score)


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
        exact = _exact_paper(picked, pool, target_marks, now)
        if exact is not None:
            picked, gap = exact, 0
    total = target_marks - gap

    return _paper(_ordered(picked), total, target_marks)


def _paper(cards: tuple[CandidateCard, ...], total: int, target: int) -> Paper:
    note = shortfall_note(total, target, len(cards))
    return Paper(cards, total, target, note is not None, note)


def _ordered(cards: list[CandidateCard]) -> tuple[CandidateCard, ...]:
    """Sections by topic, short questions first inside a section — a real paper."""
    return tuple(sorted(cards, key=lambda c: (c.topic_code, c.marks, c.card_id)))
