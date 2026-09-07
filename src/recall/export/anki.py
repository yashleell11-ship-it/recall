"""Anki .apkg export.

Insurance: whatever else happens to Recall, the user's active cards and the
habit built on them survive inside Anki. The export is a faithful mirror of
what is in the database — text is passed through untouched, and every note
carries its provenance (topic code + page ref) so a card found in Anki in two
years can still be traced back to the page it came from.

The model ids below are load-bearing. Anki keys note types by id, so changing
one orphans every note the user has already imported (they would lose their
scheduling on re-import). They are hardcoded, never generated, and must not
change.
"""

import hashlib
import os
import sqlite3

import genanki

# Never change these. See module docstring.
QA_MODEL_ID = 1_704_913_027
CLOZE_MODEL_ID = 1_704_913_028

DECK_ROOT = "Recall"

_CSS = """\
.card {
  font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  font-size: 20px;
  line-height: 1.5;
  text-align: left;
  color: #111;
  background: #fff;
}
.source {
  margin-top: 1.5em;
  font-size: 12px;
  color: #777;
}
hr#answer { border: none; border-top: 1px solid #ddd; margin: 1.2em 0; }
"""

QA_MODEL = genanki.Model(
    QA_MODEL_ID,
    "Recall Q/A",
    fields=[
        {"name": "Question"},
        {"name": "Answer"},
        {"name": "Source"},
    ],
    templates=[
        {
            "name": "Recall Q/A",
            "qfmt": "{{Question}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Answer}}'
                    '<div class="source">{{Source}}</div>',
        }
    ],
    css=_CSS,
)

CLOZE_MODEL = genanki.Model(
    CLOZE_MODEL_ID,
    "Recall Cloze",
    fields=[
        {"name": "Text"},
        {"name": "Source"},
    ],
    templates=[
        {
            "name": "Recall Cloze",
            "qfmt": "{{cloze:Text}}",
            "afmt": '{{cloze:Text}}<div class="source">{{Source}}</div>',
        }
    ],
    css=_CSS,
    model_type=genanki.Model.CLOZE,
)

_SELECT = """
SELECT
  c.id           AS id,
  c.kind         AS kind,
  c.question     AS question,
  c.answer       AS answer,
  c.cloze_text   AS cloze_text,
  t.code         AS topic_code,
  ch.page_ref    AS page_ref,
  ch.source_id   AS source_id,
  ch.ordinal     AS ordinal
FROM cards c
JOIN topics t ON t.id = c.topic_id
LEFT JOIN chunks ch ON ch.id = c.chunk_id
WHERE c.state = 'active' AND t.user_id = ?
"""

_ORDER = " ORDER BY t.code, ch.source_id, ch.ordinal, c.id"


def _deck_id(deck_name: str) -> int:
    """Stable deck id derived from the deck name.

    Same name in, same id out, so repeated exports land in the same deck
    instead of piling up duplicates in the user's sidebar.
    """
    digest = hashlib.sha256(deck_name.encode("utf-8")).digest()
    return (int.from_bytes(digest[:8], "big") % (1 << 30)) + (1 << 30)


def _deck_name(topic_code: str | None) -> str:
    return f"{DECK_ROOT}::{topic_code}" if topic_code else f"{DECK_ROOT}::All"


def _source_field(topic_code: str | None, page_ref: str | None) -> str:
    """Provenance, e.g. "CSE111 p4-p6". A product feature, not decoration."""
    return " ".join(p for p in (topic_code, page_ref) if p)


def _note_for(row: sqlite3.Row) -> genanki.Note:
    source = _source_field(row["topic_code"], row["page_ref"])
    # A stable guid keyed on the card id means a re-import updates the note
    # in place rather than creating a second copy of it.
    guid = genanki.guid_for("recall", row["id"])
    cloze_text = row["cloze_text"]
    if row["kind"] == "cloze" and cloze_text:
        # cloze_text already carries Anki's native {{c1::...}} markup.
        # Pass it through untouched.
        return genanki.Note(
            model=CLOZE_MODEL,
            fields=[cloze_text, source],
            guid=guid,
        )
    return genanki.Note(
        model=QA_MODEL,
        fields=[row["question"], row["answer"], source],
        guid=guid,
    )


def export_apkg(conn, out_path: str, user_id: int,
                topic_code: str | None = None) -> int:
    """Write one user's active cards to an Anki package at ``out_path``.

    Only cards with ``state = 'active'`` are exported — pending, rejected and
    suspended cards never leave the database.

    ``user_id`` is required rather than defaulted: this function writes a file
    to disk, and a forgotten default here would quietly package every account's
    cards into it.

    :param conn: sqlite3.Connection with ``row_factory = sqlite3.Row``.
    :param out_path: destination ``.apkg`` path.
    :param user_id: whose deck to export.
    :param topic_code: export a single topic, or every topic when ``None``.
    :returns: the number of notes written (0 is a valid, importable package).
    """
    if topic_code is None:
        rows = conn.execute(_SELECT + _ORDER, (user_id,)).fetchall()
    else:
        rows = conn.execute(
            _SELECT + " AND t.code = ?" + _ORDER, (user_id, topic_code)
        ).fetchall()

    deck_name = _deck_name(topic_code)
    deck = genanki.Deck(_deck_id(deck_name), deck_name)
    for row in rows:
        deck.add_note(_note_for(row))

    # An empty export is still a real package: both note types travel with it
    # so the deck imports cleanly and later exports merge into it.
    deck.add_model(QA_MODEL)
    deck.add_model(CLOZE_MODEL)

    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    genanki.Package(deck).write_to_file(out_path)

    return len(deck.notes)
