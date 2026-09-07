"""LPU Semester-1 (B.Tech CSE AI/ML, 2026 batch) subject registry.

Sources, in descending order of trust:

1. **LPU's own Session 2026-27 syllabus PDFs**, at
   notes.lpuverto.xyz/notes-syllabus/Sem1/26271/<CODE>/<CODE>_Syllabus.pdf.
   Five of the six subjects are there and were read directly on 2026-09-07:
   MTH165, INT108, CSE326, CSE111 and INT335. Each PDF's header line carries
   the L-T-P and the credits, and its Unit I..VI headings carry the unit
   names. Where this file disagreed with one, this file was wrong — CSE111
   was coded from an older 2-credit revision of the course, INT335's credits
   were a guess, and MTH165's unit names were a paraphrase.
2. **The owner's own course files** — his MTH165 zero-lecture slides (which
   is where the scheme comes from; the syllabus PDFs do not print one) and
   his UNIT 1 MEC103.pdf.
3. **notes.lpuverto.xyz per-course pages** for the assessment schemes, which
   the PDFs omit. Worth believing: the site carries five different schemes
   across these six subjects, so it is transcribing rather than defaulting.

MEC103 is the exception — it is not on that mirror under any path tried, so
it rests on the published LPU course deck plus the owner's own unit 1 file,
and carries scheme_confirmed=False to say so on screen.

Schemes genuinely differ per subject — INT108, CSE326 and CSE111 carry NO
mid-term at LPU, so the app must not offer one for them.

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
        # Verbatim from the Session 2026-27 syllabus PDF (header
        # "L:3 T:1 P:0 Credits:4", which also corroborates the credits), only
        # title-cased to match the rest of this file. The first list here was
        # a paraphrase — right in content, but "Linear Algebra" is not what
        # the paper calls unit 1, and the unit name goes into the generation
        # prompt.
        "units": ["Matrix Methods and Linear Systems",
                  "Differential Calculus and Its Applications",
                  "Fundamentals of Integral Calculus",
                  "Multivariate Differentiation",
                  "Multivariable Integration and Applications",
                  "Introduction to Fourier Series"],
        "scheme": {"attendance": 5, "ca": 25, "mte": 20, "ete": 50},
        "ca_policy": "CT1 units 1-2 · CT2 real-time applications (unit 4) · "
                      "CT3 cumulative over the CA1+CA2 syllabus — 30 marks each",
        "mte_exists": True,
        "exam_format": "mixed",
    },
    "CSE111": {
        "full_name": "Orientation to Computing",
        # 3, not the 2 coded first. The Session 2026-27 syllabus PDF prints
        # "L:3 T:0 P:0 Credits:3", and the notes mirror agrees independently.
        # The 2 almost certainly came from an older revision of this course
        # ("Orientation to Computing-I", L T P : 2 0 0), which is a real
        # document about a different version of it.
        "credits": 3,
        # All six are verbatim sub-headings from that syllabus, in its printed
        # order — but they are a strict SUBSET of it, and the gap is worth
        # knowing about rather than discovering in an exam:
        #
        # - "Profile Creation" is a seventh sub-heading, printed in Unit VI
        #   alongside the last two. It is here.
        # - The PDF itself prints only Unit I and Unit VI; Units II to V have
        #   no body at all, and page 2 is blank. Yet the course outcomes name
        #   operating systems, Linux, networking, virtualisation and cloud
        #   (CO2); career pathways, MOOCs and hackathons (CO3); algorithms,
        #   pseudocode and flowcharts (CO4); digital security (CO5); and ML,
        #   Agentic AI, IoT, Blockchain and Web3 (CO6). None of that has a
        #   printed unit body, so none of it is invented into one here. If it
        #   turns out to be taught, this list needs those units and they need
        #   a real source, not a guess from the outcome statements.
        "units": ["Computer Languages", "Computer Fundamentals",
                  "Computer Hardware", "Number Systems", "Version Control",
                  "Modern AI Trends and Tools", "Profile Creation"],
        # The notes mirror's grading block reads 30 attendance / 70 continuous
        # assessment / NA mid term / NA end term. That mirror is worth
        # believing — it carries five different schemes across the owner's
        # other courses, so it is transcribing rather than defaulting, and its
        # CSE121 figures match LPU's own course deck. But it is ONE source for
        # this subject, so scheme_confirmed stays False and the UI says so.
        # The part both readings agree on is the part that changes behaviour:
        # no mid-term and no end-term.
        "scheme": {"attendance": 30, "ca": 70, "mte": 0, "ete": 0},
        "ca_policy": "100% internal — no mid-term, no end-term, so every mark "
                     "comes from attendance plus continuous assessment across "
                     "all units; the per-task split is unpublished, confirm on UMS",
        "mte_exists": False,
        "exam_format": "mcq",
        "scheme_confirmed": False,
    },
    "INT108": {
        "full_name": "Python Programming",
        # Checked against the Session 2026-27 syllabus PDF and correct as
        # coded: "L:3 T:0 P:2 Credits:4", and all six unit names match its
        # printed headings.
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
        # 2, from the Session 2026-27 syllabus PDF's own header:
        # "INT335:DESIGN THINKING  L:2  T:0  P:0  Credits:2". The same
        # document prints a full sub-topic list for all six units, and the six
        # unit names below match it verbatim.
        "credits": 2,
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
        # Checked against the Session 2026-27 syllabus PDF and correct as
        # coded: "L:1 T:0 P:2 Credits:2", and all six unit names match its
        # printed headings verbatim.
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
#: MEC103 and CSE111 carry scheme_confirmed=False today.
DEFAULT_SCHEME_CONFIRMED = True

# The app's earlier ad-hoc codes map onto the real LPU codes. MTH174 was itself
# a wrong guess — the owner's own zero-lecture slides confirm the real code is
# MTH165 — so it renames the same way a legacy ad-hoc code would, preserving
# every existing card/review against the topic id.
LEGACY_RENAMES = {"MATHS": "MTH174", "HTML": "CSE326", "MTH174": "MTH165"}


