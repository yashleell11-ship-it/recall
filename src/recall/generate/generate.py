import json
from dataclasses import dataclass

from recall.generate.prompts import GENERATE_SYSTEM, GENERATE_USER
from recall.ingest.chunk import Chunk

_VALID_KINDS = {"qa", "cloze"}


@dataclass(frozen=True)
class Candidate:
    kind: str
    question: str
    answer: str
    cloze_text: str | None = None


def _parse(raw: str) -> list[Candidate]:
    """Malformed model output is expected, not exceptional. Drop it, never raise."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    out: list[Candidate] = []
    for item in data.get("cards") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        question = (item.get("question") or "").strip()
        answer = (item.get("answer") or "").strip()
        cloze_text = (item.get("cloze_text") or "").strip() or None
        if kind not in _VALID_KINDS or not question or not answer:
            continue
        if kind == "cloze" and not cloze_text:
            continue
        out.append(Candidate(kind, question, answer, cloze_text))
    return out


def generate_cards(client, chunk: Chunk, n: int = 5
                   ) -> tuple[list[Candidate], int, int]:
    resp = client.complete_json(
        GENERATE_SYSTEM,
        GENERATE_USER.format(page_ref=chunk.page_ref, text=chunk.text, n=n),
    )
    return _parse(resp.content), resp.prompt_tokens, resp.completion_tokens
