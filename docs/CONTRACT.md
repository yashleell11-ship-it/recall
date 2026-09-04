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
QueueCard   = {id, kind, question, answer, cloze_text, topic_code, page_ref, is_new}
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
