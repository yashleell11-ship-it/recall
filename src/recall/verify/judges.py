"""Paid verification gates.

Groundedness fails CLOSED: a card we cannot verify is not trusted.
Closed-book fails OPEN: its only job is removing trivia, and a judge outage
must not silently delete good cards.
"""

import json
import re

from recall.generate.generate import Candidate
from recall.ingest.chunk import Chunk
from recall.verify.prompts import (
    CLOSED_BOOK_SYSTEM,
    CLOSED_BOOK_USER,
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
