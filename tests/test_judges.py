import json

from recall.generate.generate import Candidate
from recall.ingest.chunk import Chunk
from recall.llm.fake import FakeLlmClient
from recall.verify.judges import check_closed_book, check_grounded

CHUNK = Chunk(0, "Quicksort has average time complexity O(n log n). "
                 "Its worst case is O(n^2).", "p4")
CARD = Candidate("qa", "Average time complexity of quicksort?", "O(n log n)")


def test_grounded_passes_when_quote_is_in_chunk():
    body = json.dumps({"supported": True,
                       "quote": "Quicksort has average time complexity O(n log n)."})
    assert check_grounded(FakeLlmClient([body]), CHUNK, CARD)[0] is None


def test_grounded_rejects_when_model_says_unsupported():
    body = json.dumps({"supported": False, "quote": ""})
    assert check_grounded(FakeLlmClient([body]), CHUNK, CARD)[0] == \
        "not supported by the source passage"


def test_grounded_rejects_fabricated_quote_even_when_model_claims_support():
    body = json.dumps({"supported": True,
                       "quote": "Quicksort is always O(n) in every case."})
    assert check_grounded(FakeLlmClient([body]), CHUNK, CARD)[0] == \
        "cited quote does not appear in the source passage"


def test_grounded_quote_match_ignores_whitespace_differences():
    body = json.dumps({"supported": True,
                       "quote": "Quicksort   has average\ntime complexity O(n log n)."})
    assert check_grounded(FakeLlmClient([body]), CHUNK, CARD)[0] is None


def test_grounded_rejects_malformed_judge_output():
    assert check_grounded(FakeLlmClient(["garbage"]), CHUNK, CARD)[0] == \
        "groundedness judge returned unusable output"


def test_closed_book_rejects_when_model_answers_correctly_without_source():
    body = json.dumps({"answer": "O(n log n)", "confident": True})
    assert check_closed_book(FakeLlmClient([body]), CARD)[0] == \
        "answerable without the course material"


def test_closed_book_passes_when_model_is_wrong():
    body = json.dumps({"answer": "O(n!) probably", "confident": True})
    assert check_closed_book(FakeLlmClient([body]), CARD)[0] is None


def test_closed_book_passes_when_model_is_unconfident():
    body = json.dumps({"answer": "O(n log n)", "confident": False})
    assert check_closed_book(FakeLlmClient([body]), CARD)[0] is None


def test_closed_book_fails_open_on_malformed_output():
    assert check_closed_book(FakeLlmClient(["not json"]), CARD)[0] is None


def test_closed_book_does_not_send_the_chunk():
    fake = FakeLlmClient([json.dumps({"answer": "x", "confident": False})])
    check_closed_book(fake, CARD)
    _system, user = fake.calls[0]
    assert "average time complexity O(n log n)" not in user
