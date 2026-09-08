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

## Authentication

Open registration — no invite code, no email verification. A session is an
HttpOnly, Secure, SameSite=Lax cookie (`recall_session`) holding an opaque
token valid for 10 days; the server stores only its SHA-256 hash
(`sessions` table). The expiry is fixed rather than sliding — refreshing it
per request would turn every read in the app into a database write. Every
route below `## HTTP API` requires this cookie and resolves it to a
`user_id` via `Depends(get_current_user)` — a request with no cookie, or an
expired/unknown one, gets `401 {"detail": "..."}`.

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/auth/register` | `{name, email, password}` (password ≥ 8 chars) | `{id, name, email}` + sets the session cookie. Also seeds the full LPU topic catalog and default settings for the new account — a signup is immediately usable. `422` on a taken name/email. |
| POST | `/api/auth/login` | `{email, password}` | `{id, name, email}` + sets the session cookie. `401` for either an unknown email or a wrong password — deliberately the same error, to avoid an account-enumeration oracle. |
| POST | `/api/auth/logout` | — | `{ok: true}`, clears the cookie and deletes the session row. |
| GET | `/api/auth/me` | — | `{id, name, email}` for the current session, or `401`. |

## HTTP API — FastAPI, mounted at `/api`

Every table and query is scoped by `user_id`, resolved per-request from the
session cookie above — this is a real multi-user app, not a single-owner one
with a placeholder constant.

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/topics` | — | `[{id, code, label, due, new, active, pending}]` |
| GET | `/api/queue` | `?topic=&limit=` | `{cards: [QueueCard], due_remaining, new_remaining, cap_reached}` |
| POST | `/api/review` | `{card_id, grade}` | `{card_id, interval_days, due_at, stability, difficulty}` |
| GET | `/api/pending` | `?limit=&offset=&topic=` | `{cards: [PendingCard], total}` |
| POST | `/api/pending/decide` | `{ids: [int], action: "approve"\|"reject"}` | `{updated}` |
| POST | `/api/cards/{id}/suspend` | — | `{ok, card_id, state}` — drops a card out of the queue and every paper without deleting it, so reviews already recorded against it still count toward the scheduler fit. `404` when the card is not yours. |
| GET | `/api/settings` | — | `{new_cards_per_day, daily_review_cap, desired_retention}` |
| PUT | `/api/settings` | any subset | full settings |
| GET | `/api/stats` | — | `{today: {reviewed, again, streak}, by_topic: [...], last_14_days: [{date, count}], totals: {active, pending, sources}}` |
| GET | `/api/study-plan` | — | `[{topic_code, due, new, active, units_cover, weakest_unit, units: [{number, name, active, due, mastery}], action: {kind, unit}, advice}]` |
| GET | `/api/sources` | — | `[{id, filename, topic_code, added_at, accepted, rejected, cost_estimate}]` |

```
QueueCard   = {id, kind, question, answer, cloze_text, topic_code, page_ref, is_new,
               stability, difficulty, elapsed_days, origin}
              stability/difficulty are null for new cards. They travel with the card so
              the client can price each grade button exactly rather than estimating.
PendingCard = {id, kind, question, answer, cloze_text, topic_code, page_ref,
               source_filename, origin}
origin      = "upload" | "knowledge"
              "upload"    — grounded: a verbatim quote from an uploaded file was
                            checked, in Python, before the card was kept.
              "knowledge" — written from the model's own knowledge of a syllabus
                            unit. No source exists to check it against, so the
                            grounding and closed-book gates did not run.
              The client MUST show the difference. The violet "AI" mark cannot
              carry it: every card in the app is model-authored, so that mark is
              true of both. A second, uncoloured "no source" mark carries it.
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

### What to study next

`GET /api/study-plan` answers the question the dashboard could not: not "how many
are due" but "what do I do". One entry per subject, and one `action` — a ladder,
not a score, because a recommendation offering three options is the report it
was meant to replace.

The rungs, first match wins: nothing in the deck → write some; anything due →
review it; anything never seen → meet it; a unit with no cards → write for it;
the weakest unit → sit a unit paper on it, or write more first if it is too thin
to examine. The order of the first three is load-bearing: putting empty units
above `new` told you to generate on a subject built from PDFs — where no card
belongs to a unit, so every unit reads as empty — while unmet cards sat in the
deck.

`mastery` is `1 - mean(assembly.weakness)`, computed by calling that function
rather than by a second copy of its formula. A never-reviewed unit sits at 0.5,
so a fresh deck does not read as weak merely for being new.

**`units_cover`** is how many of a subject's `active` cards the per-unit view can
account for. Only knowledge-mode cards carry a unit; an uploaded PDF is chunked
by page and a page maps to no unit. When it is 0 the endpoint declines to speak
about units at all, and the client says so — "unit 4 is your weakest" drawn from
three of forty cards is a guess wearing a fact's clothing.

Never a paid call. The web client prefetches on route intent, so a GET that
spent money would spend it on a hover.

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

**A paper is not yesterday's paper.** Ranking is by `assembly.priority`, which is
`weakness` minus a penalty for having been asked recently. The penalty is waived
entirely for a question you got **wrong** or **skipped** — those are the ones worth
asking again — halved for a partial, and applied in full to one you answered correctly
or one still sitting on a paper you have not submitted. It decays to nothing over ten
days.

It is a penalty and never an exclusion: on a deck with room, four papers in a row repeat
nothing; on a deck with nothing else to offer, the question comes back rather than the
paper coming up short. The strong-end sample is drawn by `weakness` alone, with recently
asked cards sorted last — drawing it from the tail of the priority order would make the
"not purely punishment" rule the very thing that handed yesterday's questions back.

### Endpoints

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/tests` | `{kind, topic_code?, units?}` | `{test_id, kind, topic_code, units, total_marks, time_limit_s, questions: [TestQuestion]}` |
| GET | `/api/tests/{id}` | — | same shape, plus recorded verdicts, for resuming |
| POST | `/api/tests/{id}/answer` | `{ordinal, verdict, seconds}` | `{ok: true}` |
| POST | `/api/tests/{id}/submit` | — | `TestResult` |
| DELETE | `/api/tests/{id}` | — | `{ok: true}`. Closes an unfinished paper. **409** if it has already been submitted — that is a graded result, not clutter — and **404** for a paper that is not yours, which reads identically to one that does not exist. |
| GET | `/api/tests` | — | `[{id, kind, started_at, submitted_at, obtained_marks, total_marks, duration_s, topic_code, units}]` |

**`units`** is a list of **0-based** syllabus unit indices — the paper was
scoped to those units — or `null` for one drawn from the whole subject.
Scoping requires a `topic_code`: "unit 3" means nothing across five courses
that each have one. An index outside the subject's unit list is refused (422)
rather than clamped.

A unit-scoped paper draws only from cards whose unit is actually **known**,
which means knowledge-mode cards: their chunk is the per-unit chunk of the
topic's synthetic knowledge source and its `ordinal` is the unit index. Cards
from an uploaded PDF are chunked by page, and a page maps to no unit, so they
are left out of a unit paper rather than claimed for a unit nobody checked.

**`asked_before`** is how a question went the last time it appeared on a
DIFFERENT paper, or `null` the first time — `"open"` when it is also on a paper
you have not submitted. Papers avoid repeats, so a repeat is deliberate and the
screen must say which reason applies; an unexplained repeat reads as a broken
generator. The paper also carries **`fresh`** and **`repeats`**, which sum to the
question count.

It is computed on read rather than stored on `test_questions`, because that table
is still copied by a positional `INSERT INTO test_questions_new SELECT *` in
`db.py`'s dormant repair path — adding a column there arms a migration that fires
years later on somebody's damaged database.

**`submitted_at`** is the honest answer to "is this paper finished".
`duration_s` was only ever a proxy for it and is wrong in one real case: a
paper submitted having answered nothing records `duration_s = 0`, which reads
as falsy and left the paper looking permanently unfinished.

```
TestQuestion = {ordinal, card_id, kind, question, answer, cloze_text, marks,
                topic_code, page_ref, verdict, detail, origin, asked_before}
verdict      = "correct" | "partial" | "wrong" | "skipped" | null
asked_before = verdict | "open" | null
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

## Knowledge mode — cards with nothing uploaded

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/topics/{code}/generate` | `{unit, count?}` (`unit` is 1-based; `count` ≤ 25, default 12) | `{accepted, rejected, cost_usd, stopped_early}` — the same shape as upload generation |
| POST | `/api/topics/{code}/paper` | `{kind, units?}` | A full `TestPaper`, plus `generated: {cards, rejected, cost_usd, unit_numbers, deck_already_covered_it}`. Works out which units the paper draws from (MTE → units 1-3, class test → 1-2, ETE → all), generates only the shortfall, then assembles normally. This is what the subject chips on `/test` call: `POST /api/tests` assembles from what exists and hands back an empty paper when the deck is empty, which is the "This paper has no questions" dead end. Pass `units` — **1-based** here, the numbers a student reads off a timetable, unlike the 0-based indices `POST /api/tests` takes — to examine only what was covered in class; the marks target is then spread across just those units, so asking for one unit gets a paper's worth of it. |

Writes cards for one syllabus unit from the model's own knowledge, for the case
where the student has uploaded nothing. `422` when the topic carries no unit
metadata or the unit number is past the end of the syllabus; `404` when the
topic is not yours; `429` when the account is over its daily spend cap.

**What is deliberately given up.** The upload path runs five gates; this path
runs three. `check_grounded` cannot run — there is no passage to quote — and
`check_closed_book` is meaningless here, since its whole job is to reject cards
answerable without a source, which is what these are by construction.
`check_answerable`, `check_atomic` and semantic dedup all still run.

**Where a surviving card lands depends on how thoroughly it was checked**
(`pipeline.keep_state`). An upload-grounded card cleared five gates including
a Python-verified verbatim quote, so it goes straight into rotation
(`state = 'active'`) — making someone read thirty verified cards before they
can study is judgement exercised at the moment they have the least
information, and a bad one is caught in review anyway: graded `again`,
surfaced as a leech, suspended with one press
(`POST /api/cards/{id}/suspend`).

A knowledge-mode card cleared three, and the two it skipped are exactly the
ones that check it against reality. It still lands `pending`, because the
approval queue is the only gate it has left.

Dedup for this path is seeded with the questions already on the unit. Uploaded
chunks generate exactly once, so repeats are impossible there; this button can
be pressed all day against the same unit, and without the seed a second press
would re-add what the first one wrote.

The chunk foreign key is satisfied by a synthetic per-topic source
(`sources.kind = 'knowledge'`) and one chunk per unit, not by a nullable
`chunk_id`: seven read paths inner-join `chunks`, so a null there would
silently drop these cards from the review queue, test assembly, teaching, the
CLI and the Anki export.

## Spend limits

`RECALL_MAX_COST_USD` caps a single generation run. That was sufficient while
one person owned the instance. With open registration it is not — nothing
bounded how many runs one account started — so
`RECALL_MAX_COST_USD_PER_USER_PER_DAY` (default `1.00`) caps what one account
may spend in a UTC day, tracked in `usage_daily` and checked at the top of
**both** generation endpoints before any paid call. Over the cap is `429`.
