import pytest
from fastapi.testclient import TestClient

from recall.api.app import create_app, get_conn
from recall.db import connect, init_db


@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "api.db")
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
