import os

import pytest
from fastapi.testclient import TestClient

from recall.api.app import create_app, get_conn
from recall.api.deps import get_current_user
from recall.db import connect, init_db


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "api.db")


@pytest.fixture
def client(db_path):
    db = db_path
    conn = connect(db)
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.execute("INSERT INTO settings (user_id) VALUES (1)")
    conn.execute("INSERT INTO topics (id,user_id,code,label) "
                 "VALUES (1,1,'CSE111','Programming')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) "
                 "VALUES (2,1,'MATHS','Mathematics')")
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'lec1.pdf','pdf','abc','2026-09-01')")
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref) "
                 "VALUES (1,1,0,'Pointers store addresses.','p1')")
    for cid, state in ((1, "active"), (2, "active"), (3, "pending"),
                       (4, "rejected")):
        conn.execute(
            "INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,cloze_text,"
            "arm,state,created_at) VALUES "
            f"({cid},1,1,'qa','Question {cid}?','Answer {cid}',NULL,'learned',"
            f"'{state}','2026-09-01')")
    conn.commit()
    conn.close()

    app = create_app()

    def override():
        c = connect(db)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = override
    app.dependency_overrides[get_current_user] = lambda: 1
    return TestClient(app)


def test_topics_counts_active_new_and_pending(client):
    body = client.get("/api/topics").json()
    cse = next(t for t in body if t["code"] == "CSE111")
    assert cse["active"] == 2
    assert cse["new"] == 2
    assert cse["pending"] == 1
    maths = next(t for t in body if t["code"] == "MATHS")
    assert maths["active"] == 0


def test_queue_returns_new_cards_only_when_nothing_is_due(client):
    body = client.get("/api/queue").json()
    assert [c["id"] for c in body["cards"]] == [1, 2]
    assert all(c["is_new"] for c in body["cards"])
    assert body["cap_reached"] is False


def test_queue_filters_by_topic(client):
    assert client.get("/api/queue?topic=MATHS").json()["cards"] == []


def test_review_schedules_the_card_forward(client):
    body = client.post("/api/review", json={"card_id": 1, "grade": 3}).json()
    assert body["interval_days"] > 0
    assert body["stability"] > 0
    assert 1.0 <= body["difficulty"] <= 10.0


def test_reviewed_card_leaves_the_new_queue(client):
    client.post("/api/review", json={"card_id": 1, "grade": 3})
    assert [c["id"] for c in client.get("/api/queue").json()["cards"]] == [2]


def test_again_grade_comes_back_almost_immediately(client):
    body = client.post("/api/review", json={"card_id": 1, "grade": 1}).json()
    assert body["interval_days"] < 0.02


def test_easy_schedules_further_out_than_good(client, tmp_path):
    good = client.post("/api/review", json={"card_id": 1, "grade": 3}).json()
    easy = client.post("/api/review", json={"card_id": 2, "grade": 4}).json()
    assert easy["interval_days"] >= good["interval_days"]


def test_review_rejects_unknown_card(client):
    assert client.post("/api/review", json={"card_id": 999, "grade": 3}).status_code \
        == 404


def test_review_rejects_bad_grade(client):
    assert client.post("/api/review", json={"card_id": 1, "grade": 9}).status_code \
        == 422


def test_new_card_limit_is_enforced(client):
    client.put("/api/settings", json={"new_cards_per_day": 1})
    assert len(client.get("/api/queue").json()["cards"]) == 1


def test_new_cards_introduced_today_reduce_the_budget(client):
    client.put("/api/settings", json={"new_cards_per_day": 1})
    client.post("/api/review", json={"card_id": 1, "grade": 3})
    assert client.get("/api/queue").json()["cards"] == []


def test_pending_lists_only_pending_with_source(client):
    body = client.get("/api/pending").json()
    assert body["total"] == 1
    assert body["cards"][0]["id"] == 3
    assert body["cards"][0]["source_filename"] == "lec1.pdf"


def test_decide_approve_activates_cards(client):
    assert client.post("/api/pending/decide",
                       json={"ids": [3], "action": "approve"}).json()["updated"] == 1
    assert client.get("/api/pending").json()["total"] == 0


def test_decide_never_touches_non_pending_cards(client):
    assert client.post("/api/pending/decide",
                       json={"ids": [1, 4], "action": "reject"}).json()["updated"] == 0


def test_decide_rejects_unknown_action(client):
    assert client.post("/api/pending/decide",
                       json={"ids": [3], "action": "delete"}).status_code == 422


def test_settings_round_trip(client):
    client.put("/api/settings", json={"desired_retention": 0.85})
    assert client.get("/api/settings").json()["desired_retention"] == 0.85


def test_settings_rejects_out_of_range_retention(client):
    assert client.put("/api/settings",
                      json={"desired_retention": 1.5}).status_code == 422


def test_stats_reflects_a_review(client):
    client.post("/api/review", json={"card_id": 1, "grade": 3})
    body = client.get("/api/stats").json()
    assert body["today"]["reviewed"] == 1
    assert body["today"]["streak"] == 1
    assert body["totals"]["pending"] == 1
    assert len(body["last_14_days"]) == 1


def test_sources_reports_filename_and_topic(client):
    body = client.get("/api/sources").json()
    assert body[0]["filename"] == "lec1.pdf"
    assert body[0]["topic_code"] == "CSE111"


def test_new_queue_cards_carry_no_memory_state(client):
    card = client.get("/api/queue").json()["cards"][0]
    assert card["is_new"] is True
    assert card["stability"] is None
    assert card["difficulty"] is None
    assert card["elapsed_days"] == 0.0


def test_due_queue_cards_carry_memory_state_for_exact_previews(client, db_path):
    """The client prices each grade button from this; estimates are not good enough."""
    from datetime import datetime, timedelta, timezone

    from recall.db import connect

    client.post("/api/review", json={"card_id": 1, "grade": 3})
    past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    conn = connect(db_path)
    conn.execute("UPDATE card_state SET due_at = ? WHERE card_id = 1", (past,))
    conn.commit()
    conn.close()

    card = next(c for c in client.get("/api/queue").json()["cards"] if c["id"] == 1)
    assert card["is_new"] is False
    assert card["stability"] > 0
    assert 1.0 <= card["difficulty"] <= 10.0
    assert card["elapsed_days"] >= 0.0


def test_elapsed_days_reflects_real_time_since_last_review(client, db_path):
    from datetime import datetime, timedelta, timezone

    from recall.db import connect

    client.post("/api/review", json={"card_id": 1, "grade": 3})
    conn = connect(db_path)
    long_ago = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
    conn.execute("UPDATE reviews SET reviewed_at = ? WHERE card_id = 1", (long_ago,))
    conn.execute("UPDATE card_state SET due_at = ? WHERE card_id = 1", (long_ago,))
    conn.commit()
    conn.close()

    card = next(c for c in client.get("/api/queue").json()["cards"] if c["id"] == 1)
    assert 8.9 < card["elapsed_days"] < 9.1


def test_cors_allows_the_dev_server_on_any_localhost_port(client):
    """Pinning one port breaks the moment that port is taken, which it was."""
    for origin in ("http://localhost:3000", "http://localhost:3210",
                   "http://127.0.0.1:8080"):
        r = client.get("/api/topics", headers={"Origin": origin})
        assert r.headers.get("access-control-allow-origin") == origin, origin


def test_cors_rejects_a_remote_origin(client):
    r = client.get("/api/topics", headers={"Origin": "https://evil.example.com"})
    assert r.headers.get("access-control-allow-origin") is None


def test_concurrent_requests_all_succeed(client):
    """A page load fires several requests at once. Before check_same_thread=False
    most of them returned 500 from a cross-thread sqlite close."""
    import concurrent.futures

    paths = ["/api/topics", "/api/stats", "/api/settings", "/api/queue"] * 6
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda p: client.get(p).status_code, paths))
    assert set(codes) == {200}, f"got {sorted(set(codes))}"


def test_every_contract_route_is_mounted(client):
    """A router that exists but was never included is invisible until someone hits
    it in production. Assert against the OpenAPI schema rather than app.routes:
    FastAPI represents an included router as ONE opaque entry in app.routes, so
    counting that list silently reports zero for every mounted router."""
    paths = set(client.app.openapi()["paths"])
    expected = {
        "/api/topics", "/api/queue", "/api/review", "/api/pending",
        "/api/pending/decide", "/api/settings", "/api/stats", "/api/sources",
        "/api/tests", "/api/tests/{test_id}", "/api/tests/{test_id}/answer",
        "/api/tests/{test_id}/submit", "/api/teach/explain",
        "/api/sources/upload", "/api/sources/{source_id}/generate",
    }
    missing = expected - paths
    assert not missing, f"declared in CONTRACT.md but not mounted: {sorted(missing)}"


def test_mounted_routes_actually_respond(client):
    """Schema presence is not reachability. Hit them."""
    assert client.get("/api/tests").status_code == 200
    # Unknown ids must 404, not 500 — proves the handler runs, not just the route.
    assert client.get("/api/tests/999999").status_code == 404
    assert client.post("/api/teach/explain",
                       json={"card_id": 999999}).status_code == 404


def test_a_saved_fit_actually_changes_scheduling(client, db_path):
    """Fitted weights that nothing reads are decoration. Prove they reach FSRS."""
    import json

    from recall.db import connect
    from recall.schedule.fsrs import DEFAULT_PARAMS

    baseline = client.post("/api/review", json={"card_id": 1, "grade": 3}).json()

    # Save a fit whose initial-stability weight for "good" is far larger.
    tweaked = list(DEFAULT_PARAMS)
    tweaked[2] = DEFAULT_PARAMS[2] * 3.0
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO fit_runs (ran_at, n_reviews, params_json, val_logloss)"
        " VALUES ('2026-09-05T00:00:00+00:00', 900, ?, 0.42)",
        (json.dumps(tweaked),),
    )
    conn.execute("DELETE FROM card_state")
    conn.execute("DELETE FROM reviews")
    conn.commit()
    conn.close()

    after = client.post("/api/review", json={"card_id": 1, "grade": 3}).json()
    assert after["stability"] > baseline["stability"] * 2, (
        f"fitted params ignored: {baseline['stability']} -> {after['stability']}"
    )


def test_leech_is_flagged_at_the_threshold(client, db_path):
    from recall.api.scheduling import LEECH_THRESHOLD
    from recall.db import connect

    client.post("/api/review", json={"card_id": 1, "grade": 3})
    conn = connect(db_path)
    conn.execute("UPDATE card_state SET lapses = ?, due_at = '2020-01-01T00:00:00+00:00'"
                 " WHERE card_id = 1", (LEECH_THRESHOLD,))
    conn.commit()
    conn.close()

    card = next(c for c in client.get("/api/queue").json()["cards"] if c["id"] == 1)
    assert card["is_leech"] is True
    assert card["lapses"] == LEECH_THRESHOLD
    assert client.get("/api/stats").json()["totals"]["leeches"] == 1


def test_a_card_below_the_threshold_is_not_a_leech(client, db_path):
    from recall.api.scheduling import LEECH_THRESHOLD
    from recall.db import connect

    client.post("/api/review", json={"card_id": 1, "grade": 3})
    conn = connect(db_path)
    conn.execute("UPDATE card_state SET lapses = ?, due_at = '2020-01-01T00:00:00+00:00'"
                 " WHERE card_id = 1", (LEECH_THRESHOLD - 1,))
    conn.commit()
    conn.close()
    card = next(c for c in client.get("/api/queue").json()["cards"] if c["id"] == 1)
    assert card["is_leech"] is False
    assert client.get("/api/stats").json()["totals"]["leeches"] == 0


def test_new_cards_are_never_leeches(client):
    card = client.get("/api/queue").json()["cards"][0]
    assert card["is_new"] is True
    assert card["is_leech"] is False
    assert card["lapses"] == 0


def test_startup_adds_tables_a_newer_release_introduced(tmp_path):
    """A database created before a feature shipped must gain that feature's tables
    on boot, not 500 on the first request that touches them."""
    import sqlite3

    from fastapi.testclient import TestClient

    from recall.api.app import create_app
    from recall.db import connect

    db = str(tmp_path / "old.db")
    conn = connect(db)
    conn.executescript(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);"
        "INSERT INTO users (id, name) VALUES (1, 'yash');"
    )
    conn.commit()
    conn.close()

    before = connect(db)
    with pytest.raises(sqlite3.OperationalError):
        before.execute("SELECT 1 FROM card_explanations").fetchall()
    before.close()

    os.environ["RECALL_DB"] = db
    try:
        with TestClient(create_app()):
            pass  # entering the context runs startup
    finally:
        os.environ.pop("RECALL_DB", None)

    after = connect(db)
    tables = {r["name"] for r in after.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"card_explanations", "tests", "test_questions"} <= tables
    # and the pre-existing row survived
    assert after.execute("SELECT name FROM users").fetchone()["name"] == "yash"


def test_topics_carry_lpu_meta_when_seeded(client, db_path):
    from recall.db import connect
    from recall.seed import seed_topics

    conn = connect(db_path)
    seed_topics(conn)
    conn.close()

    topics = client.get("/api/topics").json()
    mth = next(t for t in topics if t["code"] == "MTH165")
    assert mth["meta"]["full_name"] == "Mathematics for Engineers"
    assert len(mth["meta"]["units"]) == 6
    assert mth["meta"]["scheme"]["ete"] == 50
    int108 = next(t for t in topics if t["code"] == "INT108")
    assert int108["meta"]["mte_exists"] is False


def test_topics_meta_is_null_when_absent(client):
    topics = client.get("/api/topics").json()
    assert all(t["meta"] is None for t in topics)
