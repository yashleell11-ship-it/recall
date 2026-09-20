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

#: How many questions an attempt may draw. "full" is every active question in
#: the chosen units; the numbers are capped at what is available, so asking for
#: 30 out of a bank of 12 is a 12-question attempt and not an error.
LENGTHS: tuple = (30, 60, "full")


__all__ = ["MCQ_UNITS", "LENGTHS"]
