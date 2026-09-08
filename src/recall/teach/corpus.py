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
import re

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
    # A fill-in-the-blank bank is unquotable by construction: the load-bearing
    # word is the missing one. The first grounded run was offered "The rank of
    # a matrix is the maximum number of linearly independent __." and the model
    # quoted it with the gap filled in — caught by the quote gate, but the
    # passage should never have been on the table.
    if "__" in body or "….." in body or body.count("...") > 3:
        return False
    orphans = body.count(" ,") + body.count(" .") + body.count(" ?")
    return orphans / max(sentences, 1) <= _MAX_ORPHAN_RATIO


#: Extensions whose text survives extraction with its mathematics intact.
#: Measured on the MTH165 unit 1 load: 35% of HTML chunks carry a scraper
#: artefact — a bare "TEXT" marker where a formula was, or leaked LaTeX —
#: against 2% of PDF chunks. Seventeen times worse.
_DOCUMENT_SUFFIXES = (".pdf", ".pptx", ".docx", ".ppt", ".doc")

#: …so documents take most of the slots. The rest are RESERVED for scraped
#: pages rather than merely capped, which is the whole subtlety: this unit has
#: 161 document chunks against 26 scraped ones, so a cap would have handed
#: every slot to documents and amounted to a ban.
#:
#: A ban would have made the grounding worse. The one verified citation the
#: first grounded lesson earned — "Ax = b is consistent ⇔ rank(A) =
#: rank([A|b])" — came from a scraped notes page, because this corpus's PDFs
#: are textbooks and problem sets, which pose questions and work examples but
#: rarely state a definition in one crisp sentence. Documents have the better
#: text; the scrape has the better sentences.
_RESERVED_FOR_SCRAPED = 0.25

#: A scraper's placeholder for a formula it could not render. Dropping it makes
#: the sentence read as written and keeps a quote from having to step over it.
_FORMULA_PLACEHOLDER = re.compile(r"(?<![A-Za-z])TEXT(?![A-Za-z])")


def is_document(filename: str) -> bool:
    return str(filename).lower().endswith(_DOCUMENT_SUFFIXES)


#: A repeated prefix shorter than this is a coincidence, not boilerplate.
_MIN_BOILERPLATE = 180


def strip_boilerplate(texts: list[str]) -> list[str]:
    """Remove the header every page of one scraped source repeats.

    A page chunk spans several pages, so a site's navigation bar lands inside
    the same passage as its real content and no whole-passage filter separates
    them — two of the eight slots offered to the first grounded lesson were
    "You're offline Ctrl+K Home Exam Center Revision…".

    Boilerplate is exactly the text that repeats, so it is found rather than
    listed: the longest prefix common to every chunk of one source. A PDF's
    chunks share no such prefix and are left alone, and nothing has to know in
    advance which sites the corpus was collected from.
    """
    usable = [t for t in texts if t]
    if len(usable) < 3:
        return texts
    prefix = usable[0]
    for t in usable[1:]:
        limit = min(len(prefix), len(t))
        i = 0
        while i < limit and prefix[i] == t[i]:
            i += 1
        prefix = prefix[:i]
        if len(prefix) < _MIN_BOILERPLATE:
            return texts
    return [t[len(prefix):].lstrip() if t.startswith(prefix) else t
            for t in texts]


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
    # Strip each source's repeated header BEFORE judging or ranking: a chunk
    # that is half navigation bar should be scored on the half that is not.
    by_source: dict[int, list] = {}
    for r in rows:
        by_source.setdefault(r["filename"], []).append(r)
    cleaned: list[tuple] = []
    for _fn, group in by_source.items():
        for r, text in zip(group, strip_boilerplate([g["text"] for g in group])):
            cleaned.append((r, text))

    cleaned = [(r, _FORMULA_PLACEHOLDER.sub("", t)) for r, t in cleaned]
    cleaned = [(r, t) for r, t in cleaned if passage_is_usable(t)]
    if not cleaned:
        return []
    rows = [r for r, _ in cleaned]
    clean_text = {id(r): t for r, t in cleaned}

    if embed is None:
        from recall.verify.dedupe import embed_texts as embed

    texts = [clean_text[id(r)] for r in rows]
    vectors = embed([query] + texts)
    q, rest = vectors[0], vectors[1:]

    def cosine(v):
        denom = float((q @ q) ** 0.5 * (v @ v) ** 0.5)
        return 0.0 if denom == 0.0 else float(q @ v / denom)

    ranked = [r for r, _ in sorted(zip(rows, rest), key=lambda p: -cosine(p[1]))]

    # Relevance decides the order; provenance decides how many scraped pages
    # get in. Filling by relevance alone let a site's pages take most of the
    # slots, and a third of them had lost the mathematics they were about.
    reserved = max(1, round(limit * _RESERVED_FOR_SCRAPED))
    docs = [r for r in ranked if is_document(r["filename"])]
    scraped = [r for r in ranked if not is_document(r["filename"])]
    picked = docs[: limit - reserved] + scraped[:reserved]
    # Whichever pool is short, the other fills the gap: a unit held entirely in
    # PDFs still gets a full set, and so does one held entirely in scrapes.
    if len(picked) < limit:
        rest = [r for r in ranked if r not in picked]
        picked += rest[: limit - len(picked)]
    picked.sort(key=lambda r: ranked.index(r))

    return [{"chunk_id": r["id"], "text": clean_text[id(r)],
             "page_ref": r["page_ref"],
             "filename": pathlib.Path(r["filename"]).name}
            for r in picked[:limit]]


__all__ = ["is_document", "load_source", "passage_is_usable", "plan_load",
           "read_manifest", "strip_boilerplate", "unit_passages"]
