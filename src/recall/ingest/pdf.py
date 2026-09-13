import hashlib
from html.parser import HTMLParser
from pathlib import Path

import fitz

#: Everything PyMuPDF opens and paginates for us. HTML is here because the
#: best free material for a web-programming course is MDN and the specs, and
#: those are pages, not PDFs — PyMuPDF renders one into laid-out pages with
#: script and style already dropped, so no HTML parser is needed and no new
#: dependency comes with it. EPUB and XPS come along for free.
#:
#: `.txt` is here for the opposite reason: it is the format with nothing to go
#: wrong. A PDF can lose its symbols in extraction — OpenStax Calculus reached
#: a lesson as "If is continuous over and differentiable over and then there
#: exists a point such that" — and a scraped page arrives wrapped in its
#: navigation. Plain text is already the thing, and PyMuPDF paginates it like
#: anything else.
DOCUMENT_SUFFIXES = frozenset({".pdf", ".html", ".htm", ".xhtml", ".epub",
                               ".xps", ".fb2", ".mobi", ".txt"})


#: The formats PyMuPDF lays out from markup, and so the ones whose chrome is
#: still in the bytes when we get them — and the ones with no real pages.
_MARKUP_SUFFIXES = frozenset({".html", ".htm", ".xhtml"})


def is_markup(path: str) -> bool:
    """True for a format PyMuPDF paginates from markup rather than from a page.

    The distinction matters to anything reasoning about PAGES. A PDF's pages are
    real: a running head is printed on each one. An HTML page has no pages at all
    until PyMuPDF lays it out at a fixed width, so "a line that repeats on most
    pages" means nothing there — it just means the line occurs often, which for a
    tutorial is its example code.
    """
    return Path(path).suffix.lower() in _MARKUP_SUFFIXES


def document_kind(path: str) -> str:
    """The `sources.kind` to record — the suffix, without its dot."""
    return Path(path).suffix.lower().lstrip(".") or "unknown"


#: Elements whose whole subtree is page furniture rather than teaching. Dropping
#: them is the only fix that reaches MDN's sidebar curriculum tree and its CSS
#: and SVG property-index dumps — 2,295 offered sentences — because those carry
#: many full stops, repeat in too few files for any repetition rule, and are not
#: bullet-dense enough for the link-list rule.
#:
#: MDN puts the article in <main id="content"> and everything else in
#: <header class="page-layout__header">, <nav class="left-sidebar">,
#: <nav class="menu">, <nav class="reference-toc">, <aside id="main-sidebar">,
#: <aside class="reference-layout__toc"> and <footer class="footer">. It is
#: tempting to keep only <main> instead — do not: the WHATWG spec pages have no
#: <main> at all and would come through empty.
_CHROME_ELEMENTS = frozenset({"nav", "aside", "footer", "header"})

#: How wide to lay a markup document out, and why it is not left to the default.
#:
#: PyMuPDF hard-clips a non-wrapping <pre> line at the right margin — the tail is
#: DISCARDED, not wrapped onto the next line. In a web-programming course the code
#: IS the teaching content, so this silently truncates the thing the page exists to
#: show: unterminated attributes, unclosed tags, half-written statements. On
#: /corpus/CSE326/u3-mdn-box-model.html alone, 8 of its 33 code lines of 30
#: characters or more were losing their tails, among them
#:
#:     <span>words</span> have been wrapped in a <span>span element</span>.
#:
#: which arrived as 53 of its 68 characters.
#:
#: Two separate things had to be true, both measured on a 176-character line:
#: `layout()` must be CALLED at all — without it 56 of 176 characters survive, at
#: A4 86 — and the page must be WIDE — 1000pt keeps 147, 1600 keeps all 176.
#: Calling `layout()` with no rect raises "bad page size".
#:
#: The cost of a wide page is fewer laid-out pages: that file goes from 20 to 4.
#: That would matter if a page number meant anything here, and it does not — an MDN
#: page has no pages, so the number is a PyMuPDF artifact that no student can look
#: up, and the filename is the real provenance. Chunk count is unchanged at 8,
#: because chunking splits on characters rather than on pages.
#:
#: The residual limit, named rather than left to be discovered: a line beyond
#: roughly 190 characters still loses its tail. Teaching code is rarely that long,
#: and going wider collapses the document toward one page for no further gain.
_MARKUP_PAGE = fitz.Rect(0, 0, 1600, 2200)


#: A last-resort net for a parse that went badly wrong. Deliberately very low:
#: the real hazard is detected exactly (see `unterminated`), and a share-based
#: guard set anywhere near a sensible-looking value silently disables the strip
#: on the pages where chrome is most of the markup — which is most of them.
_MIN_KEPT_SHARE = 0.05


#: PyMuPDF decodes character references TWICE on its way to laid-out text, and
#: that is measured, not assumed: `&lt;` arrives as "<", which one decode would
#: also give — but `&amp;lt;` arrives as "<" too, and one decode would have given
#: "&lt;".
#:
#: A page writes `&amp;lt;` precisely in order to DISPLAY `&lt;`, which is how
#: every escaping lesson on the web is written. Under two decodes MDN's
#: literal-character/character-reference table collapses into two identical
#: columns, and the sentence beside it becomes "For example, < becomes <, and &
#: becomes &." — fluent, verbatim, citable, and teaching something FALSE. Character
#: references are a CSE326 unit 1 syllabus topic.
#:
#: Since the parser is already re-emitting every token, adding one level of
#: escaping on the way out cancels the extra decode exactly:
#:
#:     &lt;      -> &amp;lt;      -> two decodes -> <       (still right)
#:     &amp;lt;  -> &amp;amp;lt;  -> two decodes -> &lt;    (right at last)
#:
#: Attribute text inside a start tag is left alone: it is not rendered, and a URL
#: with `&amp;` in a query string has nothing to do with what a student reads.
_COMPENSATES_FOR_A_SECOND_DECODE = True


class _DropChrome(HTMLParser):
    """Re-emit HTML with every nav/aside/footer/header subtree removed.

    `convert_charrefs=False` is load-bearing, not a detail. With the default,
    `handle_data` receives DECODED text, so this class could not tell an entity
    from the character it stands for and the compensation above would be
    impossible.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.kept: list[str] = []
        self._drop_tag: str | None = None
        self._drop_depth = 0

    @property
    def unterminated(self) -> bool:
        """True when the document ended inside a dropped subtree.

        This is the one way this parser can lose real content: scraped HTML is
        exactly where a missing `</nav>` lives, and an unclosed chrome element
        swallows everything after it. Checking it directly beats guessing from
        the output's size.
        """
        return self._drop_tag is not None

    # Inside a dropped subtree, only that element's own nesting is counted, so
    # <nav>…<div>…<nav>…</nav>…</nav> closes at the right place.
    def handle_starttag(self, tag, attrs):
        if self._drop_tag is not None:
            if tag == self._drop_tag:
                self._drop_depth += 1
            return
        if tag in _CHROME_ELEMENTS:
            self._drop_tag, self._drop_depth = tag, 1
            return
        self.kept.append(self.get_starttag_text() or f"<{tag}>")

    def handle_endtag(self, tag):
        if self._drop_tag is not None:
            if tag == self._drop_tag:
                self._drop_depth -= 1
                if self._drop_depth <= 0:
                    self._drop_tag = None
            return
        self.kept.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        if self._drop_tag is None and tag not in _CHROME_ELEMENTS:
            self.kept.append(self.get_starttag_text() or f"<{tag}/>")

    def _emit(self, text: str) -> None:
        if self._drop_tag is None:
            self.kept.append(text)

    def handle_data(self, data):
        # A bare "&" is an ampersand the page meant literally ("AT&T"). It needs
        # the same extra level, or the second decode eats it.
        self._emit(data.replace("&", "&amp;"))

    # Entities and bare ampersands are re-emitted with ONE EXTRA level of
    # escaping, which is what makes an escaping lesson survive. See
    # `_COMPENSATES_FOR_A_SECOND_DECODE`.
    def handle_entityref(self, name):
        self._emit(f"&amp;{name};")

    def handle_charref(self, name):
        self._emit(f"&amp;#{name};")

    def handle_comment(self, data):
        self._emit(f"<!--{data}-->")

    def handle_decl(self, decl):
        self._emit(f"<!{decl}>")

    def handle_pi(self, data):
        self._emit(f"<?{data}>")


def strip_html_chrome(data: bytes) -> bytes:
    """Remove the navigation, sidebars and footer before PyMuPDF lays the page out.

    Bytes in, bytes out, decoded with `surrogateescape` so the round trip is
    lossless whatever the page's real encoding turns out to be.
    """
    try:
        text = data.decode("utf-8", "surrogateescape")
        parser = _DropChrome()
        parser.feed(text)
        parser.close()
        if parser.unterminated:
            # An unclosed <nav>/<aside>/<footer>/<header> ate the tail. Keeping
            # the chrome is much cheaper than losing the article.
            return data
        kept = "".join(parser.kept)
    except Exception:
        # A parser failure must never lose a document. Whatever the page is, the
        # unfiltered bytes are what we had before this function existed.
        return data
    if len(kept) < _MIN_KEPT_SHARE * len(text):
        return data
    return kept.encode("utf-8", "surrogateescape")


def read_document(path: str) -> list[tuple[int, str]]:
    """Return [(page_number_1_indexed, text)] skipping pages with no text.

    One function for every paginated format, because everything downstream —
    chunking, page refs, the verbatim-quote check — only ever wanted that
    shape.
    """
    if Path(path).suffix.lower() in _MARKUP_SUFFIXES:
        stream = strip_html_chrome(Path(path).read_bytes())
        doc = fitz.open(stream=stream, filetype="html")
        doc.layout(rect=_MARKUP_PAGE)
    else:
        doc = fitz.open(path)
    out: list[tuple[int, str]] = []
    with doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                out.append((i, text))
    return out


#: The old name. Kept because it says what almost every caller passes.
read_pdf = read_document


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()
