import fitz

from recall.ingest.pdf import file_sha256, read_pdf


def _make_pdf(path, pages):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_read_pdf_returns_page_numbers_and_text(tmp_path):
    p = tmp_path / "a.pdf"
    _make_pdf(p, ["Hello world", "Second page"])
    pages = read_pdf(str(p))
    assert [n for n, _ in pages] == [1, 2]
    assert "Hello world" in pages[0][1]


def test_read_pdf_skips_blank_pages(tmp_path):
    p = tmp_path / "b.pdf"
    _make_pdf(p, ["Content here", "   ", "More content"])
    pages = read_pdf(str(p))
    assert [n for n, _ in pages] == [1, 3]


def test_sha256_is_stable_and_differs(tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    _make_pdf(a, ["same"])
    _make_pdf(b, ["different"])
    assert file_sha256(str(a)) == file_sha256(str(a))
    assert file_sha256(str(a)) != file_sha256(str(b))
