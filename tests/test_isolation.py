"""Cross-user isolation.

Recall spent its whole life as a single-user app, so a query that filtered by
nothing was correct for years. Opening registration turned every one of those
into a leak. These are the regression tests for that class of bug — each one
failed against the code as it stood the day auth landed.

The shape to hold on to: `cards` and `chunks` carry no user_id of their own.
They are owned only through `topics.user_id` (or `sources.user_id`), so any
query that reaches them without joining one of those is suspect.
"""

import pytest
from fastapi.testclient import TestClient

from recall.api.app import create_app, get_conn
from recall.api.deps import get_current_user
from recall.db import connect, init_db

OWNER, INTRUDER = 1, 2


def deck_for(conn, user_id: int, code: str, n: int, first_id: int) -> None:
    """`n` active cards owned by `user_id`, plus one pending card."""
    conn.execute("INSERT INTO topics (user_id, code, label) VALUES (?,?,?)",
                 (user_id, code, f"{code} label"))
    topic_id = conn.execute(
        "SELECT id FROM topics WHERE user_id = ? AND code = ?", (user_id, code)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO sources (user_id,topic_id,filename,kind,sha256,added_at)"
        " VALUES (?,?,?,?,?,?)",
        (user_id, topic_id, f"{code}.pdf", "pdf", f"sha-{user_id}-{code}",
         "2026-09-01T00:00:00+00:00"))
    source_id = conn.execute(
        "SELECT id FROM sources WHERE sha256 = ?", (f"sha-{user_id}-{code}",)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO chunks (source_id,ordinal,text,page_ref) VALUES (?,0,?,?)",
        (source_id, "body", "p1"))
    chunk_id = conn.execute(
        "SELECT id FROM chunks WHERE source_id = ?", (source_id,)
    ).fetchone()["id"]
    for i in range(n):
        conn.execute(
            "INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,arm,"
            "state,created_at) VALUES (?,?,?,'qa',?,?,'learned','active',?)",
            (first_id + i, chunk_id, topic_id, f"{code} secret question {i}?",
             f"{code} secret answer {i}", "2026-09-01T00:00:00+00:00"))
    conn.execute(
        "INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,arm,"
        "state,created_at) VALUES (?,?,?,'qa',?,?,'learned','pending',?)",
        (first_id + 900, chunk_id, topic_id, f"{code} pending?", "a",
         "2026-09-01T00:00:00+00:00"))


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "iso.db")
    conn = connect(path)
    init_db(conn)
    for uid, name in ((OWNER, "owner"), (INTRUDER, "intruder")):
        conn.execute("INSERT INTO users (id, name) VALUES (?,?)", (uid, name))
        conn.execute("INSERT INTO settings (user_id) VALUES (?)", (uid,))
    deck_for(conn, OWNER, "MTH165", 5, first_id=100)
    # The intruder has an account and a topic of their own, but no cards.
    conn.execute("INSERT INTO topics (user_id, code, label) VALUES (?,?,?)",
                 (INTRUDER, "MTH165", "MTH165 label"))
    conn.commit()
    conn.close()
    return path


def client_as(db_path: str, user_id: int) -> TestClient:
    app = create_app()

    def override():
        c = connect(db_path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = override
    app.dependency_overrides[get_current_user] = lambda: user_id
    return TestClient(app)


def test_the_new_card_queue_does_not_serve_another_users_cards(db_path):
    """The one that shipped: the new-card half joined topics but never
    filtered topics.user_id, and its only user-bound predicate was "this user
    has no card_state row" — which another user's untouched card satisfies."""
    body = client_as(db_path, INTRUDER).get("/api/queue").json()
    assert body["cards"] == []


def test_the_owner_still_gets_their_own_new_cards(db_path):
    """The fix must not empty the queue for the person who owns the deck."""
    body = client_as(db_path, OWNER).get("/api/queue").json()
    assert len(body["cards"]) == 5
    assert all(c["question"].startswith("MTH165 secret") for c in body["cards"])


def test_stats_totals_count_only_your_own_cards(db_path):
    """by_topic was scoped and totals were not, so a brand-new account's
    dashboard displayed the whole instance's card count."""
    stats = client_as(db_path, INTRUDER).get("/api/stats").json()
    assert stats["totals"]["active"] == 0
    assert stats["totals"]["pending"] == 0
    owner_stats = client_as(db_path, OWNER).get("/api/stats").json()
    assert owner_stats["totals"]["active"] == 5
    assert owner_stats["totals"]["pending"] == 1


def test_a_review_cannot_be_recorded_against_another_users_card(db_path):
    r = client_as(db_path, INTRUDER).post(
        "/api/review", json={"card_id": 100, "grade": 3})
    assert r.status_code == 404
    conn = connect(db_path)
    n = conn.execute("SELECT COUNT(*) n FROM reviews WHERE user_id = ?",
                     (INTRUDER,)).fetchone()["n"]
    conn.close()
    assert n == 0


def test_the_owner_can_still_review_their_own_card(db_path):
    r = client_as(db_path, OWNER).post(
        "/api/review", json={"card_id": 100, "grade": 3})
    assert r.status_code == 200


def test_pending_triage_shows_only_your_own_cards(db_path):
    body = client_as(db_path, INTRUDER).get("/api/pending").json()
    assert body["total"] == 0
    assert body["cards"] == []


def test_decide_cannot_approve_another_users_pending_card(db_path):
    r = client_as(db_path, INTRUDER).post(
        "/api/pending/decide", json={"ids": [1000], "action": "approve"})
    assert r.json()["updated"] == 0
    conn = connect(db_path)
    state = conn.execute("SELECT state FROM cards WHERE id = 1000").fetchone()["state"]
    conn.close()
    assert state == "pending"


def test_test_mode_assembles_only_from_your_own_deck(db_path):
    r = client_as(db_path, INTRUDER).post("/api/tests", json={"kind": "class30"})
    assert r.status_code == 200
    assert r.json()["questions"] == []


def test_sources_list_is_scoped(db_path):
    assert client_as(db_path, INTRUDER).get("/api/sources").json() == []
    assert len(client_as(db_path, OWNER).get("/api/sources").json()) == 1


def test_anki_export_covers_one_user_only(db_path, tmp_path):
    """CLI-only, so not remotely reachable — but it writes a FILE, and it used
    to write every account's cards into it."""
    from recall.export.anki import export_apkg

    conn = connect(db_path)
    assert export_apkg(conn, str(tmp_path / "owner.apkg"), OWNER) == 5
    assert export_apkg(conn, str(tmp_path / "intruder.apkg"), INTRUDER) == 0
    conn.close()
