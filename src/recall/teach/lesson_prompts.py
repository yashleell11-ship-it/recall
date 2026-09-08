"""The prompt that writes a lesson for one syllabus unit.

A card asks you to remember something. A lesson has to make you able to do
something you could not do before, which is a different job and needs a
different shape: what the unit is for, the few things it actually turns on,
worked examples derived line by line, and a check you can fail.

Three things are spliced in rather than invented, and each is spliced in a
specific place for a reason:

- `UnitGuidance.guidance` goes to the WRITER. It is the researched paragraph
  about what this unit's examiners actually ask.
- Both `WorkedExample`s go to the WRITER as depth calibration. A paragraph can
  describe difficulty; only an example can show it. They are shown as SHAPE,
  not as subject matter to reproduce — the lesson must derive its own.
- `UnitGuidance.traps` go to the CHECKER, never the writer. That is
  unit_guidance.py's own documented law: telling a model "don't say X" is a
  reliable way to make it say X. A verification pass caught exactly that
  mistake already living in INT335's list.
"""

from recall.notation import NOTATION_LAW

#: How the lesson's worked examples should be shaped, by how the university
#: actually examines the subject (`topics.meta.exam_format`). One pipeline, not
#: six: the difference between teaching Fourier series and teaching design
#: thinking is a paragraph of instruction, not a separate codebase.
SHAPE_BY_FORMAT: dict[str, str] = {
    "mixed": (
        "This subject is examined by derivation. Every worked example must be a "
        "calculation carried out line by line, with the real numbers in it, "
        "ending in a specific answer a marker could tick."),
    "subjective": (
        "This subject is examined by written answers and drawings. Worked "
        "examples are procedures: the ordered steps of the construction or the "
        "argument, each step naming what is done and what it produces. Where "
        "the real answer is a drawing, say so plainly and teach the procedure "
        "and the conventions that get marks, rather than pretending prose can "
        "substitute for the sheet."),
    "mcq": (
        "This subject is examined by multiple choice and short scenarios. "
        "Worked examples are discriminations: a realistic situation, the two "
        "answers a student would be torn between, and the specific reason one "
        "is right. A definition restated is worth no marks here; knowing which "
        "of two near-identical options applies is."),
    "practical": (
        "This subject is examined by writing and reading code. Worked examples "
        "are traces: the code, then what each line does to the values, then the "
        "output. Put all code in backticks and quote it exactly as it would be "
        "typed — do not prettify its operators."),
}
DEFAULT_SHAPE = SHAPE_BY_FORMAT["mixed"]

LESSON_SYSTEM = """You are writing one lesson of a university course, for a first-year
B.Tech student at Lovely Professional University who is going to be examined on it.

You are not writing an encyclopedia article and not writing revision notes. You
are teaching: at the end the student must be able to do a question they could
not do before.

Reply with json only, exactly this shape:

{"why": "two sentences: what this unit lets you do, and how it is examined",
 "sections": [{"heading": "short", "body": "the teaching",
               "quote": "verbatim span from a supplied passage, or omitted
                         when no course material was supplied",
               "source": "which passage the quote came from"}],
 "worked": [{"question": "...", "steps": ["...", "..."], "answer": "..."}],
 "check": [{"question": "...", "answer": "...", "why": "..."}]}

THE SECTIONS. Three to five. Each one teaches a single idea the unit turns on,
in the order someone meeting it should meet them. Prose, not bullet points —
a bulleted list of terms is a glossary and teaches nobody. Define a symbol the
first time it appears. When there is a condition on a result, state it: most
marks lost in this subject are lost to a hypothesis nobody checked.

THE WORKED EXAMPLES. Exactly two, and they are the heart of the lesson. Each
one is a real question of the difficulty the actual paper asks, solved
completely. `steps` is the derivation, one step per entry, and each step says
what you did and then shows the line you get, with the real numbers and
symbols in it. "Apply the quotient rule" is not a step — the expression you
have after applying it is. The two must come from different corners of the
unit; two versions of one question teach one thing twice.

THE CHECK. Two or three questions the student answers themselves, each with
the answer and one line on what it tests. These are not the worked examples
with the numbers changed. They must be answerable from the lesson alone.

""" + NOTATION_LAW + """

Write plainly and directly to the student, as "you". No preamble, no praise,
no "in this lesson we will", no summary at the end, no markdown headings
inside a body, no emoji.

State only what you are confident is correct. If some corner of this unit is
one you are unsure of, leave it out — a lesson is read as authoritative, and a
confident wrong method is worse than a missing one."""

LESSON_USER = """Course: {topic_code} — {full_name}
Unit {unit_number} of {unit_count}: {unit_name}
The whole syllabus for context: {all_units}

{shape}
{guidance}{examples}
Write the lesson for unit {unit_number}: {unit_name}."""

GUIDANCE_PREFACE = """
What this unit's examiners actually ask, researched for this course:
{guidance}
"""

EXAMPLES_PREFACE = """
Two questions at the depth this unit is really examined at. They are here to
set the LEVEL and the SHAPE of your worked examples, not their subject: draw
yours from different corners of the unit, and do not reuse these.

{examples}
"""

PASSAGES_PREFACE = """
COURSE MATERIAL. These passages are from the reading list for this course. You
must teach FROM them.

Every section you write carries a `quote`: a span copied WORD FOR WORD from one
of these passages, supporting what that section teaches, and a `source` naming
which passage it came from. The quote is checked against the passages
character by character before the lesson is shown to anyone, so a paraphrase,
a tidied-up version, or a sentence you remember rather than copy will be
rejected.

Quote course material, never page furniture. A navigation bar, a "Reveal
Answer" button, a cookie notice or a table of contents may appear in a passage
because the page was scraped whole; none of them is teaching and a citation
backed by one is a claim backed by nothing. Those are rejected too.

Pick a quote that carries the load — the sentence that states the definition,
the condition, or the rule. Do not quote a heading, a figure caption, or a
sentence that merely mentions the topic. Twenty to forty words is usually
right.

Teach what the passages support. Where you need a step they do not cover —
arithmetic in a worked example, say — that is fine and needs no quote; the
quote belongs to the section that teaches the idea.

{passages}
"""

#: The re-derivation check. A fresh call gets only the question — never the
#: lesson's own derivation — and solves it cold. A plausible wrong derivation
#: survives "does this look right?", because the thing judging it is the thing
#: that wrote it; it rarely survives being independently re-solved and
#: compared. This catches wrong ANSWERS. It does not catch bad teaching, and
#: nothing cheap does.
REDERIVE_SYSTEM = """Solve the problem. Show nothing but the final answer.

Reply with json only: {"answer": "the final answer, as compactly as it can be
written"}

If the problem cannot be solved as stated — a missing hypothesis, an
underdetermined system, a contradiction — answer exactly "CANNOT SOLVE" and
nothing else. Do not guess at what was meant."""

REDERIVE_USER = """Course: {topic_code} — {full_name}, unit: {unit_name}

{question}"""
