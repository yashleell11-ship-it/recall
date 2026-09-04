import sqlite3
import zipfile

import pytest

from recall.db import connect, init_db
from recall.export.anki import export_apkg

FIELD_SEP = "\x1f"

CLOZE_TEXT = "The {{c1::hypothalamus}} regulates {{c2::body temperature}}."


def seed(tmp_path) -> sqlite3.Connection:
    """A DB with two topics and cards spread across every state."""
    conn = connect(str(tmp_path / "recall.db"))
    init_db(conn)

    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.execute(
        "INSERT INTO topics (id, user_id, code, label) VALUES (1, 1, 'CSE111', 'Systems')"
    )
    conn.execute(
        "INSERT INTO topics (id, user_id, code, label) VALUES (2, 1, 'BIO204', 'Physiology')"
    )
    conn.execute(
        "INSERT INTO sources (id, user_id, topic_id, filename, kind, sha256, added_at)"
        " VALUES (1, 1, 1, 'systems.pdf', 'pdf', 'abc', '2026-09-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO sources (id, user_id, topic_id, filename, kind, sha256, added_at)"
        " VALUES (2, 1, 2, 'physio.pdf', 'pdf', 'def', '2026-09-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO chunks (id, source_id, ordinal, text, page_ref)"
        " VALUES (1, 1, 0, 'paging text', 'p4-p6')"
    )
    conn.execute(
        "INSERT INTO chunks (id, source_id, ordinal, text, page_ref)"
        " VALUES (2, 2, 0, 'thermoregulation text', 'p12')"
    )

    cards = [
        # id, chunk, topic, kind, question, answer, cloze_text, state
        (1, 1, 1, "qa", "What is a TLB?", "A cache of page translations.", None, "active"),
        (2, 1, 1, "qa", "What is a page fault?", "A trap on an absent page.", None, "active"),
        (3, 1, 1, "cloze", "cloze", "cloze", CLOZE_TEXT, "active"),
        (4, 1, 1, "qa", "Pending question?", "Pending answer.", None, "pending"),
        (5, 1, 1, "qa", "Rejected question?", "Rejected answer.", None, "rejected"),
        (6, 1, 1, "qa", "Suspended question?", "Suspended answer.", None, "suspended"),
        (7, 2, 2, "qa", "What is homeostasis?", "Stable internal conditions.", None, "active"),
        (8, 2, 2, "qa", "Pending bio question?", "Pending bio answer.", None, "pending"),
    ]
    conn.executemany(
        "INSERT INTO cards"
        " (id, chunk_id, topic_id, kind, question, answer, cloze_text, arm, state, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'learned', ?, '2026-09-01T00:00:00Z')",
        cards,
    )
    conn.commit()
    return conn


def read_notes(apkg_path):
    """Open the generated .apkg (a zip around a SQLite collection) and read
    its notes back out. Proves what actually landed in the package."""
    with zipfile.ZipFile(apkg_path) as zf:
        assert "collection.anki2" in zf.namelist()
        raw = zf.read("collection.anki2")
    db_path = str(apkg_path) + ".collection"
    with open(db_path, "wb") as fh:
        fh.write(raw)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT guid, mid, flds FROM notes").fetchall()
    finally:
        conn.close()
    return [
        {"guid": guid, "mid": mid, "fields": flds.split(FIELD_SEP)}
        for guid, mid, flds in rows
    ]


def read_deck_names(apkg_path):
    import json

    with zipfile.ZipFile(apkg_path) as zf:
        raw = zf.read("collection.anki2")
    db_path = str(apkg_path) + ".decks"
    with open(db_path, "wb") as fh:
        fh.write(raw)
    conn = sqlite3.connect(db_path)
    try:
        (decks_json,) = conn.execute("SELECT decks FROM col").fetchone()
    finally:
        conn.close()
    return {d["name"] for d in json.loads(decks_json).values()}


@pytest.fixture
def conn(tmp_path):
    return seed(tmp_path)


def test_exports_only_active_cards(conn, tmp_path):
    out = tmp_path / "all.apkg"
    n = export_apkg(conn, str(out))

    active = conn.execute(
        "SELECT COUNT(*) FROM cards WHERE state = 'active'"
    ).fetchone()[0]
    assert active == 4
    assert n == active

    notes = read_notes(out)
    assert len(notes) == active
    blob = " ".join(" ".join(note["fields"]) for note in notes)
    for forbidden in ("Pending", "Rejected", "Suspended"):
        assert forbidden not in blob


def test_output_is_a_valid_zip(conn, tmp_path):
    out = tmp_path / "all.apkg"
    export_apkg(conn, str(out))
    assert out.exists()
    assert zipfile.is_zipfile(str(out))


def test_topic_filter_selects_only_that_topic(conn, tmp_path):
    out = tmp_path / "cse.apkg"
    n = export_apkg(conn, str(out), topic_code="CSE111")
    assert n == 3

    notes = read_notes(out)
    blob = " ".join(" ".join(note["fields"]) for note in notes)
    assert "TLB" in blob
    assert "homeostasis" not in blob

    out_bio = tmp_path / "bio.apkg"
    assert export_apkg(conn, str(out_bio), topic_code="BIO204") == 1


def test_unknown_topic_exports_nothing_but_still_writes(conn, tmp_path):
    out = tmp_path / "nope.apkg"
    assert export_apkg(conn, str(out), topic_code="NOSUCH") == 0
    assert zipfile.is_zipfile(str(out))
    assert read_notes(out) == []


def test_cloze_markup_survives_into_the_package(conn, tmp_path):
    out = tmp_path / "all.apkg"
    export_apkg(conn, str(out))

    notes = read_notes(out)
    cloze_notes = [n for n in notes if "{{c1::" in n["fields"][0]]
    assert len(cloze_notes) == 1
    # Byte-for-byte identical to what is in the database.
    assert cloze_notes[0]["fields"][0] == CLOZE_TEXT
    assert cloze_notes[0]["fields"][0] == conn.execute(
        "SELECT cloze_text FROM cards WHERE id = 3"
    ).fetchone()[0]


def test_cloze_note_generates_a_card_per_deletion(conn, tmp_path):
    """{{c1}} and {{c2}} must become two Anki cards, not one."""
    out = tmp_path / "all.apkg"
    export_apkg(conn, str(out))

    with zipfile.ZipFile(out) as zf:
        raw = zf.read("collection.anki2")
    db_path = str(out) + ".cards"
    with open(db_path, "wb") as fh:
        fh.write(raw)
    c = sqlite3.connect(db_path)
    try:
        note_id, = c.execute(
            "SELECT id FROM notes WHERE flds LIKE '%{{c1::%'"
        ).fetchone()
        ords = {r[0] for r in c.execute(
            "SELECT ord FROM cards WHERE nid = ?", (note_id,)
        )}
    finally:
        c.close()
    assert ords == {0, 1}


def test_source_field_carries_topic_code_and_page_ref(conn, tmp_path):
    out = tmp_path / "all.apkg"
    export_apkg(conn, str(out))

    notes = read_notes(out)
    qa = [n for n in notes if n["fields"][0] == "What is a TLB?"]
    assert len(qa) == 1
    source = qa[0]["fields"][2]
    assert "CSE111" in source
    assert "p4-p6" in source
    assert source == "CSE111 p4-p6"

    # The cloze model's Source is its second field.
    cloze = [n for n in notes if "{{c1::" in n["fields"][0]][0]
    assert cloze["fields"][1] == "CSE111 p4-p6"

    bio = [n for n in notes if n["fields"][0] == "What is homeostasis?"][0]
    assert bio["fields"][2] == "BIO204 p12"


def test_empty_database_still_produces_a_valid_package(tmp_path):
    conn = connect(str(tmp_path / "empty.db"))
    init_db(conn)
    out = tmp_path / "empty.apkg"

    assert export_apkg(conn, str(out)) == 0
    assert zipfile.is_zipfile(str(out))
    assert read_notes(out) == []


def test_no_active_cards_still_produces_a_valid_package(conn, tmp_path):
    conn.execute("UPDATE cards SET state = 'suspended'")
    conn.commit()
    out = tmp_path / "none.apkg"

    assert export_apkg(conn, str(out)) == 0
    assert zipfile.is_zipfile(str(out))
    assert read_notes(out) == []


def test_deck_is_nested_under_recall(conn, tmp_path):
    all_out = tmp_path / "all.apkg"
    export_apkg(conn, str(all_out))
    assert "Recall::All" in read_deck_names(all_out)

    topic_out = tmp_path / "cse.apkg"
    export_apkg(conn, str(topic_out), topic_code="CSE111")
    assert "Recall::CSE111" in read_deck_names(topic_out)


def test_note_identity_is_stable_across_exports(conn, tmp_path):
    """Re-importing must update the user's existing notes, not duplicate them:
    same card => same guid and same note type id, every time."""
    first = tmp_path / "first.apkg"
    second = tmp_path / "second.apkg"
    export_apkg(conn, str(first))
    export_apkg(conn, str(second))

    def identity(path):
        return sorted((n["guid"], n["mid"]) for n in read_notes(path))

    assert identity(first) == identity(second)
    assert len(set(identity(first))) == 4

    # And a Q/A note and a cloze note use different note types.
    notes = read_notes(first)
    mids = {n["mid"] for n in notes}
    assert len(mids) == 2
