"""Upload routes — how notes get in from a phone.

Upload extracts text and writes chunks, nothing more. It never calls the paid
API, so it is fast, free, and works before any key exists. Generation is a
separate, explicit endpoint because it costs money and takes time.
"""

import hashlib
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from recall.config import Config, load_config
from recall.generate.generate import Candidate, generate_cards
from recall.ingest.chunk import Chunk, chunk_pages
from recall.ingest.image import (
    OcrUnavailable,
    extract_text_from_image,
    image_pixel_count,
    sparse_text_warning,
)
from recall.ingest.pdf import read_pdf

# Private helpers imported rather than copied: the card-insert shape and the
# cost formula must not drift between the CLI path and the upload path.
from recall.pipeline import IngestResult, _cost, _insert_card, _now, assign_arm
from recall.verify.dedupe import dedupe, embed_texts
from recall.verify.heuristics import check_answerable, check_atomic
from recall.verify.judges import check_closed_book, check_grounded

USER_ID = 1  # single user for now; every query already filters by it

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
TEXT_EXTENSIONS = frozenset({".txt", ".md"})
ALLOWED_EXTENSIONS = frozenset({".pdf"}) | IMAGE_EXTENSIONS | TEXT_EXTENSIONS
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

router = APIRouter()


def get_conn():
    # Imported inside the function: app.py includes this router, so importing
    # app.py at module level here would be a circular import.
    from recall.api.app import get_conn as app_get_conn

    yield from app_get_conn()


def get_config() -> Config:
    try:
        return load_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_llm_client(cfg: Config = Depends(get_config)):
    from recall.llm.client import DeepSeekClient

    return DeepSeekClient(cfg)


def get_embed():
    """Injectable so tests never load the embedding model."""
    return embed_texts


def get_ocr():
    """Injectable so tests never need the tesseract binary."""
    return extract_text_from_image


def allowed_list() -> str:
    return ", ".join(sorted(ALLOWED_EXTENSIONS))


def file_kind(ext: str) -> str:
    if ext == ".pdf":
        return "pdf"
    return "image" if ext in IMAGE_EXTENSIONS else "text"


def extract_pages(path: str, ext: str,
                  ocr=extract_text_from_image) -> list[tuple[int, str]]:
    """Route a file to its extractor.

    Every extractor returns the PDF shape, [(page_number, text)], so chunking,
    page refs and generation work on an uploaded photo with no special-casing.
    An image and a text file are one page: `p1` is a real, honest page ref.
    """
    if ext == ".pdf":
        return read_pdf(path)
    if ext in IMAGE_EXTENSIONS:
        text = ocr(path)
    else:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    return [(1, text.strip())] if text.strip() else []


def upload_dir() -> Path:
    return Path(os.environ.get("RECALL_UPLOAD_DIR", "uploads"))


def _store(data: bytes, sha: str, ext: str) -> Path:
    """Keep the original file, named by content hash.

    Worth the disk: when OCR is replaced by a vision API the photos can be read
    again without asking for them a second time.
    """
    directory = upload_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{sha}{ext}"
    path.write_bytes(data)
    return path


def _read_capped(file: UploadFile) -> bytes:
    # One byte past the cap is enough to know it is oversize, so an enormous
    # upload is refused without reading all of it.
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    return data


def _topic_id(conn, topic_code: str) -> int:
    row = conn.execute(
        "SELECT id FROM topics WHERE user_id = ? AND code = ?", (USER_ID, topic_code)
    ).fetchone()
    if row is None:
        known = [r["code"] for r in conn.execute(
            "SELECT code FROM topics WHERE user_id = ? ORDER BY code", (USER_ID,)
        ).fetchall()]
        raise HTTPException(
            status_code=422,
            detail=f"unknown topic '{topic_code}'; known topics: "
                   f"{', '.join(known) or 'none yet'}",
        )
    return row["id"]


def _discard(stored: Path, conn, sha: str) -> None:
    """Drop stored bytes that nothing will ever reference.

    A failed extraction writes no source row and no chunks, so the file left
    behind is unreachable — up to 25 MB of it per attempt, and a phone retrying
    a photo that will not OCR repeats the attempt. Guarded by the dedupe lookup
    so a concurrent upload of the same file that *did* succeed keeps its copy.
    """
    if _existing_source(conn, sha) is None:
        stored.unlink(missing_ok=True)


def _existing_source(conn, sha: str) -> dict | None:
    row = conn.execute(
        "SELECT id, filename, kind FROM sources WHERE user_id = ? AND sha256 = ?",
        (USER_ID, sha),
    ).fetchone()
    if row is None:
        return None
    stats = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(text)), 0) AS chars"
        " FROM chunks WHERE source_id = ?", (row["id"],)
    ).fetchone()
    return {
        "source_id": row["id"],
        "filename": row["filename"],
        "kind": row["kind"],
        "chunks": stats["n"],
        "text_chars": stats["chars"],
        "warning": "this file was uploaded before; the existing source was kept",
    }


@router.post("/api/sources/upload")
def upload_source(file: UploadFile = File(...), topic_code: str = Form(...),
                  conn=Depends(get_conn), ocr=Depends(get_ocr)):
    filename = os.path.basename(file.filename or "").strip()
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"cannot read '{filename or 'this file'}'. Allowed: "
                   f"{allowed_list()}, up to "
                   f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    data = _read_capped(file)
    topic_id = _topic_id(conn, topic_code)

    # Same dedupe key the pipeline uses, so re-uploading a photo the phone
    # already sent does not create a second source.
    sha = hashlib.sha256(data).hexdigest()
    existing = _existing_source(conn, sha)
    if existing is not None:
        return existing

    stored = _store(data, sha, ext)
    try:
        pages = extract_pages(str(stored), ext, ocr=ocr)
    except OcrUnavailable as exc:
        _discard(stored, conn, sha)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError,
            ValueError, RuntimeError) as exc:
        _discard(stored, conn, sha)
        raise HTTPException(
            status_code=422,
            detail=f"could not read '{filename}' as a {file_kind(ext)} file: {exc}",
        ) from exc

    text = "\n".join(page_text for _, page_text in pages)
    warning = None
    if ext in IMAGE_EXTENSIONS:
        warning = sparse_text_warning(text, image_pixel_count(str(stored)))
    elif not pages:
        warning = ("no text found in this file"
                   + (" — a scanned PDF has no selectable text, so photograph "
                      "the pages and upload those instead" if ext == ".pdf" else ""))

    try:
        cur = conn.execute(
            "INSERT INTO sources (user_id, topic_id, filename, kind, sha256, added_at)"
            " VALUES (?,?,?,?,?,?)",
            (USER_ID, topic_id, filename, file_kind(ext), sha, _now()),
        )
    except sqlite3.IntegrityError:
        # A concurrent upload of the same file won the race between the check
        # above and this insert. A phone double-tapping Upload does exactly
        # that, and the promise is the same either way: one photo, one source.
        conn.rollback()
        duplicate = _existing_source(conn, sha)
        if duplicate is None:
            raise
        return duplicate
    source_id = cur.lastrowid
    chunks = chunk_pages(pages)
    for ch in chunks:
        conn.execute(
            "INSERT INTO chunks (source_id, ordinal, text, page_ref) VALUES (?,?,?,?)",
            (source_id, ch.ordinal, ch.text, ch.page_ref),
        )
    conn.commit()

    return {"source_id": source_id, "filename": filename, "kind": file_kind(ext),
            "chunks": len(chunks), "text_chars": len(text), "warning": warning}


def generate_for_source(conn, cfg: Config, client, *, source_id: int, topic_id: int,
                        embed=embed_texts) -> IngestResult:
    """Run the verification pipeline over one already-uploaded source.

    The gate order, the cost cap and the per-chunk commit are
    pipeline.ingest_source's, and its helpers are imported rather than copied.
    Only the chunk loop is repeated here: that function starts from a file path
    and returns early for a source it has already seen, which is every source
    that arrived through upload.
    """
    accepted = rejected = 0
    prompt_tokens = completion_tokens = 0
    stopped_early = False

    rows = conn.execute(
        "SELECT id, ordinal, text, page_ref FROM chunks"
        " WHERE source_id = ? AND generated_at IS NULL ORDER BY ordinal",
        (source_id,),
    ).fetchall()

    for row in rows:
        if _cost(cfg, prompt_tokens, completion_tokens) >= cfg.max_cost_usd_per_source:
            stopped_early = True
            break

        chunk = Chunk(row["ordinal"], row["text"], row["page_ref"])
        candidates, pt, ct = generate_cards(client, chunk)
        prompt_tokens += pt
        completion_tokens += ct

        survivors: list[Candidate] = []
        for c in candidates:
            reason = check_answerable(c) or check_atomic(c)
            if reason is None:
                reason, pt, ct = check_grounded(client, chunk, c)
                prompt_tokens += pt
                completion_tokens += ct
            if reason is None:
                reason, pt, ct = check_closed_book(client, c)
                prompt_tokens += pt
                completion_tokens += ct
            if reason is None:
                survivors.append(c)
            else:
                _insert_card(conn, row["id"], topic_id, c, "rejected", reason,
                             "learned")
                rejected += 1

        kept, dropped = dedupe(survivors, embed=embed)
        for c, reason in dropped:
            _insert_card(conn, row["id"], topic_id, c, "rejected", reason, "learned")
            rejected += 1
        for c in kept:
            _insert_card(conn, row["id"], topic_id, c, "pending", None,
                         assign_arm(accepted))
            accepted += 1

        conn.execute("UPDATE chunks SET generated_at = ? WHERE id = ?",
                     (_now(), row["id"]))
        conn.commit()

    cost = _cost(cfg, prompt_tokens, completion_tokens)
    # Exactly one gen_run row per source, accumulated across resumed runs.
    # /api/sources LEFT JOINs gen_runs without aggregating, so a second row
    # lists the source twice with half its totals each — and a resume is not
    # hypothetical: hitting max_cost_usd_per_source leaves chunks ungenerated
    # and the whole point of `stopped_early` is that Generate is pressed again.
    # No row at all when there was nothing to generate: that is not a run.
    if rows:
        existing = conn.execute(
            "SELECT id FROM gen_runs WHERE source_id = ?", (source_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO gen_runs (source_id, ran_at, model, prompt_tokens,"
                " completion_tokens, cost_estimate, cards_accepted, cards_rejected)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (source_id, _now(), cfg.model, prompt_tokens, completion_tokens,
                 cost, accepted, rejected),
            )
        else:
            conn.execute(
                "UPDATE gen_runs SET ran_at = ?, model = ?,"
                " prompt_tokens = prompt_tokens + ?,"
                " completion_tokens = completion_tokens + ?,"
                " cost_estimate = cost_estimate + ?,"
                " cards_accepted = cards_accepted + ?,"
                " cards_rejected = cards_rejected + ? WHERE id = ?",
                (_now(), cfg.model, prompt_tokens, completion_tokens, cost,
                 accepted, rejected, existing["id"]),
            )
        conn.commit()
    return IngestResult(source_id, accepted, rejected, cost, stopped_early)


@router.post("/api/sources/{source_id}/generate")
def generate_source(source_id: int, conn=Depends(get_conn),
                    cfg: Config = Depends(get_config),
                    client=Depends(get_llm_client), embed=Depends(get_embed)):
    row = conn.execute(
        "SELECT id, topic_id FROM sources WHERE id = ? AND user_id = ?",
        (source_id, USER_ID),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no source {source_id}")

    result = generate_for_source(conn, cfg, client, source_id=row["id"],
                                 topic_id=row["topic_id"], embed=embed)
    return {"accepted": result.accepted, "rejected": result.rejected,
            "cost_usd": round(result.cost_usd, 6),
            "stopped_early": result.stopped_early}
