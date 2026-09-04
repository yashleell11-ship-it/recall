# Recall — internal contract

Frozen interface between the pipeline, the scheduler, the API and the web client.
Agents build against this. Do not change a signature here without updating every consumer.

## Core dataclasses (already implemented)

```python
# recall.ingest.chunk
@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    page_ref: str          # "p4" or "p4-p6"

# recall.generate.generate
@dataclass(frozen=True)
class Candidate:
    kind: str              # "qa" | "cloze"
    question: str
    answer: str
    cloze_text: str | None # contains {{c1::...}} when kind == "cloze"

# recall.llm.client
@dataclass(frozen=True)
class LlmResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
```

`recall.db.connect(db_path) -> sqlite3.Connection` (row_factory=Row, foreign_keys ON)
`recall.db.init_db(conn) -> None`
`recall.config.load_config(env=None) -> Config`

Schema lives in `src/recall/schema.sql`. Read it before writing queries.

## Scheduler — `recall.schedule.fsrs`

```python
DEFAULT_PARAMS: tuple[float, ...]        # FSRS-4.5, 17 weights

@dataclass(frozen=True)
class MemoryState:
    stability: float                     # days until p(recall) == 0.9
    difficulty: float                    # 1.0 .. 10.0

def retrievability(elapsed_days: float, stability: float) -> float
def initial_state(grade: int, params=DEFAULT_PARAMS) -> MemoryState
def next_state(state: MemoryState, grade: int, elapsed_days: float,
               params=DEFAULT_PARAMS) -> MemoryState
def interval_days(stability: float, desired_retention: float) -> float
```

Grades: 1=again, 2=hard, 3=good, 4=easy.

## HTTP API — FastAPI, mounted at `/api`

Single user for now (`user_id = 1`), but every query filters by user_id so multi-user
is a config change, not a rewrite.

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/topics` | — | `[{id, code, label, due, new, active, pending}]` |
| GET | `/api/queue` | `?topic=&limit=` | `{cards: [QueueCard], due_remaining, new_remaining, cap_reached}` |
| POST | `/api/review` | `{card_id, grade}` | `{card_id, interval_days, due_at, stability, difficulty}` |
| GET | `/api/pending` | `?limit=&offset=&topic=` | `{cards: [PendingCard], total}` |
| POST | `/api/pending/decide` | `{ids: [int], action: "approve"\|"reject"}` | `{updated}` |
| GET | `/api/settings` | — | `{new_cards_per_day, daily_review_cap, desired_retention}` |
| PUT | `/api/settings` | any subset | full settings |
| GET | `/api/stats` | — | `{today: {reviewed, again, streak}, by_topic: [...], last_14_days: [{date, count}], totals: {active, pending, sources}}` |
| GET | `/api/sources` | — | `[{id, filename, topic_code, added_at, accepted, rejected, cost_estimate}]` |

```
QueueCard   = {id, kind, question, answer, cloze_text, topic_code, page_ref, is_new,
               stability, difficulty, elapsed_days}
              stability/difficulty are null for new cards. They travel with the card so
              the client can price each grade button exactly rather than estimating.
PendingCard = {id, kind, question, answer, cloze_text, topic_code, page_ref, source_filename}
```

Queue ordering: due cards first (oldest due first), then new cards up to
`new_cards_per_day` minus new cards already introduced today. Total capped by
`daily_review_cap`. `cap_reached` is true when the cap truncated the queue.

All errors: `{"detail": "..."}` with a real HTTP status. Never 200 with an error body.

## Web client — Next.js, `web/`

Talks only to the paths above via `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`).

### Design brief — read this twice

The failure mode to avoid is a page that looks generated. Concretely, **do not** use:
purple/indigo/violet gradients, glassmorphism, blurred coloured blobs, a centred hero
with a gradient headline, emoji in headings or buttons, `rounded-2xl` everywhere, soft
drop shadows on every surface, "✨" anything, or stock shadcn defaults left untouched.

Build instead:

- **Reference points:** Anki's density, Linear's restraint, a good terminal's calm. This
  is a tool someone opens every morning for four years, not a landing page.
- **Palette:** near-monochrome. A paper-white / near-black base with one accent used
  sparingly for the primary action and nothing else. Grade buttons are the exception and
  earn colour because they carry meaning. Dark mode is a real design, not an inversion.
- **Type:** one family, real hierarchy through weight and size, not colour. Card text is
  large and comfortable — it is the thing being read. UI chrome is small and quiet.
- **Density:** the dashboard is dense and factual. Numbers first, no giant stat cards
  with icons. A person should see today's load in one glance without scrolling.
- **Radius and shadow:** small radii (2–6px), borders instead of shadows. Flat surfaces.
- **Motion:** almost none. A card flip and a queue advance, both under 150ms. No
  page-load animations, no staggered fade-ins.
- **The review screen is the product.** It should be nearly empty: the question, plenty
  of space, the answer on reveal, four grade buttons, a thin progress indicator. No nav,
  no sidebar, no breadcrumbs. Everything that is not the card is a distraction.
- **Keyboard first.** Space reveals, 1–4 grade, Esc exits, `?` shows shortcuts. The
  mouse must work, but the keyboard is the intended path and shortcuts are visible on
  the buttons themselves.
- **Every card shows its source** (topic code + page ref) in small quiet text. Provenance
  is a feature.
- Empty states say what to do next, in a plain sentence, with no illustration.

Screens: `/` dashboard, `/review` focus mode, `/approve` bulk triage of pending cards,
`/settings`, `/sources`.

---

## Test mode

Sit a paper of a fixed mark total, then feed the results back into the scheduler.
This is the "test me and adjust the difficulty" loop: what you get wrong comes back sooner.

### Marks per card (computed at assembly, not stored on the card)

| Card | Marks |
|---|---|
| cloze | 1 |
| qa, answer <= 4 words | 1 |
| qa, answer <= 12 words | 2 |
| qa, longer | 5 |

### Papers

| kind | target | time limit | notes |
|---|---|---|---|
| `class30` | 30 marks | 45 min | a sessional / MST |
| `endterm100` | 100 marks | 180 min | a full end-term paper |
| `fullday` | every active card | none | marathon, resumable across sittings |

Assembly is stratified across topics in proportion to each topic's active cards, and
within a topic prefers weak cards (high difficulty, low stability, due or overdue) while
still including some strong ones so a paper is not purely punishment. Greedy fill to hit
the target exactly; if the deck cannot reach the target, the paper is short and says so.

### Endpoints

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/tests` | `{kind, topic_code?}` | `{test_id, kind, total_marks, time_limit_s, questions: [TestQuestion]}` |
| GET | `/api/tests/{id}` | — | same shape, plus recorded verdicts, for resuming |
| POST | `/api/tests/{id}/answer` | `{ordinal, verdict, seconds}` | `{ok: true}` |
| POST | `/api/tests/{id}/submit` | — | `TestResult` |
| GET | `/api/tests` | — | `[{id, kind, started_at, obtained_marks, total_marks, duration_s}]` |

```
TestQuestion = {ordinal, card_id, kind, question, answer, cloze_text, marks,
                topic_code, page_ref, verdict}
verdict      = "correct" | "partial" | "wrong" | "skipped" | null
TestResult   = {obtained_marks, total_marks, percent, duration_s,
                by_topic: [{topic_code, obtained, total}],
                wrong: [TestQuestion], partial: [TestQuestion]}
```

`partial` is only offered for questions worth 2 marks or more, and scores half.

### Feedback into the scheduler

On submit, every **answered** question records a real review through the normal
scheduling path, so stability and difficulty update exactly as they would in daily
review. Skipped questions record nothing — not attempting a question is not evidence
about memory. Grade mapping: `wrong -> 1 (again)`, `partial -> 2 (hard)`,
`correct -> 3 (good)`. Grade 4 is never inferred: "easy" is a claim only the person
reviewing can make, and a test does not ask.

---

## Teaching: explain what you got wrong

After a test (or a lapse in daily review), you can ask for an explanation of a card you
missed. The explanation is **grounded in the card's own source chunk** — the same text
the card was generated from — so it teaches your syllabus rather than the model's
general knowledge.

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/teach/explain` | `{card_id}` | `{explanation, source_quote, page_ref, topic_code, cached}` |

Rules:
- The explanation must cite a verbatim quote from the chunk, verified in Python exactly
  as the groundedness gate does. An explanation that cannot cite its source is not
  returned; the endpoint returns 422 with a plain reason instead of a confident guess.
- Explanations are **cached in the database** keyed by card id. They cost money and the
  same card gets missed repeatedly; regenerating each time is waste.
- Explanations are prose for a first-year student: what the answer is, why, and the one
  distinction most likely to have caused the mistake. No preamble, no encouragement.

## Image and file upload

Uploading is how notes get in from a phone, so this must work on a small screen over a
tunnelled connection.

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/sources/upload` | multipart: `file`, `topic_code` | `{source_id, filename, kind, chunks, text_chars, warning?}` |
| POST | `/api/sources/{id}/generate` | — | `{accepted, rejected, cost_usd, stopped_early}` |

Upload **extracts text and creates chunks only** — it never calls the paid API, so it is
fast and free and works before any key exists. Card generation is a separate, explicit
step because it costs money and takes time.

Accepted: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.txt`, `.md`. Max 25 MB.

**OCR honesty:** images go through Tesseract on CPU. Printed slides, textbook pages and
screenshots work well. **Handwriting works badly** — that is a real limitation of
CPU OCR, not a bug, and the response carries a `warning` when extracted text looks too
sparse for the image size. OCR sits behind a single `extract_text_from_image(path)`
function so a vision-capable API can replace it later without touching anything else.
