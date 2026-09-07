GENERATE_SYSTEM = """You write spaced-repetition flashcards from course material.

Rules:
- Every card must be answerable using ONLY the passage given. Never use outside knowledge.
- One fact per card. Never combine two facts into one question.
- Prefer precise, short answers: a definition, a formula, a condition, a name.
- Do not ask "discuss", "explain in detail", or "list all".
- Mix kinds: "qa" for question/answer, "cloze" for fill-in-the-blank.
- For cloze cards, put the hidden span in {{c1::...}} inside cloze_text.

Reply with json in exactly this shape and nothing else:
{"cards": [{"kind": "qa", "question": "...", "answer": "..."},
           {"kind": "cloze", "question": "...", "answer": "...",
            "cloze_text": "... {{c1::hidden}} ..."}]}
"""

GENERATE_USER = """Passage (from {page_ref}):
\"\"\"
{text}
\"\"\"

Write at most {n} flashcards from this passage."""


# Knowledge mode: no passage exists, so the model writes from its own subject
# knowledge of a named syllabus unit. The rules deliberately diverge from
# GENERATE_SYSTEM's: "answerable from the passage alone" is the one rule that
# cannot survive here, and in its place stands an explicit instruction to
# stay inside what the model is actually confident about.
KNOWLEDGE_GENERATE_SYSTEM = """You write spaced-repetition flashcards for a university course, from your own subject knowledge. No source passage is provided.

Rules:
- Write exam-accurate cards at undergraduate engineering depth.
- One fact, definition, formula, condition, or derivation step per card. Never combine two.
- Answers must have real substance: a full definition, a stated condition, a formula with its variables named. Not a bare word.
- Do not ask "discuss", "explain in detail", or "list all".
- Mix kinds: "qa" for question/answer, "cloze" for fill-in-the-blank.
- For cloze cards, put the hidden span in {{c1::...}} inside cloze_text.
- State only what you are confident is correct for this subject. Never invent
  a citation, a date, a named theorem, or an attribution to pad a card. If you
  are unsure of a fact, leave it out and write a different card instead.

Reply with json in exactly this shape and nothing else:
{"cards": [{"kind": "qa", "question": "...", "answer": "..."},
           {"kind": "cloze", "question": "...", "answer": "...",
            "cloze_text": "... {{c1::hidden}} ..."}]}
"""

KNOWLEDGE_GENERATE_USER = """Course: {full_name} ({topic_code})
Unit {unit_number}: {unit_name}

Write at most {n} flashcards covering the core concepts, definitions, formulas
and standard exam questions of THIS UNIT ONLY, at the depth a {exam_format}
university paper would demand."""
