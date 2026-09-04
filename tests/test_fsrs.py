"""Property tests for the FSRS-4.5 model.

DEFAULT_PARAMS will be refitted from real review logs later, so almost nothing
here asserts a magic number produced by a single run. What is pinned instead are
the invariants that have to survive a refit: monotonicity, ordering, clamping,
finiteness, and the two exact identities that come from the *definition* of
stability rather than from any fitted weight.

Two required properties do not hold with the shipped defaults. They are kept as
strict xfails so the assertion stays exactly as specified and flips to a loud
failure the moment a refit makes them true. See the reasons on each.
"""

import ast
import math
import random
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from recall.schedule import fsrs
from recall.schedule.fsrs import (
    DEFAULT_PARAMS,
    MemoryState,
    initial_state,
    interval_days,
    next_state,
    retrievability,
)

GRADES = (1, 2, 3, 4)
SUCCESS_GRADES = (2, 3, 4)

# A spread of plausible cards, from "just failed it" to "known for a decade".
STABILITIES = (0.01, 0.1, 0.4872, 1.0, 3.7145, 13.8206, 45.0, 180.0, 1000.0)
DIFFICULTIES = (1.0, 2.5, 5.0, 7.5, 10.0)
ELAPSED = (0.0, 0.25, 1.0, 3.0, 10.0, 60.0, 365.0, 3650.0)

# Measured boundary: below ~15.08 days the FSRS-4.5 lapse formula can return a
# stability larger than the one it replaces. See test_lapse_always_reduces_stability.
LAPSE_SAFE_STABILITY = 16.0


def _pairs(values):
    return list(zip(values, values[1:]))


# --------------------------------------------------------------------------
# 1. Retrievability is a decaying probability.
# --------------------------------------------------------------------------


def test_retrievability_is_one_at_zero_elapsed():
    for stability in STABILITIES:
        assert retrievability(0.0, stability) == 1.0


def test_retrievability_strictly_decreases_with_elapsed_time():
    for stability in STABILITIES:
        previous = retrievability(0.0, stability)
        for days in (0.001, 0.1, 1.0, 5.0, 30.0, 400.0, 5_000.0, 1e6):
            current = retrievability(days, stability)
            assert current < previous, (stability, days, current, previous)
            previous = current


def test_retrievability_stays_in_the_unit_interval():
    for stability in STABILITIES:
        for days in (0.0, 1e-6, 1.0, 100.0, 1e6, 1e9):
            value = retrievability(days, stability)
            assert 0.0 < value <= 1.0, (stability, days, value)


# --------------------------------------------------------------------------
# 2. Stability is *defined* as the point where retrievability hits 0.9.
# --------------------------------------------------------------------------


def test_retrievability_after_exactly_stability_days_is_ninety_percent():
    for stability in STABILITIES:
        assert retrievability(stability, stability) == pytest.approx(0.9, rel=1e-12)


# --------------------------------------------------------------------------
# 3 & 4. Initial state ordering across grades.
# --------------------------------------------------------------------------


def test_initial_stability_strictly_increases_with_grade():
    stabilities = [initial_state(grade).stability for grade in GRADES]
    assert all(a < b for a, b in _pairs(stabilities)), stabilities


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING: with DEFAULT_PARAMS this property is false. The specified "
        "initial-difficulty form D0(G) = w4 - exp(w5*(G-1)) + 1 evaluates to "
        "-5.54 for 'good' and -33.86 for 'easy', so both clamp to the floor of "
        "1.0 and the two grades become indistinguishable. The property itself "
        "is right and the implementation satisfies it for weights fitted to "
        "this form (see the test below); the shipped weights are FSRS-4.5's, "
        "which were fitted to the linear form w4 - (G-3)*w5. Expect an XPASS "
        "here after the refit, at which point delete this marker."
    ),
)
def test_initial_difficulty_strictly_decreases_with_grade():
    difficulties = [initial_state(grade).difficulty for grade in GRADES]
    assert all(a > b for a, b in _pairs(difficulties)), difficulties


def test_initial_difficulty_never_increases_with_grade():
    difficulties = [initial_state(grade).difficulty for grade in GRADES]
    assert all(a >= b for a, b in _pairs(difficulties)), difficulties


def test_initial_difficulty_strictly_decreases_when_weights_suit_the_form():
    # Identical code path, but with w4/w5 actually fitted to the exponential
    # form. Isolates the failure above to the parameters, not the arithmetic.
    params = list(DEFAULT_PARAMS)
    params[4], params[5] = 7.1949, 0.5345
    difficulties = [initial_state(grade, params).difficulty for grade in GRADES]
    assert all(a > b for a, b in _pairs(difficulties)), difficulties


def test_initial_state_is_always_in_range():
    for grade in GRADES:
        state = initial_state(grade)
        assert state.stability > 0.0
        assert fsrs.MIN_DIFFICULTY <= state.difficulty <= fsrs.MAX_DIFFICULTY


# --------------------------------------------------------------------------
# 5. Difficulty is clamped to [1, 10] no matter what.
# --------------------------------------------------------------------------


def test_difficulty_stays_clamped_through_many_lapses():
    state = initial_state(3)
    for _ in range(200):
        state = next_state(state, 1, 1.0)
        assert fsrs.MIN_DIFFICULTY <= state.difficulty <= fsrs.MAX_DIFFICULTY
    assert state.difficulty == pytest.approx(fsrs.MAX_DIFFICULTY)


def test_difficulty_stays_clamped_through_many_easy_answers():
    state = initial_state(1)
    for _ in range(200):
        state = next_state(state, 4, 30.0)
        assert fsrs.MIN_DIFFICULTY <= state.difficulty <= fsrs.MAX_DIFFICULTY
    assert state.difficulty == pytest.approx(fsrs.MIN_DIFFICULTY)


def test_out_of_range_incoming_difficulty_is_clamped():
    for difficulty in (-1e6, -3.0, 0.0, 10.5, 1e6, float("inf")):
        for grade in GRADES:
            state = next_state(MemoryState(10.0, difficulty), grade, 10.0)
            assert fsrs.MIN_DIFFICULTY <= state.difficulty <= fsrs.MAX_DIFFICULTY


# --------------------------------------------------------------------------
# 6. Stability never dies.
# --------------------------------------------------------------------------


def test_stability_stays_positive_through_random_review_histories():
    rng = random.Random(20_260_904)
    for _ in range(200):
        state = initial_state(rng.choice(GRADES))
        for _ in range(40):
            state = next_state(state, rng.choice(GRADES), rng.uniform(0.0, 400.0))
            assert state.stability > 0.0, state
            assert math.isfinite(state.stability), state


def test_stability_survives_the_worst_realistic_streaks():
    for grade in GRADES:
        state = initial_state(grade)
        for _ in range(100):
            state = next_state(state, grade, 0.0)
            assert state.stability > 0.0
            assert math.isfinite(state.stability)


# --------------------------------------------------------------------------
# 7. A lapse must weaken the memory.
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING: with DEFAULT_PARAMS this property is false for young, badly "
        "overdue cards. The lapse formula rebuilds stability from scratch "
        "rather than scaling the old value, and its exp(w14*(1-R)) term (up to "
        "e**1.587 = 4.89) can push the result above the prior stability "
        "whenever that stability is below ~15.08 days. FSRS-4.5 as specified "
        "has no min(S_new, S_old) guard, so forgetting a one-day card you last "
        "saw a year ago strengthens it — worst case observed: S 0.01 -> 0.033. "
        "Adding the guard would fix it but is not in the frozen spec, so it is "
        "reported rather than patched. The two tests below pin the region where "
        "the property does hold."
    ),
)
def test_lapse_always_reduces_stability():
    for stability in STABILITIES:
        for difficulty in DIFFICULTIES:
            for days in ELAPSED:
                before = MemoryState(stability, difficulty)
                after = next_state(before, 1, days)
                assert after.stability < before.stability, (before, days, after)


def test_lapse_reduces_stability_for_established_cards():
    # True for every difficulty and every elapsed time once stability is above
    # the measured crossover, including absurdly overdue reviews.
    for stability in (LAPSE_SAFE_STABILITY, 30.0, 120.0, 365.0, 3650.0, 36_500.0):
        for difficulty in DIFFICULTIES:
            for days in (*ELAPSED, stability * 100.0, 1e7):
                before = MemoryState(stability, difficulty)
                after = next_state(before, 1, days)
                assert after.stability < before.stability, (before, days, after)


def test_lapse_reduces_stability_when_the_card_was_reviewed_on_schedule():
    # The case the scheduler actually produces: the card is shown at its due
    # date, so retrievability is the target 0.9.
    for stability in (s for s in STABILITIES if s > fsrs.MIN_STABILITY):
        for difficulty in DIFFICULTIES:
            before = MemoryState(stability, difficulty)
            after = next_state(before, 1, interval_days(stability, 0.9))
            assert after.stability < before.stability, (before, after)


# --------------------------------------------------------------------------
# 8. Better answers are never punished.
# --------------------------------------------------------------------------


def test_higher_grade_never_yields_lower_stability():
    for stability in STABILITIES:
        for difficulty in DIFFICULTIES:
            for days in ELAPSED:
                before = MemoryState(stability, difficulty)
                results = [next_state(before, g, days).stability for g in SUCCESS_GRADES]
                assert all(a <= b for a, b in _pairs(results)), (before, days, results)


def test_higher_grade_never_yields_higher_difficulty():
    for stability in STABILITIES:
        for difficulty in DIFFICULTIES:
            before = MemoryState(stability, difficulty)
            results = [next_state(before, g, 10.0).difficulty for g in GRADES]
            assert all(a >= b for a, b in _pairs(results)), (before, results)


# --------------------------------------------------------------------------
# 9 & 10. Intervals.
# --------------------------------------------------------------------------


def test_interval_strictly_increases_with_stability():
    for retention in (0.7, 0.8, 0.9, 0.95, 0.99):
        intervals = [interval_days(s, retention) for s in STABILITIES]
        assert all(a < b for a, b in _pairs(intervals)), (retention, intervals)


def test_interval_shrinks_as_desired_retention_rises():
    for stability in STABILITIES:
        intervals = [
            interval_days(stability, r) for r in (0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0)
        ]
        assert all(a > b for a, b in _pairs(intervals)), (stability, intervals)
    assert interval_days(100.0, 1.0) == 0.0


def test_interval_at_ninety_percent_retention_equals_stability():
    for stability in STABILITIES:
        assert interval_days(stability, 0.9) == pytest.approx(stability, rel=1e-9)


def test_interval_and_retrievability_are_exact_inverses():
    for stability in STABILITIES:
        for retention in (0.6, 0.7, 0.8, 0.9, 0.95, 0.99):
            days = interval_days(stability, retention)
            assert retrievability(days, stability) == pytest.approx(retention, rel=1e-9)


# --------------------------------------------------------------------------
# 11. The spacing effect has to be emergent, not bolted on.
# --------------------------------------------------------------------------


def test_a_longer_gap_earns_a_bigger_stability_gain():
    for stability in (0.5, 1.0, 5.0, 30.0, 200.0, 1000.0):
        for difficulty in DIFFICULTIES:
            for grade in SUCCESS_GRADES:
                before = MemoryState(stability, difficulty)
                gains = [
                    next_state(before, grade, stability * factor).stability - stability
                    for factor in (0.0, 0.25, 0.5, 1.0, 2.0, 8.0, 64.0)
                ]
                assert all(a < b for a, b in _pairs(gains)), (before, grade, gains)


def test_reviewing_immediately_earns_nothing():
    # Retrievability is still 1.0, so the model gives no credit at all.
    for grade in SUCCESS_GRADES:
        before = MemoryState(20.0, 5.0)
        assert next_state(before, grade, 0.0).stability == pytest.approx(before.stability)


# --------------------------------------------------------------------------
# 12. Fuzz.
# --------------------------------------------------------------------------


def test_fuzz_500_random_updates_are_finite_and_in_range():
    rng = random.Random(4545)
    for _ in range(500):
        before = MemoryState(rng.uniform(0.01, 1000.0), rng.uniform(1.0, 10.0))
        grade = rng.choice(GRADES)
        days = rng.uniform(0.0, 3650.0)

        after = next_state(before, grade, days)
        assert math.isfinite(after.stability), (before, grade, days, after)
        assert after.stability > 0.0, (before, grade, days, after)
        assert math.isfinite(after.difficulty), (before, grade, days, after)
        assert fsrs.MIN_DIFFICULTY <= after.difficulty <= fsrs.MAX_DIFFICULTY

        value = retrievability(days, after.stability)
        assert math.isfinite(value) and 0.0 < value <= 1.0

        interval = interval_days(after.stability, rng.uniform(0.5, 0.99))
        assert math.isfinite(interval) and interval > 0.0


def test_fuzz_hostile_inputs_never_raise_or_produce_nonsense():
    rng = random.Random(1234)
    hostile = (-1e9, -1.0, -0.0, 0.0, 1e-12, 1e9)
    for _ in range(500):
        before = MemoryState(rng.choice(hostile), rng.choice((*hostile, 5.0)))
        after = next_state(before, rng.choice(GRADES), rng.choice(hostile))
        assert math.isfinite(after.stability) and after.stability > 0.0, (before, after)
        assert fsrs.MIN_DIFFICULTY <= after.difficulty <= fsrs.MAX_DIFFICULTY


def test_core_properties_survive_perturbed_parameters():
    # The point of property tests: none of the above should depend on the exact
    # weights, so re-run the load-bearing ones on 200 jittered parameter sets.
    rng = random.Random(99)
    for _ in range(200):
        params = tuple(w * rng.uniform(0.75, 1.25) for w in DEFAULT_PARAMS)
        before = MemoryState(rng.uniform(0.5, 500.0), rng.uniform(1.0, 10.0))
        days = rng.uniform(0.0, 1000.0)

        successes = [next_state(before, g, days, params).stability for g in SUCCESS_GRADES]
        assert all(a <= b for a, b in _pairs(successes)), (before, days, successes)

        short = next_state(before, 3, 1.0, params).stability
        long_gap = next_state(before, 3, 900.0, params).stability
        assert long_gap >= short, (before, short, long_gap)

        for grade in GRADES:
            after = next_state(before, grade, days, params)
            assert math.isfinite(after.stability) and after.stability > 0.0
            assert fsrs.MIN_DIFFICULTY <= after.difficulty <= fsrs.MAX_DIFFICULTY


# --------------------------------------------------------------------------
# Guards and contract.
# --------------------------------------------------------------------------


def test_negative_elapsed_days_is_treated_as_zero():
    assert retrievability(-5.0, 10.0) == 1.0
    before = MemoryState(10.0, 5.0)
    assert next_state(before, 3, -5.0) == next_state(before, 3, 0.0)
    assert interval_days(10.0, 0.9) > 0.0


def test_zero_stability_never_divides_by_zero():
    assert retrievability(1.0, 0.0) < 1.0
    assert interval_days(0.0, 0.9) == pytest.approx(fsrs.MIN_STABILITY)
    for grade in GRADES:
        assert next_state(MemoryState(0.0, 5.0), grade, 1.0).stability > 0.0


def test_out_of_range_desired_retention_is_clamped():
    assert interval_days(10.0, 1.5) == 0.0
    for retention in (0.0, -1.0):
        days = interval_days(10.0, retention)
        assert math.isfinite(days) and days > 0.0


def test_invalid_grade_raises_value_error():
    for bad in (0, 5, -1, 3.5, 100):
        with pytest.raises(ValueError):
            initial_state(bad)
        with pytest.raises(ValueError):
            next_state(MemoryState(10.0, 5.0), bad, 1.0)


def test_memory_state_is_frozen():
    state = MemoryState(10.0, 5.0)
    with pytest.raises(FrozenInstanceError):
        state.stability = 1.0


def test_default_params_is_seventeen_floats():
    assert isinstance(DEFAULT_PARAMS, tuple)
    assert len(DEFAULT_PARAMS) == 17
    assert all(isinstance(weight, float) for weight in DEFAULT_PARAMS)


def test_curve_constants_match_the_spec():
    assert fsrs.FACTOR == 19 / 81
    assert fsrs.DECAY == -0.5


def test_module_has_zero_internal_dependencies():
    tree = ast.parse(Path(fsrs.__file__).read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert not node.level, "relative import in a module that must stand alone"
            modules.add(node.module or "")
    assert not [m for m in modules if m == "recall" or m.startswith("recall.")], modules
    assert not [m for m in modules if m.split(".")[0] in {"logging", "sqlite3", "httpx"}]
