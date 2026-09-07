import hashlib
from pathlib import Path

import fitz

#: Everything PyMuPDF opens and paginates for us. HTML is here because the
#: best free material for a web-programming course is MDN and the specs, and
#: those are pages, not PDFs — PyMuPDF renders one into laid-out pages with
#: script and style already dropped, so no HTML parser is needed and no new
#: dependency comes with it. EPUB and XPS come along for free.
DOCUMENT_SUFFIXES = frozenset({".pdf", ".html", ".htm", ".xhtml", ".epub",
                               ".xps", ".fb2", ".mobi"})


def document_kind(path: str) -> str:
    """The `sources.kind` to record — the suffix, without its dot."""
    return Path(path).suffix.lower().lstrip(".") or "unknown"


def read_document(path: str) -> list[tuple[int, str]]:
    """Return [(page_number_1_indexed, text)] skipping pages with no text.

    One function for every paginated format, because everything downstream —
    chunking, page refs, the verbatim-quote check — only ever wanted that
    shape.
    """
    out: list[tuple[int, str]] = []
    with fitz.open(path) as doc:
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
