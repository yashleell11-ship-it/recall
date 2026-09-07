"""The HTTP surface for knowledge mode, and the per-user daily spend cap that
open registration needs (a single-run cap does not bound how many runs one
account starts)."""

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

CFG = Config(
    api_key="test", base_url="http://localhost", model="deepseek-chat",
    db_path=":memory:", max_cost_usd_per_source=2.0,
    price_input_per_mtok=0.27, price_output_per_mtok=1.10,
)

UNITS = ["Linear Algebra", "Fourier Series"]


def flat_embed(texts):
    return np.array([[float(i + 1), 0.0] for i, _ in enumerate(texts)])


def body(*questions):
    return json.dumps({"cards": [
        {"kind": "qa", "question": q, "answer": "A real answer of some substance"}
        for q in questions]})


def gen(*questions):
    """Knowledge mode makes two calls per unit: generate, then fact-check."""
    return [body(*questions),
            json.dumps({"verdicts": [{"i": i, "status": "ok"}
                                     for i in range(len(questions))]})]


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "kapi.db")
    conn = connect(path)
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.execute("INSERT INTO settings (user_id) VALUES (1)")
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label,meta) VALUES (1,1,'MTH165',?,?)",
        ("Mathematics for Engineers",
         json.dumps({"full_name": "Mathematics for Engineers", "units": UNITS,
                     "exam_format": "mixed"})))
    # A topic with no LPU metadata at all — older databases have these.
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label) VALUES (2,1,'BARE','Bare')")
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
    app.dependency_overrides[upload_routes.get_embed] = lambda: flat_embed
    return TestClient(app)


def test_generating_a_unit_returns_the_same_shape_as_upload_generation(db_path):
    client = make_client(db_path, FakeLlmClient(gen("What is the rank of a matrix?")))
    r = client.post("/api/topics/MTH165/generate", json={"unit": 1})
    assert r.status_code == 200
    assert r.json() == {"accepted": 1, "rejected": 0,
                        "cost_usd": pytest.approx(r.json()["cost_usd"]),
                        "stopped_early": False}


def test_a_topic_that_is_not_yours_is_a_404(db_path):
    client = make_client(db_path, FakeLlmClient(gen("q?")))
    assert client.post("/api/topics/NOPE/generate",
                       json={"unit": 1}).status_code == 404


def test_a_topic_with_no_syllabus_units_is_refused_clearly(db_path):
    client = make_client(db_path, FakeLlmClient(gen("q?")))
    r = client.post("/api/topics/BARE/generate", json={"unit": 1})
    assert r.status_code == 422
    assert "no syllabus units" in r.json()["detail"]


def test_a_unit_past_the_end_of_the_syllabus_is_refused(db_path):
    client = make_client(db_path, FakeLlmClient(gen("q?")))
    r = client.post("/api/topics/MTH165/generate", json={"unit": 9})
    assert r.status_code == 422
    assert "has 2 units" in r.json()["detail"]


def test_count_is_bounded_by_the_schema(db_path):
    client = make_client(db_path, FakeLlmClient(gen("q?")))
    assert client.post("/api/topics/MTH165/generate",
                       json={"unit": 1, "count": 500}).status_code == 422


def test_spend_is_recorded_against_the_user_and_the_day(db_path):
    client = make_client(db_path, FakeLlmClient(gen("What is the rank of a matrix?")))
    client.post("/api/topics/MTH165/generate", json={"unit": 1})
    conn = connect(db_path)
    row = conn.execute("SELECT user_id, cost_usd FROM usage_daily").fetchone()
    conn.close()
    assert row["user_id"] == 1
    assert row["cost_usd"] > 0


def test_a_user_over_their_daily_cap_is_refused_before_any_paid_call(db_path,
                                                                    monkeypatch):
    """The cap has to bite BEFORE the completion, or it is not a cap."""
    monkeypatch.setenv("RECALL_MAX_COST_USD_PER_USER_PER_DAY", "0.01")
    conn = connect(db_path)
    conn.execute("INSERT INTO usage_daily (user_id, day, cost_usd)"
                 " VALUES (1, strftime('%Y-%m-%d','now'), 5.0)")
    conn.commit()
    conn.close()

    llm = FakeLlmClient(gen("What is the rank of a matrix?"))
    client = make_client(db_path, llm)
    r = client.post("/api/topics/MTH165/generate", json={"unit": 1})
    assert r.status_code == 429
    assert "Daily generation limit" in r.json()["detail"]
    assert llm.calls == [], "the model must not have been called at all"


def test_the_cap_also_covers_upload_generation(db_path, monkeypatch):
    """Both spending routes go through one check, not two half-checks."""
    monkeypatch.setenv("RECALL_MAX_COST_USD_PER_USER_PER_DAY", "0.01")
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,added_at)"
        " VALUES (4,1,1,'n.pdf','pdf','sha4','2026-09-01')")
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref)"
                 " VALUES (4,4,0,'passage','p1')")
    conn.execute("INSERT INTO usage_daily (user_id, day, cost_usd)"
                 " VALUES (1, strftime('%Y-%m-%d','now'), 5.0)")
    conn.commit()
    conn.close()

    llm = FakeLlmClient(gen("q?"))
    client = make_client(db_path, llm)
    r = client.post("/api/sources/4/generate")
    assert r.status_code == 429
    assert llm.calls == []


class DeadLlmClient:
    """A client whose upstream refuses. The one thing every paid route has to
    survive, because a rejected key or an exhausted balance is not a bug in
    this app and must not be reported as one."""

    def __init__(self, status: int):
        self._status = status

    def complete_json(self, system, user):
        from recall.llm.client import _unavailable

        raise _unavailable(self._status)


@pytest.mark.parametrize("status,phrase", [
    (401, "key is missing or was rejected"),
    (402, "out of credit"),
    (None, "not responding"),
])
def test_an_upstream_refusal_is_a_502_that_says_why(db_path, status, phrase):
    """Not a 500. An unhandled 500 escapes outside CORSMiddleware, so the
    browser reports a CORS failure and the client says "could not reach the
    API" — the one thing that certainly did happen is that it reached the
    API."""
    client = make_client(db_path, DeadLlmClient(status))
    r = client.post("/api/topics/MTH165/generate", json={"unit": 1})
    assert r.status_code == 502
    assert phrase in r.json()["detail"]


def test_the_paper_route_fails_the_same_way(db_path):
    client = make_client(db_path, DeadLlmClient(401))
    r = client.post("/api/topics/MTH165/paper", json={"kind": "class30"})
    assert r.status_code == 502
    assert "Cards could not be written" in r.json()["detail"]


def test_the_refusal_never_carries_the_api_key(db_path):
    client = make_client(db_path, DeadLlmClient(401))
    r = client.post("/api/topics/MTH165/generate", json={"unit": 1})
    assert CFG.api_key not in r.text
    assert "Authorization" not in r.text
