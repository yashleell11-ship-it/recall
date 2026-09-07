"""Ingest orchestration.

Gate order is cheapest-first, and that is a cost decision rather than a style
one: a card killed by a free regex never reaches a paid judge.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timezone

from recall.config import Config
from recall.generate.generate import Candidate, generate_cards
from recall.ingest.chunk import Chunk, chunk_pages
from recall.ingest.pdf import document_kind, file_sha256, read_document
from recall.verify.dedupe import dedupe, embed_texts
from recall.verify.heuristics import check_answerable, check_atomic
from recall.verify.judges import check_closed_book, check_grounded


@dataclass(frozen=True)
class IngestResult:
    source_id: int
    accepted: int
    rejected: int
    cost_usd: float
    stopped_early: bool


def assign_arm(seed: int) -> str:
    """Per-card control arm, assigned within a user so motivation cancels out."""
    return random.Random(seed).choice(["learned", "baseline"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cost(cfg: Config, prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens / 1_000_000) * cfg.price_input_per_mtok + (
        completion_tokens / 1_000_000
    ) * cfg.price_output_per_mtok


_ORIGINS = ("upload", "knowledge")


def keep_state(origin: str) -> str:
    """What a surviving card is worth on the way in.

    Always 'active' now: there is no approval queue. Triage before use was
    judgement exercised at the moment you had the least information — thirty
    cards to read before you could study any of them, and no way to tell the
    good from the bad until you had actually tried to answer them.

    The checking did not go away, it moved into the pipeline. Upload-grounded
    cards clear five gates including a Python-verified verbatim quote.
    Knowledge cards have no passage to quote, so they clear a fact check
    instead (recall.verify.judges.check_facts) — the model reading its own
    batch back and dropping what it can see is wrong. Whatever survives that
    is still marked "no source" on screen, still gets graded 'again' when it
    is bad, still surfaces as a leech, and can still be suspended with one
    key. The evidence for a card is how it behaves in review; that is where
    the judgement belongs.
    """
    return "active"


def _insert_card(conn, chunk_id, topic_id, c: Candidate, state, reason, arm,
                 origin: str = "upload") -> None:
    """`origin` defaults to 'upload' so every existing call site is unchanged;
    only recall.generate.knowledge passes anything else."""
    if origin not in _ORIGINS:
        raise ValueError(f"origin must be one of {_ORIGINS}")
    conn.execute(
        "INSERT INTO cards (chunk_id, topic_id, kind, question, answer, cloze_text,"
        " arm, state, reject_reason, created_at, origin, detail)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (chunk_id, topic_id, c.kind, c.question, c.answer, c.cloze_text,
         arm, state, reason, _now(), origin, c.detail),
    )


def ingest_source(conn, cfg: Config, client, *, user_id: int, topic_id: int,
                  path: str, embed=embed_texts) -> IngestResult:
    sha = file_sha256(path)
    existing = conn.execute(
        "SELECT id FROM sources WHERE user_id = ? AND sha256 = ?", (user_id, sha)
    ).fetchone()
    if existing:
        return IngestResult(existing["id"], 0, 0, 0.0, False)

    cur = conn.execute(
        "INSERT INTO sources (user_id, topic_id, filename, kind, sha256, added_at)"
        " VALUES (?,?,?,?,?,?)",
        (user_id, topic_id, path, document_kind(path), sha, _now()),
    )
    source_id = cur.lastrowid

    for ch in chunk_pages(read_document(path)):
        conn.execute(
            "INSERT INTO chunks (source_id, ordinal, text, page_ref) VALUES (?,?,?,?)",
            (source_id, ch.ordinal, ch.text, ch.page_ref),
        )
    conn.commit()

    accepted = rejected = 0
    prompt_tokens = completion_tokens = 0
    stopped_early = False

    rows = conn.execute(
        "SELECT id, ordinal, text, page_ref FROM chunks"
        " WHERE source_id = ? AND generated_at IS NULL ORDER BY ordinal",
        (source_id,),
    ).fetchall()

    for row in rows:
        if _cost(cfg, prompt_tokens, completion_tokens) >= cfg.max_cost_usd_per_source:
            stopped_early = True
            break

        chunk = Chunk(row["ordinal"], row["text"], row["page_ref"])
        candidates, pt, ct = generate_cards(client, chunk)
        prompt_tokens += pt
        completion_tokens += ct

        survivors: list[Candidate] = []
        for c in candidates:
            reason = check_answerable(c) or check_atomic(c)
            if reason is None:
                reason, pt, ct = check_grounded(client, chunk, c)
                prompt_tokens += pt
                completion_tokens += ct
            if reason is None:
                reason, pt, ct = check_closed_book(client, c)
                prompt_tokens += pt
                completion_tokens += ct
            if reason is None:
                survivors.append(c)
            else:
                _insert_card(conn, row["id"], topic_id, c, "rejected", reason,
                             "learned")
                rejected += 1

        kept, dropped = dedupe(survivors, embed=embed)
        for c, reason in dropped:
            _insert_card(conn, row["id"], topic_id, c, "rejected", reason, "learned")
            rejected += 1
        for c in kept:
            _insert_card(conn, row["id"], topic_id, c, keep_state("upload"), None,
                         assign_arm(accepted))
            accepted += 1

        # Commit per chunk: a rate limit or crash leaves finished work intact.
        conn.execute("UPDATE chunks SET generated_at = ? WHERE id = ?",
                     (_now(), row["id"]))
        conn.commit()

    cost = _cost(cfg, prompt_tokens, completion_tokens)
    conn.execute(
        "INSERT INTO gen_runs (source_id, ran_at, model, prompt_tokens,"
        " completion_tokens, cost_estimate, cards_accepted, cards_rejected)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (source_id, _now(), cfg.model, prompt_tokens, completion_tokens, cost,
         accepted, rejected),
    )
    conn.commit()
    return IngestResult(source_id, accepted, rejected, cost, stopped_early)
