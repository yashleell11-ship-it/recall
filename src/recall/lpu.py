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
    "MEC103": {
        "full_name": "Engineering Graphics",
        "credits": 3,
        # Corrected 2026-09-07. The first version of this list put scales in
        # unit 2 and no projection anywhere in units 1-3 — which, since the
        # mid-term is units 1-3, would have examined the wrong half of the
        # subject. Two independent sources killed it: LPU's own published
        # MEC103 course deck, whose applications section labels all six units
        # in this order, and the owner's own "UNIT 1 MEC103.pdf", which runs
        # instruments -> line types -> dimensioning -> lettering -> scales and
        # ends with four worked plain/diagonal-scale problems. Scales are
        # inside unit 1, so unit 1 is the whole introduction.
        #
        # Two placements are inferred rather than quoted: projection of solids
        # (appended to unit 3) and the conics (left in unit 1, and absent from
        # the owner's file). The deck is also 2014-era and a later
        # AutoCAD-bearing revision of MEC103 exists.
        "units": ["Introduction to Engineering Drawing: Instruments, Line Types,"
                  " Lettering, Dimensioning, Scales and Conic Sections",
                  "Projections of Points, Lines and Planes",
                  "Orthographic Projections (including Projection of Regular Solids)",
                  "Sectional Views",
                  "Development of Surfaces",
                  "Isometric Projections"],
        "scheme": {"attendance": 5, "ca": 25, "mte": 20, "ete": 50},
        "ca_policy": "Ten best of twelve graded drawing sheets, plus a class "
                     "test either side of the mid-term — the deck says CA 20 / "
                     "MTE 25 against the 25 / 20 coded here; unresolved",
        "mte_exists": True,
        "exam_format": "subjective",
        # The units are researched; the WEIGHTS are not confirmed for MEC103
        # specifically — they are the common LPU pattern, shown as a
        # placeholder. The UI says so rather than presenting them as fact,
        # because a wrong exam structure in an exam-prep tool is worse than an
        # absent one. Replace this with the zero-lecture's real numbers and
        # drop the flag.
        "scheme_confirmed": False,
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

#: Subjects whose CA/MTE/ETE weights came from a real source (the owner's own
#: zero-lecture slides, or the published course pages) default to confirmed.
#: Only MEC103 carries scheme_confirmed=False today.
DEFAULT_SCHEME_CONFIRMED = True

# The app's earlier ad-hoc codes map onto the real LPU codes. MTH174 was itself
# a wrong guess — the owner's own zero-lecture slides confirm the real code is
# MTH165 — so it renames the same way a legacy ad-hoc code would, preserving
# every existing card/review against the topic id.
LEGACY_RENAMES = {"MATHS": "MTH174", "HTML": "CSE326", "MTH174": "MTH165"}


