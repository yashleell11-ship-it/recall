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
