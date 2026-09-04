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


def check_answerable(c: Candidate) -> str | None:
    if len(c.question.strip()) < _MIN_QUESTION_CHARS:
        return "question too short to be unambiguous"
    if _ESSAY_OPENERS.search(c.question):
        return "essay prompt, not a recall question"
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
