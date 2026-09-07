"""Open registration: register/login/logout/me, session expiry, and the
authorization gap a shared `cards` table opens up once more than one user's
rows can live in it (decide() must not be able to reach another user's cards
by id alone)."""

import pytest
from fastapi.testclient import TestClient

from recall.api.app import create_app, get_conn
from recall.db import connect, init_db
from recall.lpu import SUBJECTS


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "auth.db")
    conn = connect(path)
    init_db(conn)
    conn.close()
    return path


@pytest.fixture
def client(db_path):
    app = create_app()

    def override():
        c = connect(db_path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = override
    # https base_url: the session cookie is Secure, and httpx's cookie jar
    # (correctly) refuses to retain a Secure cookie set over plain http, which
    # the default "http://testserver" is.
    return TestClient(app, base_url="https://testserver")


def register(client, name="yash", email="yash@example.com", password="hunter2222"):
    return client.post("/api/auth/register",
                       json={"name": name, "email": email, "password": password})


def test_register_returns_the_user_and_sets_a_session_cookie(client):
    r = register(client)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "yash"
    assert body["email"] == "yash@example.com"
    assert "password" not in body and "password_hash" not in body
    assert "recall_session" in r.cookies


def test_me_reflects_the_registered_user(client):
    register(client)
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "yash@example.com"


def test_registration_seeds_the_full_lpu_topic_catalog(client):
    """A new signup is only actually usable once it has its own topics to
    upload against — this must happen automatically, not as a separate step."""
    register(client)
    codes = {t["code"] for t in client.get("/api/topics").json()}
    assert codes == set(SUBJECTS)


def test_duplicate_email_is_rejected(client):
    register(client, name="first")
    r = register(client, name="second")  # same default email
    assert r.status_code == 422


def test_duplicate_name_is_rejected(client):
    register(client, email="one@example.com")
    r = register(client, name="yash", email="two@example.com")
    assert r.status_code == 422


def test_login_with_the_right_password_succeeds_and_sets_a_cookie(client):
    register(client)
    client.cookies.clear()
    r = client.post("/api/auth/login",
                    json={"email": "yash@example.com", "password": "hunter2222"})
    assert r.status_code == 200
    assert "recall_session" in r.cookies


def test_login_with_the_wrong_password_is_rejected(client):
    register(client)
    client.cookies.clear()
    r = client.post("/api/auth/login",
                    json={"email": "yash@example.com", "password": "wrongpassword"})
    assert r.status_code == 401


def test_unknown_email_and_wrong_password_give_the_identical_error(client):
    """Distinguishing the two is a free account-enumeration oracle."""
    register(client)
    client.cookies.clear()
    unknown = client.post("/api/auth/login",
                          json={"email": "nobody@example.com", "password": "whatever1"})
    wrong = client.post("/api/auth/login",
                        json={"email": "yash@example.com", "password": "wrongpassword"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_email_is_case_insensitive(client):
    register(client, email="Yash@Example.com")
    client.cookies.clear()
    r = client.post("/api/auth/login",
                    json={"email": "yash@example.com", "password": "hunter2222"})
    assert r.status_code == 200


def test_logout_clears_the_session(client):
    register(client)
    assert client.get("/api/auth/me").status_code == 200
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_unauthenticated_request_to_a_protected_route_is_401(client):
    assert client.get("/api/topics").status_code == 401
    assert client.get("/api/stats").status_code == 401


def test_expired_session_is_rejected(client, db_path):
    register(client)
    conn = connect(db_path)
    conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
    conn.commit()
    conn.close()
    assert client.get("/api/auth/me").status_code == 401


def test_decide_cannot_touch_another_users_pending_card(client, db_path):
    """Once cards from more than one user can share the table, an id list
    alone is not proof of ownership — decide() must join through topics."""
    register(client, name="alice", email="alice@example.com")
    client.cookies.clear()
    register(client, name="bob", email="bob@example.com")
    # `client` is now logged in as bob.

    conn = connect(db_path)
    alice_id = conn.execute(
        "SELECT id FROM users WHERE email='alice@example.com'"
    ).fetchone()["id"]
    alice_topic = conn.execute(
        "SELECT id FROM topics WHERE user_id = ? LIMIT 1", (alice_id,)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO sources (user_id,topic_id,filename,kind,sha256,added_at)"
        " VALUES (?,?,?,?,?,?)",
        (alice_id, alice_topic, "f.pdf", "pdf", "sha-alice", "2026-09-01"),
    )
    source_id = conn.execute(
        "SELECT id FROM sources WHERE sha256='sha-alice'"
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO chunks (source_id,ordinal,text,page_ref) VALUES (?,0,'x','p1')",
        (source_id,),
    )
    chunk_id = conn.execute(
        "SELECT id FROM chunks WHERE source_id = ?", (source_id,)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO cards (chunk_id,topic_id,kind,question,answer,arm,state,created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (chunk_id, alice_topic, "qa", "alice's question?", "A", "learned",
         "pending", "2026-09-01"),
    )
    alice_card_id = conn.execute(
        "SELECT id FROM cards WHERE question = ?", ("alice's question?",)
    ).fetchone()["id"]
    conn.commit()
    conn.close()

    r = client.post("/api/pending/decide",
                    json={"ids": [alice_card_id], "action": "approve"})
    assert r.status_code == 200
    assert r.json()["updated"] == 0

    conn = connect(db_path)
    state = conn.execute(
        "SELECT state FROM cards WHERE id = ?", (alice_card_id,)
    ).fetchone()["state"]
    conn.close()
    assert state == "pending"
