"""Tests for the per-user FSRS refit.

The hard part of testing a fitter is that "it ran and produced numbers" says
nothing. So the two load-bearing tests here generate review histories from a
*known* parameter set and then ask whether the fit found its way back:

* with a rich history, the fitted weights must beat DEFAULT_PARAMS on held-out
  reviews and land closer to the truth than the defaults did;
* with a thin one, they must stay near the defaults — the prior is supposed to
  win when the data cannot support seventeen free numbers.

Everything else guards a specific way this can be silently wrong: scoring a
review against the state that already absorbed it, splitting time so that the
future leaks into training, or replaying a card's history out of order.
"""

import json
import math
import random
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from recall.db import connect, init_db
from recall.schedule import fsrs
from recall.schedule.fit import (
    DEFAULT_PARAMS,
    PARAM_BOUNDS,
    VAL_FRACTION,
    FitResult,
    _load_reviews,
    _objective,
    _prior_sigmas,
    _replay_losses,
    _sequences,
    _split_by_time,
    fit_parameters,
    load_latest_params,
    save_fit,
)

START = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)

# A person whose memory is markedly weaker than the population average: cards
# start out less stable and gain less from each success. Every weight stays
# inside PARAM_BOUNDS, so the truth is reachable rather than a trick target.
TRUE_PARAMS: tuple[float, ...] = (
    0.15, 0.5, 1.2, 4.0,          # w0..w3  initial stabilities
    *DEFAULT_PARAMS[4:8],
    0.6,                          # w8   smaller stability gain per success
    DEFAULT_PARAMS[9],
    0.5,                          # w10  weaker spacing effect
    *DEFAULT_PARAMS[11:],
)


# --------------------------------------------------------------------------
# Fixtures and helpers
# --------------------------------------------------------------------------


def make_db(tmp_path, name="fit.db"):
    """An initialised database with two users and one chunk to hang cards off."""
    conn = connect(str(tmp_path / name))
    init_db(conn)
    conn.execute("INSERT INTO users (id,name) VALUES (1,'yash')")
    conn.execute("INSERT INTO users (id,name) VALUES (2,'someone-else')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (1,1,'CSE111','P')")
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'lec1.pdf','pdf','abc','2026-06-01')")
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref) "
                 "VALUES (1,1,0,'text','p1')")
    conn.commit()
    return conn


def insert_reviews(conn, rows, user_id=1, elapsed_days=None):
    """Insert `(card_id, datetime, grade)` rows, creating cards as needed.

    `elapsed_days` overrides the stored column, which the fitter is supposed to
    ignore in favour of the timestamps.
    """
    existing = {r["id"] for r in conn.execute("SELECT id FROM cards").fetchall()}
    for card_id, when, grade in rows:
        if card_id not in existing:
            conn.execute(
                "INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,arm,"
                "state,created_at) VALUES (?,1,1,'qa','q','a','learned','active',"
                "'2026-06-01')", (card_id,))
            existing.add(card_id)
        conn.execute(
            "INSERT INTO reviews (card_id,user_id,reviewed_at,grade,elapsed_days,"
            "scheduler_version) VALUES (?,?,?,?,?,'test')",
            (card_id, user_id, when.isoformat(), grade,
             0.0 if elapsed_days is None else elapsed_days),
        )
    conn.commit()


def simulate(params, n_cards, max_reps, seed):
    """Review history of someone whose memory actually obeys `params`.

    Each card is re-shown at a random multiple (0.4x .. 2.6x) of its true
    interval rather than exactly on time. That jitter is the point: reviewing
    every card at exactly the scheduled moment pins retrievability near 0.9 for
    every review, and at a single point on the forgetting curve almost any
    parameter set explains the data equally well. Spreading the reviews across
    the curve is what makes the weights identifiable at all — and it is also
    what real use looks like, since nobody clears their queue on time.
    """
    rng = random.Random(seed)
    rows = []
    for card_id in range(1, n_cards + 1):
        when = START + timedelta(days=rng.uniform(0, 20), hours=rng.uniform(0, 10))
        grade = rng.choices((1, 2, 3, 4), weights=(0.1, 0.2, 0.6, 0.1))[0]
        state = fsrs.initial_state(grade, params)
        rows.append((card_id, when, grade))
        for _ in range(rng.randint(max_reps // 2, max_reps)):
            gap = max(0.02, fsrs.interval_days(state.stability, 0.9)
                      * rng.uniform(0.4, 2.6))
            when = when + timedelta(days=gap)
            recalled = rng.random() < fsrs.retrievability(gap, state.stability)
            grade = (rng.choices((2, 3, 4), weights=(0.2, 0.7, 0.1))[0]
                     if recalled else 1)
            rows.append((card_id, when, grade))
            state = fsrs.next_state(state, grade, gap, params)
    rows.sort(key=lambda row: row[1])
    return rows


def prior_distance(a, b):
    """Distance between two parameter sets, measured in prior standard deviations."""
    return math.sqrt(sum(((x - y) / s) ** 2
                         for x, y, s in zip(a, b, _prior_sigmas())))


@pytest.fixture(scope="module")
def rich_fit(tmp_path_factory):
    """One fit on a substantial history. Module-scoped: it takes a few seconds."""
    conn = make_db(tmp_path_factory.mktemp("rich"))
    rows = simulate(TRUE_PARAMS, n_cards=90, max_reps=13, seed=7)
    insert_reviews(conn, rows)
    return fit_parameters(conn, 1), rows


# --------------------------------------------------------------------------
# 1. Refusing to fit is a valid answer
# --------------------------------------------------------------------------


def test_returns_none_below_the_review_threshold(tmp_path):
    conn = make_db(tmp_path)
    insert_reviews(conn, simulate(DEFAULT_PARAMS, n_cards=10, max_reps=8, seed=1))
    assert fit_parameters(conn, 1) is None


def test_returns_none_with_no_reviews_at_all(tmp_path):
    conn = make_db(tmp_path)
    assert fit_parameters(conn, 1, min_reviews=1) is None


def test_returns_none_with_a_single_review(tmp_path):
    conn = make_db(tmp_path)
    insert_reviews(conn, [(1, START, 3)])
    assert fit_parameters(conn, 1, min_reviews=1) is None


def test_cards_seen_once_each_are_not_evidence(tmp_path):
    """300 reviews, none of them predictable: a first sighting has no prior state."""
    conn = make_db(tmp_path)
    rows = [(card, START + timedelta(hours=card), 3) for card in range(1, 301)]
    insert_reviews(conn, rows)
    assert fit_parameters(conn, 1, min_reviews=100) is None


def test_min_reviews_counts_scoreable_reviews_not_rows(tmp_path):
    conn = make_db(tmp_path)
    rows = [(1, START + timedelta(days=d), 3) for d in range(50)]
    insert_reviews(conn, rows)
    assert fit_parameters(conn, 1, min_reviews=50) is None  # 50 rows, 49 scoreable
    assert fit_parameters(conn, 1, min_reviews=49) is not None


def test_one_card_reviewed_fifty_times_does_not_crash(tmp_path):
    conn = make_db(tmp_path)
    grades = [3, 3, 4, 2, 1, 3, 3, 2, 3, 1]
    rows = [(1, START + timedelta(days=2.5 * d), grades[d % len(grades)])
            for d in range(50)]
    insert_reviews(conn, rows)

    result = fit_parameters(conn, 1, min_reviews=10)

    assert isinstance(result, FitResult)
    assert result.n_reviews == 49
    assert math.isfinite(result.val_logloss)
    assert math.isfinite(result.baseline_logloss)
    for value, (low, high) in zip(result.params, PARAM_BOUNDS):
        assert low <= value <= high


def test_reviews_by_another_user_do_not_count(tmp_path):
    conn = make_db(tmp_path)
    insert_reviews(conn, simulate(TRUE_PARAMS, 40, 10, seed=2), user_id=2)
    insert_reviews(conn, [(999, START + timedelta(days=d), 3) for d in range(6)],
                   user_id=1)
    assert fit_parameters(conn, 1, min_reviews=100) is None
    assert fit_parameters(conn, 2, min_reviews=100) is not None


# --------------------------------------------------------------------------
# 2. The fit actually recovers the parameters that generated the data
# --------------------------------------------------------------------------


def test_fit_beats_defaults_on_held_out_reviews(rich_fit):
    result, _ = rich_fit
    assert result is not None
    assert result.n_reviews > 800
    # The whole point of carrying baseline_logloss: the improvement is measured,
    # on reviews neither parameter set was fitted to, not assumed.
    assert result.val_logloss < result.baseline_logloss - 0.01


def test_fit_lands_closer_to_the_true_parameters_than_the_defaults(rich_fit):
    result, _ = rich_fit
    to_truth = prior_distance(result.params, TRUE_PARAMS)
    defaults_to_truth = prior_distance(DEFAULT_PARAMS, TRUE_PARAMS)
    assert to_truth < 0.85 * defaults_to_truth


def test_fit_converges_and_stays_inside_bounds(rich_fit):
    result, _ = rich_fit
    assert result.converged
    for value, (low, high) in zip(result.params, PARAM_BOUNDS):
        assert low <= value <= high
    assert all(math.isfinite(value) for value in result.params)
    assert len(result.params) == len(DEFAULT_PARAMS)


def test_default_parameters_are_inside_the_bounds():
    """A future refit of DEFAULT_PARAMS must not start outside its own box."""
    for value, (low, high) in zip(DEFAULT_PARAMS, PARAM_BOUNDS):
        assert low <= value <= high
    assert len(PARAM_BOUNDS) == len(DEFAULT_PARAMS)


# --------------------------------------------------------------------------
# 3. The prior wins when the data is thin
# --------------------------------------------------------------------------


def test_prior_keeps_a_thin_fit_near_the_defaults(tmp_path):
    """~170 reviews from very different weights must not drag the fit to them."""
    conn = make_db(tmp_path)
    insert_reviews(conn, simulate(TRUE_PARAMS, n_cards=22, max_reps=10, seed=3))

    result = fit_parameters(conn, 1, min_reviews=120)

    assert result is not None
    assert result.n_reviews < 200
    sigmas = _prior_sigmas()
    moves = [abs(fitted - default) / sigma
             for fitted, default, sigma in zip(result.params, DEFAULT_PARAMS, sigmas)]
    assert max(moves) < 2.0
    # Still anchored: closer to where it started than to the weights that
    # generated the data, which the rich fit above is closer to.
    assert (prior_distance(result.params, DEFAULT_PARAMS)
            < 0.6 * prior_distance(result.params, TRUE_PARAMS))


def test_more_data_moves_the_fit_further_from_the_defaults(rich_fit, tmp_path):
    """The prior is a spring, not a cage: evidence stretches it."""
    conn = make_db(tmp_path)
    insert_reviews(conn, simulate(TRUE_PARAMS, n_cards=22, max_reps=10, seed=3))
    thin = fit_parameters(conn, 1, min_reviews=120)
    rich, _ = rich_fit

    assert (prior_distance(rich.params, DEFAULT_PARAMS)
            > prior_distance(thin.params, DEFAULT_PARAMS))


# --------------------------------------------------------------------------
# 4. The time split, and the leak it exists to prevent
# --------------------------------------------------------------------------


def test_split_holds_out_the_most_recent_fifth(tmp_path):
    conn = make_db(tmp_path)
    rows = simulate(TRUE_PARAMS, n_cards=30, max_reps=8, seed=4)
    insert_reviews(conn, rows)

    train, val = _split_by_time(_load_reviews(conn, 1))

    assert len(train) + len(val) == len(rows)
    assert abs(len(val) / len(rows) - VAL_FRACTION) < 0.02


def test_no_validation_review_predates_a_training_review(tmp_path):
    conn = make_db(tmp_path)
    insert_reviews(conn, simulate(TRUE_PARAMS, n_cards=30, max_reps=8, seed=4))

    train, val = _split_by_time(_load_reviews(conn, 1))

    latest_trained = max(r.reviewed_at for r in train)
    earliest_held_out = min(r.reviewed_at for r in val)
    assert latest_trained < earliest_held_out
    for held_out in val:
        assert all(t.reviewed_at < held_out.reviewed_at for t in train)


def test_reviews_sharing_an_instant_land_on_the_same_side(tmp_path):
    """An index split would cut a tie down the middle; a timestamp split cannot."""
    conn = make_db(tmp_path)
    shared = START + timedelta(days=40)
    rows = [(1, START + timedelta(days=d), 3) for d in range(40)]
    rows += [(card, shared, 3) for card in range(2, 22)]
    insert_reviews(conn, rows)

    train, val = _split_by_time(_load_reviews(conn, 1))

    assert all(r.reviewed_at != shared.isoformat() for r in train)
    assert sum(1 for r in val if r.reviewed_at == shared.isoformat()) == 20


def test_training_objective_ignores_held_out_outcomes(tmp_path):
    """Flip every validation grade; the training objective must not move."""
    conn = make_db(tmp_path)
    insert_reviews(conn, simulate(TRUE_PARAMS, n_cards=20, max_reps=8, seed=5))
    reviews = _load_reviews(conn, 1)
    _, val = _split_by_time(reviews)
    sequences = _sequences(reviews, cutoff=val[0].reviewed_at)
    _, n_train, _, n_val = _replay_losses(sequences, DEFAULT_PARAMS)

    # Every held-out success becomes a lapse. Held-out reviews still shape the
    # state of later held-out ones, so the validation loss must move; the
    # training loss must not, because none of it is scored.
    corrupted = [
        tuple((elapsed, 1 if is_val else grade, is_val)
              for elapsed, grade, is_val in sequence)
        for sequence in sequences
    ]
    clean_train, _, clean_val, _ = _replay_losses(sequences, DEFAULT_PARAMS)
    dirty_train, _, dirty_val, _ = _replay_losses(corrupted, DEFAULT_PARAMS)

    assert n_val > 0
    assert dirty_train == pytest.approx(clean_train)
    assert dirty_val != pytest.approx(clean_val)
    assert _objective(np.array(DEFAULT_PARAMS), corrupted, _prior_sigmas(),
                      n_train) == pytest.approx(
        _objective(np.array(DEFAULT_PARAMS), sequences, _prior_sigmas(), n_train))


def test_baseline_logloss_is_the_defaults_on_the_same_holdout(tmp_path):
    conn = make_db(tmp_path)
    insert_reviews(conn, simulate(TRUE_PARAMS, n_cards=25, max_reps=9, seed=6))
    result = fit_parameters(conn, 1, min_reviews=100)

    reviews = _load_reviews(conn, 1)
    _, val = _split_by_time(reviews)
    sequences = _sequences(reviews, cutoff=val[0].reviewed_at)
    _, _, val_sum, val_n = _replay_losses(sequences, DEFAULT_PARAMS)

    assert result.baseline_logloss == pytest.approx(val_sum / val_n)
    assert result.baseline_logloss > 0.0


# --------------------------------------------------------------------------
# 5. Replay: order matters, and each review is scored before it is absorbed
# --------------------------------------------------------------------------


def hand_computed_loss(sequence, params):
    """The same likelihood, written out longhand from `fsrs` alone."""
    _, first_grade, _ = sequence[0]
    state = fsrs.initial_state(first_grade, params)
    total = 0.0
    for elapsed, grade, _ in sequence[1:]:
        predicted = fsrs.retrievability(elapsed, state.stability)
        total -= math.log(predicted if grade >= 2 else 1.0 - predicted)
        state = fsrs.next_state(state, grade, elapsed, params)
    return total


def test_replay_scores_each_review_from_the_state_before_it():
    sequence = ((0.0, 3, False), (4.0, 3, False), (9.0, 1, False),
                (0.5, 2, False), (12.0, 4, False))

    train_sum, train_n, _, _ = _replay_losses([sequence], DEFAULT_PARAMS)

    assert train_n == len(sequence) - 1
    assert train_sum == pytest.approx(hand_computed_loss(sequence, DEFAULT_PARAMS))


def test_a_cards_first_review_is_replayed_but_never_scored():
    single = ((0.0, 3, False),)
    train_sum, train_n, val_sum, val_n = _replay_losses([single], DEFAULT_PARAMS)
    assert (train_sum, train_n, val_sum, val_n) == (0.0, 0, 0.0, 0)


def test_replay_is_order_dependent():
    """Shuffling a card's own history has to change the likelihood.

    If it does not, the replay is not really replaying: a bag-of-reviews
    likelihood would score a card the same however its history unfolded, and
    the spacing effect the whole model rests on would be invisible.
    """
    rng = random.Random(17)
    events = [(rng.choice((0.5, 2.0, 7.0, 30.0, 90.0)),
               rng.choice((1, 2, 3, 4))) for _ in range(20)]
    ordered = tuple((elapsed, grade, False) for elapsed, grade in events)

    shuffled_events = events[:]
    rng.shuffle(shuffled_events)
    assert shuffled_events != events
    shuffled = tuple((elapsed, grade, False) for elapsed, grade in shuffled_events)

    original, _, _, _ = _replay_losses([ordered], DEFAULT_PARAMS)
    reordered, _, _, _ = _replay_losses([shuffled], DEFAULT_PARAMS)

    assert abs(original - reordered) > 1e-6


def test_replay_goes_through_the_clamped_lapse_branch():
    """Failing a card must never raise its stability inside the likelihood.

    `fsrs.next_state` clamps its lapse branch with min(S_new, S_old), which
    published FSRS-4.5 does not. If the fitter ever grew its own copy of the
    equations, this is the test that would catch the copy drifting.
    """
    long_overdue = ((0.0, 3, False), (400.0, 1, False), (1.0, 3, False))
    assert _replay_losses([long_overdue], DEFAULT_PARAMS)[0] == pytest.approx(
        hand_computed_loss(long_overdue, DEFAULT_PARAMS))

    state = fsrs.MemoryState(stability=5.0, difficulty=5.0)
    assert fsrs.next_state(state, 1, 400.0).stability <= state.stability


def test_elapsed_days_comes_from_the_clock_not_the_stored_column(tmp_path):
    conn = make_db(tmp_path)
    rows = [(1, START, 3), (1, START + timedelta(days=6), 3)]
    insert_reviews(conn, rows, elapsed_days=999.0)

    sequences = _sequences(_load_reviews(conn, 1), cutoff="9999")

    assert sequences[0][1][0] == pytest.approx(6.0)


def test_sequences_keep_cards_separate(tmp_path):
    conn = make_db(tmp_path)
    rows = [(1, START, 3), (2, START + timedelta(days=1), 2),
            (1, START + timedelta(days=3), 3), (2, START + timedelta(days=5), 1)]
    insert_reviews(conn, rows)

    sequences = _sequences(_load_reviews(conn, 1), cutoff="9999")

    assert len(sequences) == 2
    assert sorted(len(s) for s in sequences) == [2, 2]
    # Elapsed is measured from the card's own previous review, not the deck's.
    by_first_grade = {seq[0][1]: seq for seq in sequences}
    assert by_first_grade[3][1][0] == pytest.approx(3.0)
    assert by_first_grade[2][1][0] == pytest.approx(4.0)


# --------------------------------------------------------------------------
# 6. Persistence
# --------------------------------------------------------------------------


def test_load_latest_params_falls_back_to_defaults_when_nothing_is_fitted(tmp_path):
    conn = make_db(tmp_path)
    assert load_latest_params(conn) == DEFAULT_PARAMS


def test_save_fit_round_trips_through_the_database(tmp_path):
    conn = make_db(tmp_path)
    params = tuple(value * 1.1 for value in DEFAULT_PARAMS)
    result = FitResult(params, 1234, 0.31, 0.37, True)

    row_id = save_fit(conn, result)

    assert row_id > 0
    row = conn.execute("SELECT * FROM fit_runs WHERE id = ?", (row_id,)).fetchone()
    assert row["n_reviews"] == 1234
    assert row["val_logloss"] == pytest.approx(0.31)
    assert json.loads(row["params_json"]) == pytest.approx(list(params))
    datetime.fromisoformat(row["ran_at"])  # timezone-aware ISO-8601, or this raises
    assert load_latest_params(conn) == pytest.approx(params)


def test_load_latest_params_returns_the_most_recent_run(tmp_path):
    conn = make_db(tmp_path)
    older = tuple(value * 0.9 for value in DEFAULT_PARAMS)
    newer = tuple(value * 1.2 for value in DEFAULT_PARAMS)
    conn.execute("INSERT INTO fit_runs (ran_at,n_reviews,params_json,val_logloss)"
                 " VALUES ('2026-07-01T00:00:00+00:00',900,?,0.4)",
                 (json.dumps(list(older)),))
    conn.execute("INSERT INTO fit_runs (ran_at,n_reviews,params_json,val_logloss)"
                 " VALUES ('2026-08-01T00:00:00+00:00',900,?,0.3)",
                 (json.dumps(list(newer)),))
    conn.commit()

    assert load_latest_params(conn) == pytest.approx(newer)


@pytest.mark.parametrize("params_json", [
    "not json at all",
    "[1, 2, 3]",                                  # wrong number of weights
    json.dumps([None] * 17),
    json.dumps(["a"] * 17),
    json.dumps([float("nan")] * 17),
    json.dumps([1.0] * 16 + [float("inf")]),
])
def test_load_latest_params_falls_back_on_an_unusable_row(tmp_path, params_json):
    conn = make_db(tmp_path)
    conn.execute("INSERT INTO fit_runs (ran_at,n_reviews,params_json,val_logloss)"
                 " VALUES ('2026-08-01T00:00:00+00:00',900,?,0.3)", (params_json,))
    conn.commit()

    assert load_latest_params(conn) == DEFAULT_PARAMS


def test_load_latest_params_falls_back_on_out_of_bounds_weights(tmp_path):
    """Finite, well-formed, and still unusable: a weight outside PARAM_BOUNDS.

    Nothing `save_fit` writes can land outside the box, so such a row means the
    table was hand-edited or corrupted. The promise is that the scheduler keeps
    working — and without the bounds check it does not: `fsrs.next_state`
    overflows, so every review of an already-seen card would raise.
    """
    absurd = list(DEFAULT_PARAMS)
    absurd[8] = 1e6  # exp(w8) inside the success branch
    with pytest.raises(OverflowError):
        fsrs.next_state(fsrs.MemoryState(5.0, 5.0), 3, 5.0, absurd)

    conn = make_db(tmp_path)
    conn.execute("INSERT INTO fit_runs (ran_at,n_reviews,params_json,val_logloss)"
                 " VALUES ('2026-08-01T00:00:00+00:00',900,?,0.3)",
                 (json.dumps(absurd),))
    conn.commit()

    params = load_latest_params(conn)
    assert params == DEFAULT_PARAMS
    fsrs.next_state(fsrs.initial_state(3, params), 3, 5.0, params)  # must not raise


def test_a_saved_fit_can_be_scheduled_with(tmp_path):
    """Whatever comes back must be usable by the model without special-casing."""
    conn = make_db(tmp_path)
    insert_reviews(conn, simulate(TRUE_PARAMS, n_cards=25, max_reps=9, seed=6))
    result = fit_parameters(conn, 1, min_reviews=100)
    save_fit(conn, result)

    params = load_latest_params(conn)
    state = fsrs.initial_state(3, params)
    state = fsrs.next_state(state, 3, 5.0, params)

    assert params == pytest.approx(result.params)
    assert state.stability > 0.0
    assert 1.0 <= state.difficulty <= 10.0
