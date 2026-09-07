"""Prompts for writing cards.

Two shapes, one card contract. Both ask for the same JSON, and both hold the
same line on what each field is for:

  question — what you are asked, cold.
  answer   — the RETRIEVAL TARGET. Short on purpose. `check_answerable`
             rejects anything over 40 words, and testmode/marks.py prices a
             question by this field's word count (<=4 words -> 1 mark,
             <=12 -> 2, longer -> 5). A long answer here does not read as
             "more thorough", it re-prices every paper the app assembles: make
             every answer 60 words and a 40-mark MTE becomes eight questions.
  detail   — the worked explanation, read AFTER the answer is revealed. This
             is where depth belongs, because by then retrieval has already
             been attempted and elaboration costs nothing.

Both come back in ONE completion, so detail is free — no second paid call.
"""

# --- what the paper actually looks like -------------------------------------
#
# A card for an objective mid-term and a card for a Python practical are not
# the same object, and a generic prompt writes the average of the two, which
# resembles neither. `exam_format` comes from the LPU subject registry.

_FORMAT_GUIDANCE = {
    "mcq": (
        "This paper is OBJECTIVE (MCQ). Favour cards with one exact, "
        "checkable answer: a definition, a value, a condition, the one term "
        "that names a thing, the single distinction between two lookalikes. "
        "Avoid anything whose answer is a paragraph."
    ),
    "practical": (
        "This is a PROGRAMMING course examined on code. Favour cards that "
        "run code in the head: what does this expression evaluate to, what "
        "does this snippet print, which error does this raise, what is the "
        "value after this line, what is the type. Put the snippet in the "
        "question. Prefer real semantics over vocabulary."
    ),
    "mixed": (
        "This paper mixes objective and subjective questions. Write both: "
        "exact-recall cards for the objective half, and cards whose answer is "
        "a stated condition, a formula with its symbols named, or the key "
        "step of a derivation for the subjective half."
    ),
    "subjective": (
        "This paper is written by hand. Favour cards that ask for a statement "
        "worth marks: a theorem's exact conditions, the formula and what each "
        "symbol means, the step that makes a derivation work."
    ),
}

_DEFAULT_GUIDANCE = _FORMAT_GUIDANCE["mixed"]


def format_guidance(exam_format: str | None) -> str:
    """The paper-shape paragraph for a subject, or the mixed default."""
    return _FORMAT_GUIDANCE.get((exam_format or "").strip().lower(),
                                _DEFAULT_GUIDANCE)


_CARD_CONTRACT = """Every card has four parts:
- "question": what you are asked, cold. Self-contained — it must make sense
  with no passage in front of you.
- "answer": the SHORT retrieval target. Under 25 words, ideally under 12. This
  is what you must produce from memory, and it is what the exam-paper builder
  prices in marks, so padding it is not thoroughness, it is damage.
- "detail": the worked explanation, read only AFTER answering. 40-140 words.
  If the answer is DERIVED — a calculation, an algebraic manipulation, a
  theorem applied to numbers, code traced by hand — SHOW THE WORKING as
  numbered steps, one per line, like this:

      1. Take the determinant of A − λI:  λ² − 5λ + 6 = 0
      2. Factor it:  (λ − 2)(λ − 3) = 0
      3. So the eigenvalues are λ = 2 and λ = 3.

  Each step says what you did and then shows the line you get, with the real
  numbers and symbols in it. Never describe a method in prose when you can
  carry it out. Finish with one line naming the mistake most likely to be made
  here.
  If the answer is a definition or a stated fact with nothing to derive, drop
  the steps and instead say what it is, why it is that, and that same likely
  mistake.
- "cloze_text": only for kind "cloze" — the sentence with the hidden span in
  {{c1::...}}.

Rules:
- One fact per card. Never combine two into one question.
- Do not ask "discuss", "explain in detail", or "list all".
- Mix kinds: "qa" for question/answer, "cloze" for fill-in-the-blank.
- Write mathematics the way it is written on paper, not the way it is typed
  into a machine. Use the real symbols — λ θ π ∫ ∑ √ ∞ ∂ Δ ± ≤ ≥ ≠ ≈ → ° —
  and real superscripts and subscripts where they exist: x², x³, xⁿ, A⁻¹,
  a₀, aₙ, f(x⁻). Write fractions as a/b, and set a long one on its own line
  if it needs the room.
  Never write LaTeX (\\frac{a}{b}, A^{-1}, \\lambda, \\int, $...$), never
  spell a Greek letter out as "lambda" or "theta", and never use programming
  operators for mathematics: no <=, >=, !=, ->, ==, and no * for multiply.
  Code cards are the exception — code is quoted exactly as it would be typed,
  operators and all.

Reply with json in exactly this shape and nothing else:
{"cards": [{"kind": "qa", "question": "...", "answer": "...", "detail": "..."},
           {"kind": "cloze", "question": "...", "answer": "...",
            "detail": "...", "cloze_text": "... {{c1::hidden}} ..."}]}"""


GENERATE_SYSTEM = """You write spaced-repetition flashcards from course material.

""" + _CARD_CONTRACT + """

GROUNDING — the rule that separates this from guessing:
Every FACT you state, in the answer and in the detail, must come from the
passage. Do not bring in facts the passage does not contain.

That is a rule about facts, not about thinking. You may carry out the working
the passage implies — do the algebra, take the derivative, run the loop, apply
the definition it gave you to the case it is asking about — even when the
passage does not spell that step out. Showing the work is wanted. Importing an
outside fact is not."""

GENERATE_USER = """Passage (from {page_ref}):
\"\"\"
{text}
\"\"\"

Write at most {n} flashcards from this passage."""


# --- knowledge mode: no passage exists --------------------------------------

KNOWLEDGE_GENERATE_SYSTEM = """You write spaced-repetition flashcards for a university course, from your own subject knowledge. No source passage is provided.

""" + _CARD_CONTRACT + """

Because nothing here can be checked against a source, accuracy is entirely on
you:
- State only what you are confident is correct for this course at this level.
- Never invent a citation, a date, a named theorem, or an attribution to make
  a card look authoritative.
- If you are unsure of a fact, leave it out and write a different card. A
  short deck of correct cards beats a long one with three wrong ones in it —
  a student will memorise whatever you write, mistakes included."""

KNOWLEDGE_GENERATE_USER = """Course: {full_name} ({topic_code})
Unit {unit_number}: {unit_name}

{format_guidance}
{unit_guidance}
{unit_examples}
Write at most {n} flashcards covering the core concepts, definitions, formulas
and standard exam questions of THIS UNIT ONLY, at the depth this paper
demands. Match the calibration examples above in depth and difficulty if any
were given — do not write something easier because it is more comfortable to
generate."""
