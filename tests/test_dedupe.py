import numpy as np

from recall.generate.generate import Candidate
from recall.verify.dedupe import dedupe


def qa(q):
    return Candidate("qa", q, "answer")


def fake_embed(vectors_by_text):
    def embed(texts):
        return np.array([vectors_by_text[t] for t in texts], dtype=float)
    return embed


def test_identical_vectors_are_deduplicated():
    a, b = qa("What is quicksort's average complexity?"), qa("How fast is quicksort?")
    embed = fake_embed({a.question: [1.0, 0.0], b.question: [1.0, 0.0]})
    kept, dropped = dedupe([a, b], embed=embed)
    assert kept == [a]
    assert dropped[0][0] == b
    assert "duplicate" in dropped[0][1]


def test_orthogonal_vectors_are_both_kept():
    a, b = qa("What is quicksort?"), qa("What is a red-black tree?")
    embed = fake_embed({a.question: [1.0, 0.0], b.question: [0.0, 1.0]})
    kept, dropped = dedupe([a, b], embed=embed)
    assert kept == [a, b]
    assert dropped == []


def test_threshold_is_respected():
    a, b = qa("Question one here"), qa("Question two here")
    embed = fake_embed({a.question: [1.0, 0.0], b.question: [0.94, 0.34]})
    assert len(dedupe([a, b], embed=embed, threshold=0.99)[0]) == 2
    assert len(dedupe([a, b], embed=embed, threshold=0.90)[0]) == 1


def test_first_card_always_survives():
    a, b, c = qa("First one here"), qa("Second one here"), qa("Third one here")
    v = {a.question: [1.0, 0.0], b.question: [1.0, 0.0], c.question: [1.0, 0.0]}
    kept, dropped = dedupe([a, b, c], embed=fake_embed(v))
    assert kept == [a]
    assert len(dropped) == 2


def test_empty_input():
    assert dedupe([], embed=lambda t: np.zeros((0, 2))) == ([], [])
