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
    assert result.notes == []
    assert result.cost_usd > 0


def test_a_worked_example_that_does_not_survive_re_solving_is_flagged(db):
    """The one check with teeth. A plausible wrong derivation survives "does
    this look right"; it rarely survives being solved again from scratch."""
    llm = FakeLlmClient(_calls(good_body(), fresh=("7", "k ≠ 3")))
    result = write_lesson(db, llm, CFG, user_id=1, topic_id=1,
                          topic_code="MTH165", meta=META, unit_number=1)
    assert result.status == "suspect"
    assert result.notes and "7" in result.notes[0]
    assert result.lesson_id is not None, (
        "a suspect lesson is kept for a human to look at, not silently dropped")


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
