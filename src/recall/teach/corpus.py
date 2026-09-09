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

import numpy as np

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

#: Punctuation left hanging after a WORD is where an inline symbol used to be:
#: a scraped page whose MathML did not survive reads "For what value of does
#: the matrix have rank ?", which is fluent, quotable, and teaches nothing.
#:
#: It must be a word. Counting every " ," and " ." rejected the best paragraph
#: on the Mean Value Theorem page, because a plaintext extract spaces its
#: mathematics out — "f ( b ) ," and "f ( x ) ." tripped the rule thirteen
#: times in a passage whose symbols were all present and correct. The symbols
#: being THERE is the opposite of the failure this looks for.
_ORPHAN = re.compile(r"(?<=[A-Za-z]{2})\s+[,.?](?=\s|$)")

#: Above this share of the passage's sentences, it is a shell.
_MAX_ORPHAN_RATIO = 0.25


#: A function word with nothing after it but the next sentence. Real prose does
#: not end a clause on "such that" or "over and"; extracted mathematics does,
#: because the formula that belonged there did not survive the PDF.
#:
#: This is the failure the orphan-punctuation rule misses, and it is the worse
#: one: "If is continuous over and differentiable over and then there exists a
#: point such that" — from OpenStax Calculus, a PDF — reads as grammatical
#: English, quotes cleanly, and says nothing. Unit 2 ground at 25% because its
#: best-ranked sources were full of it.
_DANGLING = re.compile(
    r"\b(?:such that|equals|is|are|be|over|between|from|of|and|to|where|that)"
    r"\s+(?=[A-Z0-9])"
)

#: Per sentence. Some genuine prose does begin a sentence after "that" or
#: "and"; a passage doing it constantly has lost its symbols.
_MAX_DANGLING_PER_SENTENCE = 0.6


def looks_symbol_stripped(text: str) -> bool:
    """Did this passage lose the mathematics it was about?"""
    body = " ".join((text or "").split())
    sentences = body.count(". ") + body.count("? ") + body.count("! ") + 1
    return len(_DANGLING.findall(body)) / sentences > _MAX_DANGLING_PER_SENTENCE


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
    if looks_symbol_stripped(body):
        return False
    orphans = len(_ORPHAN.findall(body))
    return orphans / max(sentences, 1) <= _MAX_ORPHAN_RATIO


#: Extensions whose text survives extraction with its mathematics intact.
#: Measured on the MTH165 unit 1 load: 35% of HTML chunks carry a scraper
#: artefact — a bare "TEXT" marker where a formula was, or leaked LaTeX —
#: against 2% of PDF chunks. Seventeen times worse.
_DOCUMENT_SUFFIXES = (".pdf", ".pptx", ".docx", ".ppt", ".doc", ".txt")

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

#: LaTeX a scraper left in the text. A citation must stay verbatim, so it
#: cannot be tidied after the fact — the only place to fix this is BEFORE the
#: writer sees the passage, and then the quote is verbatim against the cleaned
#: text. Without this, "(\\operatorname{rank}(A)=k)" reached a student inside a
#: verified citation, having sailed past the notation law: that law is applied
#: to the lesson's prose, and a quote is not prose the model is free to write.
_LATEX_FIXES: tuple[tuple[str, str], ...] = (
    (r"\\operatorname\{([^}]*)\}", r"\1"),
    (r"\\(?:mathrm|mathbf|mathit|text|textbf)\{([^}]*)\}", r"\1"),
    (r"\\mid", "|"),
    (r"\\(?:ldots|cdots|dots)", "…"),
    (r"\\(?:leq|le)\b", "≤"),
    (r"\\(?:geq|ge)\b", "≥"),
    (r"\\(?:neq|ne)\b", "≠"),
    (r"\\times\b", "×"),
    (r"\\lambda\b", "λ"),
    (r"\\theta\b", "θ"),
    (r"\\alpha\b", "α"),
    (r"\\beta\b", "β"),
    (r"\\pi\b", "π"),
    (r"\\infty\b", "∞"),
    (r"\\sum\b", "∑"),
    (r"\\int\b", "∫"),
    (r"\\sqrt\b", "√"),
    (r"\\[()\[\]]", ""),
    (r"\$+", ""),
    # Anything still carrying a backslash: keep the word, drop the marker.
    (r"\\([A-Za-z]+)", r"\1"),
)


def _strip_displaystyle(text: str) -> str:
    """Remove Wikipedia's `{\\displaystyle …}` twins.

    A plaintext extract prints every formula twice: once in real characters and
    once as LaTeX, e.g.

        f ′ ( c ) = f ( b ) − f ( a ) b − a . {\\displaystyle f'(c)={\\frac {f(b)-f(a)}{b-a}}.}

    The first half is readable and uses the right symbols; the second is noise
    that doubles the passage's length. That length is what made the quality
    filter reject the best paragraph on the Mean Value Theorem page — sentences
    per thousand characters fell below the floor because half the characters
    were a duplicate nobody reads.

    Brace-matched rather than regexed: these nest, and a lazy `\\{[^}]*\\}` stops
    at the first inner brace and leaves the tail behind.
    """
    for marker in ("{\\displaystyle", "{\\textstyle"):
        while (start := text.find(marker)) != -1:
            depth, i = 0, start
            while i < len(text):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            text = text[:start] + text[i + 1:] if i < len(text) else text[:start]
    return text


def clean_latex(text: str) -> str:
    """Turn a scraper's leftover LaTeX into the symbols it stood for."""
    out = _strip_displaystyle(text or "")
    for pattern, repl in _LATEX_FIXES:
        out = re.sub(pattern, repl, out)
    return out


#: A scraper's placeholder for a formula it could not render. Dropping it makes
#: the sentence read as written and keeps a quote from having to step over it.
_FORMULA_PLACEHOLDER = re.compile(r"(?<![A-Za-z])TEXT(?![A-Za-z])")


def is_document(filename: str) -> bool:
    return str(filename).lower().endswith(_DOCUMENT_SUFFIXES)


#: How many passages one file may contribute. Similarity ranking alone gave
#: four of eight slots to Rolle's theorem — the same document, four times —
#: crowding out the Mean Value Theorem, L'Hopital and Taylor, which the lesson
#: also had to teach. A lesson covers a unit, so its sources must span one.
#:
#: This also dilutes junk without another filter: a chunk that is half
#: navigation bar can still take a slot, but it can no longer take four.
_MAX_PER_SOURCE = 2

#: A repeated prefix shorter than this is a coincidence, not boilerplate.
_MIN_BOILERPLATE = 180

#: …and one longer than this share of the shortest passage is not a header
#: either: the passages are just alike, and stripping would leave nothing.
_MAX_BOILERPLATE_SHARE = 0.5


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
    # Two chunks are enough. A 180-character prefix shared by two pages of the
    # same document, and short relative to them, is a header — and requiring
    # three left the navigation bar on every short scrape, which is exactly
    # where it kept showing up.
    if len(usable) < 2:
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
    # If the "boilerplate" is most of the shortest passage, it is not a header
    # — the passages are simply alike, and stripping would gut them. Seen in a
    # test with forty near-identical chunks, which is artificial, but a source
    # of repetitive generated pages would do the same thing for real.
    if len(prefix) > _MAX_BOILERPLATE_SHARE * min(len(t) for t in usable):
        return texts
    return [t[len(prefix):].lstrip() if t.startswith(prefix) else t
            for t in texts]


#: How many chunks to embed at once. Small enough that a 3.8 GB box holding a
#: running API server does not fall over, which it did at 883.
_EMBED_BATCH = 32


def ensure_vectors(conn, chunk_ids: list[int], embed=None, on_progress=None) -> int:
    """Compute and store any missing embeddings. Returns how many were added.

    Batched and committed as it goes, so an interrupted run keeps what it did
    and a large unit never has more than `_EMBED_BATCH` vectors in flight.

    `on_progress(done, total)` is called after each batch. Indexing a unit
    takes twenty minutes on the VPS's CPU, and a command that prints one line
    and then goes silent for twenty minutes is indistinguishable from one that
    has hung.
    """
    missing = [r["id"] for r in conn.execute(
        "SELECT ch.id FROM chunks ch"
        " LEFT JOIN chunk_vectors v ON v.chunk_id = ch.id"
        f" WHERE v.chunk_id IS NULL AND ch.id IN ({','.join('?' * len(chunk_ids))})",
        chunk_ids)] if chunk_ids else []
    if not missing:
        return 0
    if embed is None:
        from recall.verify.dedupe import embed_texts as embed

    done = 0
    for start in range(0, len(missing), _EMBED_BATCH):
        batch = missing[start:start + _EMBED_BATCH]
        texts = [r["text"] for r in conn.execute(
            f"SELECT id, text FROM chunks WHERE id IN ({','.join('?' * len(batch))})"
            " ORDER BY id", batch)]
        ids = [r["id"] for r in conn.execute(
            f"SELECT id FROM chunks WHERE id IN ({','.join('?' * len(batch))})"
            " ORDER BY id", batch)]
        vectors = np.asarray(embed(texts), dtype=np.float32)
        for cid, vec in zip(ids, vectors):
            conn.execute(
                "INSERT OR REPLACE INTO chunk_vectors (chunk_id, dim, vec)"
                " VALUES (?,?,?)", (cid, int(vec.shape[0]), vec.tobytes()))
        conn.commit()
        done += len(batch)
        if on_progress is not None:
            on_progress(done, len(missing))
    return done


def unit_passages(conn, *, user_id: int, topic_id: int, unit_name: str,
                  query: str | list[str], limit: int = 8,
                  embed=None) -> list[dict]:
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

    cleaned = [(r, clean_latex(_FORMULA_PLACEHOLDER.sub("", t)))
               for r, t in cleaned]
    cleaned = [(r, t) for r, t in cleaned if passage_is_usable(t)]
    if not cleaned:
        return []
    rows = [r for r, _ in cleaned]
    clean_text = {id(r): t for r, t in cleaned}

    if embed is None:
        from recall.verify.dedupe import embed_texts as embed

    # Stored vectors, computed once at load. Only the QUERY is embedded here —
    # embedding every candidate per call is what killed the box on unit 2.
    ensure_vectors(conn, [r["id"] for r in rows], embed=embed)
    stored = {r["chunk_id"]: np.frombuffer(r["vec"], dtype=np.float32)
              for r in conn.execute(
                  "SELECT chunk_id, vec FROM chunk_vectors WHERE chunk_id IN"
                  f" ({','.join('?' * len(rows))})", [r["id"] for r in rows])}
    rows = [r for r in rows if r["id"] in stored]
    if not rows:
        return []
    # Several queries, scored by the BEST match among them, not one query for
    # the whole unit. A unit is not one topic: MTH165 unit 2 has to teach
    # Rolle, the Mean Value Theorem, L'Hopital, Maclaurin and parametric
    # differentiation, and a single blended query retrieves passages that are
    # vaguely about all five and precisely about none. Loading seven pages that
    # each state one of those theorems moved the lesson's grounding not at all
    # until the retrieval could ask for them one at a time.
    queries = [query] if isinstance(query, str) else [q for q in query if q.strip()]
    qs = np.asarray(embed(queries or [unit_name]), dtype=np.float32)
    norms = np.linalg.norm(qs, axis=1)

    def best(v):
        denom = norms * float(np.linalg.norm(v))
        with np.errstate(divide="ignore", invalid="ignore"):
            sims = np.where(denom == 0.0, 0.0, (qs @ v) / np.where(denom == 0.0, 1.0, denom))
        return float(np.max(sims))

    ranked = sorted(rows, key=lambda r: -best(stored[r["id"]]))

    # Relevance decides the order; provenance decides how many scraped pages
    # get in. Filling by relevance alone let a site's pages take most of the
    # slots, and a third of them had lost the mathematics they were about.
    def spread(rows: list, cap: int) -> list:
        """Best first, but no file may take more than `cap` of the slots."""
        seen: dict[str, int] = {}
        out = []
        for r in rows:
            key = r["filename"]
            if seen.get(key, 0) >= cap:
                continue
            seen[key] = seen.get(key, 0) + 1
            out.append(r)
        return out

    docs = spread([r for r in ranked if is_document(r["filename"])], _MAX_PER_SOURCE)
    scraped = spread([r for r in ranked if not is_document(r["filename"])],
                     _MAX_PER_SOURCE)
    # Reserve for scraped pages only what scraped pages can actually fill.
    # Reserving a slot on a unit that has none spent a document's place on
    # nothing, and the top-up below then refilled it from the UNCAPPED list —
    # so the prolific file quietly took the slot the cap had just denied it.
    reserved = min(max(1, round(limit * _RESERVED_FOR_SCRAPED)), len(scraped))
    picked = docs[: limit - reserved] + scraped[:reserved]

    # Whichever pool is short, the other fills the gap: a unit held entirely in
    # PDFs gets a full set, and so does one held entirely in scrapes. And when
    # the shortfall is the CAP biting rather than a thin corpus, the cap
    # relaxes — it is a preference for breadth, the same rule the repeat
    # penalty on papers follows: rank, never exclude.
    if len(picked) < limit:
        chosen = {id(r) for r in picked}
        for r in ranked:
            if len(picked) >= limit:
                break
            if id(r) not in chosen:
                picked.append(r)
                chosen.add(id(r))
    order = {id(r): i for i, r in enumerate(ranked)}
    picked.sort(key=lambda r: order[id(r)])

    return [{"chunk_id": r["id"], "text": clean_text[id(r)],
             "page_ref": r["page_ref"],
             "filename": pathlib.Path(r["filename"]).name}
            for r in picked[:limit]]


__all__ = ["clean_latex", "ensure_vectors", "is_document", "load_source",
           "looks_symbol_stripped",
           "passage_is_usable", "plan_load",
           "read_manifest", "strip_boilerplate", "unit_passages"]
