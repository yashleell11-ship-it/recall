import json

from recall.generate.generate import generate_cards
from recall.ingest.chunk import Chunk
from recall.llm.fake import FakeLlmClient

CHUNK = Chunk(0, "Quicksort has average time complexity O(n log n).", "p4")


def test_parses_qa_and_cloze_cards():
    body = json.dumps({"cards": [
        {"kind": "qa", "question": "Average complexity of quicksort?",
         "answer": "O(n log n)"},
        {"kind": "cloze", "question": "Quicksort complexity", "answer": "O(n log n)",
         "cloze_text": "Quicksort averages {{c1::O(n log n)}}."},
    ]})
    cards, pt, ct = generate_cards(FakeLlmClient([body]), CHUNK)
    assert [c.kind for c in cards] == ["qa", "cloze"]
    assert cards[1].cloze_text.startswith("Quicksort averages")
    assert (pt, ct) == (10, 20)


def test_chunk_text_reaches_the_prompt():
    fake = FakeLlmClient([json.dumps({"cards": []})])
    generate_cards(fake, CHUNK)
    _system, user = fake.calls[0]
    assert "Quicksort has average time complexity" in user


def test_prompt_mentions_json_for_deepseek_json_mode():
    fake = FakeLlmClient([json.dumps({"cards": []})])
    generate_cards(fake, CHUNK)
    system, _user = fake.calls[0]
    assert "json" in system.lower()


def test_malformed_json_yields_no_cards_and_does_not_raise():
    cards, _, _ = generate_cards(FakeLlmClient(["not json at all"]), CHUNK)
    assert cards == []


def test_cards_missing_required_fields_are_dropped():
    body = json.dumps({"cards": [
        {"kind": "qa", "question": "Only a question"},
        {"kind": "qa", "question": "Good?", "answer": "Yes"},
    ]})
    cards, _, _ = generate_cards(FakeLlmClient([body]), CHUNK)
    assert len(cards) == 1
    assert cards[0].answer == "Yes"


def test_unknown_kind_is_dropped():
    body = json.dumps({"cards": [{"kind": "essay", "question": "Discuss",
                                  "answer": "..."}]})
    assert generate_cards(FakeLlmClient([body]), CHUNK)[0] == []


def test_cloze_without_cloze_text_is_dropped():
    body = json.dumps({"cards": [{"kind": "cloze", "question": "q", "answer": "a"}]})
    assert generate_cards(FakeLlmClient([body]), CHUNK)[0] == []


def test_null_cards_key_is_survivable():
    assert generate_cards(FakeLlmClient([json.dumps({"cards": None})]), CHUNK)[0] == []
