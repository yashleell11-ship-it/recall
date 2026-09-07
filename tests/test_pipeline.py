import json

import fitz
import numpy as np
import pytest

from recall.config import load_config
from recall.db import connect, init_db
from recall.llm.fake import FakeLlmClient
from recall.pipeline import assign_arm, ingest_source

CFG = load_config({"DEEPSEEK_API_KEY": "sk-test"})


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_db(c)
    c.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    c.execute("INSERT INTO topics (id, user_id, code, label) "
              "VALUES (1, 1, 'CSE111', 'Programming')")
    c.commit()
    return c


def make_pdf(tmp_path, text, name="src.pdf"):
    p = tmp_path / name
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(str(p))
    doc.close()
    return str(p)


def orthogonal_embed(texts):
    return np.eye(max(len(texts), 1))[: len(texts)]


def accept_all(question, answer, quote):
    return [
        json.dumps({"cards": [{"kind": "qa", "question": question, "answer": answer}]}),
        json.dumps({"supported": True, "quote": quote}),
        json.dumps({"answer": "no idea", "confident": False}),
    ]


TEXT = "Pointers store memory addresses in C."


def test_accepted_card_is_persisted_with_traceability(conn, tmp_path):
    path = make_pdf(tmp_path, TEXT)
    client = FakeLlmClient(accept_all("What do pointers store in C?",
                                      "memory addresses", TEXT))
    result = ingest_source(conn, CFG, client, user_id=1, topic_id=1, path=path,
                           embed=orthogonal_embed)
    assert result.accepted == 1
    row = conn.execute(
        "SELECT c.state, c.topic_id, ch.page_ref FROM cards c "
        "JOIN chunks ch ON ch.id = c.chunk_id"
    ).fetchone()
    # Straight into rotation: triage moved out of the way of daily use.
    assert row["state"] == "active"
    assert row["topic_id"] == 1
    assert row["page_ref"] == "p1"


def test_rejected_card_is_stored_with_reason(conn, tmp_path):
    path = make_pdf(tmp_path, TEXT)
    client = FakeLlmClient([json.dumps({"cards": [
        {"kind": "qa", "question": "Discuss pointers in C thoroughly.",
         "answer": "They store addresses"}]})])
    result = ingest_source(conn, CFG, client, user_id=1, topic_id=1, path=path,
                           embed=orthogonal_embed)
    assert result.rejected == 1
    row = conn.execute("SELECT state, reject_reason FROM cards").fetchone()
    assert row["state"] == "rejected"
    assert "essay" in row["reject_reason"]


def test_free_gates_run_before_paid_judges(conn, tmp_path):
    path = make_pdf(tmp_path, TEXT)
    client = FakeLlmClient([json.dumps({"cards": [
        {"kind": "qa", "question": "Discuss pointers in C thoroughly.",
         "answer": "addresses"}]})])
    ingest_source(conn, CFG, client, user_id=1, topic_id=1, path=path,
                  embed=orthogonal_embed)
    assert len(client.calls) == 1  # generation only; no judge was ever called


def test_reingesting_the_same_file_is_a_noop(conn, tmp_path):
    path = make_pdf(tmp_path, TEXT)
    args = dict(user_id=1, topic_id=1, path=path, embed=orthogonal_embed)
    ingest_source(conn, CFG, FakeLlmClient(
        accept_all("What do pointers store?", "addresses", TEXT)), **args)
    second = ingest_source(conn, CFG, FakeLlmClient([]), **args)
    assert second.accepted == 0
    assert conn.execute("SELECT COUNT(*) n FROM cards").fetchone()["n"] == 1


def test_cost_cap_stops_the_run(conn, tmp_path):
    cfg = load_config({"DEEPSEEK_API_KEY": "k", "RECALL_MAX_COST_USD": "0.0"})
    path = make_pdf(tmp_path, "Sentence one here. " * 400)
    client = FakeLlmClient([json.dumps({"cards": []})] * 50)
    result = ingest_source(conn, cfg, client, user_id=1, topic_id=1, path=path,
                           embed=orthogonal_embed)
    assert result.stopped_early is True


def test_gen_run_records_tokens_and_cost(conn, tmp_path):
    path = make_pdf(tmp_path, TEXT)
    ingest_source(conn, CFG, FakeLlmClient(
        accept_all("What do pointers store?", "addresses", TEXT)),
        user_id=1, topic_id=1, path=path, embed=orthogonal_embed)
    row = conn.execute("SELECT prompt_tokens, cost_estimate FROM gen_runs").fetchone()
    assert row["prompt_tokens"] > 0
    assert row["cost_estimate"] > 0


def test_resume_skips_already_generated_chunks(conn, tmp_path):
    path = make_pdf(tmp_path, TEXT)
    ingest_source(conn, CFG, FakeLlmClient(
        accept_all("What do pointers store?", "addresses", TEXT)),
        user_id=1, topic_id=1, path=path, embed=orthogonal_embed)
    assert conn.execute(
        "SELECT COUNT(*) n FROM chunks WHERE generated_at IS NULL"
    ).fetchone()["n"] == 0


def test_cards_are_split_between_arms():
    assert {assign_arm(i) for i in range(50)} == {"learned", "baseline"}
