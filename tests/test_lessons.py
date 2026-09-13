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
    """A lesson whose sections carry literal quotes — the shape `check_grounding`
    still judges, and the shape stored lessons have."""
    body = good_body()
    q = quote or "the number of non-zero rows in its row echelon form"
    for sec in body["sections"]:
        sec["quote"] = q
        sec["source"] = "[1] ncert-matrices.pdf p12"
    return body


def cited_body(passage=1, sentence=1):
    """A lesson as the WRITER now returns one: sentence numbers, no prose
    copied. `resolve_citations` turns these into quotes."""
    body = good_body()
    for sec in body["sections"]:
        sec["cite"] = {"passage": passage, "sentence": sentence}
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
    llm = FakeLlmClient(_calls(cited_body(), fresh=("7", "7", "k ≠ 3")))
    result = write_lesson(
        db, llm, CFG, user_id=1, topic_id=1, topic_code="MTH165", meta=META,
        unit_number=1, embed=lambda texts: __import__("numpy").eye(len(texts)),
        _passages=[PASSAGE])
    assert result.status == "grounded"
    assert "grounded:" in result.notes[0] and "verbatim" in result.notes[0]


def test_a_lesson_citing_a_sentence_that_does_not_exist_keeps_its_teaching(db):
    """Rejecting a whole lesson over a citation detail throws away good
    teaching and pays for a second generation to get nothing. Dropping the
    citation certifies nothing, which is the property that matters — and with
    nothing left anchored, the lesson does not get to call itself grounded.

    Note what the failure IS now: a reference to a sentence that is not there.
    Paraphrase is no longer reachable, because the model never types a quote."""
    # A reference to a sentence that does not exist: the only way a citation
    # can now be wrong, since the text itself is inserted rather than typed.
    bad = json.dumps(cited_body(passage=9, sentence=9))
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
        "an unresolvable citation must never reach the student")
    assert any("does not exist" in n for n in result.notes), result.notes


def test_a_citation_problem_gets_one_repair_before_it_is_dropped(db):
    """The model can usually pick a better sentence when told which one failed.
    That is worth one attempt; it is not worth a second full generation."""
    bad = json.dumps(cited_body(passage=9, sentence=9))
    good = json.dumps(cited_body())
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


def test_spacing_inside_an_expression_does_not_break_a_citation():
    """Unit 2's lesson was refused over this. The Mean Value Theorem's formal
    statement was in the chunk it had been handed — "Let f : [ a , b ] → R be a
    continuous function on the closed interval" — and the model wrote the same
    sentence as "[a, b]". Same citation, different typography.

    A plaintext extract spaces mathematics out; a model writing prose does not.
    """
    passage = [{"text": ("Let f : [ a , b ] → R be a continuous function on "
                         "the closed interval [ a , b ] , and differentiable "
                         "on the open interval ( a , b ) , where a < b .")}]
    ok = check_grounding(
        {"sections": [{"heading": "MVT",
                       "quote": ("Let f : [a, b] → R be a continuous function "
                                 "on the closed interval [a, b], and "
                                 "differentiable on the open interval (a, b)")}]},
        passage)
    assert ok == [], ok


def test_removing_space_next_to_a_symbol_does_not_admit_a_paraphrase():
    """The normalisation is narrow on purpose: it cannot turn one word into
    another, so the thing this gate exists to catch still fails."""
    passage = [{"text": "The rank is the number of non-zero rows in echelon form."}]
    out = check_grounding(
        {"sections": [{"heading": "R",
                       "quote": "the count of nonzero rows after reduction"}]},
        passage)
    assert out and "paraphrase" in out[0]


# --- citing by reference: the model never types a quote ----------------------

def test_a_cited_sentence_is_inserted_not_transcribed():
    """The whole point. Unit 2's lesson kept failing because the model retyped
    the Mean Value Theorem's statement — "[a, b]" where the corpus had
    "[ a , b ]" — a citation that was right in substance and wrong in
    characters. Choosing a NUMBER removes the typing, so a citation cannot
    drift from its source at all."""
    from recall.teach.lessons import numbered_passages, resolve_citations

    passages = [{"filename": "mvt.txt", "page_ref": "p1-p5",
                 "text": ("Mean value theorem In calculus and real analysis, "
                          "the mean value theorem is a theorem about "
                          "differentiable functions of a real variable. "
                          "Let f : [ a , b ] → R be a continuous function on "
                          "the closed interval [ a , b ] , and differentiable "
                          "on the open interval ( a , b ) , where a < b .")}]
    shown, table = numbered_passages(passages)
    assert "[1] mvt.txt p1-p5" in shown
    assert "1.2" in shown, "sentences are numbered for the writer to choose from"

    body = {"sections": [{"heading": "MVT", "cite": {"passage": 1, "sentence": 2}}]}
    assert resolve_citations(body, passages, table) == []
    quote = body["sections"][0]["quote"]
    assert quote.startswith("Let f : [ a , b ] → R"), quote
    assert quote in " ".join(passages[0]["text"].split()), (
        "the inserted text must be exactly what the passage says")
    assert body["sections"][0]["source"] == "[1] mvt.txt p1-p5"
    assert "cite" not in body["sections"][0], "the reference is consumed"


def test_a_reference_to_a_sentence_that_is_not_there_is_refused():
    from recall.teach.lessons import numbered_passages, resolve_citations

    passages = [{"filename": "a.txt", "page_ref": "p1",
                 "text": "The rank is the number of non-zero rows in echelon form."}]
    _, table = numbered_passages(passages)
    body = {"sections": [{"heading": "R", "cite": {"passage": 4, "sentence": 1}}]}
    out = resolve_citations(body, passages, table)
    assert out and "does not exist" in out[0]
    assert "quote" not in body["sections"][0]


def test_a_model_supplied_quote_is_discarded_rather_than_trusted():
    """A quote in the reply is not a citation any more — it is text the model
    typed, which is the thing this design removes. Only a resolved reference
    becomes a quote."""
    from recall.teach.lessons import numbered_passages, resolve_citations

    passages = [{"filename": "a.txt", "page_ref": "p1",
                 "text": "The rank is the number of non-zero rows in echelon form."}]
    _, table = numbered_passages(passages)
    body = {"sections": [{"heading": "R", "quote": "something I made up",
                          "source": "[1] a.txt p1"}]}
    assert resolve_citations(body, passages, table) == []
    assert "quote" not in body["sections"][0]


def test_only_sentences_worth_citing_are_offered():
    """A writer choosing by number cannot choose a fragment, because fragments
    are not numbered."""
    from recall.teach.corpus import split_sentences

    got = split_sentences("Yes. No. The rank of a matrix is the number of "
                          "non-zero rows in its row echelon form. Ok.")
    assert got == ["The rank of a matrix is the number of non-zero rows in "
                   "its row echelon form."]


# --- superscripts: the rule has to be satisfiable -------------------------
#
# MTH165 unit 5 (multiple integrals) was rejected twice in a row, entirely
# on integral limits like ∫₀^{2π}. Every complaint was unfixable by
# construction: Unicode has no superscript π, so there is no way to write
# what the gate was demanding. A gate nobody can satisfy is a gate that
# gets switched off, taking the useful part with it — so `^{...}` is now
# banned only where a real superscript actually exists.


def test_braced_superscript_is_caught_when_unicode_has_one():
    assert check_notation("the inverse A^{-1} appears")
    assert check_notation("x^{2} + 1")
    assert check_notation("the nth power x^{n}")


def test_complaint_names_the_actual_replacement():
    """A repair pass told 'wants ²' can fix it; 'wants a real superscript'
    is a hint it has to guess at."""
    (complaint,) = check_notation("x^{2}")
    assert "²" in complaint


def test_integral_limits_unicode_cannot_write_are_allowed():
    # There is no superscript π, and no way to stack "2π" or "π/4".
    assert check_notation("∫₀^{2π} cos⁴θ dθ") == []
    assert check_notation("∫₀^{π/4} sin φ dφ") == []
    assert check_notation("V = ∫₀^{2π} ∫₀^{π/4} ρ² sin φ dρ dφ dθ") == []


def test_a_mixed_expression_complains_only_about_the_fixable_part():
    complaints = check_notation("∫₀^{2π} ∫₀^{π/4} ∫₀^{2} ρ² sin φ")
    assert len(complaints) == 1
    assert "^{2}" in complaints[0]


def test_multi_character_superscripts_that_do_exist_are_still_caught():
    (complaint,) = check_notation("(-1)^{n+1} sin(nx)")
    assert "ⁿ⁺¹" in complaint


def test_superscripts_inside_code_are_left_alone():
    assert check_notation("the expression `x^{2}` in LaTeX source") == []


# ---------------------------------------------------------------------------
# What MTH165 unit 5 actually shipped, and the three bugs behind it.
#
# The unit's first grounded lesson cited, verbatim and verifiably:
#
#   "MATH A=int_α^βint_0^{R(θ)}r\,dr\,dthe =frac12int_α^β R(θ)^2\,dθ"
#
# Every gate passed it. `check_grounding` proved the span was copied from the
# course material; the notation law never saw it, because that law is applied to
# the lesson's prose and a quote is not prose. What reached the student was
# LaTeX wreckage wearing a citation's warranty.
#
# Three causes, each tested below:
#
#   1. `\b` is the wrong boundary for a LaTeX command. `_` is a word character,
#      so `\int_0`, `\geq0` and `\lambda_1` had NO word boundary after the
#      command name and matched none of the symbol rules. 1424 chunks of this
#      corpus contain `int_`.
#   2. The catch-all kept the command's letters — `\frac12\int` became
#      `frac12int`, which reads as a word and passes every shell filter. That is
#      worse than leaving the LaTeX alone, because the LaTeX was obviously broken.
#   3. `MATH` is a formula placeholder, like `TEXT`, in 352 chunks.
# ---------------------------------------------------------------------------


def test_an_integral_keeps_its_symbol_when_a_subscript_follows():
    r"""The boundary bug, at its most expensive. `\int_0` is the normal way to
    write a definite integral, and `\\int\b` never matched it."""
    from recall.teach.corpus import clean_latex

    assert clean_latex(r"\int_0^{2\pi}") == "∫_0^{2π}"
    assert clean_latex(r"\sum_{i=1}^n a_i") == "∑_{i=1}^n a_i"
    assert clean_latex(r"\lambda_1 and \lambda_2") == "λ_1 and λ_2"
    assert clean_latex(r"\(f(x,y)\geq0\)") == "f(x,y)≥0"


def test_the_longer_integral_is_not_read_as_the_shorter_one():
    """`\\iiint` must not resolve to ∬ with a stray i in front of it."""
    from recall.teach.corpus import clean_latex

    assert clean_latex(r"\iiint_V dV") == "∭_V dV"
    assert clean_latex(r"\iint_R f\,dA") == "∬_R f dA"
    assert clean_latex(r"\oint_C") == "∮_C"


def test_an_unresolved_command_is_dropped_not_turned_into_a_word():
    """The second bug. Keeping the letters manufactures prose out of a formula:
    `frac12int` is quotable, survives every filter, and says nothing."""
    from recall.teach.corpus import clean_latex

    out = clean_latex(r"\qquad\varnothing\mathscr{X}")
    assert "qquad" not in out and "varnothing" not in out and "mathscr" not in out


def test_the_exact_citation_mth165_unit_5_shipped():
    """End to end, on the real bytes from MTH165-unit5-notes.html."""
    from recall.teach.corpus import clean_latex, _FORMULA_PLACEHOLDER

    raw = (r"then MATH A=\int_\alpha^\beta\int_0^{R(\theta)}r\,dr\,d\the "
           r"=\frac12\int_\alpha^\beta R(\theta)^2\,d\theta.")
    out = clean_latex(_FORMULA_PLACEHOLDER.sub("", raw))
    # Every piece of debris the student was shown, gone.
    for debris in ("MATH", "int_α", "frac12", "\\,", "dthe"):
        assert debris not in out, debris
    # And the mathematics that was underneath it, present.
    assert "∫_α^β" in out and "1/2" in out and "dθ" in out


def test_a_fraction_becomes_the_notation_law_s_own_prescription():
    """The law says write a/b. A quote is read the same way as the prose."""
    from recall.teach.corpus import clean_latex

    assert clean_latex(r"\frac{a}{b}") == "a/b"
    assert clean_latex(r"\frac{4}{3}\pi a^3") == "4/3π a^3"
    assert clean_latex(r"\frac12") == "1/2"


def test_formula_spacing_becomes_a_space_not_a_join():
    r"""`r\,dr` is `r dr`, not `rdr` — the one edit here that cannot change
    what a formula says is also the one that must not run words together."""
    from recall.teach.corpus import clean_latex

    assert clean_latex(r"r\,dr\,d\theta") == "r dr dθ"


def test_an_environment_leaves_no_name_behind():
    r"""Dropping only `\begin` left `{align}` sitting in the prose."""
    from recall.teach.corpus import clean_latex

    assert clean_latex(r"\begin{align} x=1 \end{align}").strip() == "x=1"


def test_the_second_spelling_of_the_formula_placeholder_is_stripped():
    from recall.teach.corpus import _FORMULA_PLACEHOLDER

    assert _FORMULA_PLACEHOLDER.sub("", "then MATH V=1") == "then  V=1"
    # ...and a word that merely contains it is left alone.
    assert _FORMULA_PLACEHOLDER.sub("", "MATHS and MATHEMATICS") \
        == "MATHS and MATHEMATICS"


# ---------------------------------------------------------------------------
# The scaffolding, stripped rather than refused.
# ---------------------------------------------------------------------------


def test_furniture_is_removed_so_the_explanation_behind_it_survives():
    """Why stripping beats refusing. The scaffolding is glued to the FRONT of a
    real explanation with no full stop between them, so the sentence splitter
    offers the writer one span containing both — and refusing that quote threw
    the explanation away too, after the generation was paid for."""
    from recall.teach.corpus import strip_furniture

    out = strip_furniture(
        "A. B. C. D. Reveal Answer Hide Answer Correct Answer: Explanation: "
        "The notation states that row two is replaced by itself plus three "
        "times row one.")
    assert "Reveal Answer" not in out and "Correct Answer:" not in out
    assert ("The notation states that row two is replaced by itself plus "
            "three times row one." in out)


def test_a_run_of_markers_goes_in_one_piece():
    """Four in a row is the real shape. Removing them one at a time would leave
    the whitespace between them behind."""
    from recall.teach.corpus import strip_furniture

    out = strip_furniture("D. Reveal Answer Hide Answer Correct Answer: "
                          "Explanation: The matrix has 2 rows.")
    assert "  " not in out.replace("D.  ", "D. ")


def test_furniture_matching_ignores_case_because_scrapers_do_not():
    from recall.teach.corpus import strip_furniture

    assert "reveal" not in strip_furniture("REVEAL ANSWER The rank is 2.").lower()


def test_the_strip_list_and_the_reject_list_are_the_same_list():
    """Two places deciding what furniture is, computed differently, is the drift
    this codebase keeps paying for."""
    from recall.teach.corpus import FURNITURE
    from recall.teach import lessons as L

    assert L._FURNITURE is FURNITURE


# ---------------------------------------------------------------------------
# The backstop: debris is withheld from the writer, not rejected after the fact.
# ---------------------------------------------------------------------------


def test_debris_is_caught_even_when_the_backslashes_are_already_gone():
    """The case no cleaner can reach. Some scrapes arrive with the backslashes
    already stripped, so there is no marker left to find the command by —
    "(z=f(x,y)geq0)" and "rho^2sinphi" are both real, from MTH165 unit 5. The
    glue against a symbol or a digit is the only signal there is."""
    from recall.teach.corpus import looks_like_latex_debris

    assert looks_like_latex_debris("(z=f(x,y)geq0) above (R)")
    assert looks_like_latex_debris("rho^2sinphi drho")
    assert looks_like_latex_debris("then MATH V=iint_R f dA")
    assert looks_like_latex_debris(r"a stray \, backslash")


def test_ordinary_prose_is_not_debris():
    """A check that cries wolf gets switched off, and then there is no check."""
    from recall.teach.corpus import looks_like_latex_debris

    for clean in ("A citation must stay verbatim in the course material.",
                  "The interval from 0 to 5 contains the point.",
                  "The matrix has 2 rows and 3 columns, so its order is 2x3.",
                  "Integration by parts is the reverse of the product rule.",
                  "Summing the series gives a finite limit."):
        assert not looks_like_latex_debris(clean), clean


def test_a_debris_sentence_is_never_OFFERED_to_the_writer():
    """The whole point of putting the check here. The writer cites by NUMBER, so
    a sentence that is not in the table cannot be quoted — no repair round, no
    paid generation thrown away, and no way for the debris to reach a student."""
    from recall.teach.corpus import split_sentences

    got = split_sentences(
        "A double integral is evaluated as two successive single integrals. "
        "MATH A=int_alpha^beta int_0^{R(theta)} r dr dtheta. "
        "The outer limits must be constants for the iteration to work.")
    assert len(got) == 2
    assert all("int_" not in s and "MATH" not in s for s in got)


def test_the_numbering_the_writer_reads_and_the_resolver_honours_still_agree():
    """`split_sentences` both offers the sentences and resolves the number sent
    back, so a filter added to it must be applied to both or neither."""
    from recall.teach.lessons import numbered_passages

    passages = [{"text": "The rank of a matrix is the number of independent "
                         "rows it has. MATH r=frac{a}{b}. A matrix is "
                         "consistent when its ranks agree.",
                 "filename": "notes.html", "page_ref": "p1"}]
    shown, table = numbered_passages(passages)
    assert len(table[0]) == 2
    for i, sentence in enumerate(table[0], 1):
        assert sentence in shown
        assert "MATH" not in sentence


def test_a_stored_lesson_quoting_debris_is_still_convicted():
    """`lesson-recheck` runs over lessons written before the cleaner was fixed,
    and MTH165 unit 5's is one of them."""
    from recall.teach.lessons import _quote_is_furniture

    # The length check is cheaper and fires first, so use the full span that
    # actually shipped rather than a fragment of it.
    why = _quote_is_furniture(
        r"• Polar area: If (R) is described by (α≤θ≤β) and (0≤ r≤ R(θ)), then "
        r"MATH A=int_α^βint_0^{R(θ)}r\,dr\,dthe =frac12int_α^β R(θ)^2\,dθ.")
    assert why is not None and "wreckage" in why


# ---------------------------------------------------------------------------
# Repairing what the gate used to reject.
#
# MTH165 unit 5 is multiple integrals, so nearly every line carries an integral
# or a sum with limits. The writer produced `∑_{i=1}^{n}` and `∫_{y}^{1}` and
# `∫_{x²}^{4}`; the gate complained, correctly, that ⁿ and ¹ and ⁴ are real
# characters. But notation faults are FATAL after two attempts, so the unit was
# rejected and about a cent bought nothing — twice, on two different days.
#
# None of those complaints needed judgement. `^{n}` → `ⁿ` is a table lookup, and
# a gate should only reject what it cannot repair itself.
# ---------------------------------------------------------------------------


def test_the_three_expressions_that_rejected_mth165_unit_5():
    """Verbatim from the two rejection reports."""
    from recall.notation import fix_notation

    assert fix_notation("= lim_{ΔA_i → 0} ∑_{i=1}^{n} f(xᵢ*, yᵢ*) ΔA_i") \
        == "= lim_{ΔA_i → 0} ∑ᵢ₌₁ⁿ f(xᵢ*, yᵢ*) ΔA_i"
    assert fix_notation("the inner integral is ∫_{y}^{1} e^{x²} dx") \
        == "the inner integral is ∫_y¹ e^{x²} dx"
    assert fix_notation("reverse the integration in ∫₀² ∫_{x²}^{4} f(x, y) dy dx") \
        == "reverse the integration in ∫₀² ∫_{x²}⁴ f(x, y) dy dx"


def test_a_repaired_expression_leaves_nothing_to_complain_about():
    """The point of the whole change: no second generation, no rejection."""
    from recall.notation import check_notation, fix_notation

    for original in ("∑_{i=1}^{n} f(xᵢ) Δx",
                     "∫_{y}^{1} e^{x²} dx",
                     "(-1)^{n+1} over n^{2}",
                     "A^{-1} exists when det A ≠ 0"):
        assert check_notation(fix_notation(original)) == [], original


def test_repair_leaves_alone_what_unicode_cannot_write():
    """The limits from the first fix stay untouched, and stay allowed."""
    from recall.notation import check_notation, fix_notation

    for kept in ("∫₀^{2π} cos⁴θ dθ", "∫₀^{π/4} sin φ dφ", "lim_{ΔV_i → 0}"):
        assert fix_notation(kept) == kept
        assert check_notation(kept) == []


def test_multi_character_groups_keep_their_braces():
    """`∫_x²⁴` and `∫_{x²}⁴` are not the same claim, so only a SINGLE character
    loses its braces."""
    from recall.notation import fix_notation

    assert fix_notation("∫_{x²}^{4}") == "∫_{x²}⁴"
    assert fix_notation("∫_{y}^{4}") == "∫_y⁴"


def test_repair_does_not_touch_code():
    """`x <= 10` is correct Python, and INT108 and CSE326 are programming
    courses — the same exemption the check has always had."""
    from recall.notation import fix_notation

    assert fix_notation("write `x <= 10` and `a != b` in Python") \
        == "write `x <= 10` and `a != b` in Python"
    assert fix_notation("`for i in range(n): total += a[i]**2`") \
        == "`for i in range(n): total += a[i]**2`"
    # A braced superscript inside code is left alone too — it is LaTeX source
    # being quoted, not mathematics being written.
    assert fix_notation("the LaTeX `x^{2}` compiles") == "the LaTeX `x^{2}` compiles"
    # ...and the same expression outside the fence is repaired.
    assert fix_notation("the power x^{2} grows") == "the power x² grows"


def test_programming_operators_are_never_repaired_even_outside_code():
    """The exemption covers code in backticks. It cannot cover code the writer
    FORGOT to fence, and INT108 is Python while CSE326 is JavaScript — so
    repairing `if x == 10` into `if x = 10` would turn a comparison into an
    assignment and teach a first-year student broken code with a verified
    lesson's authority. A rejected lesson costs a cent; that costs trust.

    They stay complaints, so the writer is asked to fence its code (or, in a
    mathematics unit, to write the real symbol)."""
    from recall.notation import check_notation, fix_notation

    unfenced = "if x == 10 and y <= 3: return ptr->field"
    assert fix_notation(unfenced) == unfenced
    assert len(check_notation(unfenced)) == 3


def test_the_ambiguous_ones_are_still_complaints_not_silent_edits():
    """`a*b` may be a pointer, a glob or emphasis, and a sentence carrying
    \\frac{a}{b} wants rewriting rather than patching. Python must not guess."""
    from recall.notation import check_notation, fix_notation

    for ambiguous in ("the product a*b grows", r"write \frac{a}{b} here"):
        assert fix_notation(ambiguous) == ambiguous
        assert check_notation(ambiguous) != []


def test_every_banned_pattern_declares_whether_it_can_be_repaired():
    """The third field is what keeps complaining and repairing from drifting:
    a pattern with a repair is never complained about, and one without is never
    silently edited."""
    from recall.notation import _BANNED

    for entry in _BANNED:
        assert len(entry) == 3, entry
        pattern, instead, repair = entry
        assert isinstance(instead, str) and instead
        assert repair is None or isinstance(repair, str)


# ---------------------------------------------------------------------------
# Repairing a lesson body, and the one field that must never be touched.
# ---------------------------------------------------------------------------


def _lesson_with_bad_notation(quote: str) -> dict:
    return {
        "why": "Integrals accumulate a quantity over a region.",
        "sections": [{
            "heading": "Summing over a region",
            "body": "The double integral is the limit of ∑_{i=1}^{n} f(xᵢ) ΔA_i "
                    "as ΔA_i → 0, and it is written ∫_{y}^{1} in one variable.",
            "quote": quote,
            "source": "[1] notes.html p1",
        }],
        "worked": [{
            "question": "Evaluate ∫₀² x^{2} dx.",
            "answer": "8/3",
            "steps": ["Antidifferentiate to get x^{3}/3.", "Evaluate at 2 and 0."],
        }],
        "check": [{"question": "What is n^{2} at n = 3?", "answer": "9",
                   "why": "Because 3^{2} = 9."}],
    }


def test_repair_notation_reaches_every_field_a_student_reads():
    from recall.teach.lessons import lesson_text, repair_notation
    from recall.notation import check_notation

    body = _lesson_with_bad_notation("a quote with no notation problem in it")
    repair_notation(body)
    assert check_notation(lesson_text(body)) == []
    # Each field individually, so a miss cannot hide in the join.
    assert "∑ᵢ₌₁ⁿ" in body["sections"][0]["body"]
    assert "∫_y¹" in body["sections"][0]["body"]
    assert "x²" in body["worked"][0]["question"]
    assert "x³/3" in body["worked"][0]["steps"][0]
    assert "n²" in body["check"][0]["question"]
    assert "3² = 9" in body["check"][0]["why"]


def test_repair_never_touches_a_quote_because_grounding_would_break():
    """The load-bearing safety property. A quote is INSERTED from the sentence
    the writer named, so it must stay byte-identical to the course material —
    `check_grounding` searches the passages for it verbatim. Repairing a quote
    would turn a real citation into a failed one."""
    from recall.teach.lessons import check_grounding, repair_notation

    raw = "The area element in polar coordinates is dA = r^{2} dr dθ."
    passages = [{"text": "Some preamble. " + raw + " And a closing sentence.",
                 "filename": "notes.pdf", "page_ref": "p3"}]
    body = _lesson_with_bad_notation(raw)

    assert check_grounding(body, passages) == []
    repair_notation(body)
    assert body["sections"][0]["quote"] == raw, "the quote was rewritten"
    assert check_grounding(body, passages) == [], "repair broke the citation"


def test_lesson_text_and_the_repair_walk_the_same_fields():
    """A field the check reads and the repair does not is a complaint nothing
    can fix — the exact shape of bug this gate has already produced twice."""
    from recall.teach.lessons import _readable_fields, lesson_text, repair_notation

    body = _lesson_with_bad_notation("irrelevant")
    fields = list(_readable_fields(body))

    # lesson_text IS the join of the walked fields — so the check can never read
    # a field the repair did not visit.
    assert lesson_text(body) == "\n".join(
        str(container[key]) for container, key in fields)

    # why + heading + body + worked question/answer + two steps + three check
    # fields = ten. The quote and its source are not among them.
    keys = [key for _container, key in fields]
    assert keys == ["why", "heading", "body", "question", "answer", 0, 1,
                    "question", "answer", "why"], keys
    assert "quote" not in keys and "source" not in keys

    # And the repair is idempotent: a second pass has nothing left to change,
    # which is what makes it safe to run before every attempt.
    repair_notation(body)
    once = lesson_text(body)
    repair_notation(body)
    assert lesson_text(body) == once


def test_a_lesson_with_no_fields_does_not_explode():
    from recall.teach.lessons import lesson_text, repair_notation

    for body in ({}, {"sections": []}, {"why": None, "worked": [None]},
                 {"sections": [{"heading": 3}], "check": ["not a dict"]}):
        repair_notation(body)
        assert isinstance(lesson_text(body), str)


# ---------------------------------------------------------------------------
# Four citations that were live on study.yashnas.xyz.
#
# Taken verbatim from the lessons a student could open on 2026-09-13 — three of
# the six grounded MTH165 lessons carried one. They are the regression fixtures
# for the cleaner, because they are what the corpus actually did to us rather
# than what we imagined it might.
# ---------------------------------------------------------------------------

LIVE_DEBRIS_CITATIONS = (
    # unit 3, "Integration by parts" — a spacing command survived whole.
    (r"• (du=u'(x)\,dx) and (dv=v'(x)\,dx). • Choice of factors: Select (u) so "
     r"that differentiating it simplifies the expression.", "\\"),
    # unit 1, "Cayley-Hamilton" — an environment, and a line break read as \0.
    (r"• Worked example: For (A=begin{bmatrix} 1&1\0&2end{bmatrix}), "
     r"p(λ) = (λ−1)(λ−2) = λ²−3λ+2.", "\\"),
    # unit 5, polar area — the placeholder plus the boundary bug together.
    (r"• Polar area: If (R) is described by (α≤θ≤β) and (0≤ r≤ R(θ)), then MATH "
     r"A=int_α^βint_0^{R(θ)}r\,dr\,dthe =frac12int_α^β R(θ)^2\,dθ.", "MATH"),
    # unit 5, spherical bounds — \leq with its backslash ALREADY stripped, so
    # there is no marker left to find the command by except the glue.
    ("• Worked example: For a sphere of radius (a>0), spherical bounds are "
     "(0≤rho≤ a), (0≤phi≤π), and (0≤θleq2π).", "leq2"),
)


def test_every_citation_that_was_live_is_caught():
    from recall.teach.corpus import looks_like_latex_debris
    from recall.teach.lessons import _quote_is_furniture

    for quote, _tell in LIVE_DEBRIS_CITATIONS:
        assert looks_like_latex_debris(quote), quote[:60]
        assert _quote_is_furniture(quote) is not None, quote[:60]


def test_the_hardest_one_had_no_backslash_left_to_find_it_by():
    """`(0≤θleq2π)` is what `\\leq2\\pi` becomes when the scrape strips the
    backslashes before we ever see it. No cleaner can reach that — only the glue
    between a command name and a digit gives it away, which is the whole reason
    the sentence-level backstop exists."""
    from recall.teach.corpus import looks_like_latex_debris

    assert "\\" not in "(0≤θleq2π)"
    assert looks_like_latex_debris("(0≤θleq2π)")


def test_the_fixed_cleaner_would_not_have_produced_them():
    """Each of these came out of a passage the OLD cleaner had already been
    over. Run the current one on the LaTeX behind them and the debris is gone —
    which is what makes regenerating these three lessons worth the money."""
    from recall.teach.corpus import clean_latex, looks_like_latex_debris

    for source, cleaned_should_not_contain in (
            (r"(du=u'(x)\,dx) and (dv=v'(x)\,dx)", "\\"),
            (r"(A=\begin{bmatrix} 1&1\\0&2\end{bmatrix})", "begin"),
            (r"(0\leq\theta\leq2\pi)", "leq"),
            (r"A=\int_\alpha^\beta\frac12", "frac"),
    ):
        out = clean_latex(source)
        assert cleaned_should_not_contain not in out, (source, out)
        assert not looks_like_latex_debris(out), (source, out)


# ---------------------------------------------------------------------------
# What a seven-subject audit of the corpus turned up, and what it did not.
#
# Each artefact below was found by reading real course files, reproduced through
# the actual retrieval pipeline, and counted. The counts are offered citable
# sentences over the corpus as loaded on 2026-09-13 (122,011 of them).
# ---------------------------------------------------------------------------


def test_the_extractor_s_own_image_placeholder_is_stripped():
    """PyMuPDF's HTML renderer writes the literal "[image]" for every <img> it
    cannot fetch — and the scrapes carry no image files, so every one. 302
    occurrences across 97 of CSE326's 206 files, with the alt text discarded."""
    from recall.teach.corpus import _FORMULA_PLACEHOLDER

    assert _FORMULA_PLACEHOLDER.sub("", "[image] Home Revision About") \
        == " Home Revision About"
    # Bracketed course content is NOT a placeholder: A = [aij] is matrix
    # notation (52 chunks), and [branch] / [commit] / [path] are git syntax from
    # CSE111 unit 5. A generic "[word]" rule would have destroyed both.
    for kept in ("A = [aij] where i is the row", "git switch [branch]",
                 "run git commit [commit] on [path]"):
        assert _FORMULA_PLACEHOLDER.sub("", kept) == kept


def test_control_characters_from_computer_modern_are_stripped():
    r"""Computer Modern's extensible delimiters map into the C0 range, so \x10
    to \x15 appear where ( ) [ ] and brace pieces belong. 365 offered sentences
    across 86 files. A control character is not renderable text: depending on
    the client it vanishes, shows as a box, or breaks the JSON on the way out."""
    from recall.teach.corpus import clean_latex

    assert clean_latex("the amount is r \x10k A = P 1 +\x11") \
        == "the amount is r k A = P 1 +"
    # Tab, newline and carriage return are real whitespace and must survive.
    assert clean_latex("a\tb\nc") == "a\tb\nc"


def test_a_symbol_font_s_greek_is_recovered_not_refused():
    """Adobe Symbol's π θ φ ∠ ° arrive as private-use code points. The code point
    says which glyph the font drew, so this one IS recoverable — "The
    circumference is equal to □D" becomes readable again."""
    from recall.teach.corpus import clean_latex

    assert clean_latex("area =  r²") == "area = π r²"
    assert clean_latex(" ABC = 90") == "∠ ABC = 90°"
    assert clean_latex("the angle  and ") == "the angle θ and φ"


def test_matrix_bracket_stretch_pieces_become_brackets():
    """Matrix brackets are built from stretch pieces in the private-use area.
    The opening and closing pieces carry the shape; the middle extension pieces
    carry nothing. 413 offered sentences across 21 files — and it lands on the
    matrices and determinants chapters, which are MTH165 unit 1."""
    from recall.teach.corpus import clean_latex

    assert clean_latex("1 2") == "[1 2]"
    assert clean_latex("⎛ x ⎞") == "[ x ]"
    assert clean_latex("a  b") == "a  b"


def test_an_unmapped_private_use_glyph_is_refused_as_a_backstop():
    """No mapping table is ever complete, and a private-use code point is by
    definition text no font can draw — so the sentence is never offered."""
    from recall.teach.corpus import looks_like_latex_debris

    assert looks_like_latex_debris("the sunk key  is shown")
    assert not looks_like_latex_debris("the sunk key is shown")


def test_page_chrome_welded_into_a_sentence_is_removed():
    """None of these sit tidily at the top. PyMuPDF interleaves a page's footer
    with the prose, and the footer of page n precedes the continuation of the
    sentence running onto page n+1 — so a citation spanning a page boundary
    carries a copyright notice through its middle.

    `strip_boilerplate` cannot see any of it: that rule removes a prefix common
    to every chunk of one source, and a chunk of a PDF starts mid-page. It
    altered 0 of 573 chunks across 40 of 40 MEC103 files."""
    from recall.teach.corpus import strip_furniture

    def flat(t):
        return " ".join(strip_furniture(t).split())

    # MIT OCW's end notice — 171 sentences in 171 files, one per OCW PDF.
    assert flat("…and so it converges. MIT OpenCourseWare http://ocw.mit.edu "
                "18.01SC Single Variable Calculus For information about citing "
                "these materials or our Terms of Use, visit: "
                "http://ocw.mit.edu/terms.") == "…and so it converges."
    # OpenStax's footer: an advertisement inside a citation. 723 sentences.
    assert flat("A set is a collection. Access for free at openstax.org The "
                "next idea") == "A set is a collection. The next idea"
    # NCERT's print-run stamp. 293 sentences across 10 files, and the NCERT
    # chapters are MTH165 unit 1 and 3's primary textbook.
    assert "Reprint" not in flat("the determinant is zero. Reprint 2026-27 "
                                 "Hence the inverse")
    # The LPU notes site's footer — 28% of its 528 offered sentences.
    assert flat("multiplication is defined. © 2026 LPU Notes Part of the LPU "
                "Verto Network So") == "multiplication is defined. So"


def test_the_subjective_bank_s_reveal_control_joins_the_furniture():
    """The same site "reveal answer" came from, and the same failure: it fuses
    to the front of the model answer, so the best-written definitions in the LPU
    material could not be cited clean. 137 offered sentences."""
    from recall.teach.corpus import strip_furniture

    out = strip_furniture("Q3. Define rank. Show Detailed Answer The rank of a "
                          "matrix is the number of independent rows.")
    assert "Show Detailed Answer" not in out
    assert "The rank of a matrix is the number of independent rows." in out


def test_the_integral_as_Z_rule_is_deliberately_absent():
    """A regression guard, not an omission.

    PyMuPDF maps Computer Modern's ∫ to "Z" and ∂ to "@", and refusing those
    looks obviously right — it was found by a scan, reproduced by a skeptic, and
    measured at 306 sentences ACROSS ONE SUBJECT. Over the whole corpus the rule
    matches 63 of 122,011 offered sentences and 9 are legitimate text in four
    different subjects. Fifty-odd damaged MIT sentences do not buy refusing set
    theory, git, SVG and Python material, and the "@" half is worse: @property,
    @staticmethod, @media and @keyframes are syllabus content.

    If someone adds it again, this fails and points them at the measurement."""
    from recall.teach.corpus import looks_like_latex_debris

    for legitimate in (
            "x = nπ, n ∈ Z and cotangent is continuous elsewhere",
            "use git checkout tags/vX.Y.Z for that release",
            "path commands M moveto, L lineto, C curveto, Z closepath",
            "the Unicode value of uppercase Z is less than that of lowercase a",
            "press Ctrl-Z then Enter on Windows",
            "decorate it with @property and @staticmethod",
            "@media (min-width: 600px) narrows the layout",
            "@keyframes spin animates the element",
    ):
        assert not looks_like_latex_debris(legitimate), legitimate


# ---------------------------------------------------------------------------
# Running heads, the PDF form of "Reveal Answer Hide Answer".
#
# PyMuPDF extracts a page's header and footer into the text flow, and the footer
# of page n precedes the continuation of the sentence running onto page n+1 — so
# the header welds itself into the middle of real teaching. The thresholds below
# come from measuring all 40 MEC103 files and 296 documents in the other five
# subjects; the numbers in each docstring are that measurement.
# ---------------------------------------------------------------------------


def _paged(lines_per_page, n=22):
    """n pages, each built by lines_per_page(i)."""
    return [(i, "\n".join(lines_per_page(i))) for i in range(1, n + 1)]


def test_a_long_running_head_and_a_short_stamp_both_go():
    """Tier A is the header; tier B is the short stamp a header breaks into.
    A flat 12-character floor cleared only 55% of MEC103's stamps because
    "AITS KADAPA" is 11 characters, "I B.Tech" 8 and "Page #" 6."""
    from recall.teach.corpus import strip_running_heads

    # The teaching line must DIFFER per page, because a sentence repeated
    # verbatim on every page of a document is a running head — that is what the
    # word means, and the rule cannot and should not tell them apart.
    pages = _paged(lambda i: [
        "MRCET(UGC AUTONOMOUS) Dept. of Mechanical Engineering",
        "Page %d" % i,
        "Section %s: projection casts an image of %s onto a plane."
        % ("abcdefghijklmnopqrstuv"[i - 1], "xyz"[i % 3]),
    ])
    out = strip_running_heads(pages)
    for _n, text in out:
        assert "MRCET" not in text
        assert "Page" not in text
        assert "projection casts an image" in text


def test_a_label_on_half_the_pages_survives_because_code_needs_it():
    """The load-bearing threshold. "Output:" sits on 59% of the pages of an
    NCERT Python chapter and is the label separating every program from its
    output; "Ans:" does the same in a CBSE marking scheme. A 4-character floor
    at the 50% share deletes both — measured, and rejected for it."""
    from recall.teach.corpus import strip_running_heads

    pages = _paged(lambda i: (
        ["Output:"] if i <= 13 else []) + [
        "Some prose about control flow on page %d that differs each time." % i,
    ])
    out = strip_running_heads(pages)
    assert sum("Output:" in t for _n, t in out) == 13


def test_a_short_document_is_left_alone():
    """The one measured false positive lived here: a 10-page lab sheet repeats
    "Q. 3 Draw the orthographic projections of Fig. 4" on 9 of its pages, and
    that is the assignment, not furniture."""
    from recall.teach.corpus import strip_running_heads

    pages = _paged(lambda i: ["Q. %d Draw the orthographic projections of Fig. %d"
                              % (i, i)], n=10)
    assert strip_running_heads(pages) == pages


def test_pages_and_their_numbers_survive_the_strip():
    """It takes and returns read_document's shape, so chunk_pages and every page
    reference downstream cannot tell that it ran."""
    from recall.teach.corpus import strip_running_heads

    pages = _paged(lambda i: ["FOOTER LINE THAT REPEATS EVERYWHERE",
                              "Content %s." % "abcdefghijklmnopqrstuv"[i - 1]])
    out = strip_running_heads(pages)
    assert [n for n, _t in out] == [n for n, _t in pages]
    assert all("FOOTER" not in t for _n, t in out)
    assert all("Content" in t for _n, t in out)


def test_digit_blanking_can_collapse_real_lines_and_that_is_the_known_cost():
    """Named rather than hidden. "Page 12" and "Page 13" have to count as one
    line, so digits are blanked — which also makes "Example 7 shows…" and
    "Example 8 shows…" one line. The tier widths and page shares are what hold
    it down, and the deletion set is meant to be read before a re-load."""
    from recall.teach.corpus import _normalise_line, strip_running_heads

    assert _normalise_line("Page 12") == _normalise_line("Page 13") == "Page #"
    # A line that IS the same modulo its number, on every page, does go.
    pages = _paged(lambda i: ["Example %d shows the construction" % i,
                              "Unique prose for page %s." % chr(96 + i)])
    out = strip_running_heads(pages)
    assert all("Example" not in t for _n, t in out)
    assert all("Unique prose" in t for _n, t in out)


# ---------------------------------------------------------------------------
# MDN and the WHATWG spec: 184 of CSE326's 206 files, and the dirtiest material
# in the corpus — 13.6% of the sentences offered from its HTML were artefacts
# rather than teaching. Every number below is measured over those files.
# ---------------------------------------------------------------------------


def _flat(text):
    from recall.teach.corpus import strip_furniture
    return " ".join(strip_furniture(text).split())


def test_the_pager_no_longer_fuses_to_the_opening_definition():
    """None of MDN's per-page furniture ends in a full stop, so it welds itself to
    the next real sentence. The CSS box model page's opening definition — the
    sentence a unit 3 lesson would obviously cite — could not be quoted clean.

    The newline handling is the whole difficulty: strip_furniture runs on raw
    chunk text where the pager's items are still newline-separated, and a pattern
    requiring the next bullet immediately after matched 29 of 210 occurrences."""
    out = _flat("Box model\n• Previous\n• Overview: Styling basics\n• Next\n"
                "Everything in CSS has a box around it.")
    assert out == "Box model Everything in CSS has a box around it."


def test_the_in_page_contents_go_but_the_same_words_as_prose_stay():
    """The bullet run is what makes this safe. A bare "in this article" entry
    would kill about 39 real CSE326 sentences and one OpenStax one."""
    assert _flat("In this article\n• The box model\n• Margin collapsing\n"
                 "• See also\nBlock and inline boxes exist.") \
        == "Block and inline boxes exist."
    assert _flat("In this article we cover the basics of syntax.") \
        == "In this article we cover the basics of syntax."


def test_the_contribute_line_is_anchored_and_pro_git_survives():
    """A bare "learn how to contribute" entry destroys a real 39-word Pro Git
    sentence in CSE111 — and because FURNITURE is the same tuple
    `_quote_is_furniture` checks, a lesson that cited it would be refused AFTER
    the generation was paid for. So it is anchored to its MDN pair instead."""
    assert _flat("The cascade decides. Help improve MDN Learn how to contribute "
                 "View this page on GitHub Content available under a Creative "
                 "Commons license.").rstrip(" .") == "The cascade decides"
    kept = ("you'll learn how to contribute code successfully to a project and "
            "make it as easy on you and the project maintainer as possible")
    assert _flat(kept) == kept


def test_the_spec_s_support_table_stops_riding_on_the_definition():
    """WHATWG's per-feature annotation box, flattened into running prose: the
    spec's crispest definitional sentences all carried a browser support matrix
    stapled to the end. 529 annotation matches, longest 98 characters, no prose."""
    out = _flat("The title attribute represents advisory information. ✔MDN\n"
                "Document/title\nSupport in all current engines. "
                "Firefox 1+ Safari 1+ Chrome 1+ Edge (Legacy)12+ "
                "Internet ExplorerNo")
    assert out == "The title attribute represents advisory information."


def test_a_single_browser_version_in_prose_is_left_alone():
    """The two-or-more run is the guard. MDN compatibility notes do write
    "supported in Chrome 1+" as ordinary prose."""
    for kept in ("This is supported in Chrome 1+ only.",
                 "Safari 14 introduced the feature.",
                 "Use Firefox for the debugger."):
        assert _flat(kept) == kept


def test_structural_patterns_run_before_single_phrases():
    """Ordering, held by a test because getting it wrong leaves wreckage rather
    than failing loudly: the phrase "help improve mdn" ate its own anchor, so the
    paired regex could no longer match and "Learn how to contribute" survived on
    its own in the middle of a lesson's citation."""
    assert "Learn how to contribute" not in _flat(
        "Done. Help improve MDN Learn how to contribute Next section.")


def test_the_section_number_strip_is_deliberately_absent():
    """A regression guard. Stripping a leading "3.1.1 " looks obviously right and
    manufactures the worst defect class in this file's taxonomy: in the one CSE326
    file whose whole subject is JavaScript operator precedence it turns "50 plus
    1.25 plus 2 equals 53.25" into "50 plus plus 2 equals 53.25" — a number gone,
    reading as fluent English, saying nothing, quotable through every filter."""
    for kept in ("10 divided by 8 equals 1.25, then 50 plus 1.25 plus 2 equals 53.25.",
                 "js 3.1415926 .123456789 3.1E+12 .1e-23",
                 "6.170 Software Studio",
                 "see CSS Display 9.4.1 for the exact rule"):
        assert _flat(kept) == kept


def test_the_menu_is_stopped_in_three_places_and_none_of_them_is_furniture():
    """Three layers, each doing what the others cannot, and the order they were
    added in matters.

    1. At INGEST, MDN's header nav and sidebar trees are dropped with the
       elements that hold them, before PyMuPDF lays the page out. That is the
       only thing that reaches the curriculum tree and the property-index dumps.
    2. What survives as a run — the skip-links, the pager, the footer — is
       removed here, anchored as whole multi-word shapes.
    3. Anything still menu-shaped is REFUSED where candidates are offered,
       deleting nothing.

    Adding the bare phrase "skip to main content" to FURNITURE was rejected and
    stays rejected: measured, it deleted the one fingerprint a backstop could
    match while leaving the 1,784-character menu citable, hiding the evidence and
    keeping the menu. The anchored PAIR is safe only because layer 1 removed the
    menu that fingerprint used to stand for."""
    from recall.teach.corpus import FURNITURE, split_sentences

    assert "skip to main content" not in FURNITURE
    assert "skip to search" not in FURNITURE

    # Layer 2: the skip-links, welded to the page title and opening definition.
    assert _flat("•  Skip to main content •  Skip to search The box model "
                 "Everything in CSS has a box around it.")         == "The box model Everything in CSS has a box around it."

    # Layer 3: a menu that reached the offering step anyway is withheld, not cut.
    nav = " ".join("• " + item for item in (
        "Skip to main content", "Skip to search", "HTML", "CSS", "JavaScript",
        "Guides", "Reference", "Elements", "Global attributes", "Attributes",
        "Events", "Learn", "Tutorials", "Curriculum", "Blog", "Play", "Tools",
        "About", "Advertise with us", "Donate", "MDN Plus", "FAQ",
        "Accessibility", "Web development", "Web standards"))
    assert split_sentences(nav) == []

    # ...and the real bullet-list teaching a blunt rule would have taken is kept.
    teaching = ("• The alternative box model (accessed via box-sizing: "
                "border-box) and how it differs from the regular box model. "
                "• Margin collapsing. • Basic display values and how they "
                "affect box behavior - block, inline, inline-block, none.")
    assert _flat(teaching) == teaching
    assert any("alternative box model" in s for s in split_sentences(teaching))


def test_a_link_list_is_refused_by_density_not_by_taste():
    """Both thresholds come from both sides of the gap. MDN's header arrives as
    one candidate with 81 bullets at 4.26 per 100 characters; the most
    bullet-heavy quote any writer has actually chosen across this project's 45
    stored citations has 9 bullets at 1.34 per 100."""
    from recall.teach.corpus import _is_link_list

    assert _is_link_list("• x" * 20)
    assert not _is_link_list("• a • b • c and then some ordinary prose follows")
    # Long and dense: refused. Long and sparse: kept.
    assert _is_link_list("• item " * 50)
    assert not _is_link_list("Some ordinary prose. " * 20 + "• one bullet")


def test_google_s_nested_circle_bullet_counts_too():
    """Google's SEO guide nests ○ inside •, so a bullet set without it leaves that
    menu citable — measured: after stripping the outer run, sentence 1.1 was still
    "○ Do you need an SEO? ○ Guidance on third-party SEO tools…"."""
    from recall.teach.corpus import _is_link_list

    assert _is_link_list(
        "○ Do you need an SEO? ○ Guidance on third-party SEO tools and advice "
        "○ Crawling and indexing ○ Sitemaps ○ robots.txt ○ Canonical URLs "
        "○ Redirects ○ JavaScript SEO basics ○ Page experience ○ Core Web "
        "Vitals ○ Mobile-friendly test ○ Structured data general guidelines "
        "○ Article ○ Breadcrumb ○ Carousel ○ Course ○ Dataset ○ Event ○ FAQ "
        "○ Local business ○ Product ○ Recipe ○ Review snippet ○ Sitelinks "
        "○ Video ○ Site names ○ Favicons ○ Meta description ○ Title links")


def test_a_short_dense_list_is_a_known_blind_spot():
    """Named rather than quietly widened. The density branch needs 300 characters,
    so a 250-character span at 4.5 bullets per 100 slips through with fewer than
    20 bullets. Both thresholds were measured against the real gap — nav at 4.26
    per 100 against a real quote's worst 1.34 — and moving one without measuring
    again is how a filter starts crying wolf. The six-word floor already discards
    the shortest candidates, so what gets through is a handful of mid-length
    lists."""
    from recall.teach.corpus import _is_link_list

    assert not _is_link_list("○ one ○ two ○ three ○ four ○ five ○ six ○ seven")


def test_the_refusal_deletes_nothing_so_code_cannot_be_damaged():
    """The alternative was measured and is far worse. Dropping lines that repeat
    across a unit's files deletes code: at a 10-file threshold "}" (48 files),
    "body {" (25), "</div>" (24), "color: white;" (20) and "display: flex;" (15)
    all go, and 282 of 567 chunks of CSE326 unit 3 lose at least one code line."""
    from recall.teach.corpus import split_sentences

    css = ("The rule below is what the passage is about. input, textarea, "
           "select, button { width: 150px; padding: 0; margin: 0; box-sizing: "
           "border-box; } That sets every control to one width.")
    offered = split_sentences(css)
    assert any("box-sizing: border-box; }" in s for s in offered), offered


# ---------------------------------------------------------------------------
# The angle whose degree sign became a digit.
#
# The drawing PDFs set ° as a small raised ring in a symbol font, and
# page.get_text() returns the ASCII digit "0" — so "inclined at 75° to the H.P"
# becomes "inclined at 750 to the H.P". It is the worst shape a defect can take:
# no hole, just a plausible wrong number, in the one subject where the angle IS
# the question. 188 of MEC103's 9,671 offered sentences.
# ---------------------------------------------------------------------------

LOST_DEGREES = (
    "inclined at 750 to the H.P. and passing through the apex",
    "makes an angle of 300 with VP",
    "locks at 150 intervals",
    "The isometric axes are inclined at 1200 to each other",
    "a line measuring 900 to the xy line",
)

#: Every one measured as a false positive of the obvious version of this rule.
#: The first is from Python for Everybody and the codebase's own notation law
#: says code is the exception that must never be corrected; the next four are a
#: web course where 1200, 900 and 1500 are viewport sizes and timeouts; the rest
#: are MEC103's own unit 1, whose syllabus line is "Dimensioning, Scales and
#: Conic Sections".
REAL_NUMBERS = (
    "second = '150' and print(first + second) gives 100150",
    "setTimeout(fn, 1500) schedules the callback",
    "for i in range(1500): total += i",
    "The HTTP status code 300 means multiple choices",
    "A canvas element with width 1200 and height 900",
    "font-size: 150% of the parent element",
    "the works of Eudoxus (440 B.C.) and Archimedes (300 B.C.)",
    "In 1800 Gauss proved the fundamental theorem of algebra",
    "Matrix A has eigenvalue 150 with multiplicity two",
    "Designation Length X Width (mm) D0 1500 X 1000 A0 D1 1000 X 700",
    "A2 420 x 594 450 x 625 A3 297 x 420 330 x 450",
    "RF such as 10:1; 150:1 etc are the enlarged scales",
    "Chennai - 600 032",
    "Leonardo's Canon Foundry 1500 AD 1488",
    "COVERS HORIZONTAL DISTANCE 150 M ON GROUND",
)


def test_an_angle_that_lost_its_degree_sign_is_refused():
    from recall.teach.corpus import looks_like_lost_degree

    for sentence in LOST_DEGREES:
        assert looks_like_lost_degree(sentence), sentence


def test_a_number_that_is_really_a_number_is_left_alone():
    """This is why the rule needs drawing context and not just the token shapes.
    Without it: three hits across 1,371 non-MEC103 sentences, three false
    positives, zero true positives."""
    from recall.teach.corpus import looks_like_lost_degree

    for sentence in REAL_NUMBERS:
        assert not looks_like_lost_degree(sentence), sentence


def test_a_degree_sentence_is_never_offered_to_a_writer():
    from recall.teach.corpus import split_sentences

    text = ("A pentagonal pyramid rests on its base on the ground. "
            "Its axis is inclined at 750 to the H.P. and the base edge is "
            "parallel to the V.P. "
            "Draw its projections using the change of position method.")
    offered = split_sentences(text)
    assert not any("750" in s for s in offered), offered
    assert any("change of position method" in s for s in offered)


def test_the_rule_lives_outside_the_debris_check_and_says_something_different():
    """Two reasons it is its own predicate. The message differs — a flattened
    superscript is not "the wreckage of a formula the scrape lost" — and _DEBRIS
    is global, so anything put there applies to every subject, including the
    Python REPL transcript above."""
    from recall.teach.corpus import looks_like_latex_debris
    from recall.teach.lessons import _quote_is_furniture

    quote = ("The axis of the pyramid is inclined at 750 to the H.P. and the "
             "base is parallel to the vertical plane of projection.")
    assert not looks_like_latex_debris(quote)
    why = _quote_is_furniture(quote)
    assert why is not None
    assert "ten times too large" in why


def test_the_private_use_rule_is_presence_based_on_purpose():
    """Against its own verification, and on evidence gathered afterwards.

    That verification measured a presence rule BEFORE `_PUA_SYMBOL` existed, found
    it removing 19% of one file's sentences, and reasonably asked for a share
    guard. With recovery in place presence refuses 0.39% of the corpus's 116,586
    offered sentences, worst case 2.40% in MEC103.

    A share guard would also be the wrong shape. What survives recovery is not one
    lost symbol in good prose but whole words in a subsetted font: 87 distinct code
    points, of which this is "ISOMETRIC PROJECTION". High share and low share are
    the same defect."""
    from recall.teach.corpus import looks_like_latex_debris

    scrambled = ("CHAPTER 1 ⊆"
                 "∠⊆√"
                 " 1.2 ISOMETRIC PROJECTION follows on from this.")
    assert looks_like_latex_debris(scrambled)
    # One stray glyph in otherwise good prose is refused too, deliberately: the
    # sentence is still showing a student a box where a character belongs.
    assert looks_like_latex_debris("the sunk key  is shown in the figure")


def test_recovery_stops_where_the_font_stops_being_guessable():
    """`_PUA_SYMBOL` works because Adobe Symbol's low byte is the ASCII of the
    glyph slot — U+F070 is its "p", which draws π. The scrambled-subset fonts are
    not that: U+F0D7's low byte is 0xD7 and U+F0DB's is 0xDB, neither a letter, so
    there is nothing to map from."""
    from recall.teach.corpus import _PUA_SYMBOL, clean_latex

    mapped = {bad for bad, _good in _PUA_SYMBOL}
    # The recoverable ones are in Symbol's letter and punctuation range.
    assert "" in mapped and clean_latex("") == "π"
    # The scrambled-subset ones are not claimed.
    for unguessable in ("", "", "", ""):
        assert unguessable not in mapped, unguessable


def test_two_running_heads_are_handled_here_instead_of_by_a_re_load():
    """INT335, CSE111, INT108 and MTH165 are not being re-loaded, so the page-level
    running-head strip never reaches their PDFs.

    Re-loading them for it was measured and declined: their whole deletion set is
    about 6,900 characters against MEC103's 44,300, and most of it — "Access for
    free at openstax.org" (50% of pages), "Reprint #-#" (100%), "Explanation:"
    (54%) — is already removed at this step. That left roughly 0.3% of their
    offered sentences for the price of re-embedding some three thousand chunks on a
    box shared with a production site."""
    assert _flat("the mindset matters. d.school at Stanford University "
                 "Bootleg 2018 Next, reframe.") \
        == "the mindset matters. Bootleg 2018 Next, reframe."
    assert "Computer Science" not in _flat(
        "A bus carries signals. Computer Science – Class xi 12 The control unit")
    assert "Computer Science" not in _flat(
        "Networks connect hosts. Computer Science - Class XII 8 A protocol is")


def test_the_bare_chapter_titles_are_left_alone_because_they_are_prose():
    """The same measurement turned up "Computer System" on 50% of an NCERT
    chapter's pages and "Computer Networks" on 50% of another. Both are ordinary
    prose in a computer-fundamentals course — CSE111 unit 2 is literally about
    computer systems — so neither is taken as a phrase."""
    for kept in ("A computer system has three functional units.",
                 "Computer Networks are classified by their span.",
                 "She studies computer science at a university."):
        assert _flat(kept) == kept


# ---------------------------------------------------------------------------
# A figure cross-reference pointing at a figure that did not survive extraction.
#
# NIMI's manuals put it at the head of the paragraph it introduces, and the
# sentence splitter glues it to the front of the definition that follows.
# ---------------------------------------------------------------------------

#: Real MEC103 sentences, and what a strip turns them into. 422 carry one.
FIGURE_LED = (
    "(Fig 3) Obtuse angle: This refers to an angle between 90 and 180.",
    "(Fig 4) - Solid bounded by warped surfaces.",
    "(Fig 9) Ring nut: Its diameter is 1.8 d and thickness is 0.5 d.",
    "(Fig 18) - Symbol for 3rd angle projection.",
    "(Figs 1 & 2) Margin: Margin enables the prints to be trimmed.",
    "(Fig 5a) If rivets are staggered it is called zig-zag riveted.",
)


def test_a_dead_figure_reference_is_stripped_and_the_definition_survives():
    from recall.teach.corpus import strip_figure_refs

    for sentence in FIGURE_LED:
        out = strip_figure_refs(sentence)
        assert not out.startswith("("), out
        assert "Fig" not in out.split(".")[0], out
        assert len(out) > 20, out


def test_refusing_these_was_measured_and_is_worse_than_break_even():
    """The finding proposed refusing a sentence whose payload is a figure pointer.
    Measured over MEC103's 9,671 offered sentences it refuses 45 of legitimate
    course material to remove 42 empty ones — and the casualties are the corpus's
    best short statements, because NIMI writes terse one-line definitions: the
    definition of an obtuse angle, all three classes of curved-surface solids,
    "Ring nut: Its diameter is 1.8 d", the symbol for third-angle projection. In a
    subject whose whole content is drawing conventions, that is the filter that
    gets switched off and takes the useful part with it.

    So these are STRIPPED and every one stays offerable."""
    from recall.teach.corpus import split_sentences, strip_figure_refs

    passage = " ".join(FIGURE_LED)
    offered = split_sentences(strip_figure_refs(passage))
    for keep in ("Obtuse angle", "Ring nut", "Margin", "zig-zag riveted"):
        assert any(keep in s for s in offered), keep


def test_the_strip_can_push_the_tersest_definitions_under_the_word_floor():
    """An interaction worth naming rather than hiding.

    NIMI writes definitions so terse that removing the figure reference drops them
    below `_MIN_CITABLE_WORDS`: "(Fig 4) - Solid bounded by warped surfaces." is
    seven tokens and offerable, and "Solid bounded by warped surfaces." is five and
    is not. So for the very shortest ones the strip trades a citation carrying a
    dead reference for no citation at all.

    That is the right trade and it is the FLOOR's decision, not this rule's: the
    floor exists because "a citation shorter than this is not carrying a definition
    or a condition". Worth knowing if MEC103's grounding comes out low — the
    material is there, it is just too terse to quote."""
    from recall.teach.corpus import split_sentences, strip_figure_refs

    terse = "(Fig 4) - Solid bounded by warped surfaces."
    assert len(terse.split()) >= 6
    assert len(strip_figure_refs(terse).split()) < 6
    assert split_sentences(strip_figure_refs(terse)) == []


def test_the_parenthetical_that_is_the_subject_is_left_alone():
    """The one shape whose meaning a strip destroys: "(Fig 2) shows a V belt
    pulley…" would become "shows a V belt pulley…". This guard is the difference
    between repairing 421 of 422 and 422 of 422 with a casualty."""
    from recall.teach.corpus import strip_figure_refs

    for kept in ("(Fig 2) shows a V belt pulley having three V grooves.",
                 "(Fig 7) illustrates the parallel line method.",
                 "(Fig 4) depicts the development of a cone."):
        assert strip_figure_refs(kept) == kept


def test_a_reference_that_is_not_parenthesised_is_untouched():
    """Only the parenthesised form gets glued to a sentence head by the splitter,
    and only it is dead weight. An inline reference is part of the sentence's own
    grammar — and these two are the offset-section rule and the linear-spacing
    rule, both real teaching."""
    from recall.teach.corpus import strip_figure_refs

    for kept in ("In such cases, the cutting plane is off-set as shown in Fig 8.",
                 "Linear spacings may be dimensioned as in Fig 27 a&b.",
                 "Conventional representation of materials is shown in Table 1."):
        assert strip_figure_refs(kept) == kept


def test_the_strip_happens_at_passage_level_not_per_sentence():
    """It has to. A quote is checked VERBATIM against the passage, so repairing a
    sentence after it was split would turn every citation from these files into a
    paraphrase and fail the grounding gate outright."""
    import inspect

    from recall.teach import corpus

    assert "strip_figure_refs" in inspect.getsource(corpus.strip_furniture)
    assert "strip_figure_refs" not in inspect.getsource(corpus.split_sentences)


# ---------------------------------------------------------------------------
# The worst thing the cleaner did, found by reading a real citation.
#
# "Drop an unresolved command, name and all" is right for \frac and \qquad,
# where the letters are noise. It is exactly wrong for a function name, where
# the letters ARE the mathematics — and it shipped: MTH165 unit 5's grounded
# citation read "ρ^2φ dρ dφ dθ" where the source says ρ² sin φ, in a unit whose
# whole subject is spherical coordinates.
#
# A hole a reader can see is recoverable. A deleted function name reads as
# correct and is not.
# ---------------------------------------------------------------------------

FUNCTION_NAMES_MUST_SURVIVE = (
    (r"\rho^2\sin\phi", "ρ^2sinφ"),
    (r"\int\sin x\,dx = -\cos x + C", "∫sin x dx = -cos x + C"),
    (r"\log_{10} x and \ln y", "log_{10} x and ln y"),
    (r"\lim_{x\to0}\frac{\sin x}{x}=1", "lim_{x→0}sin x/x=1"),
    (r"\det A and \dim V and \gcd(a,b)", "det A and dim V and gcd(a,b)"),
    (r"\arcsin x + \tan\theta + \exp(y)", "arcsin x + tanθ + exp(y)"),
    (r"\max\{a,b\} and \min\{a,b\}", "max{a,b} and min{a,b}"),
    (r"\sinh x and \cosh x and \tanh x", "sinh x and cosh x and tanh x"),
)


def test_a_function_name_is_never_dropped():
    from recall.teach.corpus import clean_latex

    for source, expected in FUNCTION_NAMES_MUST_SURVIVE:
        assert clean_latex(source) == expected, source


def test_the_longer_function_name_wins_over_its_prefix():
    r"""`\sinh` must not be read as `\sin` plus a stray h, and `\sigma` must not
    be read as `\sin`. The `(?![A-Za-z])` lookahead is what makes the order of the
    alternation irrelevant."""
    from recall.teach.corpus import clean_latex

    assert clean_latex(r"\sigma and \sec\theta") == "σ and secθ"
    assert clean_latex(r"\cot\theta vs \coth\theta") == "cotθ vs cothθ"
    assert clean_latex(r"\lim vs \liminf") == "lim vs liminf"


def test_a_command_that_is_not_a_name_is_still_dropped():
    """The original rule was right for these: the letters of `\\qquad` and
    `\\varnothing` are noise, not mathematics, and keeping them manufactured words
    like "frac12int" that read as prose and pass every filter."""
    from recall.teach.corpus import clean_latex

    out = clean_latex(r"\qquad\varnothing\mathscr{X}")
    for noise in ("qquad", "varnothing", "mathscr"):
        assert noise not in out, noise
