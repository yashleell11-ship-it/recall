"""What to study next, per subject.

The dashboard could say "41 due". It could not say what to do. These pin the
ladder that turns the first into the second, and — more importantly — the two
ways it can lie: by reasoning per unit on a subject whose cards belong to no
unit, and by reaching cards that are not yours.
"""

import json

import pytest

from recall.api.app import create_app, get_conn
from recall.api.deps import get_current_user
from recall.db import connect, init_db
from recall.generate.knowledge import knowledge_sha
from recall.study.plan import study_plan, unit_health
from fastapi.testclient import TestClient

UNITS = ["Matrix Methods", "Differential Calculus", "Integral Calculus"]


def _db(tmp_path, name="plan.db"):
    path = str(tmp_path / name)
    conn = connect(path)
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.execute("INSERT INTO settings (user_id) VALUES (1)")
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label,meta) VALUES (1,1,'MTH165',?,?)",
        ("Mathematics for Engineers",
         json.dumps({"full_name": "Mathematics for Engineers", "units": UNITS,
                     "exam_format": "mixed", "mte_exists": True})))
    conn.commit()
    return path, conn


def _knowledge_cards(conn, per_unit: dict[int, int], user_id=1, topic_id=1):
    """Active knowledge cards under the topic's synthetic per-unit chunks —
    the only cards whose unit is knowable."""
    conn.execute(
        "INSERT OR IGNORE INTO sources (id,user_id,topic_id,filename,kind,"
        "sha256,added_at) VALUES (9,?,?,'AI knowledge','knowledge',?,'2026-01-01')",
        (user_id, topic_id, knowledge_sha(topic_id)))
    cid = 1000
    for index, count in per_unit.items():
        conn.execute(
            "INSERT OR IGNORE INTO chunks (id,source_id,ordinal,text,page_ref)"
            " VALUES (?,9,?,?,?)",
            (100 + index, index, UNITS[index], f"Unit {index + 1}"))
        for _ in range(count):
            cid += 1
            conn.execute(
                "INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,"
                "arm,state,created_at,origin) VALUES (?,?,?,'qa',?,?,"
                "'learned','active','2026-01-01','knowledge')",
                (cid, 100 + index, topic_id, f"q{cid}?", "a short answer"))
    conn.commit()


def _reviewed(conn, *, hard: set[int] = frozenset(), user_id=1):
    """Give every card a card_state row; the `hard` ones look badly learned."""
    for (cid, chunk) in conn.execute(
            "SELECT id, chunk_id FROM cards WHERE state = 'active'").fetchall():
        weak = chunk in hard
        conn.execute(
            "INSERT INTO card_state (card_id,user_id,stability,difficulty,"
            "due_at,reps,lapses) VALUES (?,?,?,?,?,1,0)",
            (cid, user_id, 0.4 if weak else 400.0, 9.5 if weak else 1.5,
             "2099-01-01T00:00:00+00:00"))
    conn.commit()


# --- the ladder --------------------------------------------------------------

def test_a_subject_with_nothing_in_it_says_to_write_something(tmp_path):
    _, conn = _db(tmp_path)
    plan = study_plan(conn, 1)[0]
    assert plan["action"] == {"kind": "generate", "unit": 1}
    conn.close()


def test_due_cards_outrank_everything_else(tmp_path):
    _, conn = _db(tmp_path)
    _knowledge_cards(conn, {0: 5})
    conn.execute("INSERT INTO card_state (card_id,user_id,stability,difficulty,"
                 "due_at,reps,lapses) SELECT id,1,1.0,5.0,"
                 "'2000-01-01T00:00:00+00:00',1,0"
                 " FROM cards")
    conn.commit()
    plan = study_plan(conn, 1)[0]
    assert plan["action"]["kind"] == "review"
    assert "due" in plan["advice"]
    conn.close()


def test_cards_you_have_never_met_outrank_writing_new_ones(tmp_path):
    """The bug this ordering exists to prevent: on a deck of unmet cards the
    plan used to tell you to generate more, because no unit looked full."""
    _, conn = _db(tmp_path)
    _knowledge_cards(conn, {0: 5})          # unit 2 and 3 are empty
    plan = study_plan(conn, 1)[0]
    assert plan["action"]["kind"] == "review"
    assert "never seen" in plan["advice"]
    conn.close()


def test_an_empty_unit_is_named_once_the_deck_is_met(tmp_path):
    _, conn = _db(tmp_path)
    _knowledge_cards(conn, {0: 5})
    _reviewed(conn)
    plan = study_plan(conn, 1)[0]
    assert plan["action"] == {"kind": "generate", "unit": 2}
    conn.close()


def test_the_weakest_unit_is_the_one_to_sit_a_test_on(tmp_path):
    _, conn = _db(tmp_path)
    _knowledge_cards(conn, {0: 6, 1: 6, 2: 6})
    _reviewed(conn, hard={101})             # unit 2's chunk
    plan = study_plan(conn, 1)[0]
    assert plan["weakest_unit"] == 2
    assert plan["action"] == {"kind": "sit", "unit": 2}
    conn.close()


def test_a_weak_unit_too_thin_to_examine_asks_for_more_questions(tmp_path):
    """Sitting a paper on two cards is not a paper."""
    _, conn = _db(tmp_path)
    _knowledge_cards(conn, {0: 6, 1: 2, 2: 6})
    _reviewed(conn, hard={101})
    plan = study_plan(conn, 1)[0]
    assert plan["action"] == {"kind": "generate", "unit": 2}
    conn.close()


def test_a_deck_that_is_all_solid_says_so(tmp_path):
    _, conn = _db(tmp_path)
    _knowledge_cards(conn, {0: 6, 1: 6, 2: 6})
    _reviewed(conn)
    plan = study_plan(conn, 1)[0]
    assert plan["action"]["kind"] == "clear"
    conn.close()


# --- honesty -----------------------------------------------------------------

def test_upload_cards_are_counted_for_the_subject_but_never_for_a_unit(tmp_path):
    """A page maps to no syllabus unit. Claiming one would be a guess wearing a
    fact's clothing, so the per-unit view reports its own coverage instead."""
    _, conn = _db(tmp_path)
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'notes.pdf','pdf','deadbeef','2026-01-01')")
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref)"
                 " VALUES (1,1,0,'body text from page 4','p4')")
    for i in range(8):
        conn.execute(
            "INSERT INTO cards (chunk_id,topic_id,kind,question,answer,arm,state,"
            "created_at,origin) VALUES (1,1,'qa',?,?, 'learned','active',"
            "'2026-01-01','upload')", (f"u{i}?", "a short answer"))
    conn.commit()
    _reviewed(conn)

    plan = study_plan(conn, 1)[0]
    assert plan["active"] == 8
    assert plan["units_cover"] == 0, "an upload card must not claim a unit"
    assert plan["action"]["kind"] == "clear"
    assert "no unit-level view" in plan["advice"], (
        "it must say the unit view is blind here, not call every unit empty")
    conn.close()


def test_another_accounts_cards_never_reach_your_plan(tmp_path):
    """cards and chunks carry no owner. Every read here has to arrive through
    topics.user_id or sources.user_id, or it is a leak."""
    path, conn = _db(tmp_path)
    _knowledge_cards(conn, {0: 6, 1: 6, 2: 6})
    _reviewed(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (2, 'someone else')")
    conn.execute("INSERT INTO settings (user_id) VALUES (2)")
    conn.commit()

    assert study_plan(conn, 2) == [], "another account has no subjects here"
    assert unit_health(conn, 2, 1, UNITS) == unit_health(conn, 2, 1, UNITS)
    assert all(u.active == 0 for u in unit_health(conn, 2, 1, UNITS)), (
        "user 2 can see user 1's per-unit deck"
    )
    conn.close()


def test_a_subject_with_no_syllabus_units_does_not_crash(tmp_path):
    """Topics created before the LPU registry carry no meta at all."""
    _, conn = _db(tmp_path)
    conn.execute("UPDATE topics SET meta = NULL WHERE id = 1")
    conn.commit()
    plan = study_plan(conn, 1)[0]
    assert plan["units"] == []
    assert plan["weakest_unit"] is None
    conn.close()


# --- the endpoint ------------------------------------------------------------

def test_the_endpoint_returns_one_entry_per_subject(tmp_path):
    path, conn = _db(tmp_path)
    _knowledge_cards(conn, {0: 6})
    conn.close()

    app = create_app()

    def override():
        c = connect(path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = override
    app.dependency_overrides[get_current_user] = lambda: 1
    client = TestClient(app)

    r = client.get("/api/study-plan")
    assert r.status_code == 200
    body = r.json()
    assert [t["topic_code"] for t in body] == ["MTH165"]
    assert body[0]["advice"]
    assert len(body[0]["units"]) == 3


def test_the_endpoint_needs_a_session(tmp_path):
    path, _ = _db(tmp_path)
    app = create_app()

    def override():
        c = connect(path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = override
    assert TestClient(app).get("/api/study-plan").status_code == 401
