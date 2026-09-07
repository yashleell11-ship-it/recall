"""Paid verification gates.

Groundedness fails CLOSED: a card we cannot verify is not trusted.
Closed-book fails OPEN: its only job is removing trivia, and a judge outage
must not silently delete good cards.
Fact check fails OPEN on an outage and CLOSED on a verdict: it is the only
thing looking at a knowledge-mode card, so a card it calls wrong is dropped,
but a broken checker does not delete work the student paid for.
"""

import json
import re

from recall.generate.generate import Candidate
from recall.generate.unit_guidance import traps_text
from recall.ingest.chunk import Chunk
from recall.verify.prompts import (
    CLOSED_BOOK_SYSTEM,
    CLOSED_BOOK_USER,
    FACT_CHECK_SYSTEM,
    FACT_CHECK_USER,
    GROUNDED_SYSTEM,
    GROUNDED_USER,
)

_OVERLAP_THRESHOLD = 0.6


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _loads(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def check_grounded(client, chunk: Chunk, c: Candidate
                   ) -> tuple[str | None, int, int]:
    resp = client.complete_json(
        GROUNDED_SYSTEM,
        GROUNDED_USER.format(text=chunk.text, question=c.question, answer=c.answer),
    )
    tokens = (resp.prompt_tokens, resp.completion_tokens)
    data = _loads(resp.content)
    if data is None or "supported" not in data:
        return ("groundedness judge returned unusable output", *tokens)
    if not data.get("supported"):
        return ("not supported by the source passage", *tokens)
    # The judge must cite verbatim, and we check the citation ourselves. This
    # is the part of the gate that cannot be talked out of.
    quote = _normalize(str(data.get("quote", "")))
    if not quote or quote not in _normalize(chunk.text):
        return ("cited quote does not appear in the source passage", *tokens)
    return (None, *tokens)


def _answers_agree(model_answer: str, card_answer: str) -> bool:
    a = set(_normalize(model_answer).split())
    b = set(_normalize(card_answer).split())
    if not b:
        return False
    return len(a & b) / len(b) >= _OVERLAP_THRESHOLD


def check_closed_book(client, c: Candidate) -> tuple[str | None, int, int]:
    resp = client.complete_json(
        CLOSED_BOOK_SYSTEM, CLOSED_BOOK_USER.format(question=c.question)
    )
    tokens = (resp.prompt_tokens, resp.completion_tokens)
    data = _loads(resp.content)
    if data is None:
        return (None, *tokens)
    if data.get("confident") and _answers_agree(str(data.get("answer", "")), c.answer):
        return ("answerable without the course material", *tokens)
    return (None, *tokens)


def _listed(i: int, c: Candidate) -> str:
    """One card as the checker sees it. The detail is included because it is
    what the student actually reads after answering, and a wrong explanation
    of a right answer still teaches the wrong thing."""
    lines = [f"[{i}] Q: {c.question}", f"    A: {c.answer}"]
    if c.detail:
        lines.append(f"    detail: {c.detail}")
    return "\n".join(lines)


def check_facts(client, cards: list[Candidate], *, topic_code: str,
                full_name: str, unit_name: str, unit_number: int | None = None
                ) -> tuple[list[tuple[Candidate, str | None]], int, int]:
    """Fact-check a batch of knowledge-mode cards in one paid call.

    Returns ``[(card, reason_or_None), ...]`` in the order given, plus the
    tokens spent. A reason means "do not keep this one".

    This exists because knowledge cards have neither of the two things that
    make an upload-grounded card trustworthy: no passage to check them
    against, and no longer a human reading them before they enter the deck.
    Something has to look, so this does.

    FAILS OPEN, deliberately. If the checker call itself errors or returns
    junk, the cards are kept rather than destroyed: the student has already
    paid for the generation, and losing all of it to a transient 500 is a
    worse outcome than keeping a batch that went unchecked once. Cards the
    checker explicitly calls wrong are dropped — that part fails closed.
    """
    if not cards:
        return [], 0, 0

    listing = "\n".join(_listed(i, c) for i, c in enumerate(cards))
    traps = (traps_text(topic_code, unit_number)
             if unit_number is not None else "")
    resp = client.complete_json(
        FACT_CHECK_SYSTEM,
        FACT_CHECK_USER.format(topic_code=topic_code, full_name=full_name,
                               unit_name=unit_name, traps=traps, cards=listing),
    )
    tokens = (resp.prompt_tokens, resp.completion_tokens)
    data = _loads(resp.content)
    if data is None:
        return [(c, None) for c in cards], *tokens

    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list):
        return [(c, None) for c in cards], *tokens

    flagged: dict[int, str] = {}
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        i, status = v.get("i"), str(v.get("status", "")).lower()
        if not isinstance(i, int) or not 0 <= i < len(cards):
            continue
        if status == "wrong":
            why = str(v.get("why") or "").strip()
            flagged[i] = (f"fact check: {why}" if why
                          else "fact check: the answer is wrong")
        elif status == "unsure":
            flagged[i] = "fact check: could not be verified"

    return [(c, flagged.get(i)) for i, c in enumerate(cards)], *tokens
