"""Knowledge mode: cards for a unit with nothing uploaded.

The point of these tests is the part that is deliberately different from the
upload path — no grounding gate, no closed-book gate, an origin marker on
every row, a synthetic source that satisfies the chunk foreign key, and a
dedup pass seeded with what the unit already holds.
"""

import json

import numpy as np
import pytest

from recall.config import Config
from recall.db import connect, init_db
from recall.generate.knowledge import (
    MAX_CARDS_PER_CALL,
    SYNTHETIC_KIND,
    generate_for_unit,
    knowledge_sha,
    topic_units,
)
from recall.llm.fake import FakeLlmClient

CFG = Config(
    api_key="test", base_url="http://localhost", model="deepseek-chat",
    db_path=":memory:", max_cost_usd_per_source=2.0,
    price_input_per_mtok=0.27, price_output_per_mtok=1.10,
)

UNITS = ["Linear Algebra", "Differential Calculus and Its Applications"]


def orthogonal_embed(texts: list[str]) -> np.ndarray:
    """Deterministic and collision-free per distinct first word, so dedup is
    exercised without loading a real model."""
    vocab: dict[str, int] = {}
    rows = []
    for t in texts:
        key = t.strip().split(" ")[0].lower()
        if key not in vocab:
            vocab[key] = len(vocab)
        v = np.zeros(64)
        v[vocab[key] % 64] = 1.0
        rows.append(v)
    return np.array(rows)


def body(cards: list[dict]) -> str:
    return json.dumps({"cards": cards})


def qa(question: str, answer: str = "A real answer of some substance") -> dict:
    return {"kind": "qa", "question": question, "answer": answer}


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "k.db"))
    init_db(c)
    c.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    c.execute("INSERT INTO users (id, name) VALUES (2, 'someone else')")
    c.execute(
        "INSERT INTO topics (id,user_id,code,label,meta) VALUES (1,1,'MTH165',?,?)",
        ("Mathematics for Engineers",
         json.dumps({"full_name": "Mathematics for Engineers", "units": UNITS,
                     "exam_format": "mixed"})),
    )
    c.commit()
    return c


def run(conn, client, *, unit_index=0, n=5, embed=orthogonal_embed):
    return generate_for_unit(
        conn, CFG, client, user_id=1, topic_id=1, topic_code="MTH165",
        full_name="Mathematics for Engineers", exam_format="mixed",
        unit_index=unit_index, unit_name=UNITS[unit_index], n=n, embed=embed,
    )


def test_cards_are_written_with_origin_knowledge(conn):
    client = FakeLlmClient([body([
        qa("What is the rank of a matrix?"),
        qa("When is a square matrix invertible?"),
    ])])
    result = run(conn, client)
    assert result.accepted == 2
    rows = conn.execute("SELECT origin, state FROM cards").fetchall()
    assert [r["origin"] for r in rows] == ["knowledge", "knowledge"]
    # Knowledge cards skipped the two gates that check them against reality,
    # so they still stop for a human. Upload-grounded cards do not.
    assert {r["state"] for r in rows} == {"pending"}


def test_uploaded_cards_keep_origin_upload(conn):
    """The new column must not silently reclassify the existing corpus."""
    conn.execute(
        "INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,added_at)"
        " VALUES (9,1,1,'notes.pdf','pdf','sha9','2026-09-01')")
    conn.execute(
        "INSERT INTO chunks (id,source_id,ordinal,text,page_ref)"
        " VALUES (9,9,0,'real passage','p1')")
    conn.execute(
        "INSERT INTO cards (chunk_id,topic_id,kind,question,answer,arm,state,created_at)"
        " VALUES (9,1,'qa','From a real PDF?','yes','learned','pending','2026-09-01')")
    conn.commit()
    origin = conn.execute(
        "SELECT origin FROM cards WHERE chunk_id = 9").fetchone()["origin"]
    assert origin == "upload"


def test_only_one_paid_call_and_no_judge_calls(conn):
    """Grounding and closed-book judges are dropped, so a unit costs exactly
    one completion however many cards come back."""
    client = FakeLlmClient([body([qa(f"Question number {i} about rank?")
                                  for i in range(5)])])
    run(conn, client)
    assert len(client.calls) == 1


def test_the_prompt_names_the_unit_and_course(conn):
    client = FakeLlmClient([body([qa("What is the rank of a matrix?")])])
    run(conn, client, unit_index=1)
    _system, user = client.calls[0]
    assert "Differential Calculus and Its Applications" in user
    assert "MTH165" in user
    assert "Unit 2" in user  # 1-based for the student, 0-based in the call


def test_heuristic_gates_still_run(conn):
    """Answerability and atomicity never needed a passage, so they survive."""
    client = FakeLlmClient([body([
        qa("Discuss the whole of linear algebra."),          # essay opener
        qa("Short?"),                                        # too short
        qa("What is the rank of a matrix?"),                 # keeper
    ])])
    result = run(conn, client)
    assert result.accepted == 1
    reasons = [r["reject_reason"] for r in conn.execute(
        "SELECT reject_reason FROM cards WHERE state='rejected'").fetchall()]
    assert any("essay" in r for r in reasons)
    assert any("short" in r for r in reasons)


def test_a_synthetic_source_and_chunk_satisfy_the_foreign_key(conn):
    client = FakeLlmClient([body([qa("What is the rank of a matrix?")])])
    run(conn, client)
    src = conn.execute(
        "SELECT id, kind, sha256 FROM sources WHERE user_id = 1").fetchone()
    assert src["kind"] == SYNTHETIC_KIND
    assert src["sha256"] == knowledge_sha(1)
    chunk = conn.execute(
        "SELECT text, page_ref FROM chunks WHERE source_id = ?", (src["id"],)
    ).fetchone()
    assert chunk["page_ref"] == "Unit 1 · Linear Algebra"
    # Deliberately just the unit name — not padded into a passage-shaped
    # paragraph that a later grounding check could be fooled by.
    assert chunk["text"] == "Linear Algebra"


def test_generating_twice_reuses_one_source_and_one_chunk_per_unit(conn):
    client = FakeLlmClient([
        body([qa("What is the rank of a matrix?")]),
        body([qa("When is a square matrix invertible?")]),
    ])
    run(conn, client)
    run(conn, client)
    assert conn.execute("SELECT COUNT(*) n FROM sources").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) n FROM chunks").fetchone()["n"] == 1


def test_each_unit_gets_its_own_chunk(conn):
    client = FakeLlmClient([
        body([qa("What is the rank of a matrix?")]),
        body([qa("What does Rolle's theorem require?")]),
    ])
    run(conn, client, unit_index=0)
    run(conn, client, unit_index=1)
    refs = {r["page_ref"] for r in conn.execute(
        "SELECT page_ref FROM chunks").fetchall()}
    assert refs == {"Unit 1 · Linear Algebra",
                    "Unit 2 · Differential Calculus and Its Applications"}


def test_a_repeat_press_does_not_flood_the_unit_with_duplicates(conn):
    """The upload path cannot hit this — a chunk generates exactly once — but
    this button can be pressed all day against the same unit."""
    client = FakeLlmClient([
        body([qa("Rank of a matrix, what is it?")]),
        body([qa("Rank of a matrix, what is it?"),     # same first word: collides
              qa("Eigenvalues, what are they?")]),     # genuinely new
    ])
    first = run(conn, client)
    assert first.accepted == 1
    second = run(conn, client)
    assert second.accepted == 1, "the repeat of an existing question must drop"
    assert second.rejected == 1
    reason = conn.execute(
        "SELECT reject_reason FROM cards WHERE state='rejected'").fetchone()
    assert "duplicate of" in reason["reject_reason"]
    kept = [r["question"] for r in conn.execute(
        "SELECT question FROM cards WHERE state='pending' ORDER BY id").fetchall()]
    assert kept == ["Rank of a matrix, what is it?", "Eigenvalues, what are they?"]


def test_cost_is_recorded_on_one_accumulating_gen_run(conn):
    # Distinct first words: orthogonal_embed keys on those, so same-word
    # questions would (correctly) be deduped against each other and the
    # second run would accept nothing.
    client = FakeLlmClient([
        body([qa("Rank of a matrix, what is it?")]),
        body([qa("Eigenvalues, what are they for?")]),
    ])
    run(conn, client)
    run(conn, client)
    rows = conn.execute("SELECT cost_estimate, cards_accepted FROM gen_runs").fetchall()
    assert len(rows) == 1, "a second row would double-count the source in /api/sources"
    assert rows[0]["cards_accepted"] == 2
    assert rows[0]["cost_estimate"] > 0


def test_n_is_capped_server_side(conn):
    """The prompt asks; this is what actually bounds one press."""
    client = FakeLlmClient([body([qa("What is the rank of a matrix?")])])
    run(conn, client, n=10_000)
    _system, user = client.calls[0]
    assert f"at most {MAX_CARDS_PER_CALL} flashcards" in user


def test_topic_units_survives_a_topic_with_no_metadata():
    assert topic_units(None) == []
    assert topic_units("not json at all") == []
    assert topic_units(json.dumps({"units": "not a list"})) == []
    assert topic_units(json.dumps({"units": ["A", 7, "B"]})) == ["A", "B"]


# --- teaching a card that has no source ------------------------------------

def test_a_knowledge_card_is_explained_without_a_citation(conn):
    """explain_card's whole discipline is "cite verbatim or say nothing". A
    knowledge card has nothing to cite, so the citation requirement is
    dropped rather than faked — and the empty quote is the signal."""
    from recall.teach.explain import explain_card

    client = FakeLlmClient([body([qa("What is the rank of a matrix?")])])
    run(conn, client)
    card_id = conn.execute(
        "SELECT id FROM cards WHERE state='pending'").fetchone()["id"]

    teacher = FakeLlmClient([json.dumps({
        "explanation": "The rank is the number of linearly independent rows. "
                       "It equals the column rank. The trap is confusing it "
                       "with the matrix dimension."})])
    out = explain_card(conn, teacher, user_id=1, card_id=card_id,
                       model="fake-model")
    assert out.source_quote == ""
    assert "linearly independent" in out.explanation
    # It must NOT have been asked to quote a passage.
    system, _user = teacher.calls[0]
    assert "no source passage" in system.lower()


def test_an_uploaded_card_still_requires_its_verbatim_quote(conn):
    """The knowledge branch must not weaken the grounded one."""
    from recall.teach.explain import explain_card

    conn.execute(
        "INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,added_at)"
        " VALUES (5,1,1,'notes.pdf','pdf','sha5','2026-09-01')")
    conn.execute(
        "INSERT INTO chunks (id,source_id,ordinal,text,page_ref)"
        " VALUES (5,5,0,'The rank of a matrix is its number of pivots.','p3')")
    conn.execute(
        "INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,arm,state,"
        "created_at) VALUES (55,5,1,'qa','What is rank?','pivots','learned',"
        "'active','2026-09-01')")
    conn.commit()

    teacher = FakeLlmClient([json.dumps({
        "explanation": "Rank counts pivots.",
        "quote": "a sentence that is nowhere in the passage"})])
    with pytest.raises(ValueError, match="does not appear in the source"):
        explain_card(conn, teacher, user_id=1, card_id=55, model="fake-model")
