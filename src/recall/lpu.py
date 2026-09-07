"""LPU Semester-1 (B.Tech CSE AI/ML, 2026 batch) subject registry.

Sources: lpu.in programme structure + notes.lpuverto.xyz per-course pages,
fetched 2026-09-05; MTH165 corrected 2026-09-07 directly from the owner's own
LPU zero-lecture slides (the original MTH174 guess had the wrong course code
and scheme). Schemes genuinely differ per subject — INT108 and CSE326 carry
NO mid-term at LPU, so the app must not offer one for them.

Global LPU conventions this encodes:
- Theory scheme: Attendance 5 + CA (best 2 of 3, 30-mark tests) + MTE + ETE.
- MTE covers units 1-3, paper marked out of 40 and scaled to its weight.
- ETE covers all six units; on MCQ courses the pattern is 45 questions:
  5 each from units 1-3 and 10 each from units 4-6, so roughly two thirds
  of the paper is post-MTE material.
"""

SUBJECTS: dict[str, dict] = {
    "MTH165": {
        "full_name": "Mathematics for Engineers",
        "credits": 4,
        "units": ["Linear Algebra", "Differential Calculus and Its Applications",
                  "Fundamentals of Integral Calculus", "Multivariate Functions",
                  "Multivariate Integrals", "Fourier Series"],
        "scheme": {"attendance": 5, "ca": 25, "mte": 20, "ete": 50},
        "ca_policy": "CT1 units 1-2 · CT2 real-time applications (unit 4) · "
                      "CT3 cumulative over the CA1+CA2 syllabus — 30 marks each",
        "mte_exists": True,
        "exam_format": "mixed",
    },
    "CSE111": {
        "full_name": "Orientation to Computing",
        "credits": 2,
        "units": ["Computer Languages", "Computer Fundamentals",
                  "Computer Hardware", "Number Systems", "Version Control",
                  "Modern AI Trends and Tools"],
        "scheme": {"attendance": 5, "ca": 95, "mte": 0, "ete": 0},
        "ca_policy": "CA-driven low-credit course; unit-wise MCQ + subjective practice",
        "mte_exists": False,
        "exam_format": "mcq",
    },
    "INT108": {
        "full_name": "Python Programming",
        "credits": 4,
        "units": ["Environment, Variables, Expressions and Statements",
                  "Conditional and Iterative Statements",
                  "Strings, Lists, Tuples and Dictionaries",
                  "Functions and Recursion",
                  "Classes, Objects and OOP Terminology",
                  "Files, Exceptions and Regular Expressions"],
        "scheme": {"attendance": 5, "ca": 50, "mte": 0, "ete": 45},
        "ca_policy": "Best 3 of 4 · code-based tests + programming practice",
        "mte_exists": False,
        "exam_format": "practical",
    },
    "INT335": {
        "full_name": "Design Thinking",
        "credits": 3,
        "units": ["Foundations of Learning, Creativity and Design Thinking",
                  "Empathy, Observation and Problem Identification",
                  "Ideation and Creative Problem Solving",
                  "Product Design and Prototyping",
                  "Testing, Validation and Customer Experience",
                  "Innovation Project, Re-Design and Product Presentation"],
        "scheme": {"attendance": 5, "ca": 25, "mte": 20, "ete": 50},
        "ca_policy": "Best 2 of 3 · MCQ test, group project, situation assignment",
        "mte_exists": True,
        "exam_format": "mcq",
    },
    "CSE326": {
        "full_name": "Internet Programming",
        "credits": 2,
        "units": ["HTML Fundamentals", "Semantic HTML and Forms",
                  "Cascading Style Sheets", "JavaScript Fundamentals",
                  "Interactive Web Development",
                  "Web Application Development and Deployment"],
        "scheme": {"attendance": 5, "ca": 45, "mte": 0, "ete": 50},
        "ca_policy": "Best 2 of 3 · project, MCQ test, BYOD practical + viva",
        "mte_exists": False,
        "exam_format": "mixed",
    },
}

# The app's earlier ad-hoc codes map onto the real LPU codes. MTH174 was itself
# a wrong guess — the owner's own zero-lecture slides confirm the real code is
# MTH165 — so it renames the same way a legacy ad-hoc code would, preserving
# every existing card/review against the topic id.
LEGACY_RENAMES = {"MATHS": "MTH174", "HTML": "CSE326", "MTH174": "MTH165"}

# MEC103 (Engineering Graphics) is a real Sem-1 course confirmed from the
# owner's own "UNIT 1 MEC103.pdf" — Unit 1 covers Drawing Instruments and Line
# Types — but that file only carries Unit 1. Credits, L-T-P, the other 5
# units, and the CA/MTE/ETE weight split are NOT yet confirmed from any
# source. Deliberately not added to SUBJECTS below: guessing a scheme in an
# exam-prep tool (e.g. inventing whether an MTE exists) is actively worse than
# the subject not existing yet. Add it once the owner supplies MEC103's own
# zero-lecture, following the exact shape of the other entries.
