"""The FSRS-4.5 memory model: when should a card be shown again?

Three ideas, in plain words.

**Stability (S)** is how durable a memory is, measured in days. It is defined as
the number of days it takes for your chance of recalling the card to fall to 90%.
A card with S = 30 will still be recalled with probability 0.9 a month from now.
Reviewing a card successfully makes S bigger; forgetting it makes S smaller.

**Difficulty (D)** is how stubborn a particular card is, on a scale from 1 (easy)
to 10 (nasty). It is a property of the card-and-you, not of the clock. Difficulty
never changes on its own; it drifts up when you press "again" and down when you
press "easy". A high-difficulty card gains less stability from each review.

**Retrievability (R)** is the probability, right now, that you would recall the
card if shown it. It starts at 1.0 the moment you finish a review and decays
towards 0 as days pass. How fast it decays is exactly what stability controls.

The scheduler's job is to show you a card when R has dropped to some chosen
target (the "desired retention", typically 0.9). Reviewing a card when R is
already low is worth more than reviewing it while it is still fresh — that is
the spacing effect, and it falls out of the formulas below rather than being
bolted on.

Grades are 1 = again, 2 = hard, 3 = good, 4 = easy.

One deliberate deviation from published FSRS-4.5: the lapse branch is clamped
with ``min(S_new, S_old)``, so failing a card can never lengthen its interval.
Stock 4.5 has no such guard and does lengthen it for cards below ~15.08 days of
stability reviewed well past their due date. Anyone refitting the weights must
know this, because the likelihood is then being fitted against the clamped
branch rather than the published one.

This module is pure: no I/O, no database, no logging, and no imports from
anywhere else in ``recall``. It is only arithmetic, so it is cheap to call and
easy to test.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "AGAIN",
    "DECAY",
    "DEFAULT_PARAMS",
    "EASY",
    "FACTOR",
    "GOOD",
    "HARD",
    "MAX_DIFFICULTY",
    "MIN_DIFFICULTY",
    "MIN_STABILITY",
    "MemoryState",
    "initial_state",
    "interval_days",
    "next_state",
    "retrievability",
]

# Shape of the forgetting curve. These two are fixed by FSRS-4.5, not fitted:
# together they make retrievability equal exactly 0.9 after `stability` days.
FACTOR: float = 19.0 / 81.0
DECAY: float = -0.5

# Guard rails. Stability is a divisor and the base of fractional powers, so it
# must stay strictly positive; difficulty is a bounded scale by definition.
MIN_STABILITY: float = 0.01
MIN_DIFFICULTY: float = 1.0
MAX_DIFFICULTY: float = 10.0
_MIN_RETENTION: float = 1e-6
_MAX_RETENTION: float = 1.0

# Grades.
AGAIN: int = 1
HARD: int = 2
GOOD: int = 3
EASY: int = 4

# The 17 fitted weights of FSRS-4.5. These are population defaults and will be
# refitted per-user later, so nothing in this module may assume their values.
DEFAULT_PARAMS: tuple[float, ...] = (
    0.4872,
    1.4003,
    3.7145,
    13.8206,
    5.1618,
    1.2298,
    0.8975,
    0.031,
    1.6474,
    0.1367,
    1.0461,
    2.1072,
    0.0793,
    0.3246,
    1.587,
    0.2272,
    2.8755,
)


@dataclass(frozen=True)
class MemoryState:
    """What we remember about one card's memory trace.

    Attributes:
        stability: Days until the chance of recall drops to 0.9. Always > 0.
        difficulty: How stubborn the card is, always within [1.0, 10.0].
    """

    stability: float
    difficulty: float


def _clamp(value: float, low: float, high: float) -> float:
    """Return `value` pinned into the closed range [low, high]."""
    return low if value < low else high if value > high else value


def _clamp_stability(stability: float) -> float:
    """Keep stability strictly positive so it is safe to divide by."""
    return stability if stability > MIN_STABILITY else MIN_STABILITY


def _clamp_difficulty(difficulty: float) -> float:
    """Keep difficulty on its defined 1..10 scale."""
    return _clamp(difficulty, MIN_DIFFICULTY, MAX_DIFFICULTY)


def _checked_grade(grade: int) -> int:
    """Validate a grade, returning it unchanged."""
    if grade not in (AGAIN, HARD, GOOD, EASY):
        raise ValueError(
            f"grade must be 1 (again), 2 (hard), 3 (good) or 4 (easy), got {grade!r}"
        )
    return grade


def _initial_difficulty_raw(grade: int, params: Sequence[float]) -> float:
    """`_initial_difficulty` before clamping, used as the mean-reversion target.

    FSRS-4.5 is linear in the grade: ``D0(G) = w4 - w5 * (G - 3)``. So w4 is the
    difficulty of a "good" first answer and w5 is one grade's worth of
    difficulty. FSRS-5 replaces this with an exponential form fitted to its own
    weights; the two must not be mixed, because the exponential form evaluated
    on 4.5's weights underflows past the clamp floor for grades 3 and 4.
    """
    return params[4] - params[5] * (grade - 3)


def _initial_difficulty(grade: int, params: Sequence[float]) -> float:
    """Difficulty assigned to a brand-new card from its very first grade."""
    return _clamp_difficulty(_initial_difficulty_raw(grade, params))


def retrievability(elapsed_days: float, stability: float) -> float:
    """Probability of recalling a card `elapsed_days` after its last review.

    ``R(t, S) = (1 + FACTOR * t / S) ** DECAY``

    Returns 1.0 at t = 0 and decays monotonically towards 0. By construction
    ``retrievability(S, S) == 0.9`` — that is what stability *means*.

    Negative elapsed times are treated as 0, and stability is floored at
    `MIN_STABILITY` so this never divides by zero.
    """
    days = elapsed_days if elapsed_days > 0.0 else 0.0
    return float((1.0 + FACTOR * days / _clamp_stability(stability)) ** DECAY)


def interval_days(stability: float, desired_retention: float) -> float:
    """Days to wait before recall probability falls to `desired_retention`.

    This is `retrievability` solved for t:
    ``I = (S / FACTOR) * (r ** (1 / DECAY) - 1)``

    So ``interval_days(S, 0.9) == S``. Asking for a *higher* retention means
    reviewing sooner, so the result shrinks towards 0 as `desired_retention`
    approaches 1.0. The retention is clamped into (0, 1] to avoid a division
    by zero, and the result is never negative.
    """
    retention = _clamp(desired_retention, _MIN_RETENTION, _MAX_RETENTION)
    days = (_clamp_stability(stability) / FACTOR) * (retention ** (1.0 / DECAY) - 1.0)
    return days if days > 0.0 else 0.0


def initial_state(
    grade: int, params: Sequence[float] = DEFAULT_PARAMS
) -> MemoryState:
    """Memory state for a card being graded for the very first time.

    Initial stability is read straight off the weights (``S0(G) = w[G-1]``), so
    grading a new card "easy" starts it with a far longer interval than "again".
    Initial difficulty is ``D0(G) = w4 - w5 * (G - 3)``, clamped to [1, 10],
    so a card you found easy on sight starts out less stubborn than one you
    failed.
    """
    checked = _checked_grade(grade)
    return MemoryState(
        stability=_clamp_stability(params[checked - 1]),
        difficulty=_initial_difficulty(checked, params),
    )


def next_state(
    state: MemoryState,
    grade: int,
    elapsed_days: float,
    params: Sequence[float] = DEFAULT_PARAMS,
) -> MemoryState:
    """Memory state after reviewing a card that was last seen `elapsed_days` ago.

    Difficulty moves first: the grade nudges it (``D - w6 * (G - 3)``), then it
    is pulled a little way back towards the difficulty an "easy" first answer
    would have given, which stops it drifting to an extreme and sticking there.

    Stability then branches on whether you remembered:

    * Success (grade >= 2) multiplies stability up. The gain is larger when the
      card is easy, when stability is still low, and — the spacing effect —
      when retrievability had already dropped, i.e. when you waited longer.
    * A lapse (grade 1) recomputes stability from scratch on a much smaller
      scale, so a forgotten card comes back soon.

    Both branches read `difficulty` from the *incoming* state, matching the
    FSRS-4.5 reference order.
    """
    checked = _checked_grade(grade)
    stability = _clamp_stability(state.stability)
    difficulty = _clamp_difficulty(state.difficulty)
    days = elapsed_days if elapsed_days > 0.0 else 0.0
    recall_prob = retrievability(days, stability)

    graded = difficulty - params[6] * (checked - 3)
    target = _initial_difficulty_raw(EASY, params)
    reverted = params[7] * target + (1.0 - params[7]) * graded
    next_difficulty = _clamp_difficulty(reverted)

    if checked == AGAIN:
        next_stability = (
            params[11]
            * difficulty ** -params[12]
            * ((stability + 1.0) ** params[13] - 1.0)
            * math.exp(params[14] * (1.0 - recall_prob))
        )
        # Deliberate deviation from stock FSRS-4.5, and load-bearing. The lapse
        # branch rebuilds stability from scratch instead of scaling the old
        # value, and its exp(w14 * (1 - R)) term (up to e**1.587 = 4.89) can
        # push the result *above* the stability it replaces. Measured against
        # DEFAULT_PARAMS: that happens for every stability below ~15.08 days
        # once the review is far enough overdue, worst case S 0.01 -> 0.033 —
        # a 3.3x *increase* in durability as a reward for forgetting. Since
        # most cards live below 15 days and students do leave cards months
        # overdue, stock 4.5 would hand out longer intervals for failures in
        # exactly the case where the schedule most needs to be trusted. Later
        # FSRS versions apply this same min().
        next_stability = min(next_stability, stability)
    else:
        hard = params[15] if checked == HARD else 1.0
        easy = params[16] if checked == EASY else 1.0
        next_stability = stability * (
            1.0
            + math.exp(params[8])
            * (11.0 - difficulty)
            * stability ** -params[9]
            * (math.exp(params[10] * (1.0 - recall_prob)) - 1.0)
            * hard
            * easy
        )

    return MemoryState(
        stability=_clamp_stability(next_stability),
        difficulty=next_difficulty,
    )
