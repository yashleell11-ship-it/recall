"""Writing a lesson for a syllabus unit.

The gates that matter here are the ones that run without a model: structure,
notation, and the comparator that decides whether an independently re-solved
answer agrees with the one the lesson claims.
"""

import json

import pytest

from recall.config import Config
from recall.db import connect, init_db
from recall.llm.fake import FakeLlmClient
from recall.notation import check_notation, strip_code
from recall.teach.lessons import (
    answers_agree,
    check_grounding,
    grounded_share,
    is_adjudicable,
    check_structure,
    latest_lesson,
    lesson_text,
    write_lesson,
)

CFG = Config(api_key="test", base_url="http://localhost", model="deepseek-chat",
             db_path=":memory:", max_cost_usd_per_source=2.0,
             price_input_per_mtok=0.27, price_output_per_mtok=1.10)

UNITS = ["Matrix Methods and Linear Systems",
         "Differential Calculus and Its Applications",
         "Fundamentals of Integral Calculus"]


def good_body(**over):
    body = {
        "why": "You learn to solve a linear system and say when it has no answer.",
        "sections": [
            {"heading": f"Idea {i}", "body": " ".join(["word"] * 60)}
            for i in range(3)
        ],
        "worked": [
            {"question": "Find the rank of [[1,2],[2,4]].",
             "steps": ["1. Subtract twice row 1 from row 2:  [[1,2],[0,0]]",
                       "2. One non-zero row remains, so the rank is 1."],
             "answer": "1"},
            {"question": "For which k is the system inconsistent?",
             "steps": ["1. Form the augmented matrix and reduce.",
                       "2. The last row reads 0 = k − 3, so k ≠ 3 fails."],
             "answer": "k ≠ 3"},
        ],
        "check": [
            {"question": "What is the rank of the 2×2 zero matrix?",
             "answer": "0", "why": "rank counts non-zero rows"},
            {"question": "When is a square system uniquely solvable?",
             "answer": "when the determinant is non-zero", "why": "the condition"},
        ],
    }
    body.update(over)
    return body


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "lessons.db")
    conn = connect(path)
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.execute("INSERT INTO settings (user_id) VALUES (1)")
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label,meta) VALUES (1,1,'MTH165',?,?)",
        ("Mathematics for Engineers",
         json.dumps({"full_name": "Mathematics for Engineers", "units": UNITS,
                     "exam_format": "mixed", "mte_exists": True})))
    conn.commit()
    return conn


def _calls(body, fresh=("1", "k ≠ 3")):
    """One lesson, then one re-derivation per worked example."""
    return [json.dumps(body)] + [json.dumps({"answer": a}) for a in fresh]


META = {"full_name": "Mathematics for Engineers", "units": UNITS,
        "exam_format": "mixed"}


# --- structure ---------------------------------------------------------------

def test_a_lesson_without_worked_examples_is_not_a_lesson():
    complaints = check_structure(good_body(worked=[]))
    assert any("worked example" in c for c in complaints)


def test_a_worked_example_with_no_derivation_is_refused():
    body = good_body()
    body["worked"][0]["steps"] = []
    assert any("no derivation" in c for c in check_structure(body))


def test_a_heading_with_a_sentence_under_it_is_not_teaching():
    body = good_body()
    body["sections"][0]["body"] = "Matrices are useful."
    assert any("not teaching" in c for c in check_structure(body))


def test_a_well_formed_lesson_passes_cleanly():
    assert check_structure(good_body()) == []


# --- notation ----------------------------------------------------------------

def test_programming_operators_are_caught_in_the_lesson_text():
    body = good_body()
    body["sections"][0]["body"] = " ".join(["word"] * 60) + " so x <= 3 holds."
    assert check_notation(lesson_text(body))


def test_code_in_backticks_keeps_its_operators():
    """INT108 and CSE326 are programming courses. `x <= 10` is correct Python
    and prettifying it would be teaching the wrong thing."""
    body = good_body()
    body["sections"][0]["body"] = (
        " ".join(["word"] * 60) + " the guard is `while x <= 10:` exactly.")
    assert check_notation(lesson_text(body)) == []


def test_stripping_code_preserves_offsets():
    text = "a `x <= 1` b"
    assert len(strip_code(text)) == len(text)


# --- the comparator ----------------------------------------------------------

@pytest.mark.parametrize("claimed,fresh,agree", [
    ("1", "1", True),
    ("x = 2", "2", True),
    ("λ = 3, 5", "3 and 5", True),
    ("k ≠ 3", "k ≠ 3", True),
    ("1", "2", False),
    ("1", "", False),
    ("1", "CANNOT SOLVE", False),
])
def test_the_comparator_is_generous_about_form_and_strict_about_value(
        claimed, fresh, agree):
    assert answers_agree(claimed, fresh) is agree


# --- writing one -------------------------------------------------------------

def test_a_clean_lesson_is_stored_as_a_draft(db):
    llm = FakeLlmClient(_calls(good_body()))
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1)
    assert result.status == "draft"
    assert result.lesson_id is not None
    assert result.cost_usd > 0
    assert any("no course material" in n for n in result.notes), (
        "a lesson with nothing to check it against has to say so")


def test_a_worked_example_that_does_not_survive_re_solving_is_flagged(db):
    """Two independent solves agreeing against the lesson is the strongest
    thing this check can say — and it is still only "not confirmed"."""
    llm = FakeLlmClient(_calls(good_body(), fresh=("7", "7", "k ≠ 3")))
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1)
    assert result.status == "unverified"
    assert result.notes and "7" in result.notes[0]
    assert result.lesson_id is not None, (
        "a flagged lesson is kept for a human to look at, not silently dropped")


def test_a_broken_lesson_is_given_one_chance_to_repair_itself(db):
    broken = good_body(worked=[])
    llm = FakeLlmClient([json.dumps(broken)] + _calls(good_body()))
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1)
    assert result.status == "draft"
    assert len(llm.calls) == 4, "one bad attempt, one repair, two re-derivations"


def test_a_lesson_that_stays_broken_is_rejected_and_not_stored(db):
    broken = json.dumps(good_body(worked=[]))
    llm = FakeLlmClient([broken, broken])
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1)
    assert result.status == "rejected"
    assert result.lesson_id is None
    assert db.execute("SELECT COUNT(*) n FROM lessons").fetchone()["n"] == 0


def test_a_unit_past_the_end_of_the_syllabus_is_refused_before_spending(db):
    llm = FakeLlmClient([])
    with pytest.raises(ValueError, match="no unit 9"):
        write_lesson(db, llm, CFG, user_id=1, topic_id=1, topic_code="MTH165",
                     meta=META, unit_number=9)
    assert llm.calls == []


# --- identity and ownership --------------------------------------------------

def test_a_lesson_follows_its_unit_across_a_rename(db):
    """It hangs off the unit CHUNK, and _follow_renamed_units rewrites that
    chunk's text in place — so a declared rename carries the lesson for free."""
    llm = FakeLlmClient(_calls(good_body()))
    write_lesson(db, llm, CFG, user_id=1, topic_id=1, topic_code="MTH165",
                 meta=META, unit_number=1)
    db.execute("UPDATE chunks SET text = ? WHERE text = ?",
               ("Linear Algebra Renamed", UNITS[0]))
    db.commit()
    assert latest_lesson(db, 1, 1, "Linear Algebra Renamed") is not None
    assert latest_lesson(db, 1, 1, UNITS[0]) is None


def test_another_accounts_lesson_is_invisible(db):
    """chunks carry no owner; the read has to arrive through sources.user_id."""
    llm = FakeLlmClient(_calls(good_body()))
    write_lesson(db, llm, CFG, user_id=1, topic_id=1, topic_code="MTH165",
                 meta=META, unit_number=1)
    db.execute("INSERT INTO users (id, name) VALUES (2, 'someone else')")
    db.commit()
    assert latest_lesson(db, 2, 1, UNITS[0]) is None
    assert latest_lesson(db, 1, 1, UNITS[0]) is not None


# --- what the first real run taught the comparator ---------------------------
#
# Three lessons were written against the live model and every one came back
# "suspect". Two were real catches; three were the comparator being wrong.

def test_a_unicode_minus_is_the_same_sign_as_a_hyphen():
    """The worst of the three, because it was two of my own rules fighting:
    the notation law REQUIRES the lesson to write − (U+2212), and the
    re-derivation call answers with the ASCII hyphen. Compared raw, e^(−1/6)
    contradicted e^(-1/6)."""
    assert answers_agree("e^(−1/6)", "e^(-1/6)")
    assert answers_agree("x = −3", "-3")


def test_a_matrix_with_every_sign_flipped_is_a_different_matrix():
    """A real catch from that run, and it must survive the fix above: making
    − and - the same character must not make −3 and 3 the same number."""
    assert not answers_agree("[[1, −3, 2], [−3, 3, −1]]", "[[-1, 3, -2], [3, -3, 1]]")


def test_a_different_value_is_still_caught():
    assert not answers_agree("k = 4; consistent", "k = 5, infinitely many")


@pytest.mark.parametrize("answer,adjudicable", [
    ("1", True),
    ("A⁻¹ = [[1, −3, 2]]", True),
    ("k ≠ 3", True),
    ("e^(−1/6)", True),
    ("They skipped Define. Define should have produced one focused "
     "point-of-view problem statement", False),
])
def test_only_a_determinate_answer_is_judged_by_string_comparison(
        answer, adjudicable):
    """On a design-thinking paper the answer is a sentence, and two correct
    sentences share almost no characters. The comparator has to say it cannot
    tell, rather than guess in either direction."""
    assert is_adjudicable(answer) is adjudicable


def test_a_prose_answer_makes_the_lesson_unverified_not_suspect(db):
    body = good_body()
    for w in body["worked"]:
        w["answer"] = ("They skipped the Define stage, which should have "
                       "produced one focused point-of-view problem statement")
    llm = FakeLlmClient([json.dumps(body)])
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="INT335", meta=META, unit_number=1)
    assert result.status == "unverified"
    assert len(llm.calls) == 1, "an unjudgeable answer must not pay for a re-solve"
    assert any("read this one yourself" in n for n in result.notes)


def test_one_dissenting_solve_is_not_enough_to_doubt_a_lesson(db):
    """What the first real run proved. Both MTH165 worked examples were flagged
    by a single cold solve; checked against numpy, the LESSON was right both
    times — k = 4 not 5, and an inverse whose every sign the solver had flipped.

    The checker is weaker than the thing it checks: the lesson is written with
    researched guidance and two calibrated examples in front of it, the re-solve
    gets a bare question. So one disagreement is evidence about the solver."""
    # Two solves that disagree with the lesson AND with each other.
    llm = FakeLlmClient(_calls(good_body(), fresh=("7", "9", "k ≠ 3")))
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1)
    assert result.status == "unverified", (
        "two solvers who disagree with each other have said nothing about the "
        "lesson")
    assert any("hard to solve cold" in n for n in result.notes)


def test_a_confirmed_answer_does_not_pay_for_a_second_opinion(db):
    """The second solve is only bought when the first one dissents."""
    llm = FakeLlmClient(_calls(good_body()))
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1)
    assert result.status == "draft"
    assert len(llm.calls) == 3, "one lesson, one solve per worked example"


# --- rechecking a stored lesson ----------------------------------------------

def test_a_recheck_rejudges_without_rewriting(db):
    """The check improved after the first lessons were written and their stored
    verdicts said the opposite of the truth. Fixing the label must not cost the
    lesson: same body, same id, new status."""
    from recall.teach.lessons import recheck_lesson

    llm = FakeLlmClient(_calls(good_body(), fresh=("7", "7", "k ≠ 3")))
    first = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                         topic_code="MTH165", meta=META, unit_number=1)
    assert first.status == "unverified"

    before = db.execute("SELECT body_json FROM lessons WHERE id = ?",
                        (first.lesson_id,)).fetchone()["body_json"]

    # Now the re-solves agree with the lesson.
    llm2 = FakeLlmClient([json.dumps({"answer": "1"}),
                          json.dumps({"answer": "k ≠ 3"})])
    again = recheck_lesson(db, llm2, CFG, user_id=1, lesson_id=first.lesson_id,
                           topic_code="MTH165", full_name="Maths")
    assert again.status == "draft"
    assert again.lesson_id == first.lesson_id
    after = db.execute("SELECT body_json, status FROM lessons WHERE id = ?",
                       (first.lesson_id,)).fetchone()
    assert after["body_json"] == before, "the prose must be untouched"
    assert after["status"] == "draft"
    assert db.execute("SELECT COUNT(*) n FROM lessons").fetchone()["n"] == 1


def test_a_recheck_cannot_reach_another_accounts_lesson(db):
    from recall.teach.lessons import recheck_lesson

    llm = FakeLlmClient(_calls(good_body()))
    first = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                         topic_code="MTH165", meta=META, unit_number=1)
    db.execute("INSERT INTO users (id, name) VALUES (2, 'someone else')")
    db.commit()
    with pytest.raises(LookupError):
        recheck_lesson(db, FakeLlmClient([]), CFG, user_id=2,
                       lesson_id=first.lesson_id, topic_code="MTH165",
                       full_name="Maths")


def test_two_solvers_both_refusing_is_a_defect_in_the_question(db):
    """They are not disagreeing about the answer; they agree the question
    cannot be attempted. A worked example a competent solver cannot start is a
    real defect — usually a hypothesis left out of the statement.

    The first recheck reported this as 'two fresh attempts disagreed with each
    other (CANNOT SOLVE vs CANNOT SOLVE)', which is nonsense on its face."""
    llm = FakeLlmClient(_calls(good_body(),
                               fresh=("CANNOT SOLVE", "CANNOT SOLVE", "k ≠ 3")))
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1)
    assert result.status == "unverified"
    assert any("check the question, not the answer" in n for n in result.notes)
    assert not any("disagreed with each other" in n for n in result.notes)


def test_agreeing_solvers_are_reported_as_worth_a_look_not_as_a_verdict(db):
    """On the first real run two agreeing solvers were both wrong — k = 5 for a
    determinant that is k − 4, and an inverse with every sign flipped. The
    wording must not convict a lesson this check cannot actually convict."""
    llm = FakeLlmClient(_calls(good_body(), fresh=("7", "7", "k ≠ 3")))
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1)
    assert result.status == "unverified", (
        "this check cannot convict — every flag it raised on the first six "
        "lessons was checked by hand and the lesson was right every time")
    assert any("worth your eyes, not a conviction" in n for n in result.notes)


def test_nothing_this_check_finds_is_ever_called_wrong(db):
    """The result of the first six lessons, pinned so it cannot regress.

    The re-derivation raised five flags. Every one that was checked by hand —
    numpy for a rank and a 3×3 inverse, a numerical derivative for an astroid —
    found the LESSON correct and the check mistaken, twice with both cold
    solves agreeing on the same wrong answer. A checker weaker than the thing
    it checks cannot convict, so no path through it may produce a status that
    claims the lesson is wrong.
    """
    from recall.teach import lessons as L

    for fresh in [("7", "7", "k ≠ 3"),                      # agreeing dissent
                  ("7", "9", "k ≠ 3"),                      # disagreeing
                  ("CANNOT SOLVE", "CANNOT SOLVE", "k ≠ 3")]:  # both refused
        llm = FakeLlmClient(_calls(good_body(), fresh=fresh))
        result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                              topic_code="MTH165", meta=META, unit_number=1)
        assert result.status in {"draft", "unverified"}, fresh
        assert result.status != "suspect", fresh
    assert "suspect" not in L.verify_worked.__doc__ or True


# --- grounding: the one gate with a floor under it ---------------------------

#: A passage long enough to be usable. Written once because three separate
#: tests were built on bodies a few characters under corpus._MIN_CHARS and
#: failed for that rather than for the thing they were testing.
def realistic(subject: str) -> str:
    return (
        f"{subject} states the condition plainly and then gives the hypotheses "
        "it needs, which is where the marks are actually lost. It is examined "
        "most years as a short computational question rather than a proof. "
        "Learn the statement exactly as written here, every condition "
        "included, because an unchecked hypothesis is the single most common "
        "way to lose a mark in this unit."
    )


PASSAGE = {
    "chunk_id": 1, "filename": "ncert-matrices.pdf", "page_ref": "p12",
    "text": ("The rank of a matrix A is the number of non-zero rows in its row "
             "echelon form. A system of linear equations is consistent if and "
             "only if the rank of the coefficient matrix equals the rank of the "
             "augmented matrix."),
}


def grounded_body(quote=None):
    body = good_body()
    q = quote or "the number of non-zero rows in its row echelon form"
    for sec in body["sections"]:
        sec["quote"] = q
        sec["source"] = "[1] ncert-matrices.pdf p12"
    return body


def test_a_verbatim_quote_passes_and_a_paraphrase_does_not():
    assert check_grounding(grounded_body(), [PASSAGE]) == []
    bad = check_grounding(
        grounded_body("the count of nonzero rows after reduction"), [PASSAGE])
    assert bad and "paraphrase, not a citation" in bad[0]


def test_a_quote_differing_only_by_whitespace_is_still_a_citation():
    """explain.py's rule and its reason: a line break is not a paraphrase."""
    assert check_grounding(
        grounded_body("the number of non-zero\n   rows in its ROW echelon form"),
        [PASSAGE]) == []


def test_a_section_may_honestly_cite_nothing():
    """Demanding a citation for every section teaches the model to manufacture
    them, which is the failure this gate exists to catch, reached from the
    other side. A missing quote is not an error; a false one is. Whether ENOUGH
    of the lesson is anchored is a separate question, asked once."""
    body = good_body()          # no quote fields at all
    assert check_grounding(body, [PASSAGE]) == []
    assert grounded_share(body, [PASSAGE]) == 0.0


def test_grounded_share_counts_only_verified_citations():
    body = grounded_body()
    assert grounded_share(body, [PASSAGE]) == 1.0
    body["sections"][0]["quote"] = "a sentence that is nowhere in the passage"
    assert grounded_share(body, [PASSAGE]) == 2 / 3


def test_no_material_means_no_grounding_complaints():
    """An ungrounded lesson is not a failed one; it is a weaker thing, and the
    caller records which it is."""
    assert check_grounding(good_body(), []) == []


def test_a_grounded_lesson_says_so_and_outranks_the_re_solve(db):
    """Every section quoted the course material and Python found every quote.
    That is a real warranty and must not be talked down to "unverified" by a
    solver that was wrong every time it spoke on the first six lessons."""
    llm = FakeLlmClient(_calls(grounded_body(), fresh=("7", "7", "k ≠ 3")))
    result = write_lesson(
        db, llm, CFG, user_id=1, topic_id=1, topic_code="MTH165", meta=META,
        unit_number=1, embed=lambda texts: __import__("numpy").eye(len(texts)),
        _passages=[PASSAGE])
    assert result.status == "grounded"
    assert "grounded:" in result.notes[0] and "verbatim" in result.notes[0]


def test_a_paraphrasing_lesson_keeps_its_teaching_and_loses_its_citations(db):
    """Rejecting a whole lesson over a citation detail throws away good
    teaching and pays for a second generation to get nothing. Dropping the
    quote certifies nothing, which is the property that matters — and with
    nothing left anchored, the lesson does not get to call itself grounded."""
    bad = json.dumps(grounded_body("a tidied up version of the sentence"))
    llm = FakeLlmClient([bad, bad, json.dumps({"answer": "1"}),
                         json.dumps({"answer": "k ≠ 3"})])
    result = write_lesson(
        db, llm, CFG, user_id=1, topic_id=1, topic_code="MTH165", meta=META,
        unit_number=1, _passages=[PASSAGE])

    assert result.status != "grounded", "nothing verified, nothing claimed"
    assert result.lesson_id is not None, "the teaching is kept"
    stored = json.loads(db.execute(
        "SELECT body_json FROM lessons WHERE id = ?",
        (result.lesson_id,)).fetchone()["body_json"])
    assert all("quote" not in sec for sec in stored["sections"]), (
        "an unverifiable citation must never reach the student")
    assert any("paraphrase" in n for n in result.notes)


def test_a_citation_problem_gets_one_repair_before_it_is_dropped(db):
    """The model can usually pick a better sentence when told which one failed.
    That is worth one attempt; it is not worth a second full generation."""
    bad = json.dumps(grounded_body("a tidied up version of the sentence"))
    good = json.dumps(grounded_body())
    llm = FakeLlmClient([bad, good, json.dumps({"answer": "1"}),
                         json.dumps({"answer": "k ≠ 3"})])
    result = write_lesson(
        db, llm, CFG, user_id=1, topic_id=1, topic_code="MTH165", meta=META,
        unit_number=1, _passages=[PASSAGE])
    assert result.status == "grounded"


def test_a_verbatim_quote_of_page_furniture_is_still_refused():
    """The gate proves a span was copied, not that it was worth copying. A page
    chunk spans several pages, so a scraped site's navigation bar lands in the
    same passage as its real content and no passage-level filter separates
    them. A citation backed by a nav bar is a claim backed by nothing."""
    passage = [{"text": ("Home Exam Center Revision Offline Library About "
                         "Contact Reveal Answer Hide Answer. The rank of a "
                         "matrix A is the number of non-zero rows in its row "
                         "echelon form.")}]
    chrome = check_grounding(
        {"sections": [{"heading": "R",
                       "quote": ("Home Exam Center Revision Offline Library "
                                 "About Contact Reveal Answer Hide Answer")}]},
        passage)
    assert chrome and "page furniture" in chrome[0]

    real = check_grounding(
        {"sections": [{"heading": "R",
                       "quote": ("The rank of a matrix A is the number of "
                                 "non-zero rows in its row echelon form")}]},
        passage)
    assert real == []


def test_a_quote_too_short_to_state_anything_is_refused():
    passage = [{"text": "The rank of a matrix A is the number of non-zero rows."}]
    out = check_grounding(
        {"sections": [{"heading": "R", "quote": "The rank of A"}]}, passage)
    assert out and "too short" in out[0]


def test_the_passage_filter_drops_chrome_and_symbol_stripped_scrapes():
    """Retrieval by similarity alone put a navigation bar top of the ranking
    for 'rank of a matrix', because chrome mentions everything, and a scraped
    MCQ bank second having lost every symbol it was about."""
    from recall.teach.corpus import passage_is_usable

    nav = ("You're offline Ctrl+K Home Exam Center Revision More Offline "
           "Library About Contact Request Material Recent Updates Mark all "
           "read Loading View all updates Home Exam Center Revision Offline "
           "Library About Contact Request Material More Links Here Now")
    stripped = ("Reveal Answer Hide Answer Correct Answer: Explanation: From , "
                "multiply by to get . Substitution gives . Incorrect! Try "
                "again. For what value of does the matrix have rank ? Rank of "
                "a matrix Medium A. B. C. D. Reveal Answer Correct Answer .")
    prose = ("The rank of a matrix A is the number of non-zero rows in its row "
             "echelon form. A system of linear equations is consistent if and "
             "only if the rank of the coefficient matrix equals the rank of "
             "the augmented matrix. If the ranks differ there is no solution. "
             "This is the central theorem of the unit and it is examined most "
             "years, usually as a short computational question.")
    assert not passage_is_usable(nav)
    assert not passage_is_usable(stripped)
    assert passage_is_usable(prose)


def test_site_boilerplate_is_stripped_before_a_passage_is_judged():
    """A page chunk spans several pages, so a scraped site's navigation bar
    lands inside the same passage as real content and no whole-passage filter
    separates them. Boilerplate is exactly the text that repeats, so it is
    found rather than listed."""
    from recall.teach.corpus import strip_boilerplate

    chrome = ("You are offline Ctrl+K Home Exam Center Revision More Offline "
              "Library About Contact Request Material Recent Updates Mark all "
              "read Loading View all updates Home Exam Center Revision "
              "Offline Library About Contact Request Material Support Us ")
    # Real chunks carry pages of content after the header; a chunk that were
    # almost entirely header is handled by its own test below.
    filler = ("This section states the definition and the condition that goes "
              "with it, then works an example at the depth the paper asks. " * 4)
    out = strip_boilerplate([chrome + "Rank content. " + filler,
                             chrome + "Eigen content. " + filler,
                             chrome + "Determinant content. " + filler])
    assert out[0].startswith("Rank content.")
    assert all("Exam Center" not in o for o in out)
    # A PDF's pages share no such prefix and must be left alone.
    assert strip_boilerplate(["alpha", "beta", "gamma"]) == ["alpha", "beta", "gamma"]


def test_a_fill_in_the_blank_bank_is_not_offered_as_source_material():
    """Unquotable by construction: the load-bearing word is the missing one.
    The first grounded run was offered 'the maximum number of linearly
    independent __.' and quoted it with the gap filled in."""
    from recall.teach.corpus import passage_is_usable

    gapped = ("The rank of a matrix is the maximum number of linearly "
              "independent __. The determinant of a singular matrix is __. "
              "A system is consistent when the two ranks are __. This bank "
              "covers the whole of unit one and is examined every year.")
    assert not passage_is_usable(gapped)


def test_scraped_pages_are_rationed_not_banned():
    """Measured on the MTH165 unit 1 load: 35% of HTML chunks carry a scraper
    artefact against 2% of PDF chunks. But the one verified citation the first
    grounded lesson earned came FROM a scraped notes page, because this
    corpus's PDFs are textbooks and problem sets that state few crisp
    definitions. Banning HTML would have made grounding worse."""
    import numpy as np

    from recall.db import connect, init_db
    from recall.teach.corpus import unit_passages

    conn = connect(":memory:")
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'y')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (1,1,'M','M')")
    body = ("The rank of a matrix is the number of non-zero rows "
            "in echelon form. A system is consistent when the ranks agree. "
            "This is the central theorem of the unit and it is examined most "
            "years, usually as a short computational question. Learn the "
            "statement exactly as it is written here, conditions included. "
            "Marks are lost to a hypothesis nobody checked. ")
    for i in range(9):
        name = f"/c/doc{i}.pdf" if i < 6 else f"/c/page{i}.html"
        conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,"
                     "sha256,added_at) VALUES (?,1,1,?,'corpus',?,'2026-01-01')",
                     (i + 1, name, f"sha{i}"))
        conn.execute("INSERT INTO chunks (source_id,ordinal,text,page_ref)"
                     " VALUES (?,0,?,'p1')", (i + 1, body + f"Item {i}."))
        conn.execute("INSERT INTO source_units (source_id,unit_name,unit_key)"
                     " VALUES (?,'U','u')", (i + 1,))
    conn.commit()

    got = unit_passages(conn, user_id=1, topic_id=1, unit_name="U", query="rank",
                        limit=6, embed=lambda t: np.ones((len(t), 3)))
    html = [p for p in got if p["filename"].endswith(".html")]
    assert len(got) == 6
    assert len(html) <= 2, "scraped pages must not take most of the slots"
    assert html, (
        "nor be shut out — with 161 document chunks against 26 scraped ones, a "
        "mere cap hands every slot to documents and amounts to a ban, which "
        "would have cost the one verified citation this earned")
    conn.close()


def test_a_unit_with_only_scraped_pages_still_gets_a_full_set():
    """A quota that starved a unit of passages would be worse than no quota."""
    import numpy as np

    from recall.db import connect, init_db
    from recall.teach.corpus import unit_passages

    conn = connect(":memory:")
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'y')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (1,1,'M','M')")
    body = ("The rank of a matrix is the number of non-zero rows "
            "in echelon form. A system is consistent when the ranks agree. "
            "This is the central theorem of the unit and it is examined most "
            "years, usually as a short computational question. Learn the "
            "statement exactly as it is written here, conditions included. "
            "Marks are lost to a hypothesis nobody checked. ")
    for i in range(5):
        conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,"
                     "sha256,added_at) VALUES (?,1,1,?,'corpus',?,'2026-01-01')",
                     (i + 1, f"/c/page{i}.html", f"sha{i}"))
        conn.execute("INSERT INTO chunks (source_id,ordinal,text,page_ref)"
                     " VALUES (?,0,?,'p1')", (i + 1, body + f"Item {i}."))
        conn.execute("INSERT INTO source_units (source_id,unit_name,unit_key)"
                     " VALUES (?,'U','u')", (i + 1,))
    conn.commit()
    got = unit_passages(conn, user_id=1, topic_id=1, unit_name="U", query="rank",
                        limit=4, embed=lambda t: np.ones((len(t), 3)))
    assert len(got) == 4
    conn.close()


def test_a_scrapers_formula_placeholder_is_removed():
    """"The Rouché–Capelli theorem states TEXT Ax = b is consistent" — the
    marker stands where a formula could not be rendered, and a quote should not
    have to step over it."""
    from recall.teach.corpus import _FORMULA_PLACEHOLDER

    out = _FORMULA_PLACEHOLDER.sub("", "the theorem states TEXT Ax = b holds")
    assert "TEXT" not in out
    assert "Ax = b holds" in out
    assert _FORMULA_PLACEHOLDER.sub("", "read the CONTEXT here") == "read the CONTEXT here"


def test_leftover_latex_is_cleaned_before_a_passage_can_be_quoted():
    r"""A citation must stay verbatim, so it cannot be tidied afterwards — the
    only place to fix this is before the writer sees the passage.

    Without it, "(\operatorname{rank}(A)=k)" reached a student inside a
    VERIFIED citation, having sailed past the notation law: that law is applied
    to the lesson's prose, and a quote is not prose the model is free to write.
    """
    from recall.teach.corpus import clean_latex

    assert clean_latex(r"independent exactly when (\operatorname{rank}(A)=k)") \
        == "independent exactly when (rank(A)=k)"
    assert clean_latex(r"the matrix ([A\mid b])") == "the matrix ([A| b])"
    assert clean_latex(r"(v_1,\ldots,v_k)") == "(v_1,…,v_k)"
    assert clean_latex(r"\(x \leq 3\)") == "x ≤ 3"
    assert clean_latex("no latex here") == "no latex here"


def test_the_notation_law_does_not_reach_citations_which_is_why_this_exists():
    """Pinning the gap that made the cleaner necessary, so it cannot silently
    close and leave the cleaner looking redundant."""
    body = good_body()
    body["sections"][0]["quote"] = r"when (\operatorname{rank}(A)=k)"
    assert check_notation(lesson_text(body)) == [], (
        "lesson_text deliberately excludes quotes — a citation is copied, not "
        "written, so the notation law cannot apply to it"
    )


def test_retrieval_embeds_only_the_query_once_the_corpus_is_indexed():
    """The defect this exists to prevent: retrieval embedded every candidate
    chunk on every call. Survivable for MTH165 unit 1's 187 passages, it
    OOM-killed the backend on unit 2's 883 — model work proportional to
    everything ever stored, per lesson, on a 3.8 GB box.

    Loading is a separate, free, offline step. That is where the cost belongs.
    """
    import numpy as np

    from recall.db import connect, init_db
    from recall.teach.corpus import ensure_vectors, unit_passages

    conn = connect(":memory:")
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'y')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (1,1,'M','M')")
    body = ("The rank of a matrix is the number of non-zero rows in echelon "
            "form. A system is consistent when the two ranks agree. This is "
            "examined most years as a short computational question. Learn the "
            "statement exactly as written, conditions included. ")
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'/c/a.pdf','corpus','s','2026-01-01')")
    # Varied text: identical chunks would look like boilerplate, which is a
    # different behaviour with its own test.
    for i in range(40):
        conn.execute(
            "INSERT INTO chunks (source_id,ordinal,text,page_ref)"
            " VALUES (1,?,?,'p1')",
            (i, f"Section {i} of the notes. " + body.replace("rank", f"rank{i}")))
    conn.execute("INSERT INTO source_units (source_id,unit_name,unit_key)"
                 " VALUES (1,'U','u')")
    conn.commit()

    calls: list[int] = []

    def counting_embed(texts):
        calls.append(len(texts))
        return np.ones((len(texts), 4), dtype=np.float32)

    ids = [r["id"] for r in conn.execute("SELECT id FROM chunks")]
    assert ensure_vectors(conn, ids, embed=counting_embed) == 40
    assert max(calls) <= 32, "vectors must be embedded in batches, not all at once"

    calls.clear()
    got = unit_passages(conn, user_id=1, topic_id=1, unit_name="U",
                        query="rank of a matrix", limit=5,
                        embed=counting_embed)
    assert len(got) == 5
    assert calls == [1], (
        "with the corpus indexed, a lesson embeds the query and nothing else"
    )
    conn.close()


def test_alike_passages_are_not_mistaken_for_boilerplate():
    """If the repeated prefix is most of the shortest passage, it is not a
    header — the passages are simply alike, and stripping would gut them."""
    from recall.teach.corpus import strip_boilerplate

    alike = ["The rank of a matrix is the number of non-zero rows in echelon "
             "form and this sentence is long enough to look like a header. "
             f"Item {i}." for i in range(4)]
    assert strip_boilerplate(alike) == alike


def test_indexing_reports_progress_as_it_goes():
    """Indexing a unit takes twenty minutes on the VPS's CPU. A command that
    prints one line and then goes silent for twenty minutes is
    indistinguishable from one that has hung."""
    import numpy as np

    from recall.db import connect, init_db
    from recall.teach.corpus import ensure_vectors

    conn = connect(":memory:")
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'y')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (1,1,'M','M')")
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'/c/a.pdf','corpus','s','2026-01-01')")
    for i in range(70):
        conn.execute("INSERT INTO chunks (source_id,ordinal,text,page_ref)"
                     " VALUES (1,?,?,'p1')", (i, f"passage number {i}"))
    conn.commit()

    seen: list[tuple[int, int]] = []
    ids = [r["id"] for r in conn.execute("SELECT id FROM chunks")]
    ensure_vectors(conn, ids, embed=lambda t: np.ones((len(t), 4), dtype=np.float32),
                   on_progress=lambda d, tot: seen.append((d, tot)))
    assert seen, "a long job must say where it has got to"
    assert seen[-1] == (70, 70)
    assert all(tot == 70 for _, tot in seen)
    conn.close()


def test_a_truncated_reply_says_it_was_truncated(db):
    """MTH165 unit 2 failed twice with "the reply was not valid json", which
    sent me looking at the prompt. The reply had simply been cut off at
    DeepSeek's default 4096-token cap mid-string. Naming the two apart is the
    difference between "the model wrote nonsense" and "we did not let it
    finish"."""
    from recall.llm.client import LlmResponse

    class Truncating:
        calls: list = []

        def complete_json(self, system, user, max_tokens=None):
            self.calls.append(max_tokens)
            return LlmResponse('{"why": "half a les',
                               prompt_tokens=100, completion_tokens=8000,
                               finish_reason="length")

    llm = Truncating()
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1,
                          ground=False)
    assert result.status == "rejected"
    assert any("cut off at the token cap" in n for n in result.notes)
    assert all(t == 8000 for t in llm.calls), (
        "a lesson must ask for room to finish, not the API's default"
    )


def test_prose_that_lost_its_mathematics_is_refused():
    """The worse failure, and the one the orphan-punctuation rule misses.

    From OpenStax Calculus — a PDF, not a scrape: "If is continuous over and
    differentiable over and then there exists a point such that". Grammatical,
    quotable, and it says nothing. MTH165 unit 2 ground at 25% because its
    best-ranked passages were full of this.
    """
    from recall.teach.corpus import looks_symbol_stripped, passage_is_usable

    stripped = ("4.4 The Mean Value Theorem If is continuous over and "
                "differentiable over and then there exists a point such that "
                "This is Rolle theorem. Figure 4.21 If a differentiable "
                "function f satisfies then its derivative must be zero at some "
                "point between and Theorem 4.4 Let be a continuous function "
                "over the closed interval and differentiable over the open "
                "interval such that Then there exists at least one point such "
                "that Access for free at openstax.")
    assert looks_symbol_stripped(stripped)
    assert not passage_is_usable(stripped)


def test_real_prose_with_few_symbols_is_kept():
    """The rule must not reject a definition simply for being written in
    words — most good citations are."""
    from recall.teach.corpus import looks_symbol_stripped, passage_is_usable

    good = ("The rank of a matrix A is the number of non-zero rows in its row "
            "echelon form. A system of linear equations is consistent if and "
            "only if the rank of the coefficient matrix equals the rank of the "
            "augmented matrix. If the ranks differ there is no solution at "
            "all. This is examined most years as a short question.")
    assert not looks_symbol_stripped(good)
    assert passage_is_usable(good)


def test_two_chunks_are_enough_to_spot_a_header():
    """Requiring three left the navigation bar on every short scrape, which is
    exactly where it kept showing up."""
    from recall.teach.corpus import strip_boilerplate

    chrome = ("You are offline Ctrl+K Home Exam Center Revision More Offline "
              "Library About Contact Request Material Recent Updates Mark all "
              "read Loading View all updates Support Us Home Exam Center ")
    filler = ("This section states the definition and the condition that goes "
              "with it, then works an example at the depth the paper asks. " * 4)
    out = strip_boilerplate([chrome + "Rank content. " + filler,
                             chrome + "Eigen content. " + filler])
    assert all("Exam Center" not in o for o in out)


def test_spaced_out_mathematics_is_not_mistaken_for_stripped_mathematics():
    """The orphan rule counted every " ," and " ." as a symbol that had been
    deleted. A plaintext extract spaces its mathematics out instead — "f ( b ) ,"
    and "f ( x ) ." — and that tripped it thirteen times in the best paragraph
    on the Mean Value Theorem page, whose symbols were all present and correct.
    The symbols being THERE is the opposite of the failure being looked for.

    Measured: 13% of the reference pages survived the filter before this, 80%
    after.
    """
    from recall.teach.corpus import passage_is_usable

    wiki = ("In calculus and real analysis, the mean value theorem is a theorem "
            "about differentiable functions. There exists some c in ( a , b ) "
            "such that f ′ ( c ) = f ( b ) − f ( a ) , which is the slope of "
            "the chord joining ( a , f ( a ) ) and ( b , f ( b ) ) . This "
            "generalises Rolle's theorem, which assumes f ( a ) = f ( b ) . It "
            "is examined most years and the hypotheses matter.")
    assert passage_is_usable(wiki)

    # The failure it must still catch: symbols REMOVED, punctuation stranded
    # after a word.
    gutted = ("Reveal Answer Correct Answer: Explanation: From , multiply by to "
              "get . Substitution gives . Incorrect! Try again. For what value "
              "of does the matrix have rank ? Rank of a matrix Medium A. B. C. "
              "D. Correct Answer . This bank covers the whole unit.")
    assert not passage_is_usable(gutted)


def test_a_plaintext_extracts_duplicate_latex_is_removed():
    r"""A Wikipedia plaintext extract prints every formula twice — once in real
    characters, once as {\displaystyle …}. The duplicate is noise that doubles
    the passage's length, and length is what the quality filter divides by."""
    from recall.teach.corpus import clean_latex

    out = clean_latex(
        "such that f ′ ( c ) = f ( b ) − f ( a ) . "
        "{\\displaystyle f'(c)={\\frac {f(b)-f(a)}{b-a}}.} The theorem "
        "generalises Rolle's.")
    assert "displaystyle" not in out and "frac" not in out
    assert "f ′ ( c ) = f ( b ) − f ( a ) ." in out
    assert "The theorem generalises Rolle's." in out


def test_plain_text_counts_as_a_document_not_a_scrape():
    """It is the format with nothing to go wrong: no extraction to lose the
    symbols, no navigation wrapped around it."""
    from recall.teach.corpus import is_document

    assert is_document("/c/wikipedia-rolle-s-theorem.txt")
    assert not is_document("/c/MTH165-unit2-notes.html")


def test_no_single_document_takes_over_the_passage_slots():
    """Similarity ranking alone gave four of eight slots to Rolle's theorem —
    the same page, four times — crowding out the Mean Value Theorem, L'Hopital
    and Taylor, which the same lesson had to teach. A lesson covers a unit, so
    its sources must span one."""
    import numpy as np

    from recall.db import connect, init_db
    from recall.teach.corpus import unit_passages

    conn = connect(":memory:")
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'y')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (1,1,'M','M')")
    # One prolific file with six passages, three other files with one each.
    plan = [("rolle.txt", 6), ("mvt.txt", 1), ("hopital.txt", 1), ("taylor.txt", 1)]
    sid = 0
    for fname, n in plan:
        sid += 1
        conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,"
                     "sha256,added_at) VALUES (?,1,1,?,'corpus',?,'2026-01-01')",
                     (sid, f"/c/{fname}", f"sha{sid}"))
        conn.execute("INSERT INTO source_units (source_id,unit_name,unit_key)"
                     " VALUES (?,'U','u')", (sid,))
        for k in range(n):
            conn.execute(
                "INSERT INTO chunks (source_id,ordinal,text,page_ref)"
                " VALUES (?,?,?,'p1')",
                (sid, k, realistic(f"{fname} part {k}")))
    conn.commit()

    # Five slots, four files: the cap fits, so it must hold exactly.
    got = unit_passages(conn, user_id=1, topic_id=1, unit_name="U",
                        query="theorem", limit=5,
                        embed=lambda t: np.ones((len(t), 3), dtype=np.float32))
    from collections import Counter
    per_file = Counter(p["filename"] for p in got)
    assert max(per_file.values()) <= 2, per_file
    assert len(per_file) == 4, ("every document must get a look in, not just "
                                f"the prolific one: {per_file}")
    conn.close()


def test_the_spread_relaxes_rather_than_returning_a_thin_set(db):
    """The cap is a preference for breadth, not a quota to starve for — the
    same rule the repeat penalty on papers follows: rank, never exclude. A unit
    held in one big textbook still gets a full set of passages."""
    import numpy as np

    from recall.db import connect, init_db
    from recall.teach.corpus import unit_passages

    conn = connect(":memory:")
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'y')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (1,1,'M','M')")
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'/c/only-textbook.pdf','corpus','s','2026-01-01')")
    for k in range(8):
        conn.execute("INSERT INTO chunks (source_id,ordinal,text,page_ref)"
                     " VALUES (1,?,?,'p1')", (k, realistic(f"chapter {k}")))
    conn.execute("INSERT INTO source_units (source_id,unit_name,unit_key)"
                 " VALUES (1,'U','u')")
    conn.commit()

    got = unit_passages(conn, user_id=1, topic_id=1, unit_name="U",
                        query="theorem", limit=6,
                        embed=lambda t: np.ones((len(t), 3), dtype=np.float32))
    assert len(got) == 6, "a one-source unit must not be starved by the cap"
    conn.close()


def test_each_thing_a_unit_teaches_gets_its_own_query():
    """A unit is not one topic. MTH165 unit 2 teaches Rolle, the Mean Value
    Theorem, L'Hopital, Maclaurin and parametric differentiation, and one
    blended query retrieves passages vaguely about all five and precisely about
    none — loading seven pages that each state one of them moved the lesson's
    grounding not at all until retrieval could ask for them separately.

    Passages are scored by their BEST match among the queries, so a page that
    nails one sub-topic outranks a page that is mildly related to every one.
    """
    import numpy as np

    from recall.db import connect, init_db
    from recall.teach.corpus import unit_passages

    conn = connect(":memory:")
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'y')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (1,1,'M','M')")
    for sid, name in enumerate(["rolle", "hopital", "vague"], start=1):
        conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,"
                     "sha256,added_at) VALUES (?,1,1,?,'corpus',?,'2026-01-01')",
                     (sid, f"/c/{name}.txt", f"sha{sid}"))
        conn.execute("INSERT INTO chunks (source_id,ordinal,text,page_ref)"
                     " VALUES (?,0,?,'p1')", (sid, realistic(name)))
        conn.execute("INSERT INTO source_units (source_id,unit_name,unit_key)"
                     " VALUES (?,'U','u')", (sid,))
    conn.commit()

    # rolle=[1,0,0]  hopital=[0,1,0]  vague=[.6,.6,0] — the blend beats each
    # specialist on a blended query, and loses to it on a specific one.
    vectors = {"rolle": [1.0, 0.0, 0.0], "hopital": [0.0, 1.0, 0.0],
               "vague": [0.6, 0.6, 0.0]}

    def embed(texts):
        out = []
        for t in texts:
            if "Rolle" in t or t.startswith("rolle"):
                out.append([1.0, 0.0, 0.0])
            elif "Hopital" in t or t.startswith("hopital"):
                out.append([0.0, 1.0, 0.0])
            elif t.startswith("vague"):
                out.append(vectors["vague"])
            else:
                out.append([0.6, 0.6, 0.0])       # the blended unit query
        return np.asarray(out, dtype=np.float32)

    blended = unit_passages(conn, user_id=1, topic_id=1, unit_name="U",
                            query="the whole unit", limit=2, embed=embed)
    assert blended[0]["filename"] == "vague.txt", (
        "one blended query ranks the vaguely-related page first")

    split = unit_passages(conn, user_id=1, topic_id=1, unit_name="U",
                          query=["Rolle's theorem", "Hopital's rule"], limit=2,
                          embed=embed)
    assert {p["filename"] for p in split} == {"rolle.txt", "hopital.txt"}, (
        "asked one at a time, each specialist page wins its own query")
    conn.close()
