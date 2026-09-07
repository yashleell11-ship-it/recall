import random
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from recall.api import tests_routes
from recall.api.app import create_app, get_conn
from recall.api.deps import get_current_user
from recall.db import connect, init_db
from recall.testmode import service
from recall.testmode.assembly import CandidateCard, assemble
from recall.testmode.marks import marks_for_card

# Card shapes used to seed decks: (kind, answer word count, marks it must be worth).
SHAPES = [("cloze", 2, 1), ("qa", 4, 1), ("qa", 8, 2), ("qa", 20, 5)]


def words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def seed(db_path: str, topics: list[tuple[str, int]]) -> None:
    """A deck of `n` active cards per topic, cycling through SHAPES."""
    conn = connect(db_path)
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.execute("INSERT INTO settings (user_id) VALUES (1)")
    for tid, (code, n) in enumerate(topics, start=1):
        conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (?,1,?,?)",
                     (tid, code, f"{code} label"))
        conn.execute(
            "INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,added_at)"
            " VALUES (?,1,?,?,'pdf',?,'2026-09-01T00:00:00+00:00')",
            (tid, tid, f"{code}.pdf", f"sha{tid}"))
        conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref)"
                     " VALUES (?,?,0,'body text',?)", (tid, tid, f"p{tid}"))
        for i in range(n):
            kind, n_words, _ = SHAPES[i % len(SHAPES)]
            conn.execute(
                "INSERT INTO cards (chunk_id,topic_id,kind,question,answer,"
                "cloze_text,arm,state,created_at) VALUES (?,?,?,?,?,?,'learned',"
                "'active','2026-09-01T00:00:00+00:00')",
                (tid, tid, kind, f"{code} q{i}?", words(n_words),
                 "{{c1::x}} y" if kind == "cloze" else None))
    # Cards that are not active must never reach a paper.
    conn.execute(
        "INSERT INTO cards (chunk_id,topic_id,kind,question,answer,cloze_text,arm,"
        "state,created_at) VALUES (1,1,'qa','pending?','a',NULL,'learned',"
        "'pending','2026-09-01T00:00:00+00:00')")
    conn.execute(
        "INSERT INTO cards (chunk_id,topic_id,kind,question,answer,cloze_text,arm,"
        "state,created_at) VALUES (1,1,'qa','rejected?','a',NULL,'learned',"
        "'rejected','2026-09-01T00:00:00+00:00')")
    conn.commit()
    conn.close()


def make_client(db_path: str) -> TestClient:
    # The real app, wired as it ships: if app.py ever stops including the test
    # router, these tests must fail rather than quietly mount it themselves.
    app = create_app()

    def override():
        conn = connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_conn] = override
    app.dependency_overrides[tests_routes.get_conn] = override
    app.dependency_overrides[get_current_user] = lambda: 1
    return TestClient(app)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "testmode.db")
    seed(path, [("CSE111", 18), ("MATHS", 9), ("PHY", 3)])
    return path


@pytest.fixture
def client(db_path):
    return make_client(db_path)


def now() -> datetime:
    return datetime.now(timezone.utc)


def ago(days: float) -> str:
    return (now() - timedelta(days=days)).isoformat()


def ahead(days: float) -> str:
    return (now() + timedelta(days=days)).isoformat()


# --- marks -----------------------------------------------------------------

@pytest.mark.parametrize("kind,answer,expected", [
    ("cloze", "", 1),
    ("cloze", words(50), 1),          # a cloze is one blank however long the text
    ("qa", "", 1),
    ("qa", words(1), 1),
    ("qa", words(4), 1),              # boundary: last 1-mark answer
    ("qa", words(5), 2),              # boundary: first 2-mark answer
    ("qa", words(12), 2),             # boundary: last 2-mark answer
    ("qa", words(13), 5),             # boundary: first 5-mark answer
    ("qa", words(200), 5),
])
def test_marks_banding_at_every_boundary(kind, answer, expected):
    assert marks_for_card(kind, answer) == expected


def test_marks_ignores_whitespace_padding():
    assert marks_for_card("qa", "  one   two \n three  ") == 1


def test_marks_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        marks_for_card("essay", "whatever")


# --- assembly --------------------------------------------------------------

def candidates(spec: list[tuple[str, int]]) -> list[CandidateCard]:
    """spec: (topic_code, count) -> cards cycling through the SHAPES marks."""
    out, cid = [], 0
    for code, n in spec:
        for i in range(n):
            cid += 1
            out.append(CandidateCard(cid, code, SHAPES[i % len(SHAPES)][2]))
    return out


def test_assembly_hits_the_target_exactly():
    paper = assemble(candidates([("A", 18), ("B", 9), ("C", 3)]), 30, now=now())
    assert paper.total_marks == 30
    assert sum(c.marks for c in paper.cards) == 30
    assert paper.short is False
    assert paper.note is None


def test_assembly_hits_a_hundred_marks_exactly():
    paper = assemble(candidates([("A", 60), ("B", 40), ("C", 20)]), 100, now=now())
    assert paper.total_marks == 100


def test_assembly_spans_topics_in_proportion_to_their_size():
    paper = assemble(candidates([("A", 18), ("B", 9), ("C", 3)]), 30, now=now())
    marks = {"A": 0, "B": 0, "C": 0}
    for card in paper.cards:
        marks[card.topic_code] += card.marks
    assert set(marks) == {"A", "B", "C"}, "every topic must be represented"
    # Shares are 18/9/3 cards out of 30, so roughly 18/9/3 of the 30 marks.
    assert 14 <= marks["A"] <= 22
    assert 6 <= marks["B"] <= 12
    assert 1 <= marks["C"] <= 6


def test_assembly_never_repeats_a_card():
    paper = assemble(candidates([("A", 18), ("B", 9), ("C", 3)]), 30, now=now())
    ids = [c.card_id for c in paper.cards]
    assert len(ids) == len(set(ids))


def test_a_single_topic_deck_still_hits_the_target():
    paper = assemble(candidates([("A", 40)]), 30, now=now())
    assert paper.total_marks == 30


def test_a_short_deck_returns_a_short_paper_and_says_so():
    deck = candidates([("A", 3)])  # 1 + 1 + 2 = 4 marks against a target of 30
    paper = assemble(deck, 30, now=now())
    assert paper.total_marks == 4
    assert len(paper.cards) == 3
    assert paper.short is True
    assert "4 of 30" in paper.note
    assert len({c.card_id for c in paper.cards}) == 3, "no padding with repeats"


def test_a_deck_with_no_one_mark_cards_still_lands_on_the_target():
    """Greedy alone stalls at 29 here: a gap of 1 cannot be paid out of 2s and 5s."""
    deck = ([CandidateCard(i, "A", 5) for i in range(1, 11)]
            + [CandidateCard(i, "A", 2) for i in range(11, 21)])
    paper = assemble(deck, 30, now=now())
    assert paper.total_marks == 30
    assert paper.short is False
    ids = [c.card_id for c in paper.cards]
    assert len(ids) == len(set(ids))


def test_a_paper_needing_two_questions_swapped_still_lands_on_the_target():
    """1,1,5,5 marks against 10: greedy fills 1+1+5 = 7 and no single swap saves
    it, but 5+5 is sitting right there."""
    deck = [CandidateCard(1, "A", 1), CandidateCard(2, "A", 1),
            CandidateCard(3, "A", 5), CandidateCard(4, "A", 5)]
    paper = assemble(deck, 10, now=now())
    assert paper.total_marks == 10
    assert paper.short is False
    assert sorted(c.card_id for c in paper.cards) == [3, 4]


def test_landing_on_the_target_never_costs_a_topic_its_place():
    """Greedy stalls on this deck and the swap that lands it on 10 marks can be
    paid for by dropping T2 entirely. Buying the last mark with a subject is not
    a trade worth making."""
    deck = [CandidateCard(1, "T0", 1), CandidateCard(2, "T0", 2),
            CandidateCard(3, "T1", 2), CandidateCard(4, "T1", 5),
            CandidateCard(5, "T2", 2), CandidateCard(6, "T2", 5)]
    paper = assemble(deck, 10, now=now())
    assert paper.total_marks == 10
    assert {c.topic_code for c in paper.cards} == {"T0", "T1", "T2"}


def test_a_big_deck_is_assembled_exactly_and_fast():
    """The exact search is bounded by the target, not by the size of the deck."""
    deck = ([CandidateCard(i, "A", 2) for i in range(1, 4001)]
            + [CandidateCard(i, "B", 5) for i in range(4001, 8001)])
    started = time.perf_counter()
    paper = assemble(deck, 101, now=now())  # odd target: needs 2s and 5s together
    assert paper.total_marks == 101
    assert time.perf_counter() - started < 2.0


def test_assembly_hits_every_reachable_target_on_random_decks():
    """The property that matters: exact whenever the deck allows, never over,
    never a repeat. Seeded, so a failure is reproducible."""
    rng = random.Random(20260905)
    for _ in range(200):
        cid, deck = 0, []
        for topic in range(rng.randint(1, 4)):
            for _ in range(rng.randint(0, 20)):
                cid += 1
                deck.append(CandidateCard(
                    cid, f"T{topic}", rng.choice([1, 1, 2, 5]),
                    stability=rng.choice([None, 0.4, 3.0, 300.0]),
                    difficulty=rng.choice([None, 1.2, 5.0, 9.8]),
                    due_at=ago(rng.uniform(-30, 30))))
        target = rng.choice([7, 13, 30, 100])
        paper = assemble(deck, target, now=now())
        ids = [c.card_id for c in paper.cards]

        assert len(ids) == len(set(ids)), "a card may never be asked twice"
        assert sum(c.marks for c in paper.cards) == paper.total_marks
        assert paper.total_marks <= target, "a paper never overshoots its target"
        assert paper.short is (paper.total_marks < target)
        if paper.short and reachable([c.marks for c in deck], target):
            raise AssertionError(
                f"stopped at {paper.total_marks} of {target} though the deck "
                f"can make it: {sorted(c.marks for c in deck)}")


def reachable(marks: list[int], target: int) -> bool:
    """Independent check: can any subset of these marks sum to the target?"""
    sums = {0}
    for m in marks:
        sums |= {s + m for s in sums if s + m <= target}
    return target in sums


def test_a_target_no_subset_can_make_is_reported_short():
    """31 marks out of 2-mark cards is arithmetic, not a deck problem — say so."""
    paper = assemble([CandidateCard(i, "A", 2) for i in range(1, 40)], 31, now=now())
    assert paper.total_marks == 30
    assert paper.short is True
    assert "30 of 31" in paper.note


def test_an_empty_deck_is_reported_rather_than_faked():
    paper = assemble([], 30, now=now())
    assert paper.cards == ()
    assert paper.short is True
    assert paper.note == "no active cards to test"


def test_assembly_prefers_weak_cards_but_still_includes_strong_ones():
    weak = [CandidateCard(i, "A", 1, stability=0.5, difficulty=9.5,
                          due_at=ago(5)) for i in range(1, 5)]
    strong = [CandidateCard(i, "A", 1, stability=300.0, difficulty=1.5,
                            due_at=ahead(60)) for i in range(5, 9)]
    paper = assemble(weak + strong, 4, now=now())

    picked = {c.card_id for c in paper.cards}
    assert paper.total_marks == 4
    assert len(picked & {1, 2, 3, 4}) == 3, "the weak cards should dominate"
    assert picked & {5, 6, 7, 8}, "a paper of only your worst cards is punishment"


def test_new_cards_rank_between_weak_and_strong():
    weakest = CandidateCard(1, "A", 1, stability=0.5, difficulty=10.0, due_at=ago(9))
    fresh = CandidateCard(2, "A", 1)
    strongest = CandidateCard(3, "A", 1, stability=400.0, difficulty=1.0,
                              due_at=ahead(90))
    from recall.testmode.assembly import weakness
    scores = [weakness(c, now()) for c in (weakest, fresh, strongest)]
    assert scores[0] > scores[1] > scores[2]


def test_fullday_takes_every_card_and_sets_no_target():
    deck = candidates([("A", 18), ("B", 9)])
    paper = assemble(deck, None, now=now())
    assert len(paper.cards) == len(deck)
    assert paper.total_marks == sum(c.marks for c in deck)
    assert paper.short is False


def test_paper_is_ordered_by_topic_then_by_marks():
    paper = assemble(candidates([("A", 18), ("B", 9), ("C", 3)]), 30, now=now())
    keys = [(c.topic_code, c.marks) for c in paper.cards]
    assert keys == sorted(keys)


# --- creating a paper ------------------------------------------------------

def test_class30_paper_is_exactly_thirty_marks_and_timed(client):
    body = client.post("/api/tests", json={"kind": "class30"}).json()
    assert body["total_marks"] == 30
    assert sum(q["marks"] for q in body["questions"]) == 30
    assert body["time_limit_s"] == 45 * 60
    assert body["short"] is False
    assert body["kind"] == "class30"


def test_created_questions_carry_the_contract_shape(client):
    q = client.post("/api/tests", json={"kind": "class30"}).json()["questions"][0]
    assert set(q) == {"ordinal", "card_id", "kind", "question", "answer",
                      "cloze_text", "marks", "topic_code", "page_ref", "verdict",
                      # A paper you cannot learn from is a paper you sat, not
                      # one you studied: the working travels with the answer,
                      # and so does whether the card had a source at all.
                      "detail", "origin"}
    assert q["ordinal"] == 1
    assert q["verdict"] is None
    assert q["page_ref"]


def test_ordinals_are_contiguous_from_one(client):
    body = client.post("/api/tests", json={"kind": "class30"}).json()
    assert [q["ordinal"] for q in body["questions"]] == \
        list(range(1, len(body["questions"]) + 1))


def test_a_paper_spans_topics(client):
    body = client.post("/api/tests", json={"kind": "class30"}).json()
    assert len({q["topic_code"] for q in body["questions"]}) == 3


def test_a_paper_never_asks_the_same_card_twice(client):
    body = client.post("/api/tests", json={"kind": "class30"}).json()
    ids = [q["card_id"] for q in body["questions"]]
    assert len(ids) == len(set(ids))


def test_only_active_cards_are_examinable(client):
    body = client.post("/api/tests", json={"kind": "fullday"}).json()
    asked = {q["question"] for q in body["questions"]}
    assert "pending?" not in asked
    assert "rejected?" not in asked
    assert len(body["questions"]) == 30


def test_fullday_is_every_active_card_with_no_time_limit(client):
    body = client.post("/api/tests", json={"kind": "fullday"}).json()
    assert body["time_limit_s"] is None
    assert len(body["questions"]) == 30
    # 18 + 9 + 3 cards cycling 1,1,2,5 marks
    assert body["total_marks"] == body["target_marks"] == 61
    assert body["short"] is False


def test_topic_filter_keeps_the_paper_inside_one_subject(client):
    body = client.post("/api/tests",
                       json={"kind": "fullday", "topic_code": "MATHS"}).json()
    assert {q["topic_code"] for q in body["questions"]} == {"MATHS"}
    assert body["topic_code"] == "MATHS"


def test_a_thin_deck_produces_a_short_paper_that_says_so(tmp_path):
    path = str(tmp_path / "thin.db")
    seed(path, [("CSE111", 3)])  # 1 + 1 + 2 = 4 marks
    body = make_client(path).post("/api/tests", json={"kind": "class30"}).json()
    assert body["total_marks"] == 4
    assert body["short"] is True
    assert "4 of 30" in body["note"]
    assert len(body["questions"]) == 3


def test_unknown_kind_is_rejected(client):
    r = client.post("/api/tests", json={"kind": "surprise"})
    assert r.status_code == 422
    assert "kind" in r.json()["detail"]


def test_unknown_topic_is_a_404(client):
    assert client.post("/api/tests",
                       json={"kind": "class30", "topic_code": "NOPE"}
                       ).status_code == 404


# --- answering and resuming ------------------------------------------------

def create(client, kind="class30", **extra) -> dict:
    return client.post("/api/tests", json={"kind": kind, **extra}).json()


def test_recorded_answers_come_back_on_reload(client):
    paper = create(client)
    tid = paper["test_id"]
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": 1, "verdict": "correct", "seconds": 12})
    body = client.get(f"/api/tests/{tid}").json()
    assert body["questions"][0]["verdict"] == "correct"
    assert body["questions"][1]["verdict"] is None
    assert body["total_marks"] == paper["total_marks"]


def test_a_fullday_test_resumes_across_sittings(client, db_path):
    """Put the paper down, come back tomorrow, keep your verdicts."""
    paper = create(client, "fullday")
    tid = paper["test_id"]
    for ordinal, verdict in ((1, "correct"), (2, "wrong"), (3, "skipped")):
        client.post(f"/api/tests/{tid}/answer",
                    json={"ordinal": ordinal, "verdict": verdict, "seconds": 5})

    later = make_client(db_path)  # a fresh process, a fresh connection
    body = later.get(f"/api/tests/{tid}").json()
    assert [q["verdict"] for q in body["questions"][:4]] == \
        ["correct", "wrong", "skipped", None]
    assert body["submitted_at"] is None

    later.post(f"/api/tests/{tid}/answer",
               json={"ordinal": 4, "verdict": "correct", "seconds": 5})
    assert client.get(f"/api/tests/{tid}").json()["questions"][3]["verdict"] \
        == "correct"


def test_an_answer_can_be_changed_before_submitting(client):
    tid = create(client)["test_id"]
    client.post(f"/api/tests/{tid}/answer", json={"ordinal": 1, "verdict": "wrong",
                                                  "seconds": 3})
    client.post(f"/api/tests/{tid}/answer", json={"ordinal": 1,
                                                  "verdict": "correct", "seconds": 4})
    assert client.get(f"/api/tests/{tid}").json()["questions"][0]["verdict"] \
        == "correct"


def test_partial_is_refused_on_a_one_mark_question(client):
    paper = create(client)
    tid = paper["test_id"]
    one = next(q for q in paper["questions"] if q["marks"] == 1)
    r = client.post(f"/api/tests/{tid}/answer",
                    json={"ordinal": one["ordinal"], "verdict": "partial",
                          "seconds": 5})
    assert r.status_code == 422
    assert "partial" in r.json()["detail"]
    assert client.get(f"/api/tests/{tid}").json()["questions"][
        one["ordinal"] - 1]["verdict"] is None


def test_partial_is_allowed_on_a_two_mark_question(client):
    paper = create(client)
    tid = paper["test_id"]
    two = next(q for q in paper["questions"] if q["marks"] >= 2)
    assert client.post(f"/api/tests/{tid}/answer",
                       json={"ordinal": two["ordinal"], "verdict": "partial",
                             "seconds": 5}).status_code == 200


def test_unknown_verdict_is_rejected(client):
    tid = create(client)["test_id"]
    assert client.post(f"/api/tests/{tid}/answer",
                       json={"ordinal": 1, "verdict": "sort of", "seconds": 1}
                       ).status_code == 422


def test_answering_a_question_that_is_not_on_the_paper_is_a_404(client):
    tid = create(client)["test_id"]
    assert client.post(f"/api/tests/{tid}/answer",
                       json={"ordinal": 9999, "verdict": "correct", "seconds": 1}
                       ).status_code == 404


def test_unknown_test_is_a_404(client):
    assert client.get("/api/tests/4242").status_code == 404
    assert client.post("/api/tests/4242/submit").status_code == 404
    assert client.post("/api/tests/4242/answer",
                       json={"ordinal": 1, "verdict": "correct", "seconds": 1}
                       ).status_code == 404


# --- submitting ------------------------------------------------------------

def reviews(db_path: str) -> list[tuple[int, int]]:
    conn = connect(db_path)
    rows = conn.execute("SELECT card_id, grade FROM reviews ORDER BY id").fetchall()
    conn.close()
    return [(r["card_id"], r["grade"]) for r in rows]


def test_submitting_scores_the_paper(client):
    paper = create(client)
    tid = paper["test_id"]
    qs = paper["questions"]
    two = next(q for q in qs if q["marks"] >= 2)
    ones = [q for q in qs if q["marks"] == 1][:3]

    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": ones[0]["ordinal"], "verdict": "correct",
                      "seconds": 10})
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": ones[1]["ordinal"], "verdict": "wrong",
                      "seconds": 20})
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": ones[2]["ordinal"], "verdict": "skipped",
                      "seconds": 1})
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": two["ordinal"], "verdict": "partial",
                      "seconds": 30})

    result = client.post(f"/api/tests/{tid}/submit").json()
    expected = 1 + two["marks"] / 2  # correct 1-mark + half of the partial
    assert result["obtained_marks"] == expected
    assert result["total_marks"] == 30
    assert result["percent"] == round(100 * expected / 30, 1)
    assert result["duration_s"] == 61
    assert [q["ordinal"] for q in result["wrong"]] == [ones[1]["ordinal"]]
    assert [q["ordinal"] for q in result["partial"]] == [two["ordinal"]]


def test_partial_scores_exactly_half(client):
    paper = create(client)
    tid = paper["test_id"]
    five = next(q for q in paper["questions"] if q["marks"] == 5)
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": five["ordinal"], "verdict": "partial",
                      "seconds": 60})
    assert client.post(f"/api/tests/{tid}/submit").json()["obtained_marks"] == 2.5


def test_by_topic_breaks_the_score_down_and_adds_up(client):
    paper = create(client)
    tid = paper["test_id"]
    for q in paper["questions"]:
        client.post(f"/api/tests/{tid}/answer",
                    json={"ordinal": q["ordinal"], "verdict": "correct",
                          "seconds": 1})
    result = client.post(f"/api/tests/{tid}/submit").json()
    assert result["obtained_marks"] == 30
    assert result["percent"] == 100.0
    assert sum(t["total"] for t in result["by_topic"]) == 30
    assert sum(t["obtained"] for t in result["by_topic"]) == 30
    assert len(result["by_topic"]) == 3


def test_submitting_records_a_review_per_answered_question(client, db_path):
    paper = create(client)
    tid = paper["test_id"]
    qs = paper["questions"]
    two = next(q for q in qs if q["marks"] >= 2)
    ones = [q for q in qs if q["marks"] == 1][:2]
    plan = {ones[0]["ordinal"]: ("correct", 3), ones[1]["ordinal"]: ("wrong", 1),
            two["ordinal"]: ("partial", 2)}
    for ordinal, (verdict, _) in plan.items():
        client.post(f"/api/tests/{tid}/answer",
                    json={"ordinal": ordinal, "verdict": verdict, "seconds": 5})

    assert reviews(db_path) == []
    client.post(f"/api/tests/{tid}/submit")

    by_ordinal = {q["ordinal"]: q["card_id"] for q in qs}
    expected = sorted((by_ordinal[o], grade) for o, (_, grade) in plan.items())
    assert sorted(reviews(db_path)) == expected


def test_submitting_moves_card_state_through_the_real_scheduler(client, db_path):
    paper = create(client)
    tid = paper["test_id"]
    q = paper["questions"][0]
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": q["ordinal"], "verdict": "correct", "seconds": 5})
    client.post(f"/api/tests/{tid}/submit")

    conn = connect(db_path)
    row = conn.execute("SELECT * FROM card_state WHERE card_id = ?",
                       (q["card_id"],)).fetchone()
    conn.close()
    assert row is not None
    assert row["stability"] > 0
    assert 1.0 <= row["difficulty"] <= 10.0
    assert row["due_at"] > datetime.now(timezone.utc).isoformat()
    assert row["reps"] == 1


def test_a_wrong_answer_comes_back_sooner_than_a_correct_one(client, db_path):
    paper = create(client)
    tid = paper["test_id"]
    good, bad = paper["questions"][0], paper["questions"][1]
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": good["ordinal"], "verdict": "correct", "seconds": 1})
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": bad["ordinal"], "verdict": "wrong", "seconds": 1})
    client.post(f"/api/tests/{tid}/submit")

    conn = connect(db_path)
    due = {r["card_id"]: r["due_at"] for r in
           conn.execute("SELECT card_id, due_at FROM card_state").fetchall()}
    conn.close()
    assert due[bad["card_id"]] < due[good["card_id"]]


def test_skipped_and_unanswered_questions_record_nothing(client, db_path):
    paper = create(client)
    tid = paper["test_id"]
    skipped = paper["questions"][0]
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": skipped["ordinal"], "verdict": "skipped",
                      "seconds": 3})
    client.post(f"/api/tests/{tid}/submit")

    assert reviews(db_path) == [], "not attempting is not evidence about memory"
    conn = connect(db_path)
    n = conn.execute("SELECT COUNT(*) AS n FROM card_state").fetchone()["n"]
    conn.close()
    assert n == 0


def test_grade_four_is_never_inferred(client, db_path):
    paper = create(client)
    tid = paper["test_id"]
    for q in paper["questions"]:
        client.post(f"/api/tests/{tid}/answer",
                    json={"ordinal": q["ordinal"], "verdict": "correct",
                          "seconds": 1})
    client.post(f"/api/tests/{tid}/submit")
    assert {grade for _, grade in reviews(db_path)} == {3}


def test_submitting_twice_does_not_double_count(client, db_path):
    paper = create(client)
    tid = paper["test_id"]
    q = paper["questions"][0]
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": q["ordinal"], "verdict": "correct", "seconds": 7})

    first = client.post(f"/api/tests/{tid}/submit").json()
    after_first = reviews(db_path)
    second = client.post(f"/api/tests/{tid}/submit").json()

    assert second == first
    assert reviews(db_path) == after_first
    assert len(after_first) == 1


def test_two_submits_landing_at_once_record_one_round_of_reviews(db_path):
    """A double tap on the button over a slow connection puts two submits in
    flight together. Reading submitted_at and then writing it would let both
    decide they were first and grade the paper into the scheduler twice."""
    conn = connect(db_path)
    paper = service.create_test(conn, 1, "class30")
    tid = paper["test_id"]
    answered = paper["questions"][:4]
    for q in answered:
        service.record_answer(conn, 1, tid, q["ordinal"], "correct", 5)
    conn.close()

    start = threading.Barrier(4)
    results, errors = [], []

    def submit():
        own = connect(db_path)
        try:
            start.wait()
            results.append(service.submit_test(own, 1, tid))
        except Exception as exc:  # reported, not swallowed
            errors.append(repr(exc))
        finally:
            own.close()

    threads = [threading.Thread(target=submit) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    expected = float(sum(q["marks"] for q in answered))
    assert errors == []
    assert len(results) == 4
    assert {r["obtained_marks"] for r in results} == {expected}
    assert len(reviews(db_path)) == len(answered), "one round of reviews, not four"
    conn = connect(db_path)
    reps = [r["reps"] for r in conn.execute("SELECT reps FROM card_state")]
    conn.close()
    assert reps == [1] * len(answered), "a card must not be graded twice"


def test_answering_after_submitting_is_refused(client):
    paper = create(client)
    tid = paper["test_id"]
    client.post(f"/api/tests/{tid}/submit")
    r = client.post(f"/api/tests/{tid}/answer",
                    json={"ordinal": 1, "verdict": "correct", "seconds": 1})
    assert r.status_code == 422
    assert "submitted" in r.json()["detail"]


def test_an_untouched_paper_scores_zero(client, db_path):
    tid = create(client)["test_id"]
    result = client.post(f"/api/tests/{tid}/submit").json()
    assert result["obtained_marks"] == 0
    assert result["percent"] == 0.0
    assert reviews(db_path) == []


# --- history ---------------------------------------------------------------

def test_history_is_empty_before_any_test(client):
    assert client.get("/api/tests").json() == []


def test_history_reports_each_paper(client):
    paper = create(client)
    tid = paper["test_id"]
    q = paper["questions"][0]
    client.post(f"/api/tests/{tid}/answer",
                json={"ordinal": q["ordinal"], "verdict": "correct", "seconds": 9})
    client.post(f"/api/tests/{tid}/submit")
    create(client, "fullday")

    rows = client.get("/api/tests").json()
    assert len(rows) == 2
    assert set(rows[0]) == {"id", "kind", "started_at", "submitted_at",
                            "obtained_marks", "total_marks", "duration_s",
                            "topic_code", "units"}
    sat = next(r for r in rows if r["id"] == tid)
    assert sat["obtained_marks"] == q["marks"]
    assert sat["total_marks"] == 30
    assert sat["duration_s"] == 9
    unsat = next(r for r in rows if r["id"] != tid)
    assert unsat["obtained_marks"] is None


def test_history_names_the_subject_a_restricted_paper_covers(client):
    """A class30/mte40/endterm100 paper for one topic says which; a fullday
    paper covers everything and has none to name."""
    restricted = create(client, "class30", topic_code="CSE111")
    spanning = create(client, "fullday")

    rows = {r["id"]: r for r in client.get("/api/tests").json()}
    assert rows[restricted["test_id"]]["topic_code"] == "CSE111"
    assert rows[spanning["test_id"]]["topic_code"] is None


def test_history_says_outright_whether_a_paper_was_submitted(client):
    """duration_s was the old proxy for this and it lies in one real case: a
    paper submitted with nothing answered records duration_s = 0, which the
    client read as falsy and therefore as still open — forever."""
    sat = create(client)
    client.post(f"/api/tests/{sat['test_id']}/submit")
    still_open = create(client)

    rows = {r["id"]: r for r in client.get("/api/tests").json()}
    assert rows[sat["test_id"]]["submitted_at"] is not None
    assert rows[sat["test_id"]]["duration_s"] == 0  # the proxy's blind spot
    assert rows[still_open["test_id"]]["submitted_at"] is None


def test_closing_an_open_paper_removes_it_from_history(client):
    paper = create(client)
    tid = paper["test_id"]
    assert client.delete(f"/api/tests/{tid}").status_code == 200
    assert tid not in {r["id"] for r in client.get("/api/tests").json()}
    assert client.get(f"/api/tests/{tid}").status_code == 404


def test_closing_a_submitted_paper_is_refused(client):
    paper = create(client)
    tid = paper["test_id"]
    client.post(f"/api/tests/{tid}/submit")
    r = client.delete(f"/api/tests/{tid}")
    assert r.status_code == 409
    # Refused, not silently ignored: the graded paper is still there.
    assert client.get(f"/api/tests/{tid}").status_code == 200


def test_closing_someone_elses_paper_is_a_404_not_a_409(client, db_path):
    """A test that exists but isn't yours must read the same as one that
    doesn't exist at all — telling the two apart would leak that the id is
    real."""
    conn = connect(db_path)
    conn.execute("INSERT INTO users (id, name) VALUES (2, 'someone else')")
    conn.commit()
    other = service.create_test(conn, 2, "class30")
    assert client.delete(f"/api/tests/{other['test_id']}").status_code == 404


def test_closing_a_test_that_never_existed_is_a_404(client):
    assert client.delete("/api/tests/999999").status_code == 404


def test_mte_kind_builds_a_40_mark_90_minute_paper(db_path):
    conn = connect(db_path)
    test = service.create_test(conn, 1, "mte40")
    assert test["target_marks"] == 40
    assert test["time_limit_s"] == 90 * 60
    conn.close()


def test_mte_refused_for_subjects_that_have_none_at_lpu(db_path):
    """INT108 and CSE326 carry no mid-term in the LPU scheme."""
    import json as _json

    conn = connect(db_path)
    conn.execute(
        "UPDATE topics SET meta = ? WHERE code = 'CSE111'",
        (_json.dumps({"mte_exists": False, "ca_policy": "CA + practical ETE only"}),),
    )
    conn.commit()
    with pytest.raises(ValueError) as exc:
        service.create_test(conn, 1, "mte40", topic_code="CSE111")
    assert "no MTE" in str(exc.value)
    conn.close()


def test_mte_allowed_when_meta_permits_or_is_absent(db_path):
    import json as _json

    conn = connect(db_path)
    test = service.create_test(conn, 1, "mte40", topic_code="CSE111")  # no meta yet
    assert test["kind"] == "mte40"
    conn.execute("UPDATE topics SET meta = ? WHERE code = 'MATHS'",
                 (_json.dumps({"mte_exists": True}),))
    conn.commit()
    assert service.create_test(conn, 1, "mte40", topic_code="MATHS")["kind"] == "mte40"
    conn.close()


# --- unit-scoped papers ------------------------------------------------------
#
# "We did unit 3 in class today, examine me on unit 3." A unit is knowable only
# for knowledge-mode cards, whose chunk is the topic's per-unit synthetic chunk
# and whose ordinal IS the unit index; an uploaded PDF is chunked by page and a
# page maps to no unit at all. These check that the line is drawn there and
# nowhere else.

def _knowledge_deck(db_path, topic_id=1, code="CSE111", per_unit=6, units=3):
    """Give a topic a knowledge source with `units` unit-chunks under it."""
    import json as _json

    from recall.generate.knowledge import knowledge_sha

    conn = connect(db_path)
    conn.execute(
        "UPDATE topics SET meta = ? WHERE id = ?",
        (_json.dumps({"full_name": code, "units": [f"Unit {i + 1}"
                                                   for i in range(units)],
                      "exam_format": "mixed", "mte_exists": True}), topic_id))
    conn.execute(
        "INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,added_at)"
        " VALUES (900,1,?,'AI knowledge','knowledge',?,'2026-09-01T00:00:00+00:00')",
        (topic_id, knowledge_sha(topic_id)))
    for u in range(units):
        conn.execute(
            "INSERT INTO chunks (id,source_id,ordinal,text,page_ref)"
            " VALUES (?,900,?,?,?)",
            (900 + u, u, f"Unit {u + 1}", f"Unit {u + 1} · Unit {u + 1}"))
        for i in range(per_unit):
            conn.execute(
                "INSERT INTO cards (chunk_id,topic_id,kind,question,answer,"
                "cloze_text,arm,state,origin,created_at) VALUES (?,?,'qa',?,?,"
                "NULL,'learned','active','knowledge','2026-09-01T00:00:00+00:00')",
                (900 + u, topic_id, f"unit{u + 1} q{i}?", words(3)))
    conn.commit()
    conn.close()


def _questions_of(client, test_id):
    return client.get(f"/api/tests/{test_id}").json()["questions"]


def test_a_unit_scoped_paper_only_draws_from_those_units(db_path):
    _knowledge_deck(db_path)
    conn = connect(db_path)
    paper = service.create_test(conn, 1, "class30", "CSE111", units=[2])
    asked = {q["question"] for q in paper["questions"]}
    assert asked, "unit 3 has cards; the paper must not be empty"
    assert all(q.startswith("unit3 ") for q in asked), sorted(asked)
    conn.close()


def test_choosing_two_units_draws_from_both_and_no_others(db_path):
    _knowledge_deck(db_path)
    conn = connect(db_path)
    paper = service.create_test(conn, 1, "endterm100", "CSE111", units=[0, 1])
    prefixes = {q["question"].split(" ")[0] for q in paper["questions"]}
    assert prefixes <= {"unit1", "unit2"}
    assert prefixes == {"unit1", "unit2"}
    conn.close()


def test_a_unit_paper_leaves_out_cards_whose_unit_is_unknown(db_path):
    """The topic's uploaded-PDF cards are chunked by page. A page is not a
    unit, so they cannot honestly be claimed for one."""
    _knowledge_deck(db_path)
    conn = connect(db_path)
    paper = service.create_test(conn, 1, "endterm100", "CSE111", units=[0, 1, 2])
    assert not any(q["question"].startswith("CSE111 q")
                   for q in paper["questions"])
    # ...and without a unit scope they are exactly where they always were.
    whole = service.create_test(conn, 1, "endterm100", "CSE111")
    assert any(q["question"].startswith("CSE111 q") for q in whole["questions"])
    conn.close()


def test_the_scope_survives_on_the_paper_and_in_history(db_path, client):
    _knowledge_deck(db_path)
    body = client.post("/api/tests", json={"kind": "class30",
                                           "topic_code": "CSE111",
                                           "units": [1, 2]}).json()
    assert body["units"] == [1, 2]
    assert client.get(f"/api/tests/{body['test_id']}").json()["units"] == [1, 2]
    row = next(r for r in client.get("/api/tests").json()
               if r["id"] == body["test_id"])
    assert row["units"] == [1, 2]


def test_a_whole_subject_paper_reports_no_scope(client):
    body = client.post("/api/tests", json={"kind": "class30"}).json()
    assert body["units"] is None


def test_a_unit_out_of_range_is_refused_rather_than_clamped(db_path):
    _knowledge_deck(db_path)          # three units
    conn = connect(db_path)
    with pytest.raises(ValueError) as exc:
        service.create_test(conn, 1, "class30", "CSE111", units=[0, 9])
    assert "no unit 10" in str(exc.value)
    conn.close()


def test_units_are_deduplicated_and_sorted(db_path):
    _knowledge_deck(db_path)
    conn = connect(db_path)
    paper = service.create_test(conn, 1, "class30", "CSE111", units=[2, 0, 2])
    assert paper["units"] == [0, 2]
    conn.close()


def test_choosing_units_without_a_subject_is_refused(db_path):
    conn = connect(db_path)
    with pytest.raises(ValueError) as exc:
        service.create_test(conn, 1, "class30", None, units=[0])
    assert "needs a subject" in str(exc.value)
    conn.close()


def test_a_subject_with_no_syllabus_cannot_be_scoped_to_a_unit(db_path):
    """PHY in the fixture carries no meta at all."""
    conn = connect(db_path)
    with pytest.raises(ValueError) as exc:
        service.create_test(conn, 1, "class30", "PHY", units=[0])
    assert "no syllabus units" in str(exc.value)
    conn.close()


def test_an_empty_unit_list_is_refused(db_path):
    _knowledge_deck(db_path)
    conn = connect(db_path)
    with pytest.raises(ValueError) as exc:
        service.create_test(conn, 1, "class30", "CSE111", units=[])
    assert "at least one unit" in str(exc.value)
    conn.close()


def test_a_unit_paper_never_reaches_another_account(db_path):
    """cards and chunks carry no owner; the only thing keeping a unit query
    inside one account is the join back to topics."""
    import json as _json

    from recall.generate.knowledge import knowledge_sha

    _knowledge_deck(db_path)
    conn = connect(db_path)
    conn.execute("INSERT INTO users (id, name) VALUES (2, 'someone else')")
    conn.execute("INSERT INTO topics (id,user_id,code,label,meta)"
                 " VALUES (77,2,'CSE111',?,?)",
                 ("theirs", _json.dumps({"units": ["Unit 1", "Unit 2", "Unit 3"]})))
    conn.execute(
        "INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,added_at)"
        " VALUES (950,2,77,'AI knowledge','knowledge',?,'2026-09-01T00:00:00+00:00')",
        (knowledge_sha(77),))
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref)"
                 " VALUES (950,950,0,'theirs','Unit 1')")
    conn.execute(
        "INSERT INTO cards (chunk_id,topic_id,kind,question,answer,cloze_text,"
        "arm,state,origin,created_at) VALUES (950,77,'qa','THEIR SECRET?',?,"
        "NULL,'learned','active','knowledge','2026-09-01T00:00:00+00:00')",
        (words(3),))
    conn.commit()

    paper = service.create_test(conn, 1, "endterm100", "CSE111", units=[0])
    assert not any("SECRET" in q["question"] for q in paper["questions"])
    conn.close()
