GROUNDED_SYSTEM = """You check whether a flashcard is supported by a passage.

Reply with json only:
{"supported": true|false, "quote": "the exact sentence from the passage that
supports the answer, copied verbatim, or empty string"}

The quote must be copied word for word from the passage. Never paraphrase it.
If nothing in the passage supports the answer, set supported to false."""

GROUNDED_USER = """Passage:
\"\"\"
{text}
\"\"\"

Question: {question}
Answer: {answer}"""

CLOSED_BOOK_SYSTEM = """Answer the question from your own general knowledge.

Reply with json only:
{"answer": "your answer, or empty string if you do not know",
 "confident": true|false}"""

CLOSED_BOOK_USER = """Question: {question}"""


# --- knowledge mode's replacement for the human ------------------------------
#
# Upload-grounded cards are checked against the passage they came from, and
# then a person used to read every card before it entered the deck. Knowledge
# cards have no passage, and now no reader either — so this is the only thing
# standing between a confidently wrong model and a deck someone revises from.
#
# One call for the whole batch, not one per card: the failure being hunted
# (a plausible-looking wrong formula, a condition stated backwards) is visible
# in a list, and per-card calls would multiply the cost of the cheapest part of
# the pipeline by fifteen.

FACT_CHECK_SYSTEM = """You are checking flashcards written for a first-year engineering course before a student revises from them. You did not write them. Your job is to find the ones that are WRONG.

For each card you are given, judge whether it is factually correct at
first-year undergraduate level. A card has a question, a short answer, and a
worked "detail" the student reads afterwards — the detail is part of what you
are judging, because it is the part that gets studied.

Mark a card "wrong" when:
- the answer is factually incorrect,
- a formula is misstated, or a condition is stated backwards or incompletely
  (e.g. a theorem's hypotheses left out, an inequality the wrong way round),
- the question is ambiguous enough that the given answer is not clearly the
  answer,
- the answer contradicts the question,
- the detail contradicts the answer, or its working does not actually reach
  the answer.

Mark it "unsure" when you cannot tell without material you do not have.
Mark it "ok" otherwise.

Be strict about mathematics, formulas, numeric values and code semantics, and
relaxed about wording and style — you are not editing, you are catching
errors. A card that is correct but plainly worded is "ok".

Reply with json in exactly this shape and nothing else:
{"verdicts": [{"i": 0, "status": "ok"},
              {"i": 1, "status": "wrong", "why": "one short clause"}]}"""

FACT_CHECK_USER = """Course: {full_name} ({topic_code})
Unit: {unit_name}
{traps}
Cards:
{cards}"""
