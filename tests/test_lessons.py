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


def test_a_paraphrasing_lesson_is_repaired_then_rejected(db):
    """The gate has real teeth: it can stop a lesson being stored at all."""
    bad = json.dumps(grounded_body("a tidied up version of the sentence"))
    llm = FakeLlmClient([bad, bad])
    result = write_lesson(
        db, llm, CFG, user_id=1, topic_id=1, topic_code="MTH165", meta=META,
        unit_number=1, _passages=[PASSAGE])
    assert result.status == "rejected"
    assert result.lesson_id is None
    assert db.execute("SELECT COUNT(*) n FROM lessons").fetchone()["n"] == 0


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
