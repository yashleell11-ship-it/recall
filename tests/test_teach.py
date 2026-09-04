import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from recall.api.teach_routes import get_conn, get_llm, router
from recall.db import connect, init_db
from recall.llm.fake import FakeLlmClient
from recall.teach.explain import explain_card

CHUNK = ("A pointer stores the memory address of another variable. "
         "A reference is an alias for a variable that already exists and cannot "
         "be made to refer to a different variable after initialisation.")
QUOTE = "A pointer stores the memory address of another variable."
PROSE = ("A pointer holds the address of another variable, not the value itself. "
         "That is why dereferencing it is a separate step. The distinction that "
         "trips people up is the reference, which is an alias fixed to one "
         "variable and cannot be repointed.")

OTHER_CHUNK = ("A stack frame is created for every function call and holds that "
               "call's parameters, local variables and return address.")
OTHER_QUOTE = "A stack frame is created for every function call"
OTHER_PROSE = ("A stack frame is the per-call block of memory. It exists because "
               "each call needs its own locals. The distinction is that it belongs "
               "to one call, not to the function.")


def ok_body(quote: str = QUOTE, explanation: str = PROSE) -> str:
    return json.dumps({"explanation": explanation, "quote": quote})


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "teach.db")
    conn = connect(path)
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.execute("INSERT INTO users (id, name) VALUES (2, 'someone else')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) "
                 "VALUES (1,1,'CSE111','Programming')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) "
                 "VALUES (2,2,'OTHER','Not yours')")
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'lec1.pdf','pdf','abc','2026-09-01')")
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref) "
                 "VALUES (1,1,0,?,'p7')", (CHUNK,))
    conn.execute(
        "INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,cloze_text,"
        "arm,state,created_at) VALUES (1,1,1,'qa','What does a pointer store?',"
        "'The memory address of another variable',NULL,'learned','active',"
        "'2026-09-01')")
    conn.execute(
        "INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,cloze_text,"
        "arm,state,created_at) VALUES (2,1,2,'qa','Whose card is this?','Not yours',"
        "NULL,'learned','active','2026-09-01')")
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref) "
                 "VALUES (2,1,1,?,'p9')", (OTHER_CHUNK,))
    conn.execute(
        "INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,cloze_text,"
        "arm,state,created_at) VALUES (3,2,1,'qa','What is a stack frame?',"
        "'The per-call block holding parameters, locals and the return address',"
        "NULL,'learned','active','2026-09-01')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def make_client(db_path):
    """Returns (TestClient, FakeLlmClient) so a test can count API calls."""
    def build(responses: list[str]):
        fake = FakeLlmClient(responses)
        app = FastAPI()
        app.include_router(router)

        def override_conn():
            conn = connect(db_path)
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_conn] = override_conn
        app.dependency_overrides[get_llm] = lambda: (fake, "fake-model")
        return TestClient(app), fake
    return build


def test_explanation_is_returned_with_its_verbatim_quote(make_client):
    client, _ = make_client([ok_body()])
    r = client.post("/api/teach/explain", json={"card_id": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["explanation"] == PROSE
    assert body["source_quote"] == QUOTE
    assert body["source_quote"] in CHUNK
    assert body["cached"] is False


def test_response_carries_the_card_provenance(make_client):
    client, _ = make_client([ok_body()])
    body = client.post("/api/teach/explain", json={"card_id": 1}).json()
    assert body["page_ref"] == "p7"
    assert body["topic_code"] == "CSE111"


def test_prompt_contains_the_chunk_the_card_came_from(make_client):
    """Grounded means grounded in this syllabus: if the chunk is not in the
    prompt, the model is answering from general knowledge."""
    client, fake = make_client([ok_body()])
    client.post("/api/teach/explain", json={"card_id": 1})
    _system, user = fake.calls[0]
    assert CHUNK in user
    assert "What does a pointer store?" in user
    assert "The memory address of another variable" in user


def test_fabricated_quote_is_rejected_with_422(make_client):
    client, _ = make_client([ok_body(quote="A pointer stores the value itself.")])
    r = client.post("/api/teach/explain", json={"card_id": 1})
    assert r.status_code == 422
    assert r.json()["detail"] == "cited quote does not appear in the source passage"


def test_paraphrased_quote_is_rejected(make_client):
    """One word changed is a paraphrase, and a paraphrase is not a citation."""
    client, _ = make_client(
        [ok_body(quote="A pointer stores the memory location of another variable.")])
    assert client.post("/api/teach/explain",
                       json={"card_id": 1}).status_code == 422


def test_empty_quote_is_rejected(make_client):
    client, _ = make_client([ok_body(quote="")])
    assert client.post("/api/teach/explain",
                       json={"card_id": 1}).status_code == 422


def test_quote_match_ignores_whitespace_and_case(make_client):
    client, _ = make_client(
        [ok_body(quote="A pointer stores the   memory\naddress of another Variable.")])
    r = client.post("/api/teach/explain", json={"card_id": 1})
    assert r.status_code == 200
    assert r.json()["cached"] is False


def test_malformed_model_json_is_rejected_not_passed_through(make_client):
    client, _ = make_client(["Sure! Here is your explanation:"])
    r = client.post("/api/teach/explain", json={"card_id": 1})
    assert r.status_code == 422
    assert r.json()["detail"] == "the explanation model returned unusable output"


def test_json_of_the_wrong_shape_is_rejected(make_client):
    client, _ = make_client([json.dumps({"explanation": ["a", "b"], "quote": QUOTE})])
    r = client.post("/api/teach/explain", json={"card_id": 1})
    assert r.status_code == 422
    assert r.json()["detail"] == "the explanation model returned unusable output"


def test_empty_explanation_is_rejected(make_client):
    client, _ = make_client([ok_body(explanation="   ")])
    r = client.post("/api/teach/explain", json={"card_id": 1})
    assert r.status_code == 422
    assert r.json()["detail"] == "the explanation model returned an empty explanation"


def test_second_request_is_served_from_cache_and_costs_nothing(make_client):
    """One queued response, two requests: the fake raises if a second call is
    made, so this asserts the cache is free rather than merely fast."""
    client, fake = make_client([ok_body()])
    first = client.post("/api/teach/explain", json={"card_id": 1}).json()
    second = client.post("/api/teach/explain", json={"card_id": 1}).json()
    assert len(fake.calls) == 1
    assert second["cached"] is True
    assert first["cached"] is False
    assert second["explanation"] == first["explanation"]
    assert second["source_quote"] == first["source_quote"]
    assert second["page_ref"] == first["page_ref"]


def test_the_cache_is_keyed_by_card_and_never_cross_served(make_client):
    """A cache lookup that ignored the card id would pass every other test in
    this file, so this is the one that pins the key down."""
    client, fake = make_client(
        [ok_body(), ok_body(quote=OTHER_QUOTE, explanation=OTHER_PROSE)])
    first = client.post("/api/teach/explain", json={"card_id": 1}).json()
    second = client.post("/api/teach/explain", json={"card_id": 3}).json()
    assert second["cached"] is False
    assert second["explanation"] == OTHER_PROSE
    assert second["source_quote"] == OTHER_QUOTE
    assert second["page_ref"] == "p9"
    assert OTHER_CHUNK in fake.calls[1][1]
    assert len(fake.calls) == 2

    again = client.post("/api/teach/explain", json={"card_id": 1}).json()
    assert again["cached"] is True
    assert again["explanation"] == first["explanation"] == PROSE
    assert again["page_ref"] == "p7"
    assert len(fake.calls) == 2


def test_a_rejected_explanation_is_not_cached(make_client):
    """Nothing trustworthy was produced, so the next attempt must really retry."""
    client, fake = make_client([ok_body(quote="invented"), ok_body()])
    assert client.post("/api/teach/explain",
                       json={"card_id": 1}).status_code == 422
    assert client.post("/api/teach/explain",
                       json={"card_id": 1}).status_code == 200
    assert len(fake.calls) == 2


def test_unknown_card_is_404(make_client):
    client, fake = make_client([ok_body()])
    r = client.post("/api/teach/explain", json={"card_id": 999})
    assert r.status_code == 404
    assert fake.calls == []


def test_another_users_card_is_404(make_client):
    client, _ = make_client([ok_body()])
    assert client.post("/api/teach/explain",
                       json={"card_id": 2}).status_code == 404


def test_row_records_the_model_and_a_sortable_timestamp(db_path):
    conn = connect(db_path)
    out = explain_card(conn, FakeLlmClient([ok_body()]), user_id=1, card_id=1,
                       model="deepseek-chat")
    row = conn.execute("SELECT * FROM card_explanations WHERE card_id = 1").fetchone()
    conn.close()
    assert out.cached is False
    assert row["model"] == "deepseek-chat"
    assert row["source_quote"] == QUOTE
    assert row["created_at"].startswith("20") and "+00:00" in row["created_at"]


def test_service_raises_lookup_error_for_an_unknown_card(db_path):
    conn = connect(db_path)
    with pytest.raises(LookupError):
        explain_card(conn, FakeLlmClient([ok_body()]), user_id=1, card_id=999,
                     model="m")
    conn.close()
