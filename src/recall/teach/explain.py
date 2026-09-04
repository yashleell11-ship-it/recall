"""Grounded explanations of cards that were answered wrongly.

Same discipline as the groundedness gate in recall.verify.judges: the model must
cite verbatim and the citation is checked here, in Python. An explanation whose
quote we cannot find in the source chunk is never shown — a fluent explanation of
something the syllabus does not say is worse than no explanation at all.

Explanations are cached by card id. They cost money, and the cards a person keeps
getting wrong are exactly the ones they will ask about again.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from recall.teach.prompts import EXPLAIN_SYSTEM, EXPLAIN_USER


@dataclass(frozen=True)
class Explanation:
    explanation: str
    source_quote: str
    page_ref: str
    topic_code: str
    cached: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    """Whitespace and case only. A quote that differs by a line break is still a
    real citation; one that differs by a word is a paraphrase, and paraphrase is
    exactly what the check exists to catch."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _loads(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _card_row(conn, user_id: int, card_id: int):
    return conn.execute(
        "SELECT c.id, c.question, c.answer, ch.text AS chunk_text, ch.page_ref,"
        " t.code AS topic_code"
        " FROM cards c"
        " JOIN chunks ch ON ch.id = c.chunk_id"
        " JOIN topics t ON t.id = c.topic_id"
        " WHERE c.id = ? AND t.user_id = ?",
        (card_id, user_id),
    ).fetchone()


def cached_explanation(conn, user_id: int, card_id: int) -> Explanation | None:
    row = conn.execute(
        "SELECT e.explanation, e.source_quote, ch.page_ref, t.code AS topic_code"
        " FROM card_explanations e"
        " JOIN cards c ON c.id = e.card_id"
        " JOIN chunks ch ON ch.id = c.chunk_id"
        " JOIN topics t ON t.id = c.topic_id"
        " WHERE e.card_id = ? AND t.user_id = ?",
        (card_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return Explanation(row["explanation"], row["source_quote"], row["page_ref"],
                       row["topic_code"], cached=True)


def explain_card(conn, client, *, user_id: int, card_id: int,
                 model: str) -> Explanation:
    """Raises LookupError for an unknown card and ValueError with a plain reason
    when the model's output cannot be trusted. The caller maps those to 404/422."""
    card = _card_row(conn, user_id, card_id)
    if card is None:
        raise LookupError(f"no card {card_id}")

    hit = cached_explanation(conn, user_id, card_id)
    if hit is not None:
        return hit

    resp = client.complete_json(
        EXPLAIN_SYSTEM,
        EXPLAIN_USER.format(text=card["chunk_text"], question=card["question"],
                            answer=card["answer"]),
    )
    data = _loads(resp.content)
    if data is None:
        raise ValueError("the explanation model returned unusable output")

    explanation, quote = data.get("explanation"), data.get("quote")
    if not isinstance(explanation, str) or not isinstance(quote, str):
        raise ValueError("the explanation model returned unusable output")
    explanation, quote = explanation.strip(), quote.strip()
    if not explanation:
        raise ValueError("the explanation model returned an empty explanation")
    if not quote or _normalize(quote) not in _normalize(card["chunk_text"]):
        raise ValueError("cited quote does not appear in the source passage")

    conn.execute(
        "INSERT INTO card_explanations (card_id, explanation, source_quote, model,"
        " created_at) VALUES (?,?,?,?,?)"
        " ON CONFLICT(card_id) DO UPDATE SET explanation=excluded.explanation,"
        " source_quote=excluded.source_quote, model=excluded.model,"
        " created_at=excluded.created_at",
        (card_id, explanation, quote, model, _now()),
    )
    conn.commit()
    return Explanation(explanation, quote, card["page_ref"], card["topic_code"],
                       cached=False)
