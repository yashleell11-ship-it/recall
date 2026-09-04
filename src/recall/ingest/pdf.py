import hashlib

import fitz


def read_pdf(path: str) -> list[tuple[int, str]]:
    """Return [(page_number_1_indexed, text)] skipping pages with no text."""
    out: list[tuple[int, str]] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                out.append((i, text))
    return out


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()
