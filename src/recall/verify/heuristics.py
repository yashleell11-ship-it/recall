"""Free verification gates. These run first so a bad card never costs money."""

import re

from recall.generate.generate import Candidate

_ESSAY_OPENERS = re.compile(
    r"^\s*(discuss|explain in detail|describe in detail|list all|"
    r"write a note|elaborate|comment on)\b",
    re.IGNORECASE,
)
_CLOZE_TAG = re.compile(r"\{\{c(\d+)::")
_MAX_ANSWER_WORDS = 40
_MIN_QUESTION_CHARS = 12

# A card is read weeks later with nothing else on screen. A question that
# points at material that is not in front of you cannot be answered at all.
#
# This is not hypothetical: four of the first eleven cards this app ever put
# into a real deck were "What is the formula for the elements of the 3×3
# matrix A in Q1?", "In Q6, what is the expression for A^n...", "In Q12, what
# are the unit sale prices...", and "...the matrix B in the passage". All four
# were generated from a tutorial sheet, all four passed every other gate, and
# all four are unanswerable away from that sheet. The prompt now forbids this;
# this is the part that enforces it, for free, before anything is paid for.
_DANGLING_REFERENCE = re.compile(
    # "in Q1?" / "In Q6," — a pointer ENDS its clause. Deliberately not
    # "the value of Q1 in a five-number summary", where Q1 is a quartile and
    # the phrase runs on: the trailing punctuation is what separates a
    # reference to a question from a term that happens to be spelled Q-digit.
    r"\b(?:in|from|per|see)\s+Q\.?\s*\d+\s*(?=[,.;:?!]|$)"
    r"|\bQ\.?\s*\d+\s*(?:above|below)"                  # "Q6 above"
    r"|\bthe\s+(?:passage|text|excerpt|source|extract|snippet)\b"
    r"|\bthe\s+(?:figure|diagram|table|graph|image)\s+(?:above|below|shown|given)"
    r"|\b(?:above|below)\s+(?:passage|text|question|figure|diagram|table)\b"
    r"|\bas\s+(?:shown|given|stated|defined)\s+(?:above|below|in\s+the\s+(?:passage|text|figure))"
    r"|\bthis\s+(?:passage|excerpt|extract)\b",
    re.IGNORECASE,
)


def check_answerable(c: Candidate) -> str | None:
    if len(c.question.strip()) < _MIN_QUESTION_CHARS:
        return "question too short to be unambiguous"
    if _ESSAY_OPENERS.search(c.question):
        return "essay prompt, not a recall question"
    match = _DANGLING_REFERENCE.search(c.question)
    if match:
        return (f"question points at material that is not on the card "
                f"({match.group(0).strip()!r}), so it cannot be answered alone")
    if len(c.answer.split()) > _MAX_ANSWER_WORDS:
        return f"answer longer than {_MAX_ANSWER_WORDS} words"
    return None


def check_atomic(c: Candidate) -> str | None:
    if c.question.count("?") > 1:
        return "more than one question"
    if re.search(r"\bwhat\b.*\band\b.*\bwhat\b", c.question, re.IGNORECASE):
        return "compound question covering two facts"
    if ";" in c.answer:
        return "answer contains multiple clauses"
    if c.cloze_text and len(set(_CLOZE_TAG.findall(c.cloze_text))) > 1:
        return "cloze card hides more than one span"
    return None
