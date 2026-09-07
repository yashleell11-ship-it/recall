"""Semantic dedup. The real embedder is isolated in one function so tests never
load a model and a library API change touches exactly one place."""

import numpy as np

from recall.generate.generate import Candidate

_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_model = None


def embed_texts(texts: list[str]) -> np.ndarray:
    """CPU-only ONNX embeddings, loaded lazily."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=_MODEL_NAME)
    return np.array(list(_model.embed(texts)), dtype=float)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if denom == 0.0 else float(np.dot(a, b) / denom)


def dedupe(
    cards: list[Candidate],
    embed=embed_texts,
    threshold: float = 0.90,
    seed_texts: list[str] | None = None,
) -> tuple[list[Candidate], list[tuple[Candidate, str]]]:
    """Drop near-duplicate questions.

    `seed_texts` are questions that already exist and are not up for keeping —
    a new card too close to one of them is dropped as a duplicate of it. The
    upload path needs none, because a chunk is generated from exactly once;
    knowledge mode does, because the same unit can be generated from again and
    again and the model will happily rewrite what it already wrote.

    Seeds and candidates are embedded in ONE call: the embedder is the
    expensive part, and two calls would double it for no reason.
    """
    if not cards:
        return [], []
    seeds = seed_texts or []
    vectors = embed(seeds + [c.question for c in cards])
    seed_vectors = list(vectors[: len(seeds)])
    card_vectors = vectors[len(seeds):]

    kept: list[Candidate] = []
    # Seeds occupy the comparison set from the start but are never "kept" —
    # they are already in the database.
    kept_vectors: list[np.ndarray] = list(seed_vectors)
    dropped: list[tuple[Candidate, str]] = []
    for card, vector in zip(cards, card_vectors):
        match = next(
            (i for i, kv in enumerate(kept_vectors) if _cosine(vector, kv) >= threshold),
            None,
        )
        if match is None:
            kept.append(card)
            kept_vectors.append(vector)
        else:
            prior = (seeds[match] if match < len(seeds)
                     else kept[match - len(seeds)].question)
            dropped.append((card, f"duplicate of: {prior}"))
    return kept, dropped
