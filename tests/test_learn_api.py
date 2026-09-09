"""Reading a stored lesson over HTTP.

A lesson pipeline that nobody can read is the `card_explanations` failure told
backwards: the feature works, costs money, and has no door. These pin the door
open, and pin the two ways it could be worse than no door at all — by handing
one account another's lesson, and by turning a page load into a paid call.
"""

import inspect
import json

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from recall.api import learn_routes, teach_routes
from recall.api.app import create_app, get_conn
from recall.api.deps import get_current_user
from recall.db import connect, init_db
from recall.generate.knowledge import knowledge_sha

UNITS = ["Matrices and determinants", "Differential calculus",
         "Integral calculus", "Vector spaces"]

META = json.dumps({"full_name": "Mathematics for Engineers", "units": UNITS,
                   "exam_format": "mixed"})


def body(*, sections: int = 5, quoted: int = 5) -> dict:
    """A lesson body of the shape `check_structure` enforces."""
    return {
        "why": "This unit is what every later unit computes with. It is examined "
               "as one long question in the MTE.",
        "sections": [
            {"heading": f"Section {i}",
             "body": f"Teaching prose for section {i}.",
             **({"quote": f"a verbatim span from the course material {i}",
                 "source": f"[{i}] ncert-matrices.pdf p{10 + i}"}
                if i <= quoted else {})}
            for i in range(1, sections + 1)],
        "worked": [
            {"question": "Find the rank of A.",
             "steps": ["Row reduce.", "Count the non-zero rows."], "answer": "2"},
            {"question": "Explain why rank is invariant.",
             "steps": ["State the definition.", "Apply it."],
             "answer": "Because row operations are invertible"}],
        "check": [
            {"question": "What is the rank of the identity?", "answer": "n",
             "why": "tests the definition rather than the procedure"},
            {"question": "Can rank exceed the number of rows?", "answer": "No",
             "why": "tests the bound"}],
    }


NOTES = ("grounded: 100% of sections carry a quote found verbatim in 8 passages"
         " of course material\n"
         "worked example 2: answer is prose, so re-solving it cannot confirm or"
         " contradict it — read this one yourself")


@pytest.fixture
def db_path(tmp_path):
    """Two accounts that both own a topic called MTH165; only user 1 has lessons.

    User 2's own MTH165 matters: with a topic of their own the topic lookup
    SUCCEEDS for them, so the only thing left standing between user 2 and user
    1's lesson is the `sources.user_id` join — which is precisely the join a
    leak of this exact shape has already skipped once in this project.
    """
    path = str(tmp_path / "learn.db")
    conn = connect(path)
    init_db(conn)
    for uid, name in ((1, "yash"), (2, "someone else"), (3, "a third")):
        conn.execute("INSERT INTO users (id, name) VALUES (?,?)", (uid, name))
        conn.execute("INSERT INTO settings (user_id) VALUES (?)", (uid,))
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label,meta) VALUES (1,1,'MTH165',?,?)",
        ("Mathematics for Engineers", META))
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label,meta) VALUES (2,2,'MTH165',?,?)",
        ("Mathematics for Engineers", META))
    # User 3 is a real account that has never touched MTH165.
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label,meta) VALUES (3,3,'INT335',?,?)",
        ("Cloud Computing",
         json.dumps({"full_name": "Cloud Computing", "units": ["Virtualisation"]})))
    # A topic carrying no LPU metadata at all — older databases have these.
    conn.execute(
        "INSERT INTO topics (id,user_id,code,label) VALUES (4,1,'BARE','Bare')")
    # The synthetic per-topic knowledge source, exactly as _knowledge_cards
    # builds it: one chunk per unit whose text IS the unit's name.
    conn.execute(
        "INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,added_at)"
        " VALUES (9,1,1,'AI knowledge','knowledge',?,'2026-01-01')",
        (knowledge_sha(1),))
    for i, unit in enumerate(UNITS):
        conn.execute(
            "INSERT INTO chunks (id,source_id,ordinal,text,page_ref)"
            " VALUES (?,9,?,?,?)", (100 + i, i, unit, f"Unit {i + 1} · {unit}"))
    conn.commit()
    conn.close()
    return path


def add_lesson(path, *, lesson_id: int, chunk_id: int = 100, topic_id: int = 1,
               status: str = "grounded", notes: str | None = NOTES,
               created_at: str = "2026-08-30T11:04:22+00:00", **kw) -> None:
    conn = connect(path)
    conn.execute(
        "INSERT INTO lessons (id,chunk_id,topic_id,body_json,status,notes,model,"
        "cost_usd,created_at) VALUES (?,?,?,?,?,?,'deepseek-chat',0.03,?)",
        (lesson_id, chunk_id, topic_id, json.dumps(body(**kw)), status, notes,
         created_at))
    conn.commit()
    conn.close()


def make_client(db_path, user_id: int = 1) -> TestClient:
    app = create_app()

    def override():
        c = connect(db_path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = override
    app.dependency_overrides[get_current_user] = lambda: user_id
    return TestClient(app)


def dump(path: str) -> str:
    conn = connect(path)
    try:
        return "\n".join(conn.iterdump())
    finally:
        conn.close()


# --- ownership: the law a leak of exactly this shape already broke once ------

def test_another_account_cannot_read_a_lesson(db_path):
    """`chunks` carries no user_id, so a lesson's owner is reachable only
    through `sources.user_id`. User 2 owns a MTH165 topic of their own, so the
    topic lookup succeeds and that join is the only thing left — drop it and
    this returns user 1's lesson to user 2."""
    add_lesson(db_path, lesson_id=12)
    r = make_client(db_path, user_id=2).get("/api/teach/lessons/MTH165/1")
    assert r.status_code == 200
    assert r.json()["lesson"] is None
    assert "verbatim span from the course material" not in r.text


def test_a_second_account_gets_404_for_a_lesson_that_exists(db_path):
    """An account with no MTH165 of its own is told the topic does not exist —
    the same 404 a genuinely unknown code gets, and NOT a 500 from a null topic
    row. Answering those two cases differently would make this route an oracle
    for what other people study."""
    add_lesson(db_path, lesson_id=12)
    r = make_client(db_path, user_id=3).get("/api/teach/lessons/MTH165/1")
    assert r.status_code == 404
    assert "MTH165" in r.json()["detail"]


def test_another_account_sees_no_lessons_in_the_index(db_path):
    """The index joins out to sources too. Without it, user 2's list of
    subjects would quietly report user 1's written units as their own."""
    add_lesson(db_path, lesson_id=12)
    entry = make_client(db_path, user_id=2).get("/api/teach/lessons").json()[0]
    assert entry["topic_code"] == "MTH165"
    assert entry["written"] == 0
    assert [u["lesson"] for u in entry["units"]] == [None] * len(UNITS)


# --- which lesson is "the" lesson -------------------------------------------

def test_the_index_returns_the_newest_lesson_for_a_unit(db_path):
    """A unit rewritten after a bad first attempt has two rows. The index and
    the reader must name the same one, or the list says `grounded` and the page
    it links to shows the older `unverified` text."""
    add_lesson(db_path, lesson_id=12, status="unverified")
    add_lesson(db_path, lesson_id=31, status="grounded")
    client = make_client(db_path)
    unit = client.get("/api/teach/lessons").json()[0]["units"][0]
    assert unit["lesson"]["id"] == 31
    assert unit["lesson"]["status"] == "grounded"
    assert client.get("/api/teach/lessons/MTH165/1").json()["lesson"]["id"] == 31


def test_a_lesson_written_for_a_unit_no_longer_in_the_syllabus_is_not_listed(db_path):
    """Stored lessons are matched to units by NAME, never by position. Match by
    position and editing a syllabus files every older lesson under whichever
    unit now sits at its index — the `_unit_chunk_id` ordinal bug, arriving
    from the index side."""
    add_lesson(db_path, lesson_id=12)          # written for "Matrices and determinants"
    conn = connect(db_path)
    conn.execute("UPDATE topics SET meta = ? WHERE id = 1",
                 (json.dumps({"full_name": "Mathematics for Engineers",
                              "units": ["Differential calculus",
                                        "Integral calculus"]}),))
    conn.commit()
    conn.close()
    entry = make_client(db_path).get("/api/teach/lessons").json()[0]
    assert entry["written"] == 0
    assert [u["name"] for u in entry["units"]] == ["Differential calculus",
                                                   "Integral calculus"]
    assert [u["lesson"] for u in entry["units"]] == [None, None]


def test_the_index_lists_every_unit_including_the_unwritten_ones(db_path):
    """"MTH165 unit 4 has nothing" is information a student wants; an index
    that only lists what exists cannot say it."""
    add_lesson(db_path, lesson_id=12)
    entries = make_client(db_path).get("/api/teach/lessons").json()
    codes = [e["topic_code"] for e in entries]
    assert codes == ["MTH165"]          # BARE has no syllabus units, so it is out
    entry = entries[0]
    assert entry["full_name"] == "Mathematics for Engineers"
    assert entry["written"] == 1
    assert [u["number"] for u in entry["units"]] == [1, 2, 3, 4]
    assert entry["units"][0]["lesson"]["status"] == "grounded"
    assert entry["units"][0]["lesson"]["created_at"] == "2026-08-30T11:04:22+00:00"
    assert [u["lesson"] for u in entry["units"][1:]] == [None, None, None]


# --- reading one unit --------------------------------------------------------

def test_reading_a_unit_with_no_lesson_returns_the_unit_name_and_a_null_lesson(db_path):
    """Nothing written is a state, not an error: the client needs the unit's
    real name in hand to print `recall lessons MTH165 --unit 3`, and a 404 body
    cannot carry it."""
    r = make_client(db_path).get("/api/teach/lessons/MTH165/3")
    assert r.status_code == 200
    assert r.json() == {"topic_code": "MTH165",
                        "full_name": "Mathematics for Engineers",
                        "unit_number": 3, "unit_name": "Integral calculus",
                        "lesson": None}


def test_an_unknown_topic_is_404_and_an_out_of_range_unit_is_422(db_path):
    """The house translation, and neither of them a 500: unit 9 of a four-unit
    syllabus used to index past the end of the list."""
    client = make_client(db_path)
    assert client.get("/api/teach/lessons/NOPE/1").status_code == 404
    r = client.get("/api/teach/lessons/MTH165/9")
    assert r.status_code == 422
    assert "there is no unit 9" in r.json()["detail"]
    assert client.get("/api/teach/lessons/MTH165/0").status_code == 422
    # A path int FastAPI itself refuses, rather than an IndexError inside.
    assert client.get("/api/teach/lessons/MTH165/abc").status_code == 422


def test_a_topic_with_no_syllabus_units_is_refused_clearly(db_path):
    """Databases made before the subject registry existed carry topics with no
    meta at all. `topic_units` returns [] for them, and indexing [] is a 500
    unless it is caught here."""
    r = make_client(db_path).get("/api/teach/lessons/BARE/1")
    assert r.status_code == 422
    assert "no syllabus units" in r.json()["detail"]


def test_the_status_and_notes_reach_the_client(db_path):
    """The screen's whole honesty story is built from these. `notes` arrives as
    a list of sentences so the client never string-splits prose, and the
    per-example caveat survives intact for the chip that shows it."""
    add_lesson(db_path, lesson_id=12, status="unverified")
    lesson = make_client(db_path).get("/api/teach/lessons/MTH165/1").json()["lesson"]
    assert lesson["id"] == 12
    assert lesson["status"] == "unverified"
    assert lesson["notes"] == NOTES.splitlines()
    assert lesson["notes"][1].startswith("worked example 2:")
    assert lesson["body"]["why"].startswith("This unit is what every later unit")
    assert lesson["body"]["sections"][0]["source"] == "[1] ncert-matrices.pdf p11"


def test_notes_are_an_empty_list_when_the_lesson_recorded_none(db_path):
    """`lessons.notes` is nullable. `None.splitlines()` is a 500."""
    add_lesson(db_path, lesson_id=12, notes=None)
    lesson = make_client(db_path).get("/api/teach/lessons/MTH165/1").json()["lesson"]
    assert lesson["notes"] == []


def test_cited_sections_counts_only_sections_carrying_a_quote(db_path):
    """The coverage meter is drawn from these two numbers, so counting a
    section with no quote as cited would draw a solid ink bar over a lesson
    that is mostly the model talking."""
    add_lesson(db_path, lesson_id=12, sections=4, quoted=1)
    lesson = make_client(db_path).get("/api/teach/lessons/MTH165/1").json()["lesson"]
    assert lesson["cited_sections"] == 1
    assert lesson["section_count"] == 4


# --- L2: reading costs nothing ----------------------------------------------

def _dependencies(fn) -> set:
    return {p.default.dependency for p in inspect.signature(fn).parameters.values()
            if isinstance(p.default, type(Depends()))}


def test_reading_a_lesson_makes_no_llm_call(db_path):
    """`prefetchFor` fires on route intent, so a paid dependency on either of
    these GETs bills the owner for a hover. Two fences: neither route declares
    an llm dependency at all, and a get_llm that explodes on construction
    cannot break them."""
    add_lesson(db_path, lesson_id=12)
    for route in (learn_routes.lessons_index, learn_routes.lessons_read):
        assert _dependencies(route) == {get_current_user, get_conn}
    assert not hasattr(learn_routes, "DeepSeekClient")

    client = make_client(db_path)

    def explode():
        raise AssertionError("a read path asked for a paid client")

    client.app.dependency_overrides[teach_routes.get_llm] = explode
    assert client.get("/api/teach/lessons").status_code == 200
    assert client.get("/api/teach/lessons/MTH165/1").status_code == 200


def test_reading_a_lesson_writes_nothing(db_path):
    """No cache row, no view counter, no commit. `card_explanations` writes on
    read because it must; this has nothing to write, and a read path that
    writes is a read path that can fail on a full disk."""
    add_lesson(db_path, lesson_id=12)
    before = dump(db_path)
    client = make_client(db_path)
    client.get("/api/teach/lessons")
    client.get("/api/teach/lessons/MTH165/1")
    client.get("/api/teach/lessons/MTH165/4")
    assert dump(db_path) == before


def test_a_lesson_whose_chunk_is_not_yours_is_invisible_even_under_your_own_topic(db_path):
    """The load-bearing join, isolated so nothing else can cover for it.

    `lessons.topic_id` and the source behind `lessons.chunk_id` are two
    separate routes to an owner, and only the second one follows the TEXT —
    `chunks` carries no user_id, so `sources.user_id` is the only column that
    can refuse a chunk. This row is built so every other filter waves it
    through: it hangs off user 2's own topic, under a source whose sha256 is
    the one user 2's topic would use, with a chunk named after a unit user 2's
    syllabus really has. Take `sources.user_id` out of either query and user 2
    reads user 1's lesson.

    Schema-legal (UNIQUE is on (user_id, sha256), not sha256), and the shape a
    mis-scoped write or a restored backup leaves behind.
    """
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,added_at)"
        " VALUES (19,1,1,'AI knowledge','knowledge',?,'2026-01-01')",
        (knowledge_sha(2),))
    conn.execute(
        "INSERT INTO chunks (id,source_id,ordinal,text,page_ref)"
        " VALUES (200,19,0,?,'Unit 1')", (UNITS[0],))
    conn.commit()
    conn.close()
    add_lesson(db_path, lesson_id=12, topic_id=2, chunk_id=200)

    client = make_client(db_path, user_id=2)
    entry = client.get("/api/teach/lessons").json()[0]
    assert entry["written"] == 0
    assert entry["units"][0]["lesson"] is None
    r = client.get("/api/teach/lessons/MTH165/1")
    assert r.status_code == 200
    assert r.json()["lesson"] is None
    assert "verbatim span from the course material" not in r.text

    # Now hand that one source to user 2 and change nothing else. It becomes
    # visible — which is what makes the assertions above a statement about
    # ownership rather than about a row nothing could have found anyway.
    conn = connect(db_path)
    conn.execute("UPDATE sources SET user_id = 2 WHERE id = 19")
    conn.commit()
    conn.close()
    assert client.get("/api/teach/lessons").json()[0]["written"] == 1
    assert client.get("/api/teach/lessons/MTH165/1").json()["lesson"]["id"] == 12
