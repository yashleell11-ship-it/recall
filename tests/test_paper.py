"""Sitting a full paper on a subject the deck cannot cover.

The bug this exists to kill: the owner pressed "Start class test" on a subject
he had uploaded nothing for and got "This paper has no questions." Assembly
was working correctly — there was simply nothing to assemble. This builds what
is missing first.
"""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from recall.api import upload_routes
from recall.api.app import create_app, get_conn
from recall.api.deps import get_current_user
from recall.config import Config
from recall.db import connect, init_db
from recall.llm.fake import FakeLlmClient
from recall.testmode.paper import cards_needed_per_unit, units_for

CFG = Config(
    api_key="test", base_url="http://localhost", model="deepseek-chat",
    db_path=":memory:", max_cost_usd_per_source=2.0,
    price_input_per_mtok=0.27, price_output_per_mtok=1.10,
)

UNITS = ["Linear Algebra", "Differential Calculus", "Integral Calculus",
         "Multivariate Functions", "Multivariate Integrals", "Fourier Series"]


def spread_embed(texts):
    """Every text its own direction, so nothing is ever deduped away."""
    n = max(len(texts), 1)
    return np.eye(n)[: len(texts)]


def cards_body(unit_hint: str, n: int) -> str:
    """n distinct, gate-passing cards. Answers are 5 words -> 2 marks each."""
    return json.dumps({"cards": [
        {"kind": "qa",
         "question": f"{unit_hint} question number {i} about the method?",
         "answer": f"answer {i} with a few words",
         "detail": f"Worked explanation for {unit_hint} item {i}."}
        for i in range(n)
    ]})


def unit_calls(unit_hint: str, n: int) -> list[str]:
    """One unit's worth of responses: generate, then the batch fact check."""
    return [cards_body(unit_hint, n),
            json.dumps({"verdicts": [{"i": i, "status": "ok"} for i in range(n)]})]


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "paper.db")
    conn = connect(path)
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.execute("INSERT INTO settings (user_id) VALUES (1)")
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label,meta) VALUES (1,1,'MTH165',?,?)",
        ("Mathematics for Engineers",
         json.dumps({"full_name": "Mathematics for Engineers", "units": UNITS,
                     "exam_format": "mixed", "mte_exists": True})))
    # A subject the university sets no mid-term for.
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label,meta) VALUES (2,1,'INT108',?,?)",
        ("Python Programming",
         json.dumps({"full_name": "Python Programming", "units": UNITS[:6],
                     "exam_format": "practical", "mte_exists": False,
                     "ca_policy": "CA + ETE only"})))
    conn.commit()
    conn.close()
    return path


def make_client(db_path, llm):
    app = create_app()

    def override():
        c = connect(db_path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = override
    app.dependency_overrides[get_current_user] = lambda: 1
    app.dependency_overrides[upload_routes.get_config] = lambda: CFG
    app.dependency_overrides[upload_routes.get_llm_client] = lambda: llm
    app.dependency_overrides[upload_routes.get_embed] = lambda: spread_embed
    return TestClient(app)


# --- the plan ---------------------------------------------------------------

def test_the_mid_term_covers_only_the_first_three_units():
    """LPU rule, not a heuristic: the MTE is units 1-3."""
    assert units_for("mte40", 6) == [0, 1, 2]


def test_the_end_term_covers_everything():
    assert units_for("endterm100", 6) == list(range(6))


def test_a_class_test_covers_the_first_two_units():
    assert units_for("class30", 6) == [0, 1]


def test_the_plan_never_runs_past_a_short_syllabus():
    assert units_for("mte40", 2) == [0, 1]
    assert units_for("endterm100", 0) == []


def test_a_bigger_paper_needs_more_cards_per_unit():
    assert (cards_needed_per_unit("endterm100", 6)
            > cards_needed_per_unit("class30", 6))


# --- sitting one ------------------------------------------------------------

def test_a_paper_on_an_empty_deck_comes_back_with_questions(db_path):
    """The whole point. This request used to return an empty paper."""
    llm = FakeLlmClient([r for i in range(3) for r in unit_calls(f"unit{i}", 14)])
    client = make_client(db_path, llm)

    r = client.post("/api/topics/MTH165/paper", json={"kind": "mte40"})
    assert r.status_code == 200, r.text
    paper = r.json()
    assert paper["questions"], "a generated paper must not be empty"
    assert paper["total_marks"] > 0
    assert paper["generated"]["cards"] > 0
    # Units 1-3 and no others.
    assert paper["generated"]["units"] == [1, 2, 3]


def test_the_generated_questions_are_real_cards_in_the_deck(db_path):
    """Not a throwaway document: they enter the deck, so answering them
    records real reviews and moves the scheduler."""
    llm = FakeLlmClient([r for i in range(3) for r in unit_calls(f"unit{i}", 14)])
    client = make_client(db_path, llm)
    paper = client.post("/api/topics/MTH165/paper", json={"kind": "mte40"}).json()

    conn = connect(db_path)
    card_ids = [q["card_id"] for q in paper["questions"]]
    placeholders = ",".join("?" for _ in card_ids)
    rows = conn.execute(
        f"SELECT state, origin FROM cards WHERE id IN ({placeholders})", card_ids
    ).fetchall()
    conn.close()
    assert rows, "every question must be backed by a card row"
    assert {r["state"] for r in rows} == {"active"}
    assert {r["origin"] for r in rows} == {"knowledge"}


def test_sitting_the_same_paper_again_does_not_pay_twice(db_path):
    """Only the shortfall is generated, so a covered unit costs nothing."""
    llm = FakeLlmClient([r for i in range(3) for r in unit_calls(f"unit{i}", 14)])
    client = make_client(db_path, llm)
    first = client.post("/api/topics/MTH165/paper", json={"kind": "mte40"}).json()
    assert first["generated"]["cards"] > 0
    assert first["generated"]["deck_already_covered_it"] is False

    # The fake client has no responses left: if this tried to generate again
    # it would raise, so passing proves nothing was generated.
    second = client.post("/api/topics/MTH165/paper", json={"kind": "mte40"}).json()
    assert second["generated"]["cards"] == 0
    assert second["generated"]["deck_already_covered_it"] is True
    assert second["questions"], "the second paper still has to be a real paper"


def test_a_subject_with_no_mid_term_is_refused_before_spending(db_path):
    """INT108 has no MTE at LPU. Refuse first, so no money is spent finding
    out — the old path only discovered this after generating."""
    llm = FakeLlmClient([])   # any generation call raises
    client = make_client(db_path, llm)
    r = client.post("/api/topics/INT108/paper", json={"kind": "mte40"})
    assert r.status_code == 422
    assert "no MTE at LPU" in r.json()["detail"]
    assert llm.calls == []


def test_an_unknown_kind_is_refused(db_path):
    client = make_client(db_path, FakeLlmClient([]))
    r = client.post("/api/topics/MTH165/paper", json={"kind": "viva"})
    assert r.status_code == 422


def test_a_topic_that_is_not_yours_is_a_404(db_path):
    client = make_client(db_path, FakeLlmClient([]))
    assert client.post("/api/topics/NOPE/paper",
                       json={"kind": "class30"}).status_code == 404


def test_the_daily_cap_stops_a_paper_before_any_paid_call(db_path, monkeypatch):
    monkeypatch.setenv("RECALL_MAX_COST_USD_PER_USER_PER_DAY", "0.01")
    conn = connect(db_path)
    conn.execute("INSERT INTO usage_daily (user_id, day, cost_usd)"
                 " VALUES (1, strftime('%Y-%m-%d','now'), 5.0)")
    conn.commit()
    conn.close()
    llm = FakeLlmClient([])
    client = make_client(db_path, llm)
    r = client.post("/api/topics/MTH165/paper", json={"kind": "mte40"})
    assert r.status_code == 429
    assert llm.calls == []
