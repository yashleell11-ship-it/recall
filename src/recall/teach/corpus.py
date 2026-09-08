"""Course material a lesson can be checked against.

The re-derivation check failed: it asked a weaker solver to re-do the lesson's
work, and on the first six lessons it was wrong every time it spoke. A model
checking a model has no floor. This is the alternative with one — a passage the
lesson must quote verbatim, verified in Python, which no amount of fluency gets
around.

`~/recall-corpus` holds 654 freely-licensed files, each mapped in
`manifest.jsonl` to a subject and to the unit numbers it serves. Loading is
free: the text is chunked and stored, and no model is called. Card generation
is what costs money on the upload path, and it is deliberately not done here —
the point is passages to quote, not more cards.

**Unit numbers become unit names at load time.** The manifest was written
against the syllabus as it stood; a number is a position, and this codebase has
already paid for treating a position as an identity.
"""

import json
import pathlib

from recall.generate.knowledge import knowledge_sha
from recall.ingest.chunk import chunk_pages
from recall.ingest.pdf import DOCUMENT_SUFFIXES, file_sha256, read_document
from recall.lpu import unit_key
from recall.pipeline import _now


def read_manifest(path: str) -> list[dict]:
    """Every usable manifest line. Unreadable lines are skipped, not fatal."""
    out = []
    for line in pathlib.Path(path).expanduser().read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def plan_load(manifest_path: str, *, subject: str | None = None,
              unit_numbers: list[int] | None = None) -> list[tuple[pathlib.Path, dict]]:
    """The files that would be loaded, filtered by subject and unit."""
    root = pathlib.Path(manifest_path).expanduser().parent
    want_units = set(unit_numbers or [])
    out = []
    for entry in read_manifest(manifest_path):
        if subject and str(entry.get("subject", "")).upper() != subject.upper():
            continue
        units = {int(u) for u in (entry.get("units") or []) if str(u).isdigit()}
        if want_units and not (units & want_units):
            continue
        path = (root / str(entry.get("path", ""))).resolve()
        if not path.is_file() or path.suffix.lower() not in DOCUMENT_SUFFIXES:
            continue
        out.append((path, entry))
    return out


def load_source(conn, *, user_id: int, topic_id: int, path: pathlib.Path,
                entry: dict, syllabus: list[str]) -> tuple[int, int]:
    """Chunk one corpus file into the database. Returns (source_id, n_chunks).

    Free — no model is called. Keyed on the file's sha256 exactly like
    `pipeline.ingest_source`, so re-running is a no-op and an interrupted load
    continues where it stopped.
    """
    sha = file_sha256(str(path))
    existing = conn.execute(
        "SELECT id FROM sources WHERE user_id = ? AND sha256 = ?",
        (user_id, sha)).fetchone()
    if existing:
        source_id = int(existing["id"])
        added = 0
    else:
        cur = conn.execute(
            "INSERT INTO sources (user_id, topic_id, filename, kind, sha256,"
            " added_at) VALUES (?,?,?,?,?,?)",
            (user_id, topic_id, str(path), "corpus", sha, _now()))
        source_id = int(cur.lastrowid)
        chunks = chunk_pages(read_document(str(path)))
        for ch in chunks:
            conn.execute(
                "INSERT INTO chunks (source_id, ordinal, text, page_ref)"
                " VALUES (?,?,?,?)",
                (source_id, ch.ordinal, ch.text, ch.page_ref))
        added = len(chunks)

    # The manifest's unit NUMBERS, resolved against the syllabus as it stands
    # now and stored as names.
    for u in (entry.get("units") or []):
        try:
            n = int(u)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= len(syllabus):
            name = syllabus[n - 1]
            conn.execute(
                "INSERT OR IGNORE INTO source_units (source_id, unit_name,"
                " unit_key) VALUES (?,?,?)", (source_id, name, unit_key(name)))
    conn.commit()
    return source_id, added


#: A passage shorter than this cannot carry a definition worth quoting.
_MIN_CHARS = 250

#: Prose has sentences. A navigation bar does not — "Home Exam Center Revision
#: More Offline Library About Contact" is fifty characters of nouns with no
#: full stop in sight. Measured per thousand characters.
_MIN_SENTENCES_PER_KCHAR = 2.0

#: " ," and " ." — a space before punctuation is where an inline symbol used to
#: be. A scraped page whose MathML did not survive reads "For what value of
#: does the matrix have rank ?", which is fluent, quotable, and teaches
#: nothing. Above this share of the passage's sentences, it is a shell.
_MAX_ORPHAN_RATIO = 0.25


def passage_is_usable(text: str) -> bool:
    """Is this worth putting in front of a lesson writer to quote?

    Retrieval by similarity alone put a site's navigation bar at the top of the
    ranking for "rank of a matrix", because chrome mentions everything. And the
    scraped MCQ bank ranked second having lost every symbol it was about. A
    lesson grounded in either is worse than an ungrounded one: it carries a
    citation, which is a claim, backed by nothing.
    """
    body = " ".join((text or "").split())
    if len(body) < _MIN_CHARS:
        return False
    sentences = body.count(". ") + body.count("? ") + body.count("! ")
    if sentences == 0:
        return False
    if sentences / (len(body) / 1000.0) < _MIN_SENTENCES_PER_KCHAR:
        return False
    orphans = body.count(" ,") + body.count(" .") + body.count(" ?")
    return orphans / max(sentences, 1) <= _MAX_ORPHAN_RATIO


def unit_passages(conn, *, user_id: int, topic_id: int, unit_name: str,
                  query: str, limit: int = 8, embed=None) -> list[dict]:
    """The corpus passages most worth showing a lesson writer for this unit.

    Ranked by cosine against `query` using the CPU-only ONNX embeddings the
    dedupe path already uses — no GPU, no network, no cost.

    `s.user_id` is load-bearing: chunks carry no owner, and the synthetic
    knowledge source is excluded because its "text" is a unit name, not a
    passage anything could be checked against.
    """
    rows = conn.execute(
        "SELECT ch.id, ch.text, ch.page_ref, s.filename"
        " FROM chunks ch"
        " JOIN sources s ON s.id = ch.source_id"
        " JOIN source_units su ON su.source_id = s.id"
        " WHERE s.user_id = ? AND s.topic_id = ? AND su.unit_key = ?"
        "   AND s.sha256 <> ?"
        " ORDER BY ch.id",
        (user_id, topic_id, unit_key(unit_name), knowledge_sha(topic_id))
    ).fetchall()
    rows = [r for r in rows if passage_is_usable(r["text"])]
    if not rows:
        return []

    if embed is None:
        from recall.verify.dedupe import embed_texts as embed

    texts = [r["text"] for r in rows]
    vectors = embed([query] + texts)
    q, rest = vectors[0], vectors[1:]

    def cosine(v):
        denom = float((q @ q) ** 0.5 * (v @ v) ** 0.5)
        return 0.0 if denom == 0.0 else float(q @ v / denom)

    ranked = sorted(zip(rows, rest), key=lambda p: -cosine(p[1]))
    return [{"chunk_id": r["id"], "text": r["text"], "page_ref": r["page_ref"],
             "filename": pathlib.Path(r["filename"]).name}
            for r, _ in ranked[:limit]]


__all__ = ["load_source", "passage_is_usable", "plan_load",
           "read_manifest", "unit_passages"]
