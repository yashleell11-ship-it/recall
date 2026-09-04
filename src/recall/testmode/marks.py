"""What a card is worth in a paper.

Marks are computed at assembly time from the card itself rather than stored on
the card, so an edited card is worth what it is worth today.
"""

# A 'partial' verdict has to be able to score a whole number of half-marks and
# has to mean something: there is no half of a one-word answer.
PARTIAL_MIN_MARKS = 2

_SHORT_ANSWER_WORDS = 4
_MEDIUM_ANSWER_WORDS = 12


def marks_for_card(kind: str, answer: str) -> int:
    """Marks for one card, per the table in docs/CONTRACT.md.

    cloze -> 1; qa -> 1 (<= 4 words), 2 (<= 12 words), 5 (longer).
    """
    if kind == "cloze":
        return 1
    if kind != "qa":
        raise ValueError(f"unknown card kind {kind!r}")
    words = len(answer.split())
    if words <= _SHORT_ANSWER_WORDS:
        return 1
    if words <= _MEDIUM_ANSWER_WORDS:
        return 2
    return 5
