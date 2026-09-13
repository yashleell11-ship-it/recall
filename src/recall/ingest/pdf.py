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


def document_kind(path: str) -> str:
    """The `sources.kind` to record — the suffix, without its dot."""
    return Path(path).suffix.lower().lstrip(".") or "unknown"


#: The formats PyMuPDF lays out from markup, and so the ones whose chrome is
#: still in the bytes when we get them.
_MARKUP_SUFFIXES = frozenset({".html", ".htm", ".xhtml"})

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

#: A last-resort net for a parse that went badly wrong. Deliberately very low:
#: the real hazard is detected exactly (see `unterminated`), and a share-based
#: guard set anywhere near a sensible-looking value silently disables the strip
#: on the pages where chrome is most of the markup — which is most of them.
_MIN_KEPT_SHARE = 0.05


class _DropChrome(HTMLParser):
    """Re-emit HTML with every nav/aside/footer/header subtree removed.

    `convert_charrefs=False` is load-bearing, not a detail. With the default,
    `handle_data` receives DECODED text and re-emitting it would silently undo
    one level of escaping — which is the bug that made an MDN page teach that the
    character reference for "<" is "<". Entities are passed through verbatim.
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
        self._emit(data)

    def handle_entityref(self, name):
        self._emit(f"&{name};")

    def handle_charref(self, name):
        self._emit(f"&#{name};")

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
