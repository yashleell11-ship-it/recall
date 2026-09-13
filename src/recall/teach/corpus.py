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
from recall.ingest.pdf import (DOCUMENT_SUFFIXES, file_sha256, is_markup,
                               read_document)
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
        # Running heads go before chunking, because a page is the unit they
        # repeat on and a chunk spans several pages — and ONLY for formats with
        # real pages. See strip_running_heads for why markup is excluded.
        pages = read_document(str(path))
        if not is_markup(str(path)):
            pages = strip_running_heads(pages)
        chunks = chunk_pages(pages)
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


#: A running head is a line that repeats on most pages of a document, and it is
#: the PDF form of the failure "Reveal Answer Hide Answer" was on scraped pages:
#: PyMuPDF extracts a page's header and footer into the text flow, and the footer
#: of page n precedes the continuation of the sentence that runs onto page n+1.
#: So the header welds itself into the MIDDLE of real teaching:
#:
#:     "ENGINEERING GRAPHICS(23HES0301) AITS KADAPA Dept. of Mechanical
#:      Engineering Page 1 UNIT-1 INTRODUCTION TO ENGINEERING DRAWING Engineering
#:      drawing is a two dimensional representation of three dimensional objects."
#:
#: That last clause is the single most quotable sentence in MEC103's corpus, and
#: it could not be cited without a college name and a page number in front of it.
#: In 594 header-carrying sentences across the 8 worst files the header is a
#: PREFIX on real teaching, so refusing the quote throws the definition away too.
#:
#: `strip_boilerplate` cannot reach this. That rule removes the prefix common to
#: every CHUNK of one source, and a chunk of a PDF starts mid-page — measured, it
#: altered 0 of 573 chunks across 40 of 40 MEC103 files. Pages are the unit a
#: running head repeats on, so this runs on pages, before chunking.
#:
#: Two tiers, because the worst headers extract as several SHORT lines and a flat
#: 12-character floor cleared only 55% of them. It is the 90% threshold on short
#: lines that is load-bearing: at ≥50% a 4-character floor deletes "Output:"
#: (59% of pages of an NCERT Python chapter), which is the label separating every
#: program from its output, and "Ans:" from a CBSE marking scheme, which welds
#: question to answer. That is the code-damage class this codebase exists to
#: avoid. At ≥90% the same floor takes "Reprint #-#" (100%) and "Page #" (93-95%)
#: and leaves "Output:", "Ans:", "Notes" and "Functions" alone.
#:
#: Measured end to end on all 40 MEC103 files: 453 → 437 usable chunks (-3.5%),
#: 9,671 → 9,401 offered sentences (-2.8%), 496 → 115 sentences carrying a stamp
#: (77% cleared). Across 296 documents in the other five subjects it flags ~25
#: lines, every one a running head, and NO code line anywhere — nothing with an
#: include, import, def, print or operator reaches even half the pages of a file.
_RUNNING_HEAD_MIN_PAGES = 20

#: (shortest, longest, share of pages). Tier A is an ordinary running head; tier
#: B is the short stamp a header breaks into, and pays for its width with a much
#: higher threshold.
_RUNNING_HEAD_TIERS: tuple[tuple[int, int, float], ...] = (
    (12, 90, 0.50),
    (4, 11, 0.90),
)


def _normalise_line(line: str) -> str:
    """A line with its whitespace collapsed and its digits blanked.

    "Page 12" and "Page 13" are the same running head, so the page number has to
    stop distinguishing them before they can be counted together.

    The cost of that is real and worth naming: blanking digits also makes
    genuinely different lines look identical, so a document whose pages each
    carry "Example 7 shows the construction" would see them counted as one line
    and, above the threshold, deleted as furniture. The tier widths and page
    shares are what hold this down, and they were chosen against the whole
    corpus — 336 documents, ~25 lines flagged, every one a running head. Before
    a re-load, print the deletion set and read it; this is a rule to verify by
    looking, not by trusting.
    """
    return re.sub(r"\d+", "#", " ".join((line or "").split()))


def strip_running_heads(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop each line that repeats on most pages of one document.

    Takes and returns `read_document`'s shape, so it slots in ahead of
    `chunk_pages` and nothing downstream knows it ran.

    **Only for formats with real pages.** `load_source` does not call this for
    HTML, and that exclusion was bought with a near miss. A PDF's pages are real
    and a running head is printed on each; an HTML document has no pages at all
    until PyMuPDF lays it out at a fixed width, so "repeats on most pages" there
    just means "occurs often" — and in a tutorial what occurs often is its example
    code. Printing the deletion set for CSE326 showed exactly that:

        17/24 (71%) '.container {'
        16/24 (67%) 'display: grid;'          'font-family: sans-serif;'
        12/23 (52%) 'box-sizing: border-box;' '<div class="wrapper">'

    which is the code-damage class this codebase exists to avoid. Worse, it was
    an interaction nothing had measured: the chrome strip in `read_document` cuts
    an MDN page from 34 laid-out pages to 20, so declarations that sat under the
    50% threshold rose above it. The verification that approved these thresholds
    ran on the unstripped pages and reported no code flagged anywhere.
    """
    if len(pages) < _RUNNING_HEAD_MIN_PAGES:
        # A short document has no running head worth finding, and the one
        # measured false positive was exactly here: a 10-page lab sheet repeats
        # "Q. # Draw the orthographic projections of Fig. #" on 9 of its pages,
        # which is the assignment, not furniture.
        return pages

    # Pages carrying each line, not occurrences of it — a header printed twice on
    # one page is still one page.
    pages_with: dict[str, int] = {}
    for _number, text in pages:
        for line in {_normalise_line(ln) for ln in (text or "").splitlines()}:
            if line:
                pages_with[line] = pages_with.get(line, 0) + 1

    total = len(pages)
    doomed = {
        line for line, count in pages_with.items()
        if any(lo <= len(line) <= hi and count >= share * total
               for lo, hi, share in _RUNNING_HEAD_TIERS)
    }
    if not doomed:
        return pages
    return [
        (number, "\n".join(ln for ln in (text or "").splitlines()
                           if _normalise_line(ln) not in doomed))
        for number, text in pages
    ]


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

#: The Greek a scraper's LaTeX was standing in for. Listed rather than pulled
#: from a library so the set is reviewable, and because the notation law names
#: the real characters as the whole point.
_GREEK: tuple[tuple[str, str], ...] = (
    ("alpha", "α"), ("beta", "β"), ("gamma", "γ"), ("delta", "δ"),
    ("varepsilon", "ε"), ("epsilon", "ε"), ("zeta", "ζ"), ("eta", "η"),
    ("vartheta", "θ"), ("theta", "θ"), ("iota", "ι"), ("kappa", "κ"),
    ("lambda", "λ"), ("mu", "μ"), ("nu", "ν"), ("xi", "ξ"), ("rho", "ρ"),
    ("sigma", "σ"), ("tau", "τ"), ("upsilon", "υ"), ("varphi", "φ"),
    ("phi", "φ"), ("chi", "χ"), ("psi", "ψ"), ("omega", "ω"), ("pi", "π"),
    ("Gamma", "Γ"), ("Delta", "Δ"), ("Theta", "Θ"), ("Lambda", "Λ"),
    ("Xi", "Ξ"), ("Sigma", "Σ"), ("Upsilon", "Υ"), ("Phi", "Φ"),
    ("Psi", "Ψ"), ("Omega", "Ω"), ("Pi", "Π"),
)

#: LaTeX a scraper left in the text. A citation must stay verbatim, so it
#: cannot be tidied after the fact — the only place to fix this is BEFORE the
#: writer sees the passage, and then the quote is verbatim against the cleaned
#: text. Without this, "(\\operatorname{rank}(A)=k)" reached a student inside a
#: verified citation, having sailed past the notation law: that law is applied
#: to the lesson's prose, and a quote is not prose the model is free to write.
#:
#: **The boundary is `(?![A-Za-z])`, never `\\b`.** That was the bug that let
#: MTH165 unit 5 ship the grounded citation "A=int_α^βint_0^{R(θ)}r\\,dr\\,dthe
#: =frac12int_α^β R(θ)^2\\,dθ". A command ends where its NAME ends, and `_` is
#: a word character — so `\\int_0`, `\\geq0` and `\\lambda_1` had no word
#: boundary after the command, matched none of these rules, and fell through to
#: the catch-all. 1424 chunks of this corpus contain `int_`; every definite
#: integral in it had lost its ∫.
_LATEX_FIXES: tuple[tuple[str, str], ...] = (
    (r"\\operatorname\{([^}]*)\}", r"\1"),
    (r"\\(?:mathrm|mathbf|mathbb|mathcal|mathit|text|textbf)\{([^}]*)\}", r"\1"),
    # An environment's name is not text. `\begin{align}` left `{align}` behind
    # when only the command was dropped.
    (r"\\(?:begin|end)\{[^{}]*\}", ""),
    # The notation law prescribes a/b for a fraction, so a quote gets the same
    # — a student reads a quote and the prose around it the same way.
    (r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2"),
    (r"\\[dt]?frac(\d)(\d)", r"\1/\2"),
    (r"\\mid(?![A-Za-z])", "|"),
    (r"\\(?:ldots|cdots|dots)(?![A-Za-z])", "…"),
    (r"\\(?:leq|le)(?![A-Za-z])", "≤"),
    (r"\\(?:geq|ge)(?![A-Za-z])", "≥"),
    (r"\\(?:neq|ne)(?![A-Za-z])", "≠"),
    (r"\\approx(?![A-Za-z])", "≈"),
    (r"\\times(?![A-Za-z])", "×"),
    (r"\\cdot(?![A-Za-z])", "·"),
    (r"\\pm(?![A-Za-z])", "±"),
    (r"\\(?:to|rightarrow)(?![A-Za-z])", "→"),
    (r"\\partial(?![A-Za-z])", "∂"),
    (r"\\infty(?![A-Za-z])", "∞"),
    (r"\\nabla(?![A-Za-z])", "∇"),
    (r"\\sum(?![A-Za-z])", "∑"),
    (r"\\prod(?![A-Za-z])", "∏"),
    # Longest first: `\iiint` must not be read as `\iint` with a stray i.
    (r"\\iiint(?![A-Za-z])", "∭"),
    (r"\\iint(?![A-Za-z])", "∬"),
    (r"\\oint(?![A-Za-z])", "∮"),
    (r"\\int(?![A-Za-z])", "∫"),
    (r"\\sqrt(?![A-Za-z])", "√"),
    (r"\\in(?![A-Za-z])", "∈"),
    (r"\\cup(?![A-Za-z])", "∪"),
    (r"\\cap(?![A-Za-z])", "∩"),
) + tuple((rf"\\{name}(?![A-Za-z])", ch) for name, ch in _GREEK) + (
    # A formula's whitespace. Removing it is the one edit here that cannot
    # change what the formula says.
    (r"\\hspace\{[^{}]*\}", " "),
    (r"\\(?:quad|qquad)(?![A-Za-z])", " "),
    # A row or line break inside a matrix or an aligned block. It must come
    # before the single-character unescape below, or `\\` becomes a lone
    # backslash — which is how "(A=begin{bmatrix} 1&1\\0&2end{bmatrix})" reached a
    # student inside a grounded MTH165 unit 1 citation even after `\begin` was
    # being dropped: every rule here matched a backslash followed by LETTERS, and
    # this one is followed by another backslash.
    (r"\\\\", " "),
    (r"\\[,;:!>]", " "),
    (r"\\[()\[\]]", ""),
    # Anything still carrying a backslash is a command with no symbol here, so
    # DROP it, name and all. Keeping the letters — which is what this used to do
    # — is worse than leaving the LaTeX alone: `\frac12\int` became `frac12int`,
    # which reads as a word, quotes cleanly, passes every shell filter, and
    # teaches nothing. A dropped command leaves a hole instead, and a passage
    # full of holes is exactly what `passage_is_usable` already refuses.
    (r"\\[A-Za-z]+", ""),
    # ...and a backslash before anything else was escaping a literal: \{ \} \%
    # \& \_ \# all stand for the character itself. Last, so no rule above has
    # to guard against a stray backslash it did not expect.
    (r"\\(.)", r"\1"),
    (r"\$+", ""),
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


#: What a PDF's own fonts did to its mathematics. Computer Modern's extensible
#: delimiters and radicals, and Adobe Symbol's Greek, are subsetted glyphs with
#: no usable ToUnicode map, so PyMuPDF returns either a C0 control character or a
#: private-use code point — text no font on earth can draw.
#:
#: Measured in this corpus: 365 offered sentences across 86 MTH165 files carry a
#: control character where a bracket belongs, and 413 across 21 files carry a
#: private-use glyph. A student sees a row of tofu boxes, or — worse, depending
#: on the client — nothing at all, leaving "the amount is r k A = P 1 +".
#:
#: The Adobe Symbol ones are RECOVERABLE, because the code point says which glyph
#: the font drew. Written out rather than computed, like `_GREEK`, so the set
#: stays reviewable.
_PUA_SYMBOL: tuple[tuple[str, str], ...] = (
    ("\uf070", "π"), ("\uf071", "θ"), ("\uf066", "φ"), ("\uf0d0", "∠"),
    ("\uf0b0", "°"), ("\uf03d", "="), ("\uf02b", "+"), ("\uf0b4", "×"),
    ("\uf05e", "⊥"), ("\uf0b7", "•"), ("\uf061", "α"), ("\uf062", "β"),
    ("\uf067", "γ"), ("\uf064", "δ"), ("\uf06c", "λ"), ("\uf06d", "μ"),
    ("\uf073", "σ"), ("\uf077", "ω"), ("\uf0ce", "⊆"), ("\uf0b9", "≠"),
    ("\uf0a3", "≤"), ("\uf0b3", "≥"), ("\uf0d6", "√"), ("\uf0a5", "∞"),
)

#: A matrix bracket, brace or big parenthesis, built from stretch pieces. The
#: opening and closing pieces carry the shape; the middle extension pieces carry
#: nothing and are dropped.
_BRACKET_OPEN = "\uf8ee\uf8f0\uf8f1\uf8f2\u239b\u239d\u23a1\u23a3"
_BRACKET_CLOSE = "\uf8f9\uf8fa\uf8fb\uf8f4\u239e\u23a0\u23a4\u23a6"
_BRACKET_EXTEND = "\uf8ef\uf8f3\uf8f5\uf8f6\uf8f7\uf8f8\u239c\u239f\u23a2\u23a5"

#: Any private-use code point at all, for the backstop. By definition the range
#: carries no meaning, so nothing legitimate is ever matched.
_PUA_ANY = "\ue000-\uf8ff"

#: C0 controls, minus tab, newline and carriage return. \x10-\x15 and \x1a are
#: where Computer Modern's ( ) [ ] and brace pieces land.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_latex(text: str) -> str:
    """Turn a scraper's leftover LaTeX into the symbols it stood for."""
    out = _strip_displaystyle(text or "")
    # First, because a control character is not text and every rule below would
    # otherwise have to step over one.
    out = _CONTROL.sub("", out)
    for bad, good in _PUA_SYMBOL:
        out = out.replace(bad, good)
    for ch in _BRACKET_OPEN:
        out = out.replace(ch, "[")
    for ch in _BRACKET_CLOSE:
        out = out.replace(ch, "]")
    for ch in _BRACKET_EXTEND:
        out = out.replace(ch, "")
    for pattern, repl in _LATEX_FIXES:
        out = re.sub(pattern, repl, out)
    return out


#: A scraper's placeholder for a formula it could not render. Dropping it makes
#: the sentence read as written and keeps a quote from having to step over it.
#:
#: `MATH` is the second spelling, found in the MTH165 unit 5 notes — 352 chunks
#: carry it, and one reached a student inside a grounded citation reading "then
#: MATH A=int_α^β…". Every scraper picks its own word for this, which is why the
#: sentence-level backstop below exists as well.
#:
#: `[image]` is the third, and it is not a scraper's word but PyMuPDF's: its HTML
#: renderer writes the literal string for every <img> it cannot fetch, and the
#: scrapes carry no image files, so every one. 302 occurrences across 97 of
#: CSE326's 206 files. The alt text — which was the figure's only description —
#: is discarded, so there is nothing to recover and nothing to lose by dropping
#: the marker. Bracketed, so it cannot collide with prose: course material about
#: images writes `<img>` or "image", never "[image]".
_FORMULA_PLACEHOLDER = re.compile(
    r"(?<![A-Za-z])(?:TEXT|MATH)(?![A-Za-z])|\[image\]")


#: Text that is furniture rather than teaching: a scraped site's quiz
#: scaffolding and navigation, which a page chunk carries into the same passage
#: as the real content.
#:
#: Stripped here, not merely refused later. MTH165 unit 5 ground at 50% because
#: two of its four sections cited sentences that BEGAN "Reveal Answer Hide
#: Answer Correct Answer: Explanation:" — the scaffolding is glued to the front
#: of a real explanation with no full stop between them, so the sentence
#: splitter offers the writer one span containing both. Refusing that quote threw
#: the explanation away with it, and it happened only after the generation was
#: paid for. Removing the scaffolding leaves the explanation citable.
#:
#: `lessons.py` checks stored quotes against this same tuple, so the two cannot
#: drift into disagreeing about what furniture is.
FURNITURE: tuple[str, ...] = (
    "reveal answer", "hide answer", "correct answer:", "incorrect!",
    "try again", "explanation:", "ctrl+k", "view all updates", "mark all read",
    "you're offline", "exam center", "offline library", "request material",
    "loading…", "click here", "download pdf", "table of contents",
    # The subjective bank's reveal control, on the same site "reveal answer"
    # came from. It fuses to the front of the model answer exactly as that one
    # did, so the best-written definitions in the LPU material could not be
    # cited clean: 137 offered sentences, 6 of CSE326's 206 files.
    "show detailed answer",
    # MDN's page footer. Each is a whole distinctive phrase, checked against every
    # other subject's prose: 0 spans removed across INT108's 37 files, CSE111
    # apart from one licence footer, MTH165's 40 and MEC103's 40.
    "view this page on github", "report a problem with this content",
    "content available under a creative commons license",
    "this page was last modified", "help improve mdn",
    # A NIMI exercise instruction, 22 offered sentences.
    "read and write the following",
)

#: Furniture that is not a phrase but a SHAPE — a footer, a notice, a stamp —
#: and so cannot go in the tuple above.
#:
#: Every one is measured, and every one was welded into the MIDDLE of a real
#: sentence rather than sitting tidily at the top: PyMuPDF interleaves a page's
#: footer with the prose, and the footer of page n precedes the continuation of
#: the sentence that runs onto page n+1. `strip_boilerplate` cannot see any of
#: it — that rule removes a prefix common to every chunk of one source, and a
#: chunk of a PDF starts mid-page, so it altered 0 of 573 chunks across 40 of 40
#: MEC103 files.
#:
#: Counts are offered citable sentences carrying the marker, over the corpus as
#: loaded on 2026-09-13.
_PAGE_CHROME: tuple[tuple[str, int], ...] = (
    # MIT OCW's five-line end notice, welded to the tail of each file's last
    # real sentence. 171 sentences in 171 files — one per OCW PDF.
    (r"MIT OpenCourseWare\s+https?://ocw\.mit\.edu.*?ocw\.mit\.edu/terms\.?", re.S),
    (r"For information about citing these materials[^.]*?\.\s*\S*", 0),
    # OpenStax's page footer: an advertisement inside a citation. 723 sentences.
    (r"Access for free at openstax\.org", 0),
    (r"\(?https?://(?:www\.)?openstax\.org/l/\S+\)?", 0),
    # NCERT's print-run stamp, which lands inside any citation spanning a page
    # boundary — and the NCERT chapters are MTH165 unit 1 and 3's main textbook.
    # 293 sentences across 10 files.
    (r"Reprint \d{4}-\d{2}", 0),
    # The LPU notes site's footer and network byline, 28% of the 528 offered LPU
    # sentences carry one of these.
    (r"©\s*20\d\d\s+LPU Notes", re.I),
    (r"Part of the LPU Verto Network", re.I),
    (r"Made with\s*\S{0,3}\s*for Vertos", re.I),
    # MDN's per-page pager and in-page table of contents. Neither ends in a full
    # stop, so both fuse to the adjacent real sentence — the CSS box model page's
    # opening definition, the sentence a unit 3 lesson would obviously cite,
    # could not be quoted without the pager in front of it.
    #
    # The bullet anchors are load-bearing and the newline handling is the whole
    # difficulty: `strip_furniture` runs on raw chunk text where the pager's items
    # are still newline-separated, so a `[^•\n]*` that must be followed
    # immediately by `•` matched 29 of 210 real occurrences. Allowing the
    # whitespace before the next bullet reaches 210 of 210.
    (r"•\s*Previous(?:\s*•[^•\n]*)*\s*•\s*Next", 0),
    # 214 matches, and every span ends at the last TOC item because that item is
    # newline-terminated and the next line is a heading. The bullet run is what
    # makes it safe: the bare phrase "in this article" is real prose in about 39
    # CSE326 sentences and 1 OpenStax one.
    (r"In this article(?:\s*•[^\n]*)+", 0),
    # Two running heads from subjects that are NOT being re-loaded, so
    # strip_running_heads will not reach them. Measured on the raw files: the
    # d.school byline is on 88 of 88 pages of the Bootleg, and NCERT's class line
    # on half the pages of every chapter it appears in.
    #
    # Re-loading those subjects to catch these was measured and declined: their
    # whole deletion set is about 6,900 characters against MEC103's 44,300, and
    # most of it — "Access for free at openstax.org", "Reprint #-#",
    # "Explanation:" — is already removed here. That left ~0.3% of their offered
    # sentences for the price of re-embedding some three thousand chunks.
    #
    # Only the UNAMBIGUOUS ones are taken as phrases. The bare chapter titles the
    # same measurement turned up — "Computer System" (50% of pages) and "Computer
    # Networks" (50%) — are left alone, because they are ordinary prose in a
    # computer-fundamentals course and CSE111 unit 2 is literally about computer
    # systems.
    (r"d\.school at Stanford University", re.I),
    (r"Computer Science\s*[-–—]\s*Class\s*(?:xi{1,2}|\d{1,2})", re.I),
    # The accessibility skip-links, as an anchored PAIR.
    #
    # A bare "skip to main content" entry was rejected earlier, and rightly: it
    # deleted the one fingerprint a backstop could match while leaving MDN's
    # 1,784-character menu citable, hiding the evidence and keeping the menu.
    # That menu is now removed at ingest, before PyMuPDF ever lays the page out,
    # so there is no longer anything behind these two links for the fingerprint to
    # stand for — and they are what remains welded to the front of the page title
    # and the opening definition.
    (r"•\s*Skip to main content\s*•\s*Skip to search", re.I),
    # Anchored, NOT a bare "learn how to contribute" entry. That phrase as
    # furniture destroys a real 39-word Pro Git sentence in CSE111 — "you'll learn
    # how to contribute code successfully to a project…" — and because FURNITURE
    # is the same tuple `_quote_is_furniture` checks, a lesson that cited it would
    # be refused AFTER the generation was paid for.
    (r"Help improve MDN\s*Learn how to contribute", re.I),
    # WHATWG's per-feature annotation box, flattened into running prose. The
    # spec's crispest definitional sentences all carry a support table stapled to
    # the end. 529 matches, median 24 characters, longest 98, no prose.
    (r"[✔⚠]MDN[^\n]*(?:\n[^\n]*)?", 0),
    (r"Support in (?:all current engines|one engine only|no engines)\.?", 0),
    # ...and the browser-version run the same table becomes. The two-or-more
    # requirement is what keeps a legitimate "supported in Chrome 1+" intact, and
    # the alternation is browser names, so no code is touched.
    (r"(?:(?:Firefox|Safari|Chrome|Opera|Edge|Internet Explorer|WebView"
     r"|Samsung Internet)(?:\s*(?:Android|iOS|\(Legacy\)))?\s*(?:\U0001f530\s*)?"
     r"(?:\d+(?:\.\d+)*\+?|\?|No|Yes)\s*){2,}", 0),
)

#: Deliberately NOT here, both rejected on measurement.
#:
#: A section-number strip `(?m)^\d+(?:\.\d+)+\s` manufactures the worst defect
#: class in this file's own taxonomy. In u4-mdn-math.html — the one CSE326 file
#: whose whole subject is JavaScript operator precedence — it turns "50 plus 1.25
#: plus 2 equals 53.25" into "50 plus plus 2 equals 53.25": a number gone, reading
#: as fluent English, saying nothing, quotable through every filter. It also eats
#: the first entry of the canonical float-literal list "3.1415926 .123456789
#: 3.1E+12 .1e-23", "6.170 " from five MIT OCW headers and "9.4.1 " from a real
#: CSS-spec citation. 181 hits that do not fix the problem, against 2 passages
#: actively corrupted.
#:
#: MDN's 340-word header mega-nav stays too, and that is an admission rather than
#: a decision: no boundary for it could be proved safe. An anchored run from "Skip
#: to main content" has no reliable end marker, and the blunt alternative —
#: refusing any span with four or more bullets — drops 656 offered CSE326
#: sentences, some of them real bullet-list teaching ("• The alternative box model
#: (accessed via box-sizing: border-box) and how it differs…"). It needs its own
#: measurement, so 154 nav spans remain citable for now.

_PAGE_CHROME_RE = tuple(re.compile(pat, flags) for pat, flags in _PAGE_CHROME)

#: A figure cross-reference in parentheses, pointing at a figure that did not
#: survive extraction.
#:
#: MEC103's NIMI manuals put it at the head of the paragraph it introduces, and
#: the sentence splitter then glues it to the front of the definition that
#: follows: "(Fig 3) Obtuse angle: This refers to an angle between 90° and 180°."
#: Removing it leaves a clean citable definition. 422 MEC103 sentences carry one.
#:
#: STRIPPED, not refused, and the difference is the whole finding. Refusing a
#: sentence for carrying a figure pointer was measured and is worse than
#: break-even: 45 sentences of legitimate course material lost to remove 42 empty
#: ones — and the casualties are the corpus's best short statements, because NIMI
#: writes terse one-line definitions. It would refuse the definition of an obtuse
#: angle, all three classes of curved-surface solids, "Ring nut: Its diameter is
#: 1.8 d and thickness is 0.5 d", and the symbol for third-angle projection, in a
#: subject whose entire content is drawing conventions. That is the filter that
#: gets switched off, taking the useful part with it.
#:
#: Done at PASSAGE level rather than per sentence, because a quote must stay
#: verbatim against the passage it is checked against — repairing the sentence
#: after it was split would turn every citation from these files into a
#: paraphrase and fail the grounding gate outright.
_FIGURE_REF = re.compile(r"\(\s*Figs?\.?\s*[^)]{0,24}\)[\s\-–—:]*")

#: ...except where the parenthetical is the grammatical SUBJECT of what follows,
#: which is the one shape whose meaning the strip would destroy: "(Fig 2) shows a
#: V belt pulley having three V grooves." becomes "shows a V belt pulley…".
#: Measured: this guard is the difference between repairing 421 of 422 and 422 of
#: 422 with one casualty.
_FIGURE_REF_SUBJECT = re.compile(
    r"^\s*(?:shows|gives|illustrates|indicates|represents|depicts)\b")


def strip_figure_refs(text: str) -> str:
    """Remove a dead figure cross-reference, keeping the sentence around it."""
    out = []
    pos = 0
    for m in _FIGURE_REF.finditer(text or ""):
        if _FIGURE_REF_SUBJECT.match(text[m.end():m.end() + 24]):
            continue
        out.append(text[pos:m.start()])
        pos = m.end()
    out.append((text or "")[pos:])
    return "".join(out)

#: A RUN of markers, not one at a time: the real text is "Reveal Answer Hide
#: Answer Correct Answer: Explanation:", four of them in a row, and removing
#: them one by one would leave the whitespace between them behind.
_FURNITURE_RUN = re.compile(
    r"(?:(?:" + "|".join(re.escape(m) for m in FURNITURE) + r")\s*)+",
    re.IGNORECASE)


def strip_furniture(text: str) -> str:
    r"""Remove a scraped page's scaffolding, leaving the teaching behind.

    Structural patterns first, single phrases second. The other order left
    wreckage: the phrase "help improve mdn" ate its own anchor, so the paired
    regex `Help improve MDN\s*Learn how to contribute` could no longer match and
    "Learn how to contribute" survived on its own. A multi-word shape has to be
    matched before anything is allowed to break it up.
    """
    out = text or ""
    for pattern in _PAGE_CHROME_RE:
        out = pattern.sub(" ", out)
    out = strip_figure_refs(out)
    return _FURNITURE_RUN.sub(" ", out)


#: LaTeX command names, for finding wreckage a cleaner could not name. Only the
#: distinctive ones: `mu`, `pi` and `end` are words and short identifiers as
#: often as they are commands, and a check that cries wolf gets switched off.
_LATEX_NAMES = (
    "iiint", "iint", "oint", "int", "sum", "prod", "frac", "sqrt", "cdot",
    "qquad", "quad", "displaystyle", "operatorname", "mathrm", "mathbb",
    "mathcal", "leq", "geq", "neq", "infty", "partial", "alpha", "beta",
    "gamma", "delta", "theta", "lambda", "sigma", "rho", "varphi", "phi",
    "psi", "omega",
)

#: Debris `clean_latex` could not fix. Two kinds: a surviving backslash, and a
#: command name butted straight against a symbol or a digit in a source whose
#: backslashes were ALREADY stripped before it reached us — "(z=f(x,y)geq0)"
#: and "rho^2sinphi" are both real, from MTH165 unit 5, and there is no marker
#: left in them to find the command by except the glue. In ordinary prose these
#: words are followed by a space or a full stop.
#: A private-use code point is, by definition, text no font can draw, so a
#: sentence carrying one shows a student a tofu box.
#:
#: Presence, not share — and that is the opposite of what the verification
#: recommended, because the verification measured a presence rule BEFORE
#: `_PUA_SYMBOL` existed. It found presence removing 199 of 1,043 sentences in the
#: CBSE textbook, 19%, and reasonably asked for a share guard instead. Measured
#: again with recovery in place, presence now refuses 457 of 116,586 offered
#: sentences across the whole corpus — 0.39%, and at worst 2.40% in MEC103:
#:
#:     CSE111 0.25%   CSE326 0.00%   INT108 0.12%
#:     INT335 0.00%   MEC103 2.40%   MTH165 0.82%
#:
#: A share guard would be the wrong shape anyway, because what is left is not one
#: lost symbol in good prose. 87 distinct code points survive, and they are whole
#: WORDS in a subsetted font with no ToUnicode map — "ISOMETRIC PROJECTION" arrives
#: as `\uf0d7\uf0cd\uf0d1\uf0d3\uf0db\uf0cc⊆\uf0d7\uf0dd\uf020∠⊆\uf0d1√\uf0db\uf0dd\uf0cc\uf0d7\uf0d1\uf0d2`,
#: which is most of its sentence. A high-share sentence and a low-share one are the
#: same defect here.
#:
#: Nor can the rest be recovered the way `_PUA_SYMBOL` recovers Adobe Symbol. That
#: table works because Symbol's low byte is the ASCII of the glyph slot: U+F070 is
#: its "p", which draws π. These are not that — U+F0D7's low byte is 0xD7, U+F0DB's
#: is 0xDB, and neither is a letter. The font carries its own subset encoding, so
#: there is nothing to map from and the sentence has to go.
#:
#: **Deliberately NOT here: "Z" for ∫.** MIT's LaTeX PDFs use Computer Modern
#: extensible glyphs and PyMuPDF maps them to Latin letters — ∫ becomes "Z", ∬
#: "ZZ", ∑ "X", ∂ "@" — and a reader is shown a letter where an operator belongs.
#: It is real, it was verified, and refusing it is still the wrong trade. The
#: rule `Z{1,3}\s+(?=[0-9a-zπ(])` matches 63 of this corpus's 122,011 offered
#: sentences, and 9 of the 63 are legitimate text in FOUR different subjects:
#:
#:     n ∈ Z and cotangent function is continuous except…   ← Z is the integers
#:     git checkout tags/vX.Y.Z, where vX.Y.Z corresponds…  ← CSE111 unit 5
#:     commands M moveto, L lineto, C curveto, Z closepath  ← CSE326 SVG paths
#:     the Unicode value of uppercase Z is less than…       ← INT108 unit 3
#:     Ctrl-Z then Enter on Windows                         ← INT108 unit 1
#:
#: Fifty-odd damaged MIT sentences are not worth refusing set-theory, git, SVG
#: and Python material, and "@" is worse still — it would refuse @property,
#: @staticmethod, @media and @keyframes, which are syllabus content for INT108
#: unit 5 and CSE326 unit 3. The verification that proposed this measured MTH165
#: alone; on the whole corpus the sign flips. A check that cries wolf gets
#: switched off, and then there is no check.
_DEBRIS = re.compile(
    r"\\"
    r"|(?<![A-Za-z])(?:" + "|".join(_LATEX_NAMES) + r")[_^{}\d]"
    r"|(?<![A-Za-z])(?:MATH|TEXT)(?![A-Za-z])"
    r"|[" + _PUA_ANY + r"]")


def looks_like_latex_debris(text: str) -> bool:
    """True when a span still carries the wreckage of a formula.

    The backstop under `clean_latex`, because no list of commands is ever
    complete. It runs where sentences are OFFERED rather than where quotes are
    judged: the writer cites by number, so a sentence this refuses cannot be
    quoted at all, and nothing has to be generated, paid for and then rejected.
    """
    return _DEBRIS.search(text or "") is not None


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


#: A sentence ends at ., ! or ? followed by space and something that starts a
#: new sentence. Deliberately not a general sentence splitter: it only has to
#: agree with ITSELF, because the same function numbers the sentences shown to
#: the writer and resolves the number it sends back.
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


#: An angle whose degree sign became a digit.
#:
#: In the drawing-course PDFs the degree sign is drawn as a small raised ring in a
#: symbol font, and `page.get_text()` returns it as the ASCII digit "0" — so every
#: angle silently gains a decimal place and "inclined at 75° to the H.P" becomes
#: "inclined at 750 to the H.P". This is the worst shape a defect can take: it
#: leaves no hole, it leaves a PLAUSIBLE WRONG NUMBER, and MEC103 is a subject
#: where the angle is the question. 188 of its 9,671 offered sentences.
#:
#: Refused, not repaired, and kept as its own predicate rather than folded into
#: `_DEBRIS`. Two reasons. The message differs — a flattened superscript is not
#: "the wreckage of a formula the scrape lost" — and `_DEBRIS` is global, so
#: anything put there is applied to every subject.
#:
#: That globality is exactly what makes the obvious version unshippable. Matching
#: these tokens without context rejects, measured: a Python for Everybody REPL
#: transcript (">>> second = '150' >>> print(first + second) 100150"), "the works
#: of Eudoxus (440 B.C.) and Archimedes (300 B.C.)", "setTimeout(fn, 1500)",
#: "range(1500)", "HTTP status code 300", "width 1200 and height 900",
#: "font-size: 150%" and "eigenvalue 150" — and CSE326 is a web course where
#: 1200, 900 and 1500 are viewport sizes and timeouts. Three hits across 1,371
#: non-MEC103 sentences, three false positives, zero true positives.
#:
#: Inside MEC103 the naive form is only 83% precise, and its collateral lands on
#: unit 1, whose syllabus line is "Dimensioning, Scales and Conic Sections": the
#: drawing-board table "D0 1500 X 1000", the sheet sizes "450 x 625", the scale
#: ratios "150:1", "Chennai - 600 032", "Leonardo's Canon Foundry 1500 AD".
#:
#: So the token shapes that are literal numbers are excluded, and a drawing word
#: must appear within 45 characters. That rejects 140 rather than 188, keeps every
#: prose case that is a true degree loss, and fires zero times outside MEC103.
_DEGREE_ZERO = re.compile(
    r"(?<![\d.:/–-])(?:15|30|45|60|75|90|105|120|135|150|180)0(?![\d:])"
    r"(?!\s*(?:[Mm]{1,2}|[Cc][Mm]|[Kk][Mm]|kg|rpm|[Nn]|AD|BC|[Xx×]|\d{3})\b)")

#: The vocabulary of a drawing office. Without it this rule is unshippable.
_DEGREE_CTX = re.compile(
    r"inclin|angle|degree|chamfer|countersunk|counter sunk|csk|measur|"
    r"perpendicular|isometric|flank|apex|bevel|rotat|interval|"
    r"to (the )?(H\.?P|V\.?P|xy|axis)|with (the )?(H\.?P|V\.?P)", re.I)

#: How far either side of the number a drawing word may sit.
_DEGREE_CTX_WINDOW = 45


def looks_like_lost_degree(text: str) -> bool:
    """True when a number in this span was almost certainly an angle.

    A repair would be better than a refusal and is possible — 83% of these carry
    the evidence in the PDF, as a raised or smaller glyph that `rawdict` exposes —
    but that changes `read_document` for every subject and needs the whole corpus
    re-loaded. This is the cheap half, and it is the half that stops a wrong
    number reaching a student now.
    """
    for m in _DEGREE_ZERO.finditer(text or ""):
        start = max(0, m.start() - _DEGREE_CTX_WINDOW)
        if _DEGREE_CTX.search(text[start:m.end() + _DEGREE_CTX_WINDOW]):
            return True
    return False


#: The glyphs a rendered link list is built from. `○` is not decoration: Google's
#: nav nests it inside `•`, so a set without it leaves that menu citable.
_BULLET = re.compile(r"[•○‣▪▸»]")

#: A menu is not a sentence, and the thresholds come from both sides of the gap
#: rather than from taste. MDN's header mega-nav arrives as one candidate with 81
#: bullets at 4.26 per 100 characters; the most bullet-heavy quote any writer has
#: actually chosen across this project's 45 stored citations has 9 bullets at 1.34
#: per 100. These sit between the two with about 2x margin either way.
_LINK_LIST_BULLETS = 20
_LINK_LIST_MIN_CHARS = 300
_LINK_LIST_DENSITY = 2.5


def _is_link_list(sentence: str) -> bool:
    """True when a candidate is a navigation menu wearing a sentence's clothes.

    Refusing it HERE is the cheap place: the writer cites by number, so a
    candidate `split_sentences` does not return can never reach a student, and
    nothing is deleted from any passage — no code, no formula, no quote can be
    altered by a rule that only withholds.

    The alternative was tried and measured far worse. Dropping lines that repeat
    across a unit's files deletes CODE: at a 10-file threshold `}` (48 files),
    `body {` (25), `</div>` (24), `color: white;` (20) and `display: flex;` (15)
    all go, and 282 of 567 chunks of CSE326 unit 3 lose at least one code line —
    turning the very declaration a passage exists to teach, "input, textarea,
    select, button { width: 150px; padding: 0; margin: 0; box-sizing: border-box;
    }", into "input, textarea, select, button { width: 150px;".

    Measured over all 184 CSE326 files: 354 of 36,509 offered candidates refused
    (0.97%), 151 of them the header menu, in 151 of the 153 files that carry it.
    Mathematics is untouched, because extracted mathematics has no bullets.
    """
    bullets = len(_BULLET.findall(sentence))
    if bullets >= _LINK_LIST_BULLETS:
        return True
    if len(sentence) <= _LINK_LIST_MIN_CHARS:
        return False
    return bullets / (len(sentence) / 100.0) >= _LINK_LIST_DENSITY


def split_sentences(text: str) -> list[str]:
    """The citable sentences of a passage, in order.

    Only sentences long enough to state something are returned — the same floor
    the citation check applies — so a writer choosing by number cannot choose a
    fragment, and the prompt is not padded with lines nobody may cite.
    """
    flat = " ".join((text or "").split())
    return [s.strip() for s in _SENTENCE.split(flat)
            if len(s.split()) >= _MIN_CITABLE_WORDS
            and not looks_like_latex_debris(s)
            and not looks_like_lost_degree(s)
            and not _is_link_list(s)]


#: Matches lessons._MIN_QUOTE_WORDS. Kept here as its own name because this is
#: what decides which sentences are OFFERED, and that is a different decision
#: from what is accepted — they simply agree today.
_MIN_CITABLE_WORDS = 6


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

    # Scaffolding first, then the formula placeholders, then the LaTeX: each
    # one is noise the NEXT step would otherwise have to read around.
    cleaned = [(r, clean_latex(_FORMULA_PLACEHOLDER.sub("", strip_furniture(t))))
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


__all__ = ["FURNITURE", "clean_latex", "ensure_vectors", "is_document",
           "load_source", "looks_like_latex_debris", "looks_like_lost_degree",
           "looks_symbol_stripped",
           "passage_is_usable", "plan_load",
           "read_manifest", "strip_boilerplate", "strip_figure_refs",
           "strip_furniture", "strip_running_heads", "unit_passages"]
