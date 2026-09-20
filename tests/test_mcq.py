"""Yash Made Test: the curated MCQ bank, end to end.

The bank under test is tests/fixtures/mcq — twelve questions over three topics
in unit 1, four in unit 2 — never src/recall/mcq/bank, so these tests describe
a bank they control and do not break when a real question is written.
"""

import json
import random
import shutil
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from recall.api.app import create_app, get_conn
from recall.api.deps import get_current_user
from recall.db import connect, init_db
from recall.mcq import bank, registry, service
from recall.mcq.bank import load_bank, load_questions, validate_question
from recall.mcq.seed import seed_mcq_bank
from recall.mcq.service import McqConflict

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mcq"

OWNER, INTRUDER = 1, 2

#: The fixture bank keyed by question text, so a test can work out which shown
#: option is the right one without ever reading the attempt's stored order.
BY_TEXT = {q["question"]: q for q in load_questions(FIXTURES)}


# --- helpers ---------------------------------------------------------------

def make_db(path: str, bank_dir: Path = FIXTURES) -> None:
    conn = connect(path)
    init_db(conn)
    for uid, name in ((OWNER, "owner"), (INTRUDER, "intruder")):
        conn.execute("INSERT INTO users (id, name) VALUES (?,?)", (uid, name))
        conn.execute("INSERT INTO settings (user_id) VALUES (?)", (uid,))
    conn.commit()
    seed_mcq_bank(conn, bank_dir)
    conn.close()


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "mcq.db")
    make_db(path)
    return path


def client_as(db_path: str, user_id: int) -> TestClient:
    # The real app, wired as it ships: if app.py ever stops including the mcq
    # router these tests must fail rather than quietly mount it themselves.
    app = create_app()

    def override():
        conn = connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_conn] = override
    app.dependency_overrides[get_current_user] = lambda: user_id
    return TestClient(app)


@pytest.fixture
def client(db_path):
    return client_as(db_path, OWNER)


def start(client: TestClient, units=(1,), length="full") -> dict:
    r = client.post("/api/mcq/attempts", json={
        "subject_code": "CSE111", "units": list(units), "length": length})
    assert r.status_code == 200, r.text
    return r.json()


def correct_shown(question: dict) -> int:
    """Which SHOWN option is the right one, read from the fixture file."""
    source = BY_TEXT[question["question"]]
    return question["options"].index(source["options"][source["correct"]])


def wrong_shown(question: dict) -> int:
    return next(i for i in range(4) if i != correct_shown(question))


def a_question(**overrides) -> dict:
    """A valid question dict, before whatever the caller breaks about it."""
    question = {
        "key": "X-1", "topic": "Linux", "kind": "recall",
        "q": "Which command prints the working directory?",
        "options": ["pwd", "ls", "cd", "mkdir"],
        "correct": 0,
        "explain": "pwd prints the absolute path of the current directory.",
        "why_wrong": ["", "ls lists contents.", "cd changes directory.",
                      "mkdir makes one."],
    }
    question.update(overrides)
    return question


# --- the loader ------------------------------------------------------------

def test_a_valid_question_passes():
    validate_question(a_question())


@pytest.mark.parametrize("overrides,reason", [
    ({"options": ["a", "b", "c"]}, "exactly 4 options"),
    ({"correct": 4}, "correct must be 0-3"),
    ({"correct": -1}, "correct must be 0-3"),
    ({"why_wrong": ["", "b", "c"]}, "exactly 4 why_wrong"),
    ({"correct": 1}, "correct option"),                # why_wrong[1] is not ""
    ({"why_wrong": ["", "b", "   ", "d"]}, "why_wrong[2] is blank"),
    ({"kind": "trivia"}, "kind must be one of"),
    ({"q": "  "}, "q must be a non-empty string"),
    ({"explain": ""}, "explain must be a non-empty string"),
    ({"topic": ""}, "topic must be a non-empty string"),
])
def test_validation_names_the_key_and_the_reason(overrides, reason):
    with pytest.raises(ValueError) as exc:
        validate_question(a_question(**overrides))
    message = str(exc.value)
    assert "X-1" in message, message
    assert reason in message, message


def test_a_question_with_no_key_is_refused_by_position():
    question = a_question()
    del question["key"]
    with pytest.raises(ValueError, match="has no key"):
        validate_question(question, where="f.json question 3")


def test_duplicate_keys_across_files_are_refused(tmp_path):
    """The key is what an attempt stores and what the seeder upserts on, so
    two files sharing one would overwrite each other on every boot."""
    for name, unit in (("a.json", 1), ("b.json", 2)):
        (tmp_path / name).write_text(json.dumps({
            "subject_code": "CSE111", "unit": unit, "unit_label": "u",
            "questions": [a_question(key="CSE111-DUP")],
        }))
    with pytest.raises(ValueError) as exc:
        load_bank(tmp_path)
    assert "CSE111-DUP" in str(exc.value)
    assert "duplicate key" in str(exc.value)


def test_a_missing_bank_directory_is_zero_questions_not_an_error(tmp_path):
    assert load_bank(tmp_path / "nothing-here") == []


def test_an_empty_bank_directory_is_zero_questions(tmp_path):
    assert load_bank(tmp_path) == []


def test_underscore_keys_are_ignored():
    files = load_bank(FIXTURES)
    assert len(files) == 2
    assert all("_note" not in q for f in files for q in f.questions)


def test_the_file_shapes_question_text_from_q():
    unit1 = next(f for f in load_bank(FIXTURES) if f.unit == 1)
    assert len(unit1.questions) == 12
    assert all(q["question"] and "q" not in q for q in unit1.questions)
    assert unit1.subject_code == "CSE111"


# --- seeding ---------------------------------------------------------------

def test_seeding_twice_changes_nothing(tmp_path):
    path = str(tmp_path / "seed.db")
    conn = connect(path)
    init_db(conn)
    first = seed_mcq_bank(conn, FIXTURES)
    second = seed_mcq_bank(conn, FIXTURES)
    assert first == second
    assert first == {"files": 2, "questions": 16, "retired": 0, "active": 16,
                     "unreachable": 0}
    ids =[r["id"] for r in conn.execute("SELECT id FROM mcq_questions ORDER BY id")]
    assert len(ids) == 16, "upsert on key, never a second row for one question"
    conn.close()


def test_editing_a_question_fixes_it_in_place(tmp_path):
    """The row id must survive an edit: attempts store it."""
    bank_dir = tmp_path / "bank"
    shutil.copytree(FIXTURES, bank_dir)
    path = str(tmp_path / "edit.db")
    conn = connect(path)
    init_db(conn)
    seed_mcq_bank(conn, bank_dir)
    before = conn.execute(
        "SELECT id, question FROM mcq_questions WHERE key = 'CSE111-U2-002'"
    ).fetchone()

    data = json.loads((bank_dir / "cse111_unit2.json").read_text())
    for q in data["questions"]:
        if q["key"] == "CSE111-U2-002":
            q["q"] = "How many bits does one byte hold?"
    (bank_dir / "cse111_unit2.json").write_text(json.dumps(data))
    seed_mcq_bank(conn, bank_dir)

    after = conn.execute(
        "SELECT id, question FROM mcq_questions WHERE key = 'CSE111-U2-002'"
    ).fetchone()
    assert after["id"] == before["id"]
    assert after["question"] != before["question"]
    conn.close()


def test_a_question_removed_from_the_json_is_retired_not_deleted(tmp_path):
    """And an attempt that already drew it stays readable and gradable — which
    is the whole reason retirement exists instead of a DELETE."""
    bank_dir = tmp_path / "bank"
    shutil.copytree(FIXTURES, bank_dir)
    path = str(tmp_path / "retire.db")
    make_db(path, bank_dir)

    client = client_as(path, OWNER)
    attempt = start(client, units=[1], length="full")
    assert attempt["total"] == 12

    dropped = BY_TEXT["Which Linux command prints the full path of the "
                      "directory you are currently in?"]
    held = next(q for q in attempt["questions"]
                if q["question"] == dropped["question"])

    data = json.loads((bank_dir / "cse111_unit1.json").read_text())
    data["questions"] = [q for q in data["questions"]
                         if q["key"] != dropped["key"]]
    (bank_dir / "cse111_unit1.json").write_text(json.dumps(data))

    conn = connect(path)
    counts = seed_mcq_bank(conn, bank_dir)
    assert counts["retired"] == 1
    row = conn.execute("SELECT active FROM mcq_questions WHERE key = ?",
                       (dropped["key"],)).fetchone()
    assert row["active"] == 0
    # Seeding again retires nothing more: it is already off.
    assert seed_mcq_bank(conn, bank_dir)["retired"] == 0
    conn.close()

    resumed = client.get(f"/api/mcq/attempts/{attempt['attempt_id']}").json()
    assert resumed["total"] == 12, "a retired question stays on its attempt"
    r = client.post(f"/api/mcq/attempts/{attempt['attempt_id']}/answer",
                    json={"position": held["position"],
                          "chosen": correct_shown(held)})
    assert r.status_code == 200, r.text
    assert r.json()["is_correct"] is True

    # And it is out of the draw from now on.
    fresh = start(client, units=[1], length="full")
    assert fresh["total"] == 11


def test_retirement_does_not_reach_units_the_files_do_not_cover(tmp_path):
    """Seeding from a directory holding only unit 1 says nothing about unit 2."""
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    shutil.copy(FIXTURES / "cse111_unit1.json", bank_dir)
    path = str(tmp_path / "partial.db")
    make_db(path)                       # full bank first
    conn = connect(path)
    seed_mcq_bank(conn, bank_dir)
    live = conn.execute(
        "SELECT COUNT(*) AS n FROM mcq_questions WHERE unit = 2 AND active = 1"
    ).fetchone()["n"]
    conn.close()
    assert live == 4


def test_a_retired_question_comes_back_if_it_returns_to_the_json(tmp_path):
    bank_dir = tmp_path / "bank"
    shutil.copytree(FIXTURES, bank_dir)
    path = str(tmp_path / "revive.db")
    make_db(path, bank_dir)
    data = json.loads((bank_dir / "cse111_unit2.json").read_text())
    kept = [q for q in data["questions"] if q["key"] != "CSE111-U2-004"]
    (bank_dir / "cse111_unit2.json").write_text(
        json.dumps({**data, "questions": kept}))
    conn = connect(path)
    seed_mcq_bank(conn, bank_dir)
    shutil.copy(FIXTURES / "cse111_unit2.json", bank_dir)
    seed_mcq_bank(conn, bank_dir)
    row = conn.execute("SELECT active FROM mcq_questions WHERE key = ?",
                       ("CSE111-U2-004",)).fetchone()
    conn.close()
    assert row["active"] == 1


# --- subjects --------------------------------------------------------------

def test_subjects_lists_every_unit_with_its_live_count(client):
    body = client.get("/api/mcq/subjects").json()
    assert [s["subject_code"] for s in body] == ["CSE111"]
    subject = body[0]
    assert subject["label"] == "Orientation to Computing"
    assert subject["lengths"] == [30, 60, "full"]
    assert [(u["unit"], u["count"]) for u in subject["units"]] == [(1, 12), (2, 4)]
    assert subject["units"][0]["label"].startswith("Computational Thinking")


def test_a_unit_with_no_questions_still_appears_with_a_count_of_zero(tmp_path):
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    shutil.copy(FIXTURES / "cse111_unit1.json", bank_dir)
    path = str(tmp_path / "unit1only.db")
    make_db(path, bank_dir)
    units = client_as(path, OWNER).get("/api/mcq/subjects").json()[0]["units"]
    assert [(u["unit"], u["count"]) for u in units] == [(1, 12), (2, 0)]


# --- creating an attempt ---------------------------------------------------

def test_asking_for_thirty_from_a_bank_of_twelve_draws_twelve(client):
    attempt = start(client, units=[1], length=30)
    assert attempt["total"] == 12
    assert len(attempt["questions"]) == 12
    assert attempt["length"] == 30
    assert attempt["units"] == [1]
    assert attempt["submitted_at"] is None


def test_a_fresh_attempt_never_carries_the_answer(client):
    r = client.post("/api/mcq/attempts", json={
        "subject_code": "CSE111", "units": [1, 2], "length": "full"})
    assert "why_wrong" not in r.text
    assert "correct_index" not in r.text
    for question in r.json()["questions"]:
        assert set(question) == {"position", "topic", "kind", "question",
                                 "options", "answer"}
        assert question["answer"] is None


def test_every_option_order_is_a_real_permutation(client):
    for question in start(client, units=[1, 2])["questions"]:
        source = BY_TEXT[question["question"]]
        assert len(question["options"]) == 4
        assert sorted(question["options"]) == sorted(source["options"])


def test_two_seeds_give_two_different_sittings(db_path):
    conn = connect(db_path)
    one = service.create_attempt(conn, OWNER, "CSE111", [1], 30,
                                 rng=random.Random(1))
    two = service.create_attempt(conn, OWNER, "CSE111", [1], 30,
                                 rng=random.Random(2))
    conn.close()
    texts_one = [q["question"] for q in one["questions"]]
    texts_two = [q["question"] for q in two["questions"]]
    options_one = [q["options"] for q in one["questions"]]
    assert sorted(texts_one) == sorted(texts_two), "same pool, both times"
    assert (texts_one, options_one) != (
        texts_two, [q["options"] for q in two["questions"]])


def test_the_same_seed_gives_the_same_sitting(db_path):
    conn = connect(db_path)
    one = service.create_attempt(conn, OWNER, "CSE111", [1], 30,
                                 rng=random.Random(7))
    two = service.create_attempt(conn, OWNER, "CSE111", [1], 30,
                                 rng=random.Random(7))
    conn.close()
    assert [(q["question"], q["options"]) for q in one["questions"]] == \
           [(q["question"], q["options"]) for q in two["questions"]]


def test_two_units_pool_both_files(client):
    attempt = start(client, units=[1, 2], length="full")
    assert attempt["total"] == 16
    topics = {q["topic"] for q in attempt["questions"]}
    assert "Number Systems" in topics
    assert "Linux" in topics


def test_units_are_a_set_not_a_sequence(client):
    """[2,1] and [1,2] are one selection, so they are one leaderboard."""
    assert start(client, units=[2, 1])["units"] == [1, 2]
    assert start(client, units=[1, 1, 2])["units"] == [1, 2]


@pytest.mark.parametrize("body", [
    {"subject_code": "NOPE", "units": [1], "length": 30},
    {"subject_code": "CSE111", "units": [9], "length": 30},
    {"subject_code": "CSE111", "units": [], "length": 30},
    {"subject_code": "CSE111", "units": [1], "length": 45},
    {"subject_code": "CSE111", "units": [1], "length": "half"},
])
def test_an_impossible_selection_is_422(client, body):
    r = client.post("/api/mcq/attempts", json=body)
    assert r.status_code == 422, r.text
    assert "detail" in r.json()


def test_a_selection_with_no_questions_is_422(tmp_path):
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    shutil.copy(FIXTURES / "cse111_unit1.json", bank_dir)
    path = str(tmp_path / "unit1only.db")
    make_db(path, bank_dir)
    r = client_as(path, OWNER).post("/api/mcq/attempts", json={
        "subject_code": "CSE111", "units": [2], "length": 30})
    assert r.status_code == 422
    assert "no questions yet" in r.json()["detail"]


# --- answering -------------------------------------------------------------

def test_a_right_answer_reveals_in_shown_order_with_no_scolding(client):
    attempt = start(client, units=[1])
    question = attempt["questions"][0]
    shown = correct_shown(question)
    body = client.post(f"/api/mcq/attempts/{attempt['attempt_id']}/answer",
                       json={"position": question["position"], "chosen": shown}
                       ).json()
    assert body["is_correct"] is True
    assert body["chosen"] == shown
    assert body["correct_index"] == shown
    assert question["options"][body["correct_index"]] == \
        BY_TEXT[question["question"]]["options"][
            BY_TEXT[question["question"]]["correct"]]
    assert body["why_wrong"] == ""
    assert body["explain"] == BY_TEXT[question["question"]]["explain"]
    assert (body["answered"], body["correct_so_far"]) == (1, 1)


def test_a_wrong_answer_gets_the_note_for_the_option_it_picked(client):
    attempt = start(client, units=[1])
    question = attempt["questions"][0]
    source = BY_TEXT[question["question"]]
    picked = wrong_shown(question)
    body = client.post(f"/api/mcq/attempts/{attempt['attempt_id']}/answer",
                       json={"position": question["position"], "chosen": picked}
                       ).json()
    assert body["is_correct"] is False
    assert body["correct_index"] == correct_shown(question)
    expected = source["why_wrong"][source["options"].index(
        question["options"][picked])]
    assert body["why_wrong"] == expected != ""
    assert (body["answered"], body["correct_so_far"]) == (1, 0)


def test_the_running_totals_climb(client):
    attempt = start(client, units=[1])
    aid = attempt["attempt_id"]
    seen = []
    for question in attempt["questions"][:3]:
        seen.append(client.post(
            f"/api/mcq/attempts/{aid}/answer",
            json={"position": question["position"],
                  "chosen": correct_shown(question)}).json())
    assert [s["answered"] for s in seen] == [1, 2, 3]
    assert [s["correct_so_far"] for s in seen] == [1, 2, 3]


def test_the_first_click_is_the_answer(client):
    attempt = start(client, units=[1])
    aid, question = attempt["attempt_id"], attempt["questions"][0]
    first = client.post(f"/api/mcq/attempts/{aid}/answer",
                        json={"position": question["position"],
                              "chosen": wrong_shown(question)})
    assert first.status_code == 200
    second = client.post(f"/api/mcq/attempts/{aid}/answer",
                         json={"position": question["position"],
                               "chosen": correct_shown(question)})
    assert second.status_code == 409
    assert "already answered" in second.json()["detail"]
    stored = client.get(f"/api/mcq/attempts/{aid}").json()["questions"][
        question["position"] - 1]["answer"]
    assert stored["is_correct"] is False, "a 409 must not rewrite the answer"


def test_two_answers_in_flight_together_settle_on_one(db_path):
    """UNIQUE(attempt_id, position) is what makes the 409 true under a race,
    not a read-then-write check that both threads can pass."""
    conn = connect(db_path)
    attempt = service.create_attempt(conn, OWNER, "CSE111", [1], 30,
                                     rng=random.Random(3))
    conn.close()
    aid = attempt["attempt_id"]
    question = attempt["questions"][0]

    barrier = threading.Barrier(4)
    accepted, conflicts, errors = [], [], []

    def answer(choice: int):
        own = connect(db_path)
        try:
            barrier.wait()
            accepted.append(service.answer_attempt(own, OWNER, aid, 1, choice))
        except McqConflict:
            conflicts.append(choice)
        except Exception as exc:  # reported, not swallowed
            errors.append(repr(exc))
        finally:
            own.close()

    threads = [threading.Thread(target=answer, args=(correct_shown(question),))
               for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(accepted) == 1
    assert len(conflicts) == 3
    conn = connect(db_path)
    n = conn.execute("SELECT COUNT(*) AS n FROM mcq_answers WHERE attempt_id = ?",
                     (aid,)).fetchone()["n"]
    conn.close()
    assert n == 1


@pytest.mark.parametrize("payload", [
    {"position": 0, "chosen": 0},
    {"position": 99, "chosen": 0},
    {"position": 1, "chosen": 4},
    {"position": 1, "chosen": -1},
])
def test_an_out_of_range_answer_is_422(client, payload):
    attempt = start(client, units=[1])
    r = client.post(f"/api/mcq/attempts/{attempt['attempt_id']}/answer",
                    json=payload)
    assert r.status_code == 422, r.text


def test_answering_a_submitted_attempt_is_409(client):
    attempt = start(client, units=[1])
    aid = attempt["attempt_id"]
    client.post(f"/api/mcq/attempts/{aid}/submit")
    r = client.post(f"/api/mcq/attempts/{aid}/answer",
                    json={"position": 1, "chosen": 0})
    assert r.status_code == 409
    assert "submitted" in r.json()["detail"]


def test_answering_an_attempt_that_does_not_exist_is_404(client):
    r = client.post("/api/mcq/attempts/9999/answer",
                    json={"position": 1, "chosen": 0})
    assert r.status_code == 404


# --- submitting ------------------------------------------------------------

def sit(client: TestClient, attempt: dict, right: int, wrong: int) -> dict:
    """Answer `right` questions correctly and `wrong` wrongly; skip the rest."""
    aid = attempt["attempt_id"]
    questions = attempt["questions"]
    for question in questions[:right]:
        client.post(f"/api/mcq/attempts/{aid}/answer",
                    json={"position": question["position"],
                          "chosen": correct_shown(question)})
    for question in questions[right:right + wrong]:
        client.post(f"/api/mcq/attempts/{aid}/answer",
                    json={"position": question["position"],
                          "chosen": wrong_shown(question)})
    return client.post(f"/api/mcq/attempts/{aid}/submit").json()


def test_submitting_halfway_is_an_honest_score(client):
    attempt = start(client, units=[1], length="full")
    result = sit(client, attempt, right=5, wrong=2)
    assert result["total"] == 12, "total is what was drawn, not what was answered"
    assert result["answered"] == 7
    assert result["score"] == 5
    assert result["percent"] == round(100 * 5 / 12)
    assert result["duration_s"] >= 0


def test_by_topic_covers_every_question_drawn(client):
    attempt = start(client, units=[1], length="full")
    result = sit(client, attempt, right=4, wrong=1)
    assert sum(t["total"] for t in result["by_topic"]) == 12
    assert sum(t["correct"] for t in result["by_topic"]) == result["score"]
    assert {t["topic"] for t in result["by_topic"]} == {
        "Computational Thinking", "Operating Systems", "Linux"}
    assert [t["topic"] for t in result["by_topic"]] == sorted(
        t["topic"] for t in result["by_topic"])


def test_missed_lists_the_wrong_and_the_unanswered_in_attempt_order(client):
    attempt = start(client, units=[1], length="full")
    result = sit(client, attempt, right=3, wrong=2)
    positions = [m["position"] for m in result["missed"]]
    assert positions == sorted(positions)
    assert len(result["missed"]) == 12 - 3

    answered_wrong = [m for m in result["missed"] if m["chosen"] is not None]
    assert len(answered_wrong) == 2
    for missed in answered_wrong:
        assert missed["why_wrong"] != ""
        assert missed["options"][missed["correct_index"]] == \
            BY_TEXT[missed["question"]]["options"][
                BY_TEXT[missed["question"]]["correct"]]

    unanswered = [m for m in result["missed"] if m["chosen"] is None]
    assert len(unanswered) == 7
    for missed in unanswered:
        assert missed["why_wrong"] == "", "nothing was picked to explain"
        assert missed["explain"]


def test_submitting_twice_returns_the_same_result(client):
    attempt = start(client, units=[1], length="full")
    first = sit(client, attempt, right=4, wrong=1)
    second = client.post(
        f"/api/mcq/attempts/{attempt['attempt_id']}/submit").json()
    assert first == second


def test_two_submits_in_flight_together_do_not_double_anything(db_path):
    conn = connect(db_path)
    attempt = service.create_attempt(conn, OWNER, "CSE111", [1], 30,
                                     rng=random.Random(11))
    aid = attempt["attempt_id"]
    for question in attempt["questions"][:4]:
        service.answer_attempt(conn, OWNER, aid, question["position"],
                               correct_shown(question))
    conn.close()

    barrier = threading.Barrier(4)
    results, errors = [], []

    def submit():
        own = connect(db_path)
        try:
            barrier.wait()
            results.append(service.submit_attempt(own, OWNER, aid))
        except Exception as exc:  # reported, not swallowed
            errors.append(repr(exc))
        finally:
            own.close()

    threads = [threading.Thread(target=submit) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(results) == 4
    assert {r["score"] for r in results} == {4}
    assert {r["duration_s"] for r in results} == {results[0]["duration_s"]}
    conn = connect(db_path)
    row = conn.execute("SELECT submitted_at, score FROM mcq_attempts WHERE id = ?",
                       (aid,)).fetchone()
    n = conn.execute("SELECT COUNT(*) AS n FROM mcq_answers WHERE attempt_id = ?",
                     (aid,)).fetchone()["n"]
    conn.close()
    assert row["score"] == 4 and row["submitted_at"] is not None
    assert n == 4, "answers are not re-recorded by a second submit"


def test_a_sitting_nobody_answered_has_no_rank(client):
    attempt = start(client, units=[1])
    result = client.post(
        f"/api/mcq/attempts/{attempt['attempt_id']}/submit").json()
    assert result["answered"] == 0
    assert result["score"] == 0
    assert result["rank"] is None


def test_submitting_an_attempt_that_does_not_exist_is_404(client):
    assert client.post("/api/mcq/attempts/9999/submit").status_code == 404


# --- abandoning ------------------------------------------------------------

def test_abandoning_an_open_attempt_removes_it(client):
    attempt = start(client, units=[1])
    aid = attempt["attempt_id"]
    client.post(f"/api/mcq/attempts/{aid}/answer",
                json={"position": 1, "chosen": 0})
    r = client.delete(f"/api/mcq/attempts/{aid}")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert client.get(f"/api/mcq/attempts/{aid}").status_code == 404
    assert client.get("/api/mcq/attempts").json() == []


def test_abandoning_a_submitted_attempt_is_409(client):
    attempt = start(client, units=[1])
    aid = attempt["attempt_id"]
    client.post(f"/api/mcq/attempts/{aid}/submit")
    r = client.delete(f"/api/mcq/attempts/{aid}")
    assert r.status_code == 409
    assert client.get(f"/api/mcq/attempts/{aid}").status_code == 200


def test_abandoning_an_attempt_that_does_not_exist_is_404(client):
    assert client.delete("/api/mcq/attempts/9999").status_code == 404


# --- history ---------------------------------------------------------------

def test_history_is_newest_first_and_open_attempts_have_no_score(client):
    older = start(client, units=[1])
    sit(client, older, right=3, wrong=1)
    newer = start(client, units=[1, 2])

    rows = client.get("/api/mcq/attempts").json()
    assert [r["id"] for r in rows] == [newer["attempt_id"], older["attempt_id"]]
    assert rows[0]["score"] is None and rows[0]["submitted_at"] is None
    assert rows[0]["answered"] == 0 and rows[0]["units"] == [1, 2]
    assert rows[1]["score"] == 3 and rows[1]["answered"] == 4
    assert rows[1]["total"] == 12 and rows[1]["length"] == "full"


# --- isolation -------------------------------------------------------------

def test_another_users_attempt_is_missing_not_forbidden(db_path):
    """404 identical to an id that never existed: answering the two
    differently would make this route an oracle for other accounts."""
    owner = client_as(db_path, OWNER)
    intruder = client_as(db_path, INTRUDER)
    attempt = start(owner, units=[1])
    aid = attempt["attempt_id"]

    assert intruder.get(f"/api/mcq/attempts/{aid}").status_code == 404
    assert intruder.post(f"/api/mcq/attempts/{aid}/answer",
                         json={"position": 1, "chosen": 0}).status_code == 404
    assert intruder.post(f"/api/mcq/attempts/{aid}/submit").status_code == 404
    assert intruder.delete(f"/api/mcq/attempts/{aid}").status_code == 404
    # Word for word what an id that never existed gets, so the message itself
    # does not leak that this one does.
    assert intruder.get(f"/api/mcq/attempts/{aid}").json()["detail"] == \
        f"no attempt {aid}"
    assert intruder.get("/api/mcq/attempts/9999").json()["detail"] == \
        "no attempt 9999"

    # None of that touched the owner's attempt.
    assert owner.get(f"/api/mcq/attempts/{aid}").status_code == 200
    conn = connect(db_path)
    n = conn.execute("SELECT COUNT(*) AS n FROM mcq_answers").fetchone()["n"]
    conn.close()
    assert n == 0


def test_history_shows_only_your_own_attempts(db_path):
    owner = client_as(db_path, OWNER)
    intruder = client_as(db_path, INTRUDER)
    start(owner, units=[1])
    start(owner, units=[2])
    mine = start(intruder, units=[1])

    assert len(owner.get("/api/mcq/attempts").json()) == 2
    theirs = intruder.get("/api/mcq/attempts").json()
    assert [r["id"] for r in theirs] == [mine["attempt_id"]]


# --- the leaderboard -------------------------------------------------------

def board(client: TestClient, units="1", length="full") -> list[dict]:
    r = client.get("/api/mcq/leaderboard", params={
        "subject_code": "CSE111", "units": units, "length": length})
    assert r.status_code == 200, r.text
    return r.json()


def set_duration(db_path: str, attempt_id: int, seconds: int) -> None:
    """Duration is wall clock, so a test that wants to compare two has to say
    what they were."""
    conn = connect(db_path)
    conn.execute("UPDATE mcq_attempts SET duration_s = ? WHERE id = ?",
                 (seconds, attempt_id))
    conn.commit()
    conn.close()


def test_the_board_ranks_by_percent_then_by_the_shorter_sitting(db_path):
    owner, intruder = client_as(db_path, OWNER), client_as(db_path, INTRUDER)
    a = start(owner, units=[1], length="full")
    sit(owner, a, right=6, wrong=0)
    set_duration(db_path, a["attempt_id"], 600)
    b = start(intruder, units=[1], length="full")
    sit(intruder, b, right=6, wrong=0)
    set_duration(db_path, b["attempt_id"], 120)

    rows = board(owner)
    assert [r["user_id"] for r in rows] == [INTRUDER, OWNER]
    assert [r["name"] for r in rows] == ["intruder", "owner"]
    assert all(r["score"] == 6 and r["total"] == 12 for r in rows)
    assert all(r["percent"] == 50 for r in rows)
    assert [r["duration_s"] for r in rows] == [120, 600]


def test_the_board_keeps_each_users_best_attempt_only(db_path):
    owner = client_as(db_path, OWNER)
    for right in (3, 9, 5):
        sit(owner, start(owner, units=[1], length="full"), right=right, wrong=0)
    rows = board(owner)
    assert len(rows) == 1
    assert rows[0]["score"] == 9


def test_different_selections_are_different_boards(db_path):
    owner = client_as(db_path, OWNER)
    sit(owner, start(owner, units=[1], length="full"), right=6, wrong=0)
    sit(owner, start(owner, units=[1, 2], length="full"), right=2, wrong=0)

    one = board(owner, units="1")
    both = board(owner, units="1,2")
    assert [r["total"] for r in one] == [12]
    assert [r["total"] for r in both] == [16]
    assert board(owner, units="2") == []
    assert board(owner, units="1", length="30") == []


def test_a_reversed_unit_list_is_the_same_board(db_path):
    owner = client_as(db_path, OWNER)
    sit(owner, start(owner, units=[2, 1], length="full"), right=4, wrong=0)
    assert len(board(owner, units="1,2")) == 1
    assert len(board(owner, units="2,1")) == 1


def test_an_open_attempt_is_not_on_the_board(db_path):
    owner = client_as(db_path, OWNER)
    attempt = start(owner, units=[1], length="full")
    owner.post(f"/api/mcq/attempts/{attempt['attempt_id']}/answer",
               json={"position": 1,
                     "chosen": correct_shown(attempt["questions"][0])})
    assert board(owner) == []


def test_the_submit_result_says_where_you_landed(db_path):
    owner, intruder = client_as(db_path, OWNER), client_as(db_path, INTRUDER)
    first = sit(owner, start(owner, units=[1], length="full"), right=9, wrong=0)
    assert first["rank"] == {"position": 1, "of": 1}
    second = sit(intruder, start(intruder, units=[1], length="full"),
                 right=4, wrong=1)
    assert second["rank"] == {"position": 2, "of": 2}
    assert sit(owner, start(owner, units=[1], length="full"),
               right=2, wrong=0)["rank"] == {"position": 1, "of": 2}, \
        "the board holds your best, so a worse sitting does not demote you"


@pytest.mark.parametrize("params", [
    {"subject_code": "NOPE", "units": "1", "length": "full"},
    {"subject_code": "CSE111", "units": "9", "length": "full"},
    {"subject_code": "CSE111", "units": "one", "length": "full"},
    {"subject_code": "CSE111", "units": "1", "length": "45"},
    {"subject_code": "CSE111", "units": "1", "length": "half"},
])
def test_a_nonsense_board_request_is_422(client, params):
    r = client.get("/api/mcq/leaderboard", params=params)
    assert r.status_code == 422, r.text


def test_the_board_is_capped(db_path):
    conn = connect(db_path)
    for uid in range(3, 33):
        conn.execute("INSERT INTO users (id, name) VALUES (?,?)", (uid, f"u{uid}"))
        attempt = service.create_attempt(conn, uid, "CSE111", [1], "full",
                                         rng=random.Random(uid))
        service.answer_attempt(
            conn, uid, attempt["attempt_id"], 1,
            correct_shown(attempt["questions"][0]))
        service.submit_attempt(conn, uid, attempt["attempt_id"])
    rows = service.leaderboard(conn, "CSE111", [1], "full")
    conn.close()
    assert len(rows) == 25


# --- the router is really mounted -----------------------------------------

def test_every_contract_path_is_on_the_app():
    paths = create_app().openapi()["paths"]
    for path in ("/api/mcq/subjects", "/api/mcq/attempts",
                 "/api/mcq/attempts/{attempt_id}",
                 "/api/mcq/attempts/{attempt_id}/answer",
                 "/api/mcq/attempts/{attempt_id}/submit",
                 "/api/mcq/leaderboard"):
        assert path in paths, path


def test_the_shipped_bank_directory_is_readable():
    """It may be empty or absent — that is zero questions, not a boot failure."""
    assert isinstance(load_bank(bank.BANK_DIR), list)


# --- review pass: trying to break it ---------------------------------------

def bank_copy(tmp_path) -> Path:
    """A writable copy of the fixture bank, so a test can edit it mid-flight."""
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    for name in ("cse111_unit1.json", "cse111_unit2.json"):
        shutil.copy(FIXTURES / name, bank_dir)
    return bank_dir


def drop_key(bank_dir: Path, filename: str, key: str) -> None:
    path = bank_dir / filename
    data = json.loads(path.read_text())
    data["questions"] = [q for q in data["questions"] if q["key"] != key]
    path.write_text(json.dumps(data))


def test_a_question_retired_mid_attempt_is_still_answerable_and_gradable(tmp_path):
    """`active` gates the DRAW, not the replay: a sitting already holding a
    question must stay answerable and gradable after the JSON drops it."""
    bank_dir = bank_copy(tmp_path)
    path = str(tmp_path / "retire.db")
    make_db(path, bank_dir)
    client = client_as(path, OWNER)
    attempt = start(client, units=[1], length="full")
    aid = attempt["attempt_id"]
    doomed = attempt["questions"][0]
    key = BY_TEXT[doomed["question"]]["key"]

    drop_key(bank_dir, "cse111_unit1.json", key)
    conn = connect(path)
    counts = seed_mcq_bank(conn, bank_dir)
    conn.close()
    assert counts["retired"] == 1

    resumed = client.get(f"/api/mcq/attempts/{aid}").json()
    assert len(resumed["questions"]) == 12, "a retired question is not dropped"
    assert resumed["questions"][0]["question"] == doomed["question"]

    reveal = client.post(f"/api/mcq/attempts/{aid}/answer", json={
        "position": 1, "chosen": correct_shown(doomed)})
    assert reveal.status_code == 200, reveal.text
    assert reveal.json()["is_correct"] is True

    result = client.post(f"/api/mcq/attempts/{aid}/submit").json()
    assert result["total"] == 12 and result["score"] == 1
    assert sum(t["total"] for t in result["by_topic"]) == 12
    assert len(result["missed"]) == 11

    fresh = start(client, units=[1], length="full")
    assert fresh["total"] == 11, "only new draws exclude a retired question"
    assert doomed["question"] not in {q["question"] for q in fresh["questions"]}


def test_a_reversed_unit_list_at_creation_reaches_the_one_board(db_path):
    """[2,1] must be stored, ranked and looked up as [1,2] — one paper, one
    board, whichever way the picker happened to hand the units over."""
    owner = client_as(db_path, OWNER)
    result = sit(owner, start(owner, units=[2, 1], length="full"),
                 right=4, wrong=0)
    assert result["rank"] == {"position": 1, "of": 1}
    conn = connect(db_path)
    stored = conn.execute("SELECT units_json FROM mcq_attempts").fetchone()
    conn.close()
    assert stored["units_json"] == json.dumps([1, 2])
    for units in ("1,2", "2,1", "2,1,2"):
        assert len(board(owner, units=units)) == 1, units


def test_full_across_two_units_draws_every_active_question_once(client):
    attempt = start(client, units=[1, 2], length="full")
    assert attempt["length"] == "full"
    assert attempt["total"] == 16 and len(attempt["questions"]) == 16
    texts = [q["question"] for q in attempt["questions"]]
    assert len(set(texts)) == 16, "drawn without replacement"
    assert set(texts) == set(BY_TEXT)
    assert [q["position"] for q in attempt["questions"]] == list(range(1, 17))


def test_two_http_answers_to_the_first_question_settle_on_one(db_path):
    """The 409 has to hold through the route, not only in the service."""
    owner = client_as(db_path, OWNER)
    attempt = start(owner, units=[1], length="full")
    aid = attempt["attempt_id"]
    shown = correct_shown(attempt["questions"][0])

    barrier = threading.Barrier(2)
    codes: list[int] = []

    def answer():
        own = client_as(db_path, OWNER)
        barrier.wait()
        codes.append(own.post(f"/api/mcq/attempts/{aid}/answer",
                              json={"position": 1, "chosen": shown}).status_code)

    threads = [threading.Thread(target=answer) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(codes) == [200, 409]


def test_a_note_on_the_correct_option_is_refused_by_key(tmp_path):
    """The message has to name the key: the person fixing the file is looking
    at a thousand lines of JSON, not at a stack trace."""
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    (bank_dir / "bad.json").write_text(json.dumps({
        "subject_code": "CSE111", "unit": 1,
        "questions": [a_question(key="CSE111-U1-777",
                                 why_wrong=["it is not", "ls lists contents.",
                                            "cd changes directory.",
                                            "mkdir makes one."])],
    }))
    with pytest.raises(ValueError) as exc:
        load_bank(bank_dir)
    assert "CSE111-U1-777" in str(exc.value)
    assert "why_wrong[0]" in str(exc.value)


def test_an_absent_bank_directory_seeds_nothing_and_raises_nothing(tmp_path):
    path = str(tmp_path / "empty.db")
    conn = connect(path)
    init_db(conn)
    counts = seed_mcq_bank(conn, tmp_path / "not-here")
    conn.close()
    assert counts == {"files": 0, "questions": 0, "retired": 0, "active": 0,
                      "unreachable": 0}
    body = client_as(path, OWNER).get("/api/mcq/subjects").json()
    assert [u["count"] for u in body[0]["units"]] == [0, 0]


def test_every_contract_operation_is_on_the_app():
    """Eight operations, not six paths: DELETE and the two GETs on
    /api/mcq/attempts are separate rows in the contract's table."""
    paths = create_app().openapi()["paths"]
    wanted = {
        ("get", "/api/mcq/subjects"),
        ("post", "/api/mcq/attempts"),
        ("get", "/api/mcq/attempts"),
        ("get", "/api/mcq/attempts/{attempt_id}"),
        ("post", "/api/mcq/attempts/{attempt_id}/answer"),
        ("post", "/api/mcq/attempts/{attempt_id}/submit"),
        ("delete", "/api/mcq/attempts/{attempt_id}"),
        ("get", "/api/mcq/leaderboard"),
    }
    have = {(method, path) for path, ops in paths.items() for method in ops}
    assert wanted <= have, wanted - have


def test_the_lifespan_seeds_the_bank(tmp_path, monkeypatch):
    """A local dev database started by hand has to get the bank too — the
    entrypoint only covers the container."""
    from recall.api import app as app_module

    seen: list[str] = []
    real = app_module.seed_mcq_bank
    monkeypatch.setattr(app_module, "seed_mcq_bank",
                        lambda conn, *a, **k: seen.append("called") or real(conn))
    monkeypatch.setenv("RECALL_DB", str(tmp_path / "boot.db"))
    with TestClient(app_module.create_app()):
        pass
    assert seen == ["called"]


def test_the_container_entrypoint_seeds_the_bank():
    text = (Path(__file__).resolve().parents[1]
            / "ops" / "vps" / "entrypoint.sh").read_text()
    assert "from recall.mcq.seed import seed_mcq_bank" in text
    assert "seed_mcq_bank(conn)" in text


def test_an_empty_board_is_an_empty_list_not_a_404(client):
    r = client.get("/api/mcq/leaderboard", params={
        "subject_code": "CSE111", "units": "1,2", "length": "60"})
    assert r.status_code == 200 and r.json() == []


def test_no_attempt_or_answer_is_reached_without_its_owner(db_path):
    """Every service entry point, called with the wrong user_id, is a
    LookupError and leaves the rows alone."""
    conn = connect(db_path)
    attempt = service.create_attempt(conn, OWNER, "CSE111", [1], "full",
                                     rng=random.Random(5))
    aid = attempt["attempt_id"]
    service.answer_attempt(conn, OWNER, aid, 1,
                           correct_shown(attempt["questions"][0]))
    for call in (lambda: service.get_attempt(conn, INTRUDER, aid),
                 lambda: service.answer_attempt(conn, INTRUDER, aid, 2, 0),
                 lambda: service.submit_attempt(conn, INTRUDER, aid),
                 lambda: service.abandon_attempt(conn, INTRUDER, aid)):
        with pytest.raises(LookupError):
            call()
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM mcq_answers WHERE attempt_id = ?",
        (aid,)).fetchone()["n"] == 1
    assert service.list_attempts(conn, INTRUDER) == []
    assert len(service.list_attempts(conn, OWNER)) == 1
    conn.close()


def test_submitting_survives_a_unit_leaving_the_registry(db_path, monkeypatch):
    """MCQ_UNITS is code and it changes as units get written and renamed. An
    attempt drawn before such an edit must still submit: ranking it re-checked
    the selection against the registry, so dropping one unit turned every open
    attempt covering it into a 500 with the sitting unrecoverable."""
    owner = client_as(db_path, OWNER)
    attempt = start(owner, units=[1, 2], length="full")
    aid = attempt["attempt_id"]
    owner.post(f"/api/mcq/attempts/{aid}/answer", json={
        "position": 1, "chosen": correct_shown(attempt["questions"][0])})

    units = registry.MCQ_UNITS["CSE111"]["units"]
    monkeypatch.setitem(registry.MCQ_UNITS["CSE111"], "units", {1: units[1]})

    r = owner.post(f"/api/mcq/attempts/{aid}/submit")
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["score"] == 1 and result["total"] == 16
    assert result["rank"] == {"position": 1, "of": 1}
    assert owner.get(f"/api/mcq/attempts/{aid}").status_code == 200
    assert [row["id"] for row in owner.get("/api/mcq/attempts").json()] == [aid]


def test_a_subject_leaving_the_registry_does_not_strand_its_attempts(db_path,
                                                                     monkeypatch):
    owner = client_as(db_path, OWNER)
    attempt = start(owner, units=[1], length=30)
    aid = attempt["attempt_id"]
    owner.post(f"/api/mcq/attempts/{aid}/answer", json={
        "position": 1, "chosen": correct_shown(attempt["questions"][0])})
    monkeypatch.delitem(registry.MCQ_UNITS, "CSE111")
    r = owner.post(f"/api/mcq/attempts/{aid}/submit")
    assert r.status_code == 200, r.text
    assert r.json()["rank"] == {"position": 1, "of": 1}


def test_a_board_a_user_asks_for_is_still_validated(client):
    """The split that fixed the above must not stop validating the front door."""
    r = client.get("/api/mcq/leaderboard", params={
        "subject_code": "CSE111", "units": "9", "length": "full"})
    assert r.status_code == 422


@pytest.mark.parametrize("options,reason", [
    (["pwd", "ls", "pwd", "mkdir"], "options 0 and 2"),
    (["pwd", "ls", "cd", " LS "], "options 1 and 3"),
])
def test_two_options_that_read_the_same_are_refused(options, reason):
    """`is_correct` compares positions, so a duplicate of the right answer
    marks a student wrong for reading the words that were right."""
    with pytest.raises(ValueError) as exc:
        validate_question(a_question(options=options))
    assert "X-1" in str(exc.value) and reason in str(exc.value)


def test_the_fixture_bank_has_no_duplicate_options():
    assert len(load_questions(FIXTURES)) == 16


def test_seeding_counts_questions_no_picker_can_reach(tmp_path):
    """A file named for a subject or unit the registry does not declare seeds
    fine and is then reachable by nobody. It must not take the boot down — the
    entrypoint runs under `set -e` — but it must not be silent either."""
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    (bank_dir / "cse326_unit1.json").write_text(json.dumps({
        "subject_code": "CSE326", "unit": 1,
        "questions": [a_question(key="CSE326-U1-001")],
    }))
    (bank_dir / "cse111_unit9.json").write_text(json.dumps({
        "subject_code": "CSE111", "unit": 9,
        "questions": [a_question(key="CSE111-U9-001")],
    }))
    shutil.copy(FIXTURES / "cse111_unit1.json", bank_dir)

    path = str(tmp_path / "stray.db")
    conn = connect(path)
    init_db(conn)
    counts = seed_mcq_bank(conn, bank_dir)
    conn.close()
    assert counts["questions"] == 14 and counts["unreachable"] == 2

    body = client_as(path, OWNER).get("/api/mcq/subjects").json()
    assert [s["subject_code"] for s in body] == ["CSE111"]
    assert [(u["unit"], u["count"]) for u in body[0]["units"]] == [(1, 12), (2, 0)]


def test_a_wired_up_bank_reaches_everything_it_seeds(tmp_path):
    conn = connect(str(tmp_path / "ok.db"))
    init_db(conn)
    counts = seed_mcq_bank(conn, FIXTURES)
    conn.close()
    assert counts["unreachable"] == 0
