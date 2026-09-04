# Recall Phase 1 — Generation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a course PDF into verified, deduplicated, traceable flashcards stored in SQLite and exportable to Anki, with API spend measured and capped.

**Architecture:** A pure-Python library plus a CLI. Every network call lives in exactly one module (`llm/client.py`) behind an injectable interface, so the entire pipeline is testable offline with zero API spend. Ingest and chunking are pure functions; verification gates are a mix of free heuristics and paid LLM judges, ordered cheapest-first so bad cards die before they cost money.

**Tech Stack:** Python 3.12 (via `uv`), `sqlite3` (stdlib, no ORM), `pymupdf`, `httpx`, `fastembed` (CPU ONNX embeddings), `genanki`, `pytest`.

## Global Constraints

- **Python 3.12 exactly**, installed via `uv`. The system Python is 3.14, for which PyTorch (needed in Phase 3) publishes no wheels.
- **No GPU use of any kind.** Owner directive. Embeddings run on CPU via ONNX.
- **No ORM in Phase 1.** Raw `sqlite3` and `schema.sql`. Add SQLAlchemy later only if it earns its place.
- **All network calls confined to `src/recall/llm/client.py`.** No other module may import `httpx`.
- **No test may make a network call.** Tests inject `FakeLlmClient` or `httpx.MockTransport`. A test suite that costs money to run will not be run.
- **`DEEPSEEK_API_KEY` comes from the environment only.** Never committed, never logged, never printed in an error message.
- **Every card carries `chunk_id`.** A question that cannot be traced to a page is a question that cannot be trusted.
- **Hard cost cap per source**, enforced in the pipeline loop, default $2.00.
- SQLite runs in WAL mode.
- Topic codes for this project: `MATHS`, `CSE111`, `INT108`, `INT335`, `HTML`.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | deps, pytest config |
| `.env.example` | documents required env vars; the real `.env` is gitignored |
| `src/recall/config.py` | env → frozen `Config`; fails loudly on missing key |
| `src/recall/schema.sql` | full schema, including Phase 2/3 tables so no migration churn |
| `src/recall/db.py` | connection, `init_db`, small typed helpers |
| `src/recall/ingest/pdf.py` | PDF → `list[(page_no, text)]` |
| `src/recall/ingest/chunk.py` | pages → `Chunk` list (pure, no I/O) |
| `src/recall/llm/client.py` | **the only networked module**; retries, token accounting |
| `src/recall/llm/fake.py` | `FakeLlmClient` for tests |
| `src/recall/generate/prompts.py` | prompt text, kept separate so it can be tuned without touching logic |
| `src/recall/generate/generate.py` | chunk → candidate cards |
| `src/recall/verify/heuristics.py` | free gates: answerability, atomicity |
| `src/recall/verify/judges.py` | paid gates: groundedness, closed-book leakage |
| `src/recall/verify/dedupe.py` | embedding dedup behind an injectable `embed` function |
| `src/recall/pipeline.py` | orchestration, persistence, cost cap, resumability |
| `src/recall/export/anki.py` | `.apkg` export for qa + cloze notes |
| `src/recall/cli.py` | `init`, `add-topic`, `ingest`, `queue`, `approve`, `export` |

---

### Task 1: Project scaffold, config, and database schema

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`
- Create: `src/recall/__init__.py`, `src/recall/config.py`, `src/recall/schema.sql`, `src/recall/db.py`
- Test: `tests/test_config.py`, `tests/test_db.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `Config` frozen dataclass with fields `api_key: str`, `base_url: str`, `model: str`, `db_path: str`, `max_cost_usd_per_source: float`, `price_input_per_mtok: float`, `price_output_per_mtok: float`; `load_config(env: Mapping[str,str] | None = None) -> Config`; `connect(db_path: str) -> sqlite3.Connection`; `init_db(conn: sqlite3.Connection) -> None`

- [ ] **Step 1: Create the project and pin Python 3.12**

```bash
mkdir -p ~/code/recall/src/recall/{ingest,llm,generate,verify,export} ~/code/recall/tests
cd ~/code/recall
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
uv init --lib --python 3.12 --no-workspace 2>/dev/null || true
uv add pymupdf httpx fastembed genanki numpy
uv add --dev pytest
```

Expected: `uv` creates `.venv` with Python 3.12; `uv run python -V` prints `Python 3.12.x`.

- [ ] **Step 2: Write `.gitignore` and `.env.example`**

`.gitignore`:
```
.venv/
__pycache__/
*.db
*.db-wal
*.db-shm
.env
*.apkg
.pytest_cache/
```

`.env.example`:
```
# Copy to .env and fill in. .env is gitignored — never commit the real key.
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
RECALL_MODEL=deepseek-chat
RECALL_DB=recall.db
RECALL_MAX_COST_USD=2.0
# Verify current DeepSeek pricing before trusting these; they only affect estimates.
RECALL_PRICE_INPUT_PER_MTOK=0.27
RECALL_PRICE_OUTPUT_PER_MTOK=1.10
```

- [ ] **Step 3: Write the failing config test**

`tests/test_config.py`:
```python
import pytest
from recall.config import load_config


def test_load_config_reads_env():
    cfg = load_config({"DEEPSEEK_API_KEY": "sk-test"})
    assert cfg.api_key == "sk-test"
    assert cfg.base_url == "https://api.deepseek.com"
    assert cfg.model == "deepseek-chat"
    assert cfg.max_cost_usd_per_source == 2.0


def test_load_config_overrides():
    cfg = load_config({"DEEPSEEK_API_KEY": "k", "RECALL_MODEL": "deepseek-reasoner"})
    assert cfg.model == "deepseek-reasoner"


def test_missing_key_raises_without_leaking_env():
    with pytest.raises(RuntimeError) as exc:
        load_config({})
    assert "DEEPSEEK_API_KEY" in str(exc.value)
```

- [ ] **Step 4: Run it and confirm it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.config'`

- [ ] **Step 5: Implement `config.py`**

```python
import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    model: str
    db_path: str
    max_cost_usd_per_source: float
    price_input_per_mtok: float
    price_output_per_mtok: float


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    api_key = env.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set. Put it in .env (which is gitignored)."
        )
    return Config(
        api_key=api_key,
        base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=env.get("RECALL_MODEL", "deepseek-chat"),
        db_path=env.get("RECALL_DB", "recall.db"),
        max_cost_usd_per_source=float(env.get("RECALL_MAX_COST_USD", "2.0")),
        price_input_per_mtok=float(env.get("RECALL_PRICE_INPUT_PER_MTOK", "0.27")),
        price_output_per_mtok=float(env.get("RECALL_PRICE_OUTPUT_PER_MTOK", "1.10")),
    )
```

- [ ] **Step 6: Run config tests — expect PASS**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 7: Write `schema.sql`**

Includes Phase 2 and 3 tables now so later phases never migrate.

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS settings (
  user_id           INTEGER PRIMARY KEY REFERENCES users(id),
  new_cards_per_day INTEGER NOT NULL DEFAULT 15,
  daily_review_cap  INTEGER NOT NULL DEFAULT 120,
  desired_retention REAL    NOT NULL DEFAULT 0.90
);

CREATE TABLE IF NOT EXISTS topics (
  id      INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  code    TEXT NOT NULL,
  label   TEXT NOT NULL,
  UNIQUE(user_id, code)
);

CREATE TABLE IF NOT EXISTS sources (
  id       INTEGER PRIMARY KEY,
  user_id  INTEGER NOT NULL REFERENCES users(id),
  topic_id INTEGER NOT NULL REFERENCES topics(id),
  filename TEXT NOT NULL,
  kind     TEXT NOT NULL,
  sha256   TEXT NOT NULL,
  added_at TEXT NOT NULL,
  UNIQUE(user_id, sha256)
);

CREATE TABLE IF NOT EXISTS chunks (
  id           INTEGER PRIMARY KEY,
  source_id    INTEGER NOT NULL REFERENCES sources(id),
  ordinal      INTEGER NOT NULL,
  text         TEXT NOT NULL,
  page_ref     TEXT NOT NULL,
  generated_at TEXT,
  UNIQUE(source_id, ordinal)
);

CREATE TABLE IF NOT EXISTS cards (
  id            INTEGER PRIMARY KEY,
  chunk_id      INTEGER NOT NULL REFERENCES chunks(id),
  topic_id      INTEGER NOT NULL REFERENCES topics(id),
  kind          TEXT NOT NULL CHECK (kind IN ('qa','cloze')),
  question      TEXT NOT NULL,
  answer        TEXT NOT NULL,
  cloze_text    TEXT,
  arm           TEXT NOT NULL CHECK (arm IN ('learned','baseline')),
  state         TEXT NOT NULL CHECK (state IN ('pending','active','suspended','rejected')),
  reject_reason TEXT,
  created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_state ON cards(state);
CREATE INDEX IF NOT EXISTS idx_cards_topic ON cards(topic_id);

CREATE TABLE IF NOT EXISTS gen_runs (
  id                INTEGER PRIMARY KEY,
  source_id         INTEGER NOT NULL REFERENCES sources(id),
  ran_at            TEXT NOT NULL,
  model             TEXT NOT NULL,
  prompt_tokens     INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost_estimate     REAL NOT NULL DEFAULT 0.0,
  cards_accepted    INTEGER NOT NULL DEFAULT 0,
  cards_rejected    INTEGER NOT NULL DEFAULT 0
);

-- Phase 2/3, created now to avoid migrations later.
CREATE TABLE IF NOT EXISTS reviews (
  id                INTEGER PRIMARY KEY,
  card_id           INTEGER NOT NULL REFERENCES cards(id),
  user_id           INTEGER NOT NULL REFERENCES users(id),
  reviewed_at       TEXT NOT NULL,
  grade             INTEGER NOT NULL CHECK (grade BETWEEN 1 AND 4),
  elapsed_days      REAL NOT NULL,
  predicted_r       REAL,
  scheduler_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_card ON reviews(card_id, reviewed_at);

CREATE TABLE IF NOT EXISTS card_state (
  card_id    INTEGER NOT NULL REFERENCES cards(id),
  user_id    INTEGER NOT NULL REFERENCES users(id),
  stability  REAL NOT NULL,
  difficulty REAL NOT NULL,
  due_at     TEXT NOT NULL,
  reps       INTEGER NOT NULL DEFAULT 0,
  lapses     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (card_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_card_state_due ON card_state(user_id, due_at);

CREATE TABLE IF NOT EXISTS fit_runs (
  id           INTEGER PRIMARY KEY,
  ran_at       TEXT NOT NULL,
  n_reviews    INTEGER NOT NULL,
  params_json  TEXT NOT NULL,
  val_logloss  REAL NOT NULL
);
```

- [ ] **Step 8: Write the failing db test**

`tests/test_db.py`:
```python
from recall.db import connect, init_db


def test_init_db_creates_all_tables(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert {"users", "settings", "topics", "sources", "chunks",
            "cards", "gen_runs", "reviews", "card_state", "fit_runs"} <= names


def test_init_db_is_idempotent(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    init_db(conn)  # must not raise


def test_rows_are_dict_like(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    conn.execute("INSERT INTO users (name) VALUES ('yash')")
    row = conn.execute("SELECT id, name FROM users").fetchone()
    assert row["name"] == "yash"


def test_foreign_keys_enforced(tmp_path):
    import sqlite3
    import pytest
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO topics (user_id, code, label) VALUES (999, 'X', 'X')"
        )
```

- [ ] **Step 9: Run it and confirm it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.db'`

- [ ] **Step 10: Implement `db.py`**

```python
import sqlite3
from importlib import resources


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    sql = resources.files("recall").joinpath("schema.sql").read_text()
    conn.executescript(sql)
    conn.commit()
```

Add to `pyproject.toml` so the `.sql` file ships with the package:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/recall"]

[tool.hatch.build.targets.wheel.force-include]
"src/recall/schema.sql" = "recall/schema.sql"
```

- [ ] **Step 11: Run db tests — expect PASS**

Run: `uv run pytest tests/ -v`
Expected: 7 passed

- [ ] **Step 12: Commit**

```bash
git init
git add -A
git commit -m "feat: project scaffold, config loading, and sqlite schema"
```

---

### Task 2: PDF ingest

**Files:**
- Create: `src/recall/ingest/__init__.py`, `src/recall/ingest/pdf.py`
- Test: `tests/test_pdf.py`

**Interfaces:**
- Consumes: nothing
- Produces: `read_pdf(path: str) -> list[tuple[int, str]]` returning `(page_number_1_indexed, text)`, skipping pages whose text is blank; `file_sha256(path: str) -> str`

- [ ] **Step 1: Write the failing test**

The fixture PDF is generated by the test itself, so no binary files enter the repo.

`tests/test_pdf.py`:
```python
import fitz
from recall.ingest.pdf import read_pdf, file_sha256


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
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_pdf.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.ingest.pdf'`

- [ ] **Step 3: Implement `pdf.py`**

```python
import hashlib

import fitz


def read_pdf(path: str) -> list[tuple[int, str]]:
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
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_pdf.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/recall/ingest tests/test_pdf.py
git commit -m "feat: pdf ingest with blank-page skipping and content hashing"
```

---

### Task 3: Chunking

**Files:**
- Create: `src/recall/ingest/chunk.py`
- Test: `tests/test_chunk.py`

**Interfaces:**
- Consumes: page tuples from `read_pdf`
- Produces: frozen dataclass `Chunk(ordinal: int, text: str, page_ref: str)`; `chunk_pages(pages: list[tuple[int,str]], target_chars: int = 3000, overlap_chars: int = 300) -> list[Chunk]`

Chunking is a pure function with no I/O, which is what makes it cheap to test hard.

- [ ] **Step 1: Write the failing test**

`tests/test_chunk.py`:
```python
from recall.ingest.chunk import Chunk, chunk_pages


def test_short_input_is_one_chunk():
    chunks = chunk_pages([(1, "A short sentence. Another one.")])
    assert len(chunks) == 1
    assert chunks[0].ordinal == 0
    assert chunks[0].page_ref == "p1"


def test_long_input_splits_into_multiple_chunks():
    body = " ".join(f"Sentence number {i}." for i in range(400))
    chunks = chunk_pages([(1, body)], target_chars=500, overlap_chars=50)
    assert len(chunks) > 3
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_chunks_overlap():
    body = " ".join(f"Fact {i} is true." for i in range(200))
    chunks = chunk_pages([(1, body)], target_chars=400, overlap_chars=100)
    first_tail_words = set(chunks[0].text.split()[-8:])
    second_head_words = set(chunks[1].text.split()[:8])
    assert first_tail_words & second_head_words


def test_page_ref_spans_pages():
    pages = [(3, "Alpha sentence. " * 30), (4, "Beta sentence. " * 30)]
    chunks = chunk_pages(pages, target_chars=100_000)
    assert chunks[0].page_ref == "p3-p4"


def test_single_enormous_sentence_terminates():
    chunks = chunk_pages([(1, "x" * 20_000)], target_chars=500, overlap_chars=50)
    assert len(chunks) == 1
    assert chunks[0].text.startswith("x")


def test_blank_input_yields_nothing():
    assert chunk_pages([]) == []
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_chunk.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.ingest.chunk'`

- [ ] **Step 3: Implement `chunk.py`**

```python
import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    page_ref: str


def _segments(pages: list[tuple[int, str]]) -> list[tuple[str, int]]:
    segs: list[tuple[str, int]] = []
    for page_no, text in pages:
        for part in _SENTENCE_END.split(text):
            part = part.strip()
            if part:
                segs.append((part, page_no))
    return segs


def _page_ref(first: int, last: int) -> str:
    return f"p{first}" if first == last else f"p{first}-p{last}"


def chunk_pages(
    pages: list[tuple[int, str]],
    target_chars: int = 3000,
    overlap_chars: int = 300,
) -> list[Chunk]:
    segs = _segments(pages)
    chunks: list[Chunk] = []
    i = 0
    while i < len(segs):
        buf: list[tuple[str, int]] = []
        size = 0
        j = i
        while j < len(segs) and size < target_chars:
            buf.append(segs[j])
            size += len(segs[j][0]) + 1
            j += 1
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                text=" ".join(s for s, _ in buf),
                page_ref=_page_ref(buf[0][1], buf[-1][1]),
            )
        )
        if j >= len(segs):
            break
        # Step back for overlap, but never past i+1 or the loop cannot advance.
        k, back = j, 0
        while k > i + 1 and back < overlap_chars:
            k -= 1
            back += len(segs[k][0]) + 1
        i = k
    return chunks
```

The `k > i + 1` guard is load-bearing: without it, a large `overlap_chars` relative to `target_chars` makes `i` stop advancing and the function never returns.

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_chunk.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/recall/ingest/chunk.py tests/test_chunk.py
git commit -m "feat: sentence-aware chunking with overlap and page refs"
```

---

### Task 4: LLM client and fake

**Files:**
- Create: `src/recall/llm/__init__.py`, `src/recall/llm/client.py`, `src/recall/llm/fake.py`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: `Config` from Task 1
- Produces: frozen dataclass `LlmResponse(content: str, prompt_tokens: int, completion_tokens: int)`; `DeepSeekClient(cfg: Config, transport=None, sleep=time.sleep)` with method `complete_json(system: str, user: str) -> LlmResponse`; `FakeLlmClient(responses: list[str])` with the same `complete_json` signature plus attribute `calls: list[tuple[str, str]]`

This is the **only** module permitted to import `httpx`.

- [ ] **Step 1: Write the failing test**

`tests/test_llm_client.py`:
```python
import httpx
import pytest

from recall.config import load_config
from recall.llm.client import DeepSeekClient
from recall.llm.fake import FakeLlmClient

CFG = load_config({"DEEPSEEK_API_KEY": "sk-test"})


def _ok(payload_content):
    def handler(request):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": payload_content}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 22},
        })
    return httpx.MockTransport(handler)


def test_complete_json_returns_content_and_tokens():
    client = DeepSeekClient(CFG, transport=_ok('{"cards": []}'))
    resp = client.complete_json("sys", "user")
    assert resp.content == '{"cards": []}'
    assert resp.prompt_tokens == 11
    assert resp.completion_tokens == 22


def test_request_sends_auth_and_json_mode():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    DeepSeekClient(CFG, transport=httpx.MockTransport(handler)).complete_json("s", "u")
    assert seen["auth"] == "Bearer sk-test"
    assert "json_object" in seen["body"]


def test_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    client = DeepSeekClient(CFG, transport=httpx.MockTransport(handler),
                            sleep=lambda _s: None)
    assert client.complete_json("s", "u").content == "{}"
    assert calls["n"] == 3


def test_gives_up_after_max_retries():
    client = DeepSeekClient(
        CFG,
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
        sleep=lambda _s: None,
    )
    with pytest.raises(RuntimeError):
        client.complete_json("s", "u")


def test_api_key_never_appears_in_error():
    client = DeepSeekClient(
        CFG,
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
        sleep=lambda _s: None,
    )
    with pytest.raises(RuntimeError) as exc:
        client.complete_json("s", "u")
    assert "sk-test" not in str(exc.value)


def test_fake_client_returns_queued_responses_in_order():
    fake = FakeLlmClient(['{"a": 1}', '{"b": 2}'])
    assert fake.complete_json("s", "u1").content == '{"a": 1}'
    assert fake.complete_json("s", "u2").content == '{"b": 2}'
    assert fake.calls == [("s", "u1"), ("s", "u2")]
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.llm.client'`

- [ ] **Step 3: Implement `client.py`**

```python
import time
from dataclasses import dataclass

import httpx

from recall.config import Config

_RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class LlmResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int


class DeepSeekClient:
    def __init__(self, cfg: Config, transport=None, sleep=time.sleep,
                 max_retries: int = 4):
        self._cfg = cfg
        self._sleep = sleep
        self._max_retries = max_retries
        self._http = httpx.Client(
            base_url=cfg.base_url, timeout=120.0, transport=transport
        )

    def complete_json(self, system: str, user: str) -> LlmResponse:
        payload = {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        last_status = None
        for attempt in range(self._max_retries):
            resp = self._http.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._cfg.api_key}"},
                json=payload,
            )
            if resp.status_code in _RETRY_STATUS:
                last_status = resp.status_code
                self._sleep(min(2 ** attempt, 30))
                continue
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            return LlmResponse(
                content=data["choices"][0]["message"]["content"],
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )
        # Deliberately does not include the payload or headers — the key must
        # never reach a log or a traceback.
        raise RuntimeError(
            f"DeepSeek request failed after {self._max_retries} attempts "
            f"(last status {last_status})"
        )
```

DeepSeek's JSON mode requires the word "json" to appear in the prompt; Task 5's prompts satisfy that. Verify against current DeepSeek docs during the first live run.

- [ ] **Step 4: Implement `fake.py`**

```python
from recall.llm.client import LlmResponse


class FakeLlmClient:
    """Test double. Returns queued response bodies in order."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> LlmResponse:
        self.calls.append((system, user))
        if not self._responses:
            raise AssertionError("FakeLlmClient ran out of queued responses")
        return LlmResponse(self._responses.pop(0), prompt_tokens=10,
                           completion_tokens=20)
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_llm_client.py -v`
Expected: 6 passed

- [ ] **Step 6: Add the import-boundary guard test**

`tests/test_boundaries.py`:
```python
import pathlib


def test_only_llm_client_imports_httpx():
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "recall"
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if "httpx" in p.read_text() and p.name != "client.py"
    ]
    assert offenders == [], f"httpx must stay in llm/client.py, found in {offenders}"
```

Run: `uv run pytest tests/test_boundaries.py -v` — Expected: 1 passed

- [ ] **Step 7: Commit**

```bash
git add src/recall/llm tests/test_llm_client.py tests/test_boundaries.py
git commit -m "feat: deepseek client with retries, fake double, and import boundary guard"
```

---

### Task 5: Card generation

**Files:**
- Create: `src/recall/generate/__init__.py`, `src/recall/generate/prompts.py`, `src/recall/generate/generate.py`
- Test: `tests/test_generate.py`

**Interfaces:**
- Consumes: `Chunk` (Task 3), `FakeLlmClient` / `DeepSeekClient` (Task 4)
- Produces: frozen dataclass `Candidate(kind: str, question: str, answer: str, cloze_text: str | None)`; `generate_cards(client, chunk: Chunk, n: int = 5) -> tuple[list[Candidate], int, int]` returning `(candidates, prompt_tokens, completion_tokens)`

Malformed model output is expected, not exceptional — it gets dropped, never raised.

- [ ] **Step 1: Write the failing test**

`tests/test_generate.py`:
```python
import json

from recall.generate.generate import Candidate, generate_cards
from recall.ingest.chunk import Chunk
from recall.llm.fake import FakeLlmClient

CHUNK = Chunk(0, "Quicksort has average time complexity O(n log n).", "p4")


def test_parses_qa_and_cloze_cards():
    body = json.dumps({"cards": [
        {"kind": "qa", "question": "Average complexity of quicksort?",
         "answer": "O(n log n)"},
        {"kind": "cloze", "question": "Quicksort complexity",
         "answer": "O(n log n)",
         "cloze_text": "Quicksort averages {{c1::O(n log n)}}."},
    ]})
    cards, pt, ct = generate_cards(FakeLlmClient([body]), CHUNK)
    assert [c.kind for c in cards] == ["qa", "cloze"]
    assert cards[1].cloze_text.startswith("Quicksort averages")
    assert (pt, ct) == (10, 20)


def test_chunk_text_and_page_ref_reach_the_prompt():
    fake = FakeLlmClient([json.dumps({"cards": []})])
    generate_cards(fake, CHUNK)
    _system, user = fake.calls[0]
    assert "Quicksort has average time complexity" in user


def test_prompt_mentions_json_for_deepseek_json_mode():
    fake = FakeLlmClient([json.dumps({"cards": []})])
    generate_cards(fake, CHUNK)
    system, _user = fake.calls[0]
    assert "json" in system.lower()


def test_malformed_json_yields_no_cards_and_does_not_raise():
    cards, _, _ = generate_cards(FakeLlmClient(["not json at all"]), CHUNK)
    assert cards == []


def test_cards_missing_required_fields_are_dropped():
    body = json.dumps({"cards": [
        {"kind": "qa", "question": "Only a question"},
        {"kind": "qa", "question": "Good?", "answer": "Yes"},
    ]})
    cards, _, _ = generate_cards(FakeLlmClient([body]), CHUNK)
    assert len(cards) == 1
    assert cards[0].answer == "Yes"


def test_unknown_kind_is_dropped():
    body = json.dumps({"cards": [
        {"kind": "essay", "question": "Discuss", "answer": "..."},
    ]})
    cards, _, _ = generate_cards(FakeLlmClient([body]), CHUNK)
    assert cards == []


def test_cloze_without_cloze_text_is_dropped():
    body = json.dumps({"cards": [
        {"kind": "cloze", "question": "q", "answer": "a"},
    ]})
    cards, _, _ = generate_cards(FakeLlmClient([body]), CHUNK)
    assert cards == []
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_generate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.generate.generate'`

- [ ] **Step 3: Implement `prompts.py`**

```python
GENERATE_SYSTEM = """You write spaced-repetition flashcards from course material.

Rules:
- Every card must be answerable using ONLY the passage given. Never use outside knowledge.
- One fact per card. Never combine two facts into one question.
- Prefer precise, short answers: a definition, a formula, a condition, a name.
- Do not ask "discuss", "explain in detail", or "list all".
- Mix kinds: "qa" for question/answer, "cloze" for fill-in-the-blank.
- For cloze cards, put the hidden span in {{c1::...}} inside cloze_text.

Reply with json in exactly this shape and nothing else:
{"cards": [{"kind": "qa", "question": "...", "answer": "..."},
           {"kind": "cloze", "question": "...", "answer": "...",
            "cloze_text": "... {{c1::hidden}} ..."}]}
"""

GENERATE_USER = """Passage (from {page_ref}):
\"\"\"
{text}
\"\"\"

Write at most {n} flashcards from this passage."""
```

- [ ] **Step 4: Implement `generate.py`**

```python
import json
from dataclasses import dataclass

from recall.generate.prompts import GENERATE_SYSTEM, GENERATE_USER
from recall.ingest.chunk import Chunk

_VALID_KINDS = {"qa", "cloze"}


@dataclass(frozen=True)
class Candidate:
    kind: str
    question: str
    answer: str
    cloze_text: str | None = None


def _parse(raw: str) -> list[Candidate]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out: list[Candidate] = []
    for item in data.get("cards", []) or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        question = (item.get("question") or "").strip()
        answer = (item.get("answer") or "").strip()
        cloze_text = (item.get("cloze_text") or "").strip() or None
        if kind not in _VALID_KINDS or not question or not answer:
            continue
        if kind == "cloze" and not cloze_text:
            continue
        out.append(Candidate(kind, question, answer, cloze_text))
    return out


def generate_cards(client, chunk: Chunk, n: int = 5
                   ) -> tuple[list[Candidate], int, int]:
    resp = client.complete_json(
        GENERATE_SYSTEM,
        GENERATE_USER.format(page_ref=chunk.page_ref, text=chunk.text, n=n),
    )
    return _parse(resp.content), resp.prompt_tokens, resp.completion_tokens
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_generate.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add src/recall/generate tests/test_generate.py
git commit -m "feat: card generation with tolerant parsing of malformed model output"
```

---

### Task 6: Free verification gates (answerability, atomicity)

**Files:**
- Create: `src/recall/verify/__init__.py`, `src/recall/verify/heuristics.py`
- Test: `tests/test_heuristics.py`

**Interfaces:**
- Consumes: `Candidate` (Task 5)
- Produces: `check_answerable(c: Candidate) -> str | None` and `check_atomic(c: Candidate) -> str | None`, each returning a rejection reason string or `None` if the card passes

These cost nothing, so they run **first** — a card killed here never reaches a paid judge.

- [ ] **Step 1: Write the failing test**

`tests/test_heuristics.py`:
```python
from recall.generate.generate import Candidate
from recall.verify.heuristics import check_answerable, check_atomic


def qa(q, a):
    return Candidate("qa", q, a)


def test_good_card_passes_both_gates():
    c = qa("What is the average time complexity of quicksort?", "O(n log n)")
    assert check_answerable(c) is None
    assert check_atomic(c) is None


def test_essay_prompts_are_rejected():
    assert check_answerable(qa("Discuss the merits of quicksort.", "It is fast"))
    assert check_answerable(qa("Explain in detail how quicksort works.", "..."))
    assert check_answerable(qa("List all sorting algorithms.", "..."))


def test_very_long_answer_is_not_answerable():
    assert check_answerable(qa("What is quicksort?", " ".join(["word"] * 60)))


def test_empty_or_tiny_question_rejected():
    assert check_answerable(qa("Why?", "Because"))


def test_compound_question_is_not_atomic():
    assert check_atomic(qa("What is quicksort and what is mergesort?", "Both sorts"))


def test_two_question_marks_is_not_atomic():
    assert check_atomic(qa("What is X? What is Y?", "Things"))


def test_semicolon_answer_is_not_atomic():
    assert check_atomic(qa("What are the steps?", "First do A; then do B"))


def test_cloze_with_multiple_deletions_is_not_atomic():
    c = Candidate("cloze", "q", "a", "The {{c1::first}} and the {{c2::second}}.")
    assert check_atomic(c)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_heuristics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.verify.heuristics'`

- [ ] **Step 3: Implement `heuristics.py`**

```python
import re

from recall.generate.generate import Candidate

_ESSAY_OPENERS = re.compile(
    r"^\s*(discuss|explain in detail|describe in detail|list all|"
    r"write a note|elaborate|comment on)\b",
    re.IGNORECASE,
)
_CLOZE_TAG = re.compile(r"\{\{c(\d+)::")
_MAX_ANSWER_WORDS = 40
_MIN_QUESTION_CHARS = 12


def check_answerable(c: Candidate) -> str | None:
    if len(c.question.strip()) < _MIN_QUESTION_CHARS:
        return "question too short to be unambiguous"
    if _ESSAY_OPENERS.search(c.question):
        return "essay prompt, not a recall question"
    if len(c.answer.split()) > _MAX_ANSWER_WORDS:
        return f"answer longer than {_MAX_ANSWER_WORDS} words"
    return None


def check_atomic(c: Candidate) -> str | None:
    if c.question.count("?") > 1:
        return "more than one question"
    if re.search(r"\band\b.*\?", c.question) and c.question.count(" and ") >= 1:
        if re.search(r"\bwhat\b.*\band\b.*\bwhat\b", c.question, re.IGNORECASE):
            return "compound question covering two facts"
    if ";" in c.answer:
        return "answer contains multiple clauses"
    if c.cloze_text:
        tags = set(_CLOZE_TAG.findall(c.cloze_text))
        if len(tags) > 1:
            return "cloze card hides more than one span"
    return None
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_heuristics.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/recall/verify tests/test_heuristics.py
git commit -m "feat: free answerability and atomicity gates"
```

---

### Task 7: Paid verification gates (groundedness, closed-book leakage)

**Files:**
- Create: `src/recall/verify/judges.py`
- Modify: `src/recall/generate/prompts.py` (append two prompts)
- Test: `tests/test_judges.py`

**Interfaces:**
- Consumes: `Candidate` (Task 5), an LLM client (Task 4), `Chunk` (Task 3)
- Produces: `check_grounded(client, chunk: Chunk, c: Candidate) -> tuple[str | None, int, int]` and `check_closed_book(client, c: Candidate) -> tuple[str | None, int, int]`, each returning `(rejection_reason_or_None, prompt_tokens, completion_tokens)`

The groundedness judge must **quote** its evidence, and the quote is then verified against the chunk in plain Python. That check is not an LLM opinion — it is the part of the gate that cannot be talked out of.

- [ ] **Step 1: Write the failing test**

`tests/test_judges.py`:
```python
import json

from recall.generate.generate import Candidate
from recall.ingest.chunk import Chunk
from recall.llm.fake import FakeLlmClient
from recall.verify.judges import check_closed_book, check_grounded

CHUNK = Chunk(0, "Quicksort has average time complexity O(n log n). "
                 "Its worst case is O(n^2).", "p4")
CARD = Candidate("qa", "Average time complexity of quicksort?", "O(n log n)")


def test_grounded_passes_when_quote_is_in_chunk():
    body = json.dumps({"supported": True,
                       "quote": "Quicksort has average time complexity O(n log n)."})
    reason, _, _ = check_grounded(FakeLlmClient([body]), CHUNK, CARD)
    assert reason is None


def test_grounded_rejects_when_model_says_unsupported():
    body = json.dumps({"supported": False, "quote": ""})
    reason, _, _ = check_grounded(FakeLlmClient([body]), CHUNK, CARD)
    assert reason == "not supported by the source passage"


def test_grounded_rejects_fabricated_quote_even_when_model_claims_support():
    body = json.dumps({"supported": True,
                       "quote": "Quicksort is always O(n) in every case."})
    reason, _, _ = check_grounded(FakeLlmClient([body]), CHUNK, CARD)
    assert reason == "cited quote does not appear in the source passage"


def test_grounded_quote_match_ignores_whitespace_differences():
    body = json.dumps({"supported": True,
                       "quote": "Quicksort   has average\ntime complexity O(n log n)."})
    reason, _, _ = check_grounded(FakeLlmClient([body]), CHUNK, CARD)
    assert reason is None


def test_grounded_rejects_malformed_judge_output():
    reason, _, _ = check_grounded(FakeLlmClient(["garbage"]), CHUNK, CARD)
    assert reason == "groundedness judge returned unusable output"


def test_closed_book_rejects_when_model_answers_correctly_without_source():
    body = json.dumps({"answer": "O(n log n)", "confident": True})
    reason, _, _ = check_closed_book(FakeLlmClient([body]), CARD)
    assert reason == "answerable without the course material"


def test_closed_book_passes_when_model_is_wrong():
    body = json.dumps({"answer": "O(n!) probably", "confident": True})
    reason, _, _ = check_closed_book(FakeLlmClient([body]), CARD)
    assert reason is None


def test_closed_book_passes_when_model_is_unconfident():
    body = json.dumps({"answer": "O(n log n)", "confident": False})
    reason, _, _ = check_closed_book(FakeLlmClient([body]), CARD)
    assert reason is None


def test_closed_book_does_not_send_the_chunk():
    fake = FakeLlmClient([json.dumps({"answer": "x", "confident": False})])
    check_closed_book(fake, CARD)
    _system, user = fake.calls[0]
    assert "average time complexity O(n log n)" not in user
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_judges.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.verify.judges'`

- [ ] **Step 3: Append judge prompts to `prompts.py`**

```python
GROUNDED_SYSTEM = """You check whether a flashcard is supported by a passage.

Reply with json only:
{"supported": true|false, "quote": "the exact sentence from the passage that
supports the answer, copied verbatim, or empty string"}

The quote must be copied word for word from the passage. Never paraphrase it.
If nothing in the passage supports the answer, set supported to false."""

GROUNDED_USER = """Passage:
\"\"\"
{text}
\"\"\"

Question: {question}
Answer: {answer}"""

CLOSED_BOOK_SYSTEM = """Answer the question from your own general knowledge.

Reply with json only:
{"answer": "your answer, or empty string if you do not know",
 "confident": true|false}"""

CLOSED_BOOK_USER = """Question: {question}"""
```

- [ ] **Step 4: Implement `judges.py`**

```python
import json
import re

from recall.generate.generate import Candidate
from recall.generate.prompts import (
    CLOSED_BOOK_SYSTEM,
    CLOSED_BOOK_USER,
    GROUNDED_SYSTEM,
    GROUNDED_USER,
)
from recall.ingest.chunk import Chunk

_OVERLAP_THRESHOLD = 0.6


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _loads(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def check_grounded(client, chunk: Chunk, c: Candidate
                   ) -> tuple[str | None, int, int]:
    resp = client.complete_json(
        GROUNDED_SYSTEM,
        GROUNDED_USER.format(text=chunk.text, question=c.question, answer=c.answer),
    )
    tokens = (resp.prompt_tokens, resp.completion_tokens)
    data = _loads(resp.content)
    if data is None or "supported" not in data:
        return ("groundedness judge returned unusable output", *tokens)
    if not data.get("supported"):
        return ("not supported by the source passage", *tokens)
    quote = _normalize(str(data.get("quote", "")))
    if not quote or quote not in _normalize(chunk.text):
        return ("cited quote does not appear in the source passage", *tokens)
    return (None, *tokens)


def _answers_agree(model_answer: str, card_answer: str) -> bool:
    a = set(_normalize(model_answer).split())
    b = set(_normalize(card_answer).split())
    if not b:
        return False
    return len(a & b) / len(b) >= _OVERLAP_THRESHOLD


def check_closed_book(client, c: Candidate) -> tuple[str | None, int, int]:
    resp = client.complete_json(
        CLOSED_BOOK_SYSTEM, CLOSED_BOOK_USER.format(question=c.question)
    )
    tokens = (resp.prompt_tokens, resp.completion_tokens)
    data = _loads(resp.content)
    if data is None:
        return (None, *tokens)  # judge failure must not silently delete good cards
    if data.get("confident") and _answers_agree(str(data.get("answer", "")), c.answer):
        return ("answerable without the course material", *tokens)
    return (None, *tokens)
```

Note the asymmetry: a broken groundedness judge **rejects** (fail closed, a card we cannot verify is not trusted), while a broken closed-book judge **passes** (fail open, since its job is only to remove trivia and its failure should not destroy good cards).

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_judges.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add src/recall/verify/judges.py src/recall/generate/prompts.py tests/test_judges.py
git commit -m "feat: groundedness and closed-book judges with verbatim quote checking"
```

---

### Task 8: Semantic deduplication

**Files:**
- Create: `src/recall/verify/dedupe.py`
- Test: `tests/test_dedupe.py`

**Interfaces:**
- Consumes: `Candidate` (Task 5)
- Produces: `embed_texts(texts: list[str]) -> "np.ndarray"` (real ONNX embedder, CPU); `dedupe(cards: list[Candidate], embed=embed_texts, threshold: float = 0.90) -> tuple[list[Candidate], list[tuple[Candidate, str]]]` returning `(kept, [(dropped_card, reason)])`

The real embedder is isolated in one function so tests never load a model, and so a library API change touches exactly one place.

- [ ] **Step 1: Write the failing test**

`tests/test_dedupe.py`:
```python
import numpy as np

from recall.generate.generate import Candidate
from recall.verify.dedupe import dedupe


def qa(q):
    return Candidate("qa", q, "answer")


def fake_embed(vectors_by_text):
    def embed(texts):
        return np.array([vectors_by_text[t] for t in texts], dtype float)
    return embed


def test_identical_vectors_are_deduplicated():
    a, b = qa("What is quicksort's average complexity?"), qa("How fast is quicksort?")
    embed = fake_embed({a.question: [1.0, 0.0], b.question: [1.0, 0.0]})
    kept, dropped = dedupe([a, b], embed=embed)
    assert kept == [a]
    assert dropped[0][0] == b
    assert "duplicate" in dropped[0][1]


def test_orthogonal_vectors_are_both_kept():
    a, b = qa("What is quicksort?"), qa("What is a red-black tree?")
    embed = fake_embed({a.question: [1.0, 0.0], b.question: [0.0, 1.0]})
    kept, dropped = dedupe([a, b], embed=embed)
    assert kept == [a, b]
    assert dropped == []


def test_threshold_is_respected():
    a, b = qa("Question one here"), qa("Question two here")
    embed = fake_embed({a.question: [1.0, 0.0], b.question: [0.94, 0.34]})
    assert len(dedupe([a, b], embed=embed, threshold=0.99)[0]) == 2
    assert len(dedupe([a, b], embed=embed, threshold=0.90)[0]) == 1


def test_first_card_always_survives():
    a, b, c = qa("First one here"), qa("Second one here"), qa("Third one here")
    v = {a.question: [1.0, 0.0], b.question: [1.0, 0.0], c.question: [1.0, 0.0]}
    kept, dropped = dedupe([a, b, c], embed=fake_embed(v))
    assert kept == [a]
    assert len(dropped) == 2


def test_empty_input():
    assert dedupe([], embed=lambda t: np.zeros((0, 2))) == ([], [])
```

Fix the typo before running: `dtype float` must be `dtype=float`.

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_dedupe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.verify.dedupe'`

- [ ] **Step 3: Implement `dedupe.py`**

```python
import numpy as np

from recall.generate.generate import Candidate

_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_model = None


def embed_texts(texts: list[str]) -> np.ndarray:
    """Real embedder. CPU-only ONNX, loaded lazily so tests never touch it."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=_MODEL_NAME)
    return np.array(list(_model.embed(texts)), dtype=float)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if denom == 0.0 else float(np.dot(a, b) / denom)


def dedupe(
    cards: list[Candidate],
    embed=embed_texts,
    threshold: float = 0.90,
) -> tuple[list[Candidate], list[tuple[Candidate, str]]]:
    if not cards:
        return [], []
    vectors = embed([c.question for c in cards])
    kept: list[Candidate] = []
    kept_vectors: list[np.ndarray] = []
    dropped: list[tuple[Candidate, str]] = []
    for card, vector in zip(cards, vectors):
        match = next(
            (i for i, kv in enumerate(kept_vectors) if _cosine(vector, kv) >= threshold),
            None,
        )
        if match is None:
            kept.append(card)
            kept_vectors.append(vector)
        else:
            dropped.append((card, f"duplicate of: {kept[match].question}"))
    return kept, dropped
```

If `fastembed`'s API differs from the call above, `embed_texts` is the only function that changes — every caller and every test is insulated from it.

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_dedupe.py -v`
Expected: 5 passed

- [ ] **Step 5: Verify the real embedder works once, by hand**

Run: `uv run python -c "from recall.verify.dedupe import embed_texts; v = embed_texts(['quicksort complexity','how fast is quicksort']); print(v.shape)"`
Expected: downloads the model on first run, then prints a shape like `(2, 384)`. If the API differs, fix `embed_texts` only.

- [ ] **Step 6: Commit**

```bash
git add src/recall/verify/dedupe.py tests/test_dedupe.py
git commit -m "feat: semantic dedup via CPU onnx embeddings behind an injectable interface"
```

---

### Task 9: Pipeline orchestration, persistence, and cost cap

**Files:**
- Create: `src/recall/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 1–8
- Produces: frozen dataclass `IngestResult(source_id: int, accepted: int, rejected: int, cost_usd: float, stopped_early: bool)`; `ingest_source(conn, cfg, client, *, user_id: int, topic_id: int, path: str, embed=embed_texts) -> IngestResult`

Gate order is cheapest-first, and it is a cost decision, not a style one: heuristics (free) → groundedness (paid) → closed-book (paid) → dedup (free, but needs the survivors).

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline.py`:
```python
import json

import fitz
import numpy as np
import pytest

from recall.config import load_config
from recall.db import connect, init_db
from recall.llm.fake import FakeLlmClient
from recall.pipeline import ingest_source

CFG = load_config({"DEEPSEEK_API_KEY": "sk-test"})


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_db(c)
    c.execute("INSERT INTO users (id, name) VALUES (1, 'yash')")
    c.execute("INSERT INTO topics (id, user_id, code, label) "
              "VALUES (1, 1, 'CSE111', 'Programming')")
    c.commit()
    return c


def make_pdf(tmp_path, text):
    p = tmp_path / "src.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(str(p))
    doc.close()
    return str(p)


def orthogonal_embed(texts):
    return np.eye(max(len(texts), 1))[: len(texts)]


def accept_all_responses(question, answer, quote):
    return [
        json.dumps({"cards": [{"kind": "qa", "question": question, "answer": answer}]}),
        json.dumps({"supported": True, "quote": quote}),
        json.dumps({"answer": "no idea", "confident": False}),
    ]


def test_accepted_card_is_persisted_with_traceability(conn, tmp_path):
    text = "Pointers store memory addresses in C."
    path = make_pdf(tmp_path, text)
    client = FakeLlmClient(accept_all_responses(
        "What do pointers store in C?", "memory addresses", text))
    result = ingest_source(conn, CFG, client, user_id=1, topic_id=1,
                           path=path, embed=orthogonal_embed)
    assert result.accepted == 1
    row = conn.execute(
        "SELECT c.state, c.topic_id, ch.page_ref FROM cards c "
        "JOIN chunks ch ON ch.id = c.chunk_id"
    ).fetchone()
    assert row["state"] == "pending"
    assert row["topic_id"] == 1
    assert row["page_ref"] == "p1"


def test_rejected_card_is_stored_with_reason(conn, tmp_path):
    text = "Pointers store memory addresses in C."
    path = make_pdf(tmp_path, text)
    client = FakeLlmClient([
        json.dumps({"cards": [{"kind": "qa",
                               "question": "Discuss pointers in C thoroughly.",
                               "answer": "They store addresses"}]}),
    ])
    result = ingest_source(conn, CFG, client, user_id=1, topic_id=1,
                           path=path, embed=orthogonal_embed)
    assert result.rejected == 1
    row = conn.execute("SELECT state, reject_reason FROM cards").fetchone()
    assert row["state"] == "rejected"
    assert "essay" in row["reject_reason"]


def test_free_gates_run_before_paid_judges(conn, tmp_path):
    """An essay-prompt card must cost nothing beyond generation."""
    path = make_pdf(tmp_path, "Pointers store memory addresses in C.")
    client = FakeLlmClient([
        json.dumps({"cards": [{"kind": "qa",
                               "question": "Discuss pointers in C thoroughly.",
                               "answer": "addresses"}]}),
    ])
    ingest_source(conn, CFG, client, user_id=1, topic_id=1, path=path,
                  embed=orthogonal_embed)
    assert len(client.calls) == 1  # generation only, no judge calls


def test_reingesting_the_same_file_is_a_noop(conn, tmp_path):
    text = "Pointers store memory addresses in C."
    path = make_pdf(tmp_path, text)
    args = dict(user_id=1, topic_id=1, path=path, embed=orthogonal_embed)
    ingest_source(conn, CFG, FakeLlmClient(
        accept_all_responses("What do pointers store?", "addresses", text)), **args)
    second = ingest_source(conn, CFG, FakeLlmClient([]), **args)
    assert second.accepted == 0
    assert conn.execute("SELECT COUNT(*) n FROM cards").fetchone()["n"] == 1


def test_cost_cap_stops_the_run(conn, tmp_path):
    cfg = load_config({"DEEPSEEK_API_KEY": "k", "RECALL_MAX_COST_USD": "0.0"})
    path = make_pdf(tmp_path, "Sentence one here. " * 200)
    client = FakeLlmClient([json.dumps({"cards": []})] * 50)
    result = ingest_source(conn, cfg, client, user_id=1, topic_id=1,
                           path=path, embed=orthogonal_embed)
    assert result.stopped_early is True


def test_gen_run_records_tokens_and_cost(conn, tmp_path):
    text = "Pointers store memory addresses in C."
    path = make_pdf(tmp_path, text)
    ingest_source(conn, CFG, FakeLlmClient(
        accept_all_responses("What do pointers store?", "addresses", text)),
        user_id=1, topic_id=1, path=path, embed=orthogonal_embed)
    row = conn.execute("SELECT prompt_tokens, cost_estimate FROM gen_runs").fetchone()
    assert row["prompt_tokens"] > 0
    assert row["cost_estimate"] > 0


def test_cards_are_split_between_arms(conn, tmp_path):
    """Arm assignment must produce both arms across many cards."""
    from recall.pipeline import assign_arm
    arms = {assign_arm(i) for i in range(50)}
    assert arms == {"learned", "baseline"}
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.pipeline'`

- [ ] **Step 3: Implement `pipeline.py`**

```python
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from recall.config import Config
from recall.generate.generate import Candidate, generate_cards
from recall.ingest.chunk import chunk_pages
from recall.ingest.pdf import file_sha256, read_pdf
from recall.verify.dedupe import dedupe, embed_texts
from recall.verify.heuristics import check_answerable, check_atomic
from recall.verify.judges import check_closed_book, check_grounded


@dataclass(frozen=True)
class IngestResult:
    source_id: int
    accepted: int
    rejected: int
    cost_usd: float
    stopped_early: bool


def assign_arm(seed: int) -> str:
    return random.Random(seed).choice(["learned", "baseline"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cost(cfg: Config, prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens / 1_000_000) * cfg.price_input_per_mtok + (
        completion_tokens / 1_000_000
    ) * cfg.price_output_per_mtok


def _insert_card(conn, chunk_id, topic_id, c: Candidate, state, reason, arm) -> None:
    conn.execute(
        "INSERT INTO cards (chunk_id, topic_id, kind, question, answer, cloze_text,"
        " arm, state, reject_reason, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (chunk_id, topic_id, c.kind, c.question, c.answer, c.cloze_text,
         arm, state, reason, _now()),
    )


def ingest_source(conn, cfg: Config, client, *, user_id: int, topic_id: int,
                  path: str, embed=embed_texts) -> IngestResult:
    sha = file_sha256(path)
    existing = conn.execute(
        "SELECT id FROM sources WHERE user_id = ? AND sha256 = ?", (user_id, sha)
    ).fetchone()
    if existing:
        return IngestResult(existing["id"], 0, 0, 0.0, False)

    cur = conn.execute(
        "INSERT INTO sources (user_id, topic_id, filename, kind, sha256, added_at)"
        " VALUES (?,?,?,?,?,?)",
        (user_id, topic_id, path, "pdf", sha, _now()),
    )
    source_id = cur.lastrowid

    chunks = chunk_pages(read_pdf(path))
    for ch in chunks:
        conn.execute(
            "INSERT INTO chunks (source_id, ordinal, text, page_ref) VALUES (?,?,?,?)",
            (source_id, ch.ordinal, ch.text, ch.page_ref),
        )
    conn.commit()

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

        from recall.ingest.chunk import Chunk
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
                _insert_card(conn, row["id"], topic_id, c, "rejected", reason, "learned")
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
    conn.execute(
        "INSERT INTO gen_runs (source_id, ran_at, model, prompt_tokens,"
        " completion_tokens, cost_estimate, cards_accepted, cards_rejected)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (source_id, _now(), cfg.model, prompt_tokens, completion_tokens,
         cost, accepted, rejected),
    )
    conn.commit()
    return IngestResult(source_id, accepted, rejected, cost, stopped_early)
```

Each chunk commits as it completes, so a rate limit or crash mid-course leaves the work already done intact — rerunning skips chunks whose `generated_at` is set.

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: 7 passed

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -v`
Expected: all tests pass, no network access

- [ ] **Step 6: Commit**

```bash
git add src/recall/pipeline.py tests/test_pipeline.py
git commit -m "feat: ingest pipeline with cheapest-first gating, cost cap, and resumability"
```

---

### Task 10: Anki export and CLI

**Files:**
- Create: `src/recall/export/__init__.py`, `src/recall/export/anki.py`, `src/recall/cli.py`
- Modify: `pyproject.toml` (add the console script)
- Test: `tests/test_anki.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above
- Produces: `export_apkg(conn, out_path: str, topic_code: str | None = None) -> int` returning the number of notes written; a `recall` console command with subcommands `init`, `add-topic`, `ingest`, `queue`, `approve`, `export`

Export lands now rather than in week 4 — insurance that arrives last is not insurance.

- [ ] **Step 1: Write the failing export test**

`tests/test_anki.py`:
```python
import zipfile

from recall.db import connect, init_db
from recall.export.anki import export_apkg


def seeded(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (1,'yash')")
    conn.execute("INSERT INTO topics (id,user_id,code,label) VALUES (1,1,'CSE111','C')")
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'f.pdf','pdf','abc','2026-09-04')")
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref) "
                 "VALUES (1,1,0,'text','p1')")
    conn.execute("INSERT INTO cards (chunk_id,topic_id,kind,question,answer,"
                 "cloze_text,arm,state,created_at) VALUES "
                 "(1,1,'qa','Q1?','A1',NULL,'learned','active','2026-09-04')")
    conn.execute("INSERT INTO cards (chunk_id,topic_id,kind,question,answer,"
                 "cloze_text,arm,state,created_at) VALUES "
                 "(1,1,'cloze','Q2','A2','The {{c1::answer}}.','learned','active',"
                 "'2026-09-04')")
    conn.execute("INSERT INTO cards (chunk_id,topic_id,kind,question,answer,"
                 "cloze_text,arm,state,reject_reason,created_at) VALUES "
                 "(1,1,'qa','Bad?','x',NULL,'learned','rejected','essay',"
                 "'2026-09-04')")
    conn.commit()
    return conn


def test_export_writes_active_cards_only(tmp_path):
    conn = seeded(tmp_path)
    out = str(tmp_path / "deck.apkg")
    n = export_apkg(conn, out)
    assert n == 2
    assert zipfile.is_zipfile(out)


def test_export_filters_by_topic(tmp_path):
    conn = seeded(tmp_path)
    assert export_apkg(conn, str(tmp_path / "a.apkg"), topic_code="CSE111") == 2
    assert export_apkg(conn, str(tmp_path / "b.apkg"), topic_code="MATHS") == 0
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_anki.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recall.export.anki'`

- [ ] **Step 3: Implement `anki.py`**

```python
import genanki

_QA_MODEL = genanki.Model(
    1607392319,
    "Recall QA",
    fields=[{"name": "Question"}, {"name": "Answer"}, {"name": "Source"}],
    templates=[{
        "name": "Card 1",
        "qfmt": "{{Question}}",
        "afmt": "{{FrontSide}}<hr id=answer>{{Answer}}<br><small>{{Source}}</small>",
    }],
)

_CLOZE_MODEL = genanki.Model(
    1607392320,
    "Recall Cloze",
    fields=[{"name": "Text"}, {"name": "Source"}],
    templates=[{
        "name": "Cloze",
        "qfmt": "{{cloze:Text}}",
        "afmt": "{{cloze:Text}}<br><small>{{Source}}</small>",
    }],
    model_type=genanki.Model.CLOZE,
)


def export_apkg(conn, out_path: str, topic_code: str | None = None) -> int:
    sql = (
        "SELECT c.kind, c.question, c.answer, c.cloze_text, t.code, ch.page_ref "
        "FROM cards c JOIN topics t ON t.id = c.topic_id "
        "JOIN chunks ch ON ch.id = c.chunk_id WHERE c.state = 'active'"
    )
    params: tuple = ()
    if topic_code:
        sql += " AND t.code = ?"
        params = (topic_code,)
    rows = conn.execute(sql, params).fetchall()

    deck = genanki.Deck(2059400110, f"Recall::{topic_code or 'All'}")
    for row in rows:
        source = f"{row['code']} {row['page_ref']}"
        if row["kind"] == "cloze":
            deck.add_note(genanki.Note(
                model=_CLOZE_MODEL, fields=[row["cloze_text"], source]))
        else:
            deck.add_note(genanki.Note(
                model=_QA_MODEL, fields=[row["question"], row["answer"], source]))
    genanki.Package(deck).write_to_file(out_path)
    return len(rows)
```

- [ ] **Step 4: Run export tests — expect PASS**

Run: `uv run pytest tests/test_anki.py -v`
Expected: 2 passed

- [ ] **Step 5: Implement `cli.py`**

```python
import argparse
import sys

from recall.config import load_config
from recall.db import connect, init_db
from recall.export.anki import export_apkg
from recall.llm.client import DeepSeekClient
from recall.pipeline import ingest_source

TOPICS = {
    "MATHS": "Mathematics",
    "CSE111": "CSE111",
    "INT108": "INT108",
    "INT335": "INT335",
    "HTML": "HTML",
}


def _conn(cfg):
    return connect(cfg.db_path)


def cmd_init(args, cfg) -> int:
    conn = _conn(cfg)
    init_db(conn)
    conn.execute("INSERT OR IGNORE INTO users (id, name) VALUES (1, ?)", (args.user,))
    conn.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (1)")
    for code, label in TOPICS.items():
        conn.execute(
            "INSERT OR IGNORE INTO topics (user_id, code, label) VALUES (1, ?, ?)",
            (code, label),
        )
    conn.commit()
    print(f"initialised {cfg.db_path} with topics: {', '.join(TOPICS)}")
    return 0


def cmd_ingest(args, cfg) -> int:
    conn = _conn(cfg)
    row = conn.execute(
        "SELECT id FROM topics WHERE user_id = 1 AND code = ?", (args.topic,)
    ).fetchone()
    if row is None:
        print(f"unknown topic {args.topic}; known: {', '.join(TOPICS)}",
              file=sys.stderr)
        return 2
    result = ingest_source(conn, cfg, DeepSeekClient(cfg), user_id=1,
                           topic_id=row["id"], path=args.path)
    print(f"accepted={result.accepted} rejected={result.rejected} "
          f"cost=${result.cost_usd:.4f}"
          + (" [stopped at cost cap]" if result.stopped_early else ""))
    return 0


def cmd_queue(args, cfg) -> int:
    conn = _conn(cfg)
    rows = conn.execute(
        "SELECT c.id, t.code, c.kind, c.question, c.answer, ch.page_ref "
        "FROM cards c JOIN topics t ON t.id = c.topic_id "
        "JOIN chunks ch ON ch.id = c.chunk_id "
        "WHERE c.state = 'pending' ORDER BY c.id LIMIT ?", (args.limit,)
    ).fetchall()
    for r in rows:
        print(f"[{r['id']}] {r['code']} {r['page_ref']} ({r['kind']})\n"
              f"    Q: {r['question']}\n    A: {r['answer']}")
    print(f"\n{len(rows)} pending shown")
    return 0


def cmd_approve(args, cfg) -> int:
    conn = _conn(cfg)
    state = "rejected" if args.reject else "active"
    reason = "rejected by hand" if args.reject else None
    conn.executemany(
        "UPDATE cards SET state = ?, reject_reason = ? WHERE id = ? AND "
        "state = 'pending'",
        [(state, reason, cid) for cid in args.ids],
    )
    conn.commit()
    print(f"{len(args.ids)} cards -> {state}")
    return 0


def cmd_export(args, cfg) -> int:
    n = export_apkg(_conn(cfg), args.out, topic_code=args.topic)
    print(f"wrote {n} notes to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recall")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.add_argument("--user", default="yash")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("ingest")
    s.add_argument("--topic", required=True)
    s.add_argument("path")
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("queue"); s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser("approve")
    s.add_argument("ids", nargs="+", type=int)
    s.add_argument("--reject", action="store_true")
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("export")
    s.add_argument("--topic", default=None)
    s.add_argument("--out", default="recall.apkg")
    s.set_defaults(func=cmd_export)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args, load_config())


if __name__ == "__main__":
    raise SystemExit(main())
```

Add to `pyproject.toml`:
```toml
[project.scripts]
recall = "recall.cli:main"
```

- [ ] **Step 6: Write the CLI test**

`tests/test_cli.py`:
```python
from recall.cli import build_parser, cmd_init, cmd_queue
from recall.config import load_config


def test_parser_accepts_ingest_arguments():
    args = build_parser().parse_args(["ingest", "--topic", "CSE111", "notes.pdf"])
    assert args.topic == "CSE111"
    assert args.path == "notes.pdf"


def test_init_creates_all_five_topics(tmp_path, capsys):
    cfg = load_config({"DEEPSEEK_API_KEY": "k",
                       "RECALL_DB": str(tmp_path / "t.db")})
    args = build_parser().parse_args(["init"])
    assert cmd_init(args, cfg) == 0
    from recall.db import connect
    codes = {r["code"] for r in connect(cfg.db_path).execute(
        "SELECT code FROM topics").fetchall()}
    assert codes == {"MATHS", "CSE111", "INT108", "INT335", "HTML"}


def test_init_is_idempotent(tmp_path):
    cfg = load_config({"DEEPSEEK_API_KEY": "k",
                       "RECALL_DB": str(tmp_path / "t.db")})
    args = build_parser().parse_args(["init"])
    cmd_init(args, cfg)
    assert cmd_init(args, cfg) == 0


def test_queue_on_empty_db_reports_zero(tmp_path, capsys):
    cfg = load_config({"DEEPSEEK_API_KEY": "k",
                       "RECALL_DB": str(tmp_path / "t.db")})
    cmd_init(build_parser().parse_args(["init"]), cfg)
    cmd_queue(build_parser().parse_args(["queue"]), cfg)
    assert "0 pending shown" in capsys.readouterr().out
```

- [ ] **Step 7: Run the full suite — expect PASS**

Run: `uv run pytest -v`
Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add src/recall/export src/recall/cli.py tests/test_anki.py tests/test_cli.py pyproject.toml
git commit -m "feat: anki apkg export and cli"
```

- [ ] **Step 9: First real run, on one real course**

```bash
cp .env.example .env    # then edit .env and paste your key into it
uv run recall init
uv run recall ingest --topic CSE111 ~/path/to/lecture-notes.pdf
uv run recall queue --limit 30
```

Expected: a cost line under $1, and a queue of pending cards.

**Then do the thing that decides whether the project is worth continuing:** read 30 cards and count how many you would actually keep. That acceptance rate is the number the whole project rests on. If it is above ~60%, continue to Phase 2. If it is far below, the fix is in `prompts.py` and the gate thresholds, not in more features.

- [ ] **Step 10: Approve and export**

```bash
uv run recall approve 1 2 3 5 8
uv run recall export --topic CSE111 --out cse111.apkg
```

Expected: `wrote N notes to cse111.apkg`, importable into Anki. **From here on you have a working study tool even if nothing else ships.**

---

## Self-Review

**Spec coverage:**

| Spec section | Covered by |
|---|---|
| §4 module boundaries | File structure table; enforced by Task 4 Step 6 |
| §5 data model | Task 1 Step 7 (full schema, including Phase 2/3 tables) |
| §6 ingest + chunking | Tasks 2, 3 |
| §6 generation, cloze cards | Task 5 |
| §6 gates 1–2 (groundedness, closed-book) | Task 7 |
| §6 gate 3 (dedup) | Task 8 |
| §6 gates 4–5 (answerability, atomicity) | Task 6 |
| §6 human gate | Task 10 (`queue`, `approve`) |
| §6 cost tracking + cap | Task 9 (`gen_runs`, `stopped_early`) |
| §6 credentials never committed | Task 1 (`.gitignore`, `.env.example`), Task 4 (key absent from errors) |
| §4 export as insurance | Task 10 |
| §7 daily load controls | **Phase 2** — `settings` table exists now, no scheduler yet |
| §7 memory model | **Phase 3** |
| §8 evaluation | **Phase 4**; `cards.arm` is populated from Task 9 so data exists from day one |

Two deliberate deferrals, both flagged rather than dropped: the scheduler and evaluation are separate plans, but the schema and arm assignment they depend on are built here, so no rework is needed later.

**Placeholder scan:** no TBDs, no "add error handling", no "similar to Task N". Every code step carries complete code.

**Type consistency:** `Candidate`, `Chunk`, `LlmResponse`, `Config`, and `IngestResult` are defined once and used with matching field names throughout. Both judges return the same `(reason, prompt_tokens, completion_tokens)` shape. `check_answerable` and `check_atomic` share the `str | None` convention.

**One known defect left in the plan on purpose:** `tests/test_dedupe.py` Step 1 contains `dtype float`, which is a syntax error. Task 8 Step 1 says to fix it to `dtype=float`. It is flagged rather than silently corrected so the implementer reads the test rather than pasting it.
