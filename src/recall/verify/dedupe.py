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
) -> tuple[list[Candidate], list[tuple[Candidate, str]]]:
    if not cards:
        return [], []
    vectors = embed([c.question for c in cards])
    kept: list[Candidate] = []
    kept_vectors: list[np.ndarray] = []
    dropped: list[tuple[Candidate, str]] = []
    for card, vector in zip(cards, vectors):
        match = next(
            (i for i, kv in enumerate(kept_vectors) if _cosine(vector, kv) >= threshold),
            None,
        )
        if match is None:
            kept.append(card)
            kept_vectors.append(vector)
        else:
            dropped.append((card, f"duplicate of: {kept[match].question}"))
    return kept, dropped
