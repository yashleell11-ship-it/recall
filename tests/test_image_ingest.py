import hashlib
import io
import json

import fitz
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from recall.api import upload_routes
from recall.api.deps import get_current_user
from recall.config import load_config
from recall.db import connect, init_db
from recall.ingest.image import (
    MAX_LONG_EDGE,
    SPARSE_WARNING,
    OcrUnavailable,
    extract_text_from_image,
    sparse_text_warning,
)
from recall.llm.fake import FakeLlmClient

CFG = load_config({"DEEPSEEK_API_KEY": "sk-test"})

# Long enough to be plausible for the image sizes used below, so the sparse
# warning only fires in the test that asks for it.
DENSE_TEXT = ("Pointers store memory addresses in C. A pointer variable holds "
              "the address of another object.")


class FakeOcr:
    """Stands in for Tesseract. No test may need the binary."""

    def __init__(self, text: str = DENSE_TEXT):
        self.text = text
        self.calls: list[str] = []

    def __call__(self, path: str) -> str:
        self.calls.append(path)
        return self.text


def orthogonal_embed(texts):
    return np.eye(max(len(texts), 1))[: len(texts)]


def accept_all(question, answer, quote):
    return [
        json.dumps({"cards": [{"kind": "qa", "question": question, "answer": answer}]}),
        json.dumps({"supported": True, "quote": quote}),
        json.dumps({"answer": "no idea", "confident": False}),
    ]


def image_bytes(size=(1200, 900), fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (210, 210, 210)).save(buf, format=fmt)
    return buf.getvalue()


def pdf_bytes(pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def make_jpg(path, size=(800, 600), orientation=None) -> str:
    kwargs = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation  # EXIF Orientation
        kwargs["exif"] = exif
    Image.new("RGB", size, (240, 240, 240)).save(str(path), **kwargs)
    return str(path)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "upload.db")


@pytest.fixture
def ocr():
    return FakeOcr()


@pytest.fixture
def llm():
    # No queued responses: this client raises the moment anything calls it.
    return FakeLlmClient([])


@pytest.fixture
def client(db_path, tmp_path, monkeypatch, ocr, llm):
    conn = connect(db_path)
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    conn.execute("INSERT INTO settings (user_id) VALUES (1)")
    conn.execute("INSERT INTO topics (id,user_id,code,label) "
                 "VALUES (1,1,'CSE111','Programming')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("RECALL_UPLOAD_DIR", str(tmp_path / "uploads"))

    app = FastAPI()
    app.include_router(upload_routes.router)

    def override_conn():
        c = connect(db_path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[upload_routes.get_conn] = override_conn
    app.dependency_overrides[upload_routes.get_config] = lambda: CFG
    app.dependency_overrides[upload_routes.get_llm_client] = lambda: llm
    app.dependency_overrides[upload_routes.get_embed] = lambda: orthogonal_embed
    app.dependency_overrides[upload_routes.get_ocr] = lambda: ocr
    app.dependency_overrides[get_current_user] = lambda: 1
    return TestClient(app)


def upload(client, name, data, topic="CSE111"):
    return client.post("/api/sources/upload",
                       files={"file": (name, data, "application/octet-stream")},
                       data={"topic_code": topic})


def query(db_path, sql, args=()):
    conn = connect(db_path)
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


# --- routing to the right extractor -----------------------------------------

def test_png_is_read_by_ocr_and_becomes_chunks(client, db_path, ocr):
    body = upload(client, "notes.png", image_bytes()).json()
    assert body["kind"] == "image"
    assert body["chunks"] == 1
    assert body["text_chars"] == len(DENSE_TEXT)
    assert len(ocr.calls) == 1
    chunks = query(db_path, "SELECT text, page_ref FROM chunks")
    assert chunks[0]["text"] == DENSE_TEXT


@pytest.mark.parametrize("name", ["photo.jpg", "photo.jpeg", "photo.webp"])
def test_every_image_extension_reaches_the_ocr_extractor(client, ocr, name):
    fmt = "WEBP" if name.endswith(".webp") else "JPEG"
    body = upload(client, name, image_bytes(fmt=fmt)).json()
    assert body["kind"] == "image"
    assert ocr.calls, f"{name} should have gone through OCR"


def test_pdf_is_read_by_the_pdf_extractor_not_ocr(client, db_path, ocr):
    body = upload(client, "lecture.pdf",
                  pdf_bytes(["Pointers store addresses.", "Arrays decay."])).json()
    assert body["kind"] == "pdf"
    assert ocr.calls == []
    assert body["chunks"] >= 1


def test_text_file_needs_no_ocr_at_all(client, db_path):
    def refuse(path):
        raise AssertionError("a text file must never be sent to OCR")

    client.app.dependency_overrides[upload_routes.get_ocr] = lambda: refuse
    body = upload(client, "notes.txt", b"Recursion needs a base case.").json()
    assert body["kind"] == "text"
    assert body["text_chars"] == len("Recursion needs a base case.")
    assert query(db_path, "SELECT text FROM chunks")[0]["text"] == \
        "Recursion needs a base case."


def test_markdown_is_read_as_text(client, ocr):
    body = upload(client, "notes.md", b"# Trees\n\nA binary tree has two children.")
    assert body.status_code == 200
    assert body.json()["kind"] == "text"
    assert ocr.calls == []


# --- rejection ---------------------------------------------------------------

def test_unsupported_extension_is_rejected_naming_what_is_allowed(client):
    resp = upload(client, "slides.docx", b"whatever")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    for ext in upload_routes.ALLOWED_EXTENSIONS:
        assert ext in detail


def test_file_with_no_extension_is_rejected(client):
    assert upload(client, "scan", b"whatever").status_code == 422


@pytest.mark.parametrize("name", ["IMG_0431.PNG", "Scan.PDF", "Notes.TXT"])
def test_uppercase_extensions_are_accepted(client, name):
    """Phones and scanner apps produce these. Case is not a file format."""
    payload = pdf_bytes(["Some text."]) if name.endswith(".PDF") else (
        image_bytes() if name.endswith(".PNG") else b"Some text.")
    assert upload(client, name, payload).status_code == 200


def test_the_stored_filename_is_a_name_not_a_path(client, db_path):
    upload(client, "../../etc/notes.txt", b"Recursion needs a base case.")
    assert query(db_path, "SELECT filename FROM sources")[0]["filename"] == "notes.txt"


def test_oversize_upload_is_rejected(client, monkeypatch):
    assert upload_routes.MAX_UPLOAD_BYTES == 25 * 1024 * 1024
    monkeypatch.setattr(upload_routes, "MAX_UPLOAD_BYTES", 1024)
    resp = upload(client, "big.txt", b"x" * 2048)
    assert resp.status_code == 413
    assert "larger than" in resp.json()["detail"]


def test_unknown_topic_is_rejected(client):
    resp = upload(client, "notes.png", image_bytes(), topic="NOPE")
    assert resp.status_code == 422
    assert "NOPE" in resp.json()["detail"]


def test_bytes_that_are_not_an_image_are_rejected(client):
    # Real loader, fake OCR backend: decoding fails long before Tesseract.
    client.app.dependency_overrides[upload_routes.get_ocr] = \
        lambda: (lambda path: extract_text_from_image(path, ocr=lambda img: "text"))
    resp = upload(client, "notes.png", b"this is not a PNG")
    assert resp.status_code == 422
    assert "notes.png" in resp.json()["detail"]


def test_missing_ocr_binary_is_reported_as_a_server_problem(client):
    def unavailable(path):
        raise OcrUnavailable("tesseract is not installed on this machine")

    client.app.dependency_overrides[upload_routes.get_ocr] = lambda: unavailable
    resp = upload(client, "notes.png", image_bytes())
    assert resp.status_code == 503
    assert "tesseract" in resp.json()["detail"]


# --- dedupe, chunks, warnings ------------------------------------------------

def test_the_same_file_uploaded_twice_creates_one_source(client, db_path):
    data = image_bytes()
    first = upload(client, "board.png", data).json()
    second = upload(client, "board.png", data).json()
    assert second["source_id"] == first["source_id"]
    assert len(query(db_path, "SELECT id FROM sources")) == 1
    assert len(query(db_path, "SELECT id FROM chunks")) == first["chunks"]
    assert "uploaded before" in second["warning"]


def test_a_concurrent_second_upload_still_creates_one_source(client, db_path,
                                                             monkeypatch):
    """Two uploads in flight at once — a double-tapped Upload button.

    Both requests can pass the dedupe SELECT before either one INSERTs, so the
    UNIQUE(user_id, sha256) constraint is what actually holds the line. The
    losing request must return the winner's source, not a 500.
    """
    data = image_bytes()
    sha = hashlib.sha256(data).hexdigest()
    real_store = upload_routes._store

    def store_then_lose_the_race(payload, digest, ext):
        # A different connection commits the same file mid-request, which is
        # what a second in-flight upload does. Everything else stays real,
        # including the recovery lookup after the constraint fires.
        other = connect(db_path)
        other.execute(
            "INSERT INTO sources (user_id, topic_id, filename, kind, sha256,"
            " added_at) VALUES (1, 1, 'board.png', 'image', ?, '2026-01-01T00:00:00Z')",
            (digest,),
        )
        other.commit()
        other.close()
        return real_store(payload, digest, ext)

    monkeypatch.setattr(upload_routes, "_store", store_then_lose_the_race)
    resp = upload(client, "board.png", data)

    assert resp.status_code == 200
    sources = query(db_path, "SELECT id, sha256 FROM sources")
    assert len(sources) == 1
    assert sources[0]["sha256"] == sha
    assert resp.json()["source_id"] == sources[0]["id"]


def test_a_different_photo_is_a_different_source(client, db_path):
    upload(client, "a.png", image_bytes(size=(1200, 900)))
    upload(client, "b.png", image_bytes(size=(1201, 900)))
    assert len(query(db_path, "SELECT id FROM sources")) == 2


def test_chunks_are_created_with_page_refs(client, db_path):
    upload(client, "notes.png", image_bytes())
    upload(client, "lecture.pdf", pdf_bytes(["Page one text.", "Page two text."]))
    refs = [r["page_ref"] for r in query(db_path, "SELECT page_ref FROM chunks")]
    assert refs and all(ref.startswith("p1") for ref in refs)
    pdf_refs = [r["page_ref"] for r in query(
        db_path,
        "SELECT page_ref FROM chunks WHERE source_id ="
        " (SELECT id FROM sources WHERE kind = 'pdf')")]
    assert pdf_refs == ["p1-p2"]


def test_sparse_text_for_a_large_image_produces_a_warning(client):
    client.app.dependency_overrides[upload_routes.get_ocr] = \
        lambda: FakeOcr("Ax Bq")
    body = upload(client, "whiteboard.png", image_bytes(size=(2000, 2000))).json()
    assert SPARSE_WARNING in body["warning"]


def test_plausible_text_produces_no_warning(client):
    body = upload(client, "slide.png", image_bytes(size=(1200, 900))).json()
    assert body["warning"] is None


def test_pdf_with_no_selectable_text_says_so(client):
    body = upload(client, "scan.pdf", pdf_bytes([" "])).json()
    assert body["chunks"] == 0
    assert "no text found" in body["warning"]


def test_upload_makes_zero_llm_calls(client, llm):
    def no_key():
        raise AssertionError("upload must work before any API key exists")

    # An empty double blows up on any call at all. Proven on a throwaway rather
    # than on `llm` itself, whose call log is the assertion below.
    with pytest.raises(AssertionError):
        FakeLlmClient([]).complete_json("system", "user")

    client.app.dependency_overrides[upload_routes.get_config] = no_key
    assert upload(client, "notes.png", image_bytes()).status_code == 200
    assert upload(client, "notes.pdf", pdf_bytes(["Some text."])).status_code == 200
    assert upload(client, "notes.txt", b"Some text.").status_code == 200
    assert llm.calls == []


# --- image preprocessing -----------------------------------------------------

def test_exif_rotation_is_applied_before_ocr(tmp_path):
    seen = {}

    def ocr(image):
        seen["size"] = image.size
        return "text"

    # Orientation 6 means "rotate 90° clockwise to view", the usual portrait
    # phone photo. Without the transpose the OCR reads a sideways page.
    extract_text_from_image(make_jpg(tmp_path / "r.jpg", (400, 200), orientation=6),
                            ocr=ocr)
    assert seen["size"] == (200, 400)


def test_large_image_is_downscaled_before_ocr(tmp_path):
    seen = {}

    def ocr(image):
        seen["size"] = image.size
        return ""

    extract_text_from_image(make_jpg(tmp_path / "big.jpg", (6000, 3000)), ocr=ocr)
    assert max(seen["size"]) == MAX_LONG_EDGE
    assert seen["size"] == (3000, 1500)


def test_small_image_is_not_upscaled(tmp_path):
    seen = {}

    def ocr(image):
        seen["size"] = image.size
        return ""

    extract_text_from_image(make_jpg(tmp_path / "small.jpg", (800, 600)), ocr=ocr)
    assert seen["size"] == (800, 600)


def test_extracted_text_is_stripped(tmp_path):
    text = extract_text_from_image(make_jpg(tmp_path / "s.jpg"),
                                   ocr=lambda image: "\n  hello \n\n")
    assert text == "hello"


def test_pytesseract_is_the_default_backend(tmp_path, monkeypatch):
    import pytesseract

    monkeypatch.setattr(pytesseract, "image_to_string", lambda image: " ocr text ")
    assert extract_text_from_image(make_jpg(tmp_path / "d.jpg")) == "ocr text"


def test_missing_tesseract_binary_raises_a_clear_error(tmp_path, monkeypatch):
    import pytesseract

    def boom(image):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_string", boom)
    with pytest.raises(OcrUnavailable) as exc:
        extract_text_from_image(make_jpg(tmp_path / "n.jpg"))
    assert "tesseract" in str(exc.value)


# --- the sparse-text judgement itself ----------------------------------------

def test_warning_scales_with_image_area():
    # The same handful of characters is fine for a screenshot and implausible
    # for a 12 MP photo.
    assert sparse_text_warning("x" * 45, 100_000) is None
    assert sparse_text_warning("x" * 45, 12_000_000) is not None


def test_warning_names_handwriting_as_the_likely_cause():
    warning = sparse_text_warning("Ax Bq", 12_000_000)
    assert SPARSE_WARNING in warning
    assert "12.0 MP" in warning


def test_no_warning_when_text_matches_the_image_size():
    assert sparse_text_warning("x" * 500, 4_000_000) is None


def test_empty_text_always_warns():
    assert sparse_text_warning("   ", 1000) is not None


# --- generation over an uploaded source --------------------------------------

def generating_client(client, question, answer, quote):
    client.app.dependency_overrides[upload_routes.get_llm_client] = \
        lambda: FakeLlmClient(accept_all(question, answer, quote))
    return client


def test_generate_turns_an_uploaded_photo_into_active_cards(client, db_path):
    source_id = upload(client, "notes.png", image_bytes()).json()["source_id"]
    generating_client(client, "What do pointers store in C?", "memory addresses",
                      "Pointers store memory addresses in C.")
    body = client.post(f"/api/sources/{source_id}/generate").json()
    assert body["accepted"] == 1
    assert body["stopped_early"] is False
    assert body["cost_usd"] > 0
    card = query(db_path, "SELECT c.state, ch.page_ref FROM cards c"
                          " JOIN chunks ch ON ch.id = c.chunk_id")[0]
    assert card["state"] == "active"
    assert card["page_ref"] == "p1"


def test_generate_records_the_run(client, db_path):
    source_id = upload(client, "notes.png", image_bytes()).json()["source_id"]
    generating_client(client, "What do pointers store in C?", "memory addresses",
                      "Pointers store memory addresses in C.")
    client.post(f"/api/sources/{source_id}/generate")
    run = query(db_path, "SELECT prompt_tokens, cards_accepted FROM gen_runs")[0]
    assert run["prompt_tokens"] > 0
    assert run["cards_accepted"] == 1


def test_generating_twice_does_not_pay_twice(client, db_path):
    source_id = upload(client, "notes.png", image_bytes()).json()["source_id"]
    generating_client(client, "What do pointers store in C?", "memory addresses",
                      "Pointers store memory addresses in C.")
    client.post(f"/api/sources/{source_id}/generate")

    # An empty client raises if anything calls it: the second run must not.
    client.app.dependency_overrides[upload_routes.get_llm_client] = \
        lambda: FakeLlmClient([])
    second = client.post(f"/api/sources/{source_id}/generate").json()
    assert second["accepted"] == 0
    assert len(query(db_path, "SELECT id FROM cards")) == 1
    assert len(query(db_path, "SELECT id FROM gen_runs")) == 1


def test_generate_on_an_unknown_source_is_404(client):
    resp = client.post("/api/sources/999/generate")
    assert resp.status_code == 404
    assert "999" in resp.json()["detail"]


def test_generate_without_an_api_key_says_so(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    source_id = upload(client, "notes.png", image_bytes()).json()["source_id"]
    client.app.dependency_overrides.pop(upload_routes.get_config)
    resp = client.post(f"/api/sources/{source_id}/generate")
    assert resp.status_code == 503
    assert "DEEPSEEK_API_KEY" in resp.json()["detail"]


# --- resuming a run that stopped on the cost cap -------------------------------

LONG_TEXT = " ".join(
    f"Sentence number {i} explains a concept about pointers and memory."
    for i in range(120)
)


def test_resuming_a_stopped_run_keeps_one_gen_run_per_source(client, db_path):
    """A source that hit the cost cap is generated again — one row, not two.

    /api/sources LEFT JOINs gen_runs without aggregating, so a second row for
    the same source lists that source twice, each showing half the real totals.
    """
    source_id = upload(client, "big.txt", LONG_TEXT.encode()).json()["source_id"]
    assert len(query(db_path, "SELECT id FROM chunks")) >= 2

    # A cap this small stops after the first chunk, leaving the rest ungenerated.
    capped = load_config({"DEEPSEEK_API_KEY": "k", "RECALL_MAX_COST_USD": "0.000001"})
    client.app.dependency_overrides[upload_routes.get_config] = lambda: capped
    responses = accept_all("What does a pointer store?", "an address",
                           "Sentence number 0 explains a concept about pointers")
    client.app.dependency_overrides[upload_routes.get_llm_client] = \
        lambda: FakeLlmClient(responses * 40)

    first = client.post(f"/api/sources/{source_id}/generate").json()
    assert first["stopped_early"] is True
    assert query(db_path, "SELECT COUNT(*) AS n FROM chunks"
                          " WHERE generated_at IS NULL")[0]["n"] > 0

    client.app.dependency_overrides[upload_routes.get_llm_client] = \
        lambda: FakeLlmClient(responses * 40)
    second = client.post(f"/api/sources/{source_id}/generate").json()

    runs = query(db_path, "SELECT prompt_tokens, cost_estimate, cards_accepted,"
                          " cards_rejected FROM gen_runs")
    assert len(runs) == 1, "a resumed run must not add a second gen_run row"
    # The one row carries both passes, so the sources page shows the true bill.
    cards = query(db_path, "SELECT state FROM cards")
    assert runs[0]["cards_accepted"] + runs[0]["cards_rejected"] == len(cards)
    # abs, not rel: each response rounds its own cost to 6 places.
    assert runs[0]["cost_estimate"] == pytest.approx(
        first["cost_usd"] + second["cost_usd"], abs=2e-6)
    assert runs[0]["cost_estimate"] > first["cost_usd"]


def test_a_file_that_cannot_be_read_leaves_nothing_on_disk(client, tmp_path):
    """A 25 MB photo that fails to decode must not sit in uploads/ forever."""
    def boom(path):
        raise ValueError("not a picture")

    client.app.dependency_overrides[upload_routes.get_ocr] = lambda: boom
    assert upload(client, "bad.png", image_bytes()).status_code == 422
    uploads = tmp_path / "uploads"
    left = list(uploads.iterdir()) if uploads.exists() else []
    assert left == [], f"unreadable upload left behind: {left}"


def test_a_readable_file_is_kept_on_disk(client, tmp_path):
    """The stored original is how a vision API re-reads the photo later."""
    upload(client, "notes.png", image_bytes())
    assert len(list((tmp_path / "uploads").iterdir())) == 1
