"""Fit the FSRS weights to one person's own review history.

``DEFAULT_PARAMS`` is a population average. This module replaces it with weights
fitted to the reviews *this* user actually logged, which is the difference
between a scheduler that is right on average and one that is right about you.

The whole design is driven by one uncomfortable fact: there are three users and
about a month of data, and FSRS-4.5 has seventeen free weights. Seventeen
weights against a few hundred binary outcomes will fit the noise perfectly and
predict nothing. So:

* **Maximum a posteriori, not maximum likelihood.** A Gaussian prior centred on
  ``DEFAULT_PARAMS`` is added to the objective. On thin data the prior wins and
  the fit stays essentially at the defaults; as reviews accumulate the
  likelihood term grows linearly with the review count while the prior term does
  not, so the data eventually overcomes it. Nothing switches on — the same
  objective simply changes shape.
* **Refuse to fit at all below ``min_reviews``.** Returning ``None`` is the
  correct answer to a question the data cannot answer, not a failure.
* **Replay, never peek.** Each card's memory state is rebuilt by walking its
  reviews in order through ``fsrs.next_state``, and each review is predicted
  from the state *before* it. Scoring a review against the state that already
  absorbed its own grade is the classic leak, and it produces a beautiful
  meaningless log-loss.
* **Hold out by time, not at random.** The most recent 20% of reviews are
  validation. A random split would put a card's later reviews in training and
  its earlier ones in validation, and since the later state is computed *from*
  the earlier reviews, the model would be tested on what it was told.

The likelihood runs through ``fsrs.next_state`` itself rather than a private
re-derivation of the formulas. That matters here: this project's lapse branch is
deliberately clamped with ``min(S_new, S_old)``, which published FSRS-4.5 is not,
so weights fitted against the published equations would be fitted against a
model the scheduler does not run.

What is being predicted is binary — did the review succeed (grade >= 2) or not —
and the metric is log-loss, in nats per review. ``FitResult`` carries the
baseline log-loss of ``DEFAULT_PARAMS`` on the same held-out reviews, so
"did fitting actually help" is a question with an answer rather than an
assumption.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import minimize

from recall.schedule import fsrs
from recall.schedule.fsrs import DEFAULT_PARAMS

__all__ = [
    "PARAM_BOUNDS",
    "PRIOR_REL_SD",
    "VAL_FRACTION",
    "FitResult",
    "fit_parameters",
    "load_latest_params",
    "save_fit",
]

# Fraction of reviews, most recent first, held out for validation.
VAL_FRACTION: float = 0.20

# Strength of the Gaussian prior, as a standard deviation relative to each
# weight's own default magnitude. This single number is the overfitting dial and
# the tradeoff is real in both directions: too small (0.05) and the fit is
# frozen at the defaults no matter how much the user reviews, so the feature is
# decoration; too large (2.0) and seventeen weights chase a month of noise and
# the schedule gets worse for everyone with a short history. 0.25 says "a weight
# may move about a quarter of its own size before the data has to start paying
# for it", which measured on synthetic histories leaves ~200 reviews within one
# SD of the defaults while ~1500 reviews move the weights far enough to beat
# them on held-out data.
PRIOR_REL_SD: float = 0.25

# Floor on the prior scale. Two defaults (w7 = 0.031, w12 = 0.0793) are near
# zero, and a sigma proportional to them would pin those weights permanently.
PRIOR_SCALE_FLOOR: float = 0.1

# Box constraints, one (low, high) per weight, matching the clamps the FSRS
# reference optimizer uses. They are not decoration: they keep the model inside
# the regime where its own arithmetic is defined (initial stabilities positive,
# initial difficulty on the 1..10 scale, mean-reversion a genuine interpolation
# in [0, 1]) and they bound every exponent, so no exp() in `fsrs` can overflow
# however far the optimizer wanders.
PARAM_BOUNDS: tuple[tuple[float, float], ...] = (
    (0.001, 100.0),   # w0..w3  initial stability per first grade, in days
    (0.001, 100.0),
    (0.001, 100.0),
    (0.001, 100.0),
    (1.0, 10.0),      # w4  initial difficulty of a "good" first answer
    (0.001, 4.0),     # w5  difficulty per grade step
    (0.001, 4.0),     # w6  difficulty nudge per review
    (0.001, 0.75),    # w7  mean-reversion weight, an interpolation factor
    (0.0, 4.5),       # w8  success: overall stability gain
    (0.0, 0.8),       # w9  success: how much gain shrinks as stability grows
    (0.001, 3.5),     # w10 success: spacing-effect strength
    (0.001, 5.0),     # w11 lapse: post-lapse stability scale
    (0.001, 0.25),    # w12 lapse: difficulty penalty
    (0.001, 0.9),     # w13 lapse: dependence on prior stability
    (0.0, 4.0),       # w14 lapse: spacing-effect strength
    (0.0, 1.0),       # w15 hard penalty
    (1.0, 6.0),       # w16 easy bonus
)

# L-BFGS-B settings. The objective is a Python replay loop and the gradient is
# a finite difference, so every step costs 18 full passes over the history. The
# tolerance is deliberately loose: `_TOLERANCE` stops when a step buys less than
# ~1e-8 nats per review, which is nine orders of magnitude below anything a
# log-loss can mean, and stopping there rather than at the default 1e-9 halves
# the fit time. `_FINITE_DIFF_STEP` is larger than SciPy's default 1e-8 because
# the weights differ in scale by three orders of magnitude and the smallest of
# them lose their signal in rounding at that step.
_MAX_ITERATIONS: int = 200
_TOLERANCE: float = 1e-7
_FINITE_DIFF_STEP: float = 1e-6

# Probabilities are clamped before the log so a confident wrong prediction costs
# a large finite number rather than infinity.
_P_FLOOR: float = 1e-6

# Returned when a candidate parameter set drives stability to infinity. Large,
# finite, and constant, so the optimizer simply backs away from that corner.
_DIVERGED_LOSS: float = 1e6


@dataclass(frozen=True)
class FitResult:
    """One fitting run, and the evidence for whether it was worth doing.

    Attributes:
        params: The fitted weights, in ``fsrs`` order.
        n_reviews: Reviews that entered the likelihood (see `fit_parameters`).
        val_logloss: Mean log-loss of `params` on the held-out reviews, in nats.
        baseline_logloss: The same metric for ``DEFAULT_PARAMS`` on the same
            held-out reviews. Lower than `val_logloss` means the fit made
            predictions worse and should not be adopted.
        converged: Whether the optimizer reported convergence rather than
            running out of iterations.
    """

    params: tuple[float, ...]
    n_reviews: int
    val_logloss: float
    baseline_logloss: float
    converged: bool


@dataclass(frozen=True)
class _Review:
    """One logged review, reduced to what the likelihood needs."""

    card_id: int
    reviewed_at: str
    grade: int


def _prior_sigmas() -> tuple[float, ...]:
    """Per-weight prior standard deviations, scaled to each weight's own size."""
    return tuple(
        PRIOR_REL_SD * max(abs(default), PRIOR_SCALE_FLOOR)
        for default in DEFAULT_PARAMS
    )


def _load_reviews(conn: sqlite3.Connection, user_id: int) -> list[_Review]:
    """Every review by `user_id`, oldest first.

    Ties on the timestamp are broken by insertion order, so the sequence a card
    is replayed in is the sequence it was actually reviewed in.
    """
    rows = conn.execute(
        "SELECT card_id, reviewed_at, grade FROM reviews WHERE user_id = ?"
        " ORDER BY reviewed_at ASC, id ASC",
        (user_id,),
    ).fetchall()
    return [_Review(r["card_id"], r["reviewed_at"], int(r["grade"])) for r in rows]


def _split_by_time(reviews: Sequence[_Review]) -> tuple[list[_Review], list[_Review]]:
    """Split into (train, validation) at a timestamp, most recent held out.

    The cut is on the timestamp rather than the index, so reviews sharing an
    instant cannot land on opposite sides: every validation review is strictly
    later than every training review. That is the property that makes the
    held-out score mean something for a model whose state is cumulative.
    """
    if len(reviews) < 2:
        return list(reviews), []
    held_out = max(1, round(len(reviews) * VAL_FRACTION))
    cutoff = reviews[len(reviews) - held_out].reviewed_at
    train = [r for r in reviews if r.reviewed_at < cutoff]
    val = [r for r in reviews if r.reviewed_at >= cutoff]
    return train, val


def _sequences(
    reviews: Sequence[_Review], cutoff: str
) -> list[tuple[tuple[float, int, bool], ...]]:
    """Group reviews into per-card histories of ``(elapsed_days, grade, is_val)``.

    Elapsed time is recomputed from consecutive timestamps rather than read from
    ``reviews.elapsed_days``: the stored column is what the scheduler believed at
    the time, and a replay that disagrees with the clock is a replay of a history
    that never happened.
    """
    by_card: dict[int, list[tuple[float, int, bool]]] = {}
    last_seen: dict[int, datetime] = {}
    for review in reviews:
        when = datetime.fromisoformat(review.reviewed_at)
        previous = last_seen.get(review.card_id)
        elapsed = 0.0 if previous is None else max(
            0.0, (when - previous).total_seconds() / 86400.0
        )
        last_seen[review.card_id] = when
        by_card.setdefault(review.card_id, []).append(
            (elapsed, review.grade, review.reviewed_at >= cutoff)
        )
    return [tuple(seq) for seq in by_card.values()]


def _replay_losses(
    sequences: Sequence[Sequence[tuple[float, int, bool]]],
    params: Sequence[float],
) -> tuple[float, int, float, int]:
    """Replay every card and total the log-loss.

    Returns ``(train_sum, train_n, val_sum, val_n)`` in nats.

    A card's first review is replayed but never scored: with no prior state
    there is nothing to have predicted from. Every later review is scored
    against the state as it stood *before* that review, and only then is the
    grade folded in.
    """
    train_sum = 0.0
    train_n = 0
    val_sum = 0.0
    val_n = 0
    for sequence in sequences:
        _, first_grade, _ = sequence[0]
        state = fsrs.initial_state(first_grade, params)
        for elapsed, grade, is_val in sequence[1:]:
            predicted = fsrs.retrievability(elapsed, state.stability)
            predicted = min(max(predicted, _P_FLOOR), 1.0 - _P_FLOOR)
            recalled = grade >= fsrs.HARD
            loss = -math.log(predicted if recalled else 1.0 - predicted)
            if is_val:
                val_sum += loss
                val_n += 1
            else:
                train_sum += loss
                train_n += 1
            state = fsrs.next_state(state, grade, elapsed, params)
    return train_sum, train_n, val_sum, val_n


def _objective(
    x: np.ndarray,
    sequences: Sequence[Sequence[tuple[float, int, bool]]],
    sigmas: Sequence[float],
    n_train: int,
) -> float:
    """Negative log posterior on the training reviews, per review.

    ``mean NLL + (prior penalty / n_train)``. Dividing the whole thing by the
    training count is what makes the prior fade: the penalty is a fixed cost
    spread over every review, so at 200 reviews a weight must buy its move with
    real accuracy and at 20,000 it barely has to pay.
    """
    params = tuple(float(v) for v in x)
    train_sum, _, _, _ = _replay_losses(sequences, params)
    if not math.isfinite(train_sum):
        return _DIVERGED_LOSS
    penalty = 0.0
    for value, default, sigma in zip(params, DEFAULT_PARAMS, sigmas):
        z = (value - default) / sigma
        penalty += z * z
    return (train_sum + 0.5 * penalty) / n_train


def fit_parameters(
    conn: sqlite3.Connection, user_id: int, *, min_reviews: int = 200
) -> FitResult | None:
    """Fit the FSRS weights to `user_id`'s review history, or decline to.

    Returns ``None`` when the history cannot support a fit: fewer than
    `min_reviews` scoreable reviews, or a history too short or too bunched in
    time to hold anything out.

    `min_reviews` counts *scoreable* reviews — the ones with a prior state to be
    predicted from, which excludes each card's first sighting. Ten thousand cards
    seen once each say nothing about how memory decays, and this counts them as
    the zero evidence they are.
    """
    reviews = _load_reviews(conn, user_id)
    train, val = _split_by_time(reviews)
    if not train or not val:
        return None

    sequences = _sequences(reviews, cutoff=val[0].reviewed_at)
    base_train_sum, n_train, base_val_sum, n_val = _replay_losses(
        sequences, DEFAULT_PARAMS
    )
    if n_train == 0 or n_val == 0 or n_train + n_val < min_reviews:
        return None

    sigmas = _prior_sigmas()
    args = (sequences, sigmas, n_train)
    result = minimize(
        _objective,
        np.array(DEFAULT_PARAMS, dtype=float),
        args=args,
        method="L-BFGS-B",
        bounds=PARAM_BOUNDS,
        options={
            "maxiter": _MAX_ITERATIONS,
            "ftol": _TOLERANCE,
            "eps": _FINITE_DIFF_STEP,
        },
    )

    fitted = tuple(float(v) for v in result.x)
    # A bad optimizer run must not be able to ship a worse scheduler than the one
    # we already have, so the defaults stay in the race to the last comparison.
    if _objective(np.array(fitted), *args) >= _objective(
        np.array(DEFAULT_PARAMS, dtype=float), *args
    ):
        fitted = DEFAULT_PARAMS

    _, _, val_sum, _ = _replay_losses(sequences, fitted)
    return FitResult(
        params=fitted,
        n_reviews=n_train + n_val,
        val_logloss=val_sum / n_val,
        baseline_logloss=base_val_sum / n_val,
        converged=bool(result.success),
    )


def save_fit(conn: sqlite3.Connection, result: FitResult) -> int:
    """Record a fitting run in ``fit_runs`` and return its row id.

    Every run is recorded, including one that lost to the defaults, because the
    history of what the fitter has been doing is the only way to notice it going
    wrong. Deciding whether a run is good enough to schedule with is the
    caller's: compare `FitResult.val_logloss` against
    `FitResult.baseline_logloss` before saving.
    """
    cursor = conn.execute(
        "INSERT INTO fit_runs (ran_at, n_reviews, params_json, val_logloss)"
        " VALUES (?,?,?,?)",
        (
            datetime.now(timezone.utc).isoformat(),
            result.n_reviews,
            json.dumps(list(result.params)),
            result.val_logloss,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def load_latest_params(conn: sqlite3.Connection) -> tuple[float, ...]:
    """Weights from the most recent fit, or ``DEFAULT_PARAMS`` if there is none.

    Anything unreadable — no runs yet, malformed JSON, the wrong number of
    weights, a non-finite value — falls back to the defaults. A scheduler that
    refuses to start because a fit row is corrupt is worse than one that
    schedules like everyone else.
    """
    row = conn.execute(
        "SELECT params_json FROM fit_runs ORDER BY ran_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return DEFAULT_PARAMS
    try:
        values = json.loads(row["params_json"])
        params = tuple(float(v) for v in values)
    except (TypeError, ValueError):
        return DEFAULT_PARAMS
    if len(params) != len(DEFAULT_PARAMS):
        return DEFAULT_PARAMS
    if not all(math.isfinite(v) for v in params):
        return DEFAULT_PARAMS
    return params
