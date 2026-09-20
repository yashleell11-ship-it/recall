"""Which subjects and units the curated bank covers, and how long a sitting is.

Declared here rather than derived from what happens to be in the bank, so a
unit with nothing written yet still appears on the picker with a count of 0
and a "waiting for material" note. A unit that vanishes from a screen because
nobody has written its questions is indistinguishable, to the student, from a
unit that does not exist.

The unit numbers are the ones printed on the lecture decks, 1-based.
"""

#: subject_code -> {"label": str, "units": {unit_number: unit_label}}
MCQ_UNITS: dict[str, dict] = {
    "CSE111": {
        "label": "Orientation to Computing",
        "units": {
            1: "Computational Thinking & Computing Environment",
            2: "Version Control & Cyber Security Basics",
        },
    },
}

#: The ladder, hardest last. Order is load-bearing: `by_difficulty` on a result
#: is reported in this order, so a student reads their sitting as a climb
#: rather than as an alphabetical list ("easy, hard, max, medium" is nonsense).
#:
#:   easy   — one fact, stated directly in the material.
#:   medium — telling neighbours apart: which-is-NOT, ordering, the near miss.
#:   hard   — applying the idea to a short realistic scenario.
#:   max    — the hardest FAIR tier: a trap-adjacent scenario, two concepts
#:            joined, or a precise exception. Never a trick, never off-syllabus.
DIFFICULTIES: tuple = ("easy", "medium", "hard", "max")

#: The lengths the picker offers as one-tap presets. Not the limit: a student
#: may ask for any whole number between LENGTH_MIN and LENGTH_MAX, or "full"
#: for every active question in the selection. Every number is capped at what
#: is available, so asking for 30 out of a bank of 12 is a 12-question attempt
#: and not an error.
LENGTHS: tuple = (30, 60, "full")

#: The free-choice range. Five is the floor because a sitting shorter than that
#: is a coin toss the leaderboard would rank as a result; 200 is the ceiling
#: because it is the size of the bank and a sitting nobody finishes teaches
#: nothing.
LENGTH_MIN = 5
LENGTH_MAX = 200


__all__ = ["MCQ_UNITS", "LENGTHS", "LENGTH_MIN", "LENGTH_MAX", "DIFFICULTIES"]
