# Recall — an exam-prep engine with a learned scheduler

**Date:** 2026-09-04
**Status:** design, pending review
**Owner:** Yash
**Users:** Yash + 2 friends (3 total, private, no public launch)
**Subjects (initial topics):** MATHS, CSE111, INT108, INT335, HTML
**Use case:** daily learning across the semester, not only exam-week cramming
**Budget:** 1 month, ₹0 in new hardware, a few dollars of API spend

---

## 1. Problem

Revising for exams from your own course material is done badly: you re-read notes,
feel familiar with them, and mistake familiarity for recall. Spaced repetition fixes
this, but building the deck is the work nobody does — writing hundreds of good
questions by hand is why Anki decks get abandoned in week two.

Two things have to be true for this to actually get used:

1. The questions must be generated **from your own course material**, automatically,
   and be good enough that you don't resent them.
2. The scheduling must adapt to **you**, not to a generic curve.

## 2. What makes this a month and not a week

The app itself — upload files, show cards, record grades — is a weekend for this
owner. The month goes into three genuinely hard pieces, none of which is affected by
where the model runs:

**H1. Generating questions that are worth answering.** Ungrounded generation produces
plausible questions with wrong answers, and trivia answerable without ever opening the
course. Both are fatal to adoption. Solving it needs a real verification pipeline, not
a better prompt.

**H2. Fitting a memory model to almost no data.** FSRS has ~17 parameters and wants
thousands of reviews per user to fit. This project has 3 users and 30 days. Naive
per-user fitting will overfit badly. The answer is a **hierarchical model with partial
pooling** — users share a population prior and differentiate only as their own data
earns it. This is the statistical core of the project.

**H3. Proving it works.** Almost every spaced-repetition project claims improvement and
measures nothing. Doing this honestly means a control arm, a leak-free split, and being
willing to report that the result was inconclusive.

## 3. Non-goals

Cut ruthlessly, because a month is short:

- **No GPU use of any kind** (owner directive, 2026-09-04). No local model serving, no
  fine-tuning, no Ollama. Generation is an API call; the memory model trains on CPU in
  seconds. The RTX 3090 Ti is off-limits and the laptop's 5070 goes unused.
- No sharing outside the 3 users, no accounts system beyond 3 rows, no onboarding.
- No image or diagram questions in v1 — text only.
- No mobile app until week 4, and only if the rest has landed.
- No handwriting OCR. Ingest is PDFs, slides, and typed notes.
- No "AI tutor" chat. This is a scheduler, not a chatbot.

## 4. Architecture

Because generation is now a network call rather than a GPU workload, the entire system
is a single deployable on the VPS, alongside the existing manhwamaniacs stack. No home
worker, no job-pull protocol, no dependency on the laptop being on.

```
  ┌──────────── VPS (existing Caddy + cloudflared + Docker) ────────────┐
  │  FastAPI + SQLite                                                    │
  │    ingest → chunk → generate → verify      (calls DeepSeek API out)  │
  │    nightly cron: fit memory model on CPU, ~seconds                   │
  │    serving: due-card selection = pure arithmetic                     │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │
                     Next.js review UI   (Flutter later)
```

The laptop is a development machine only. Nothing in production depends on it.

### Module boundaries

Each is independently testable, with the API behind a mockable interface:

| Module | Input → Output | Notes |
|---|---|---|
| `ingest/` | file → chunks + source refs | pure, no network |
| `generate/` | chunk → candidate Q/A | only module that calls DeepSeek |
| `verify/` | candidate → accept/reject + reason | pure, given model responses |
| `memory/` | review history → fitted parameters | pure math, property-testable |
| `schedule/` | card state + params → due set | pure, deterministic |
| `api/` | FastAPI routes | thin |
| `web/` | Next.js review UI | keyboard-driven |

Putting every network call in `generate/` and `verify/`'s adapter means the whole
pipeline can be tested offline against recorded fixtures — which matters, because you
do not want a test suite that costs money to run.

### Export as insurance

`export/` writes the deck to an Anki-importable package (cards, cloze notes, and review
history where it maps cleanly). This lands in **week 2, not week 4** — insurance that
arrives last is not insurance. If the project stalls at any point, the cards and the
revision habit survive in a tool that already works. It costs about an hour and removes
the worst downside of building this instead of just using Anki.

## 5. Data model (SQLite)

```
users          id, name
settings       user_id, new_cards_per_day, daily_review_cap, desired_retention
topics         id, user_id, code, label       -- MATHS, CSE111, INT108, INT335, HTML
sources        id, user_id, topic_id, filename, kind, added_at
chunks         id, source_id, ordinal, text, page_ref
cards          id, chunk_id, topic_id, kind ('qa'|'cloze'),
               question, answer, cloze_text,
               arm ('learned' | 'baseline'),
               state ('pending'|'active'|'suspended'|'rejected')
reviews        id, card_id, user_id, reviewed_at, grade (1-4),
               elapsed_days, predicted_r, scheduler_version
card_state     card_id, user_id, stability, difficulty, due_at, reps, lapses
fit_runs       id, ran_at, n_reviews, params_json, val_logloss
gen_runs       id, source_id, model, prompt_tokens, completion_tokens, cost_estimate
```

Every card carries a `chunk_id`, so any question traces back to the exact page it came
from. A question you can't trace is a question you can't trust. `gen_runs` exists so
API spend is a number you can look at, not a surprise on a bill.

## 6. Question generation (H1)

1. **Ingest** — PDFs via PyMuPDF, slides, markdown, typed notes. Chunk to ~500–800
   tokens with overlap, preserving page references.
2. **Generate** — DeepSeek API, `deepseek-chat` for bulk generation (cheap and fast;
   `deepseek-reasoner` is not worth the cost or latency here). JSON output mode, with a
   schema. Several question kinds per chunk: direct recall, application, comparison,
   "why does this hold" — plus **cloze deletions**, which are cheap to generate, hard to
   get wrong, and among the most effective card types for daily retention.
3. **Verify** — four gates, and this is where the quality lives:
   - **Groundedness.** A judge pass sees chunk + Q + A and must quote the supporting
     sentence. No quote → reject.
   - **Closed-book leakage.** Ask the model the question *without* the chunk. If it
     answers correctly and confidently, the question tests general knowledge rather
     than your course → reject. Cheap, and it catches most trivia.
   - **Deduplication.** Semantic near-duplicates, see below.
   - **Answerability.** One unambiguous answer; no "discuss the following".
   - **Atomicity.** One fact per card. Compound questions — two facts wearing a
     trenchcoat — are the dominant quality failure in generated cards, and they wreck
     scheduling, because a single grade has to stand for two different memories. Reject
     them, or split them into two cards.
4. **Human gate** — a bulk approve/reject queue. Rejections tune the thresholds.

**Deduplication without a GPU.** DeepSeek exposes no embeddings endpoint, so this
needs its own answer. Lexical methods (TF-IDF, MinHash) miss the case that matters —
"what is quicksort's average complexity" versus "how fast is quicksort typically" are
lexically unrelated and semantically identical. Plan: a small ONNX sentence-embedding
model (MiniLM-class, ~90 MB) running **on CPU** during ingest. Thousands of short
questions embed in seconds on two cores, adds no GPU dependency and no per-call cost.
Lexical dedup stays as a cheap pre-filter.

**Cost.** Rough order for one course of ~300 pages: ~1M input and ~300k output tokens
across generation and both verification passes, which at DeepSeek's current rates lands
around **$1**, plus less on cache hits. Several courses across three users over a month
should stay in single-digit dollars. Verify current pricing before trusting this — it
changes, and `gen_runs` tracks the real number regardless.

**Known weakness, stated plainly:** gates 1 and 2 use an LLM to judge an LLM, which is
circular. The closed-book check partially escapes this because it is a *different kind*
of evidence, not a second opinion. Human spot-checks on a random sample stay in the loop
for the whole month — I am not going to pretend the judge is trustworthy on its own.

**Credentials.** The API key lives in a `.env` on the VPS that is never committed, read
via environment variable. Do not paste it into a chat, this one included.

**Third-party data.** Course material and generated questions are sent to DeepSeek's
API. Your own lecture notes are almost certainly fine; just know that is where they go,
and don't feed it anything confidential.

## 7. Memory model and scheduler (H2)

**Base model — FSRS.** Each (card, user) carries stability `S` (days until recall
probability falls to 0.9), difficulty `D`, and retrievability `R(t) = (1 + F·t/S)^-d`.
After each review, `S` and `D` update via parameterised formulas, with different paths
for success and lapse. Parameters are fitted by maximising the log-likelihood of
observed binary recall.

**The extension — hierarchical partial pooling.** Rather than fitting 17 parameters per
user on a month of data:

```
θ_pop  ~ Normal(FSRS defaults, τ²)        population level
θ_u    ~ Normal(θ_pop, σ²)                per user, shrunk toward population
d_c    ~ Normal(μ_topic, ω²)              per card difficulty as a random effect
```

Fit all three users jointly by MAP in PyTorch, **CPU only**. With little data, `σ` stays
small and everyone behaves like the population; as reviews accumulate, users
differentiate on evidence. Card difficulty as a pooled random effect is a step beyond
stock FSRS, where `D` follows a fixed deterministic update.

A few hundred lines, trains in seconds on two cores. Refit nightly by cron on the VPS.

### Daily load control

Daily learning fails in a specific, predictable way: the deck grows, reviews compound,
the daily queue passes half an hour, and you quit in week three. Three controls, all
per-user, all in `settings`:

- **`new_cards_per_day`** — the cap that actually matters. Every new card introduced
  today becomes reviews for months. Default 15; hard ceiling enforced server-side, not
  a suggestion in the UI.
- **`daily_review_cap`** — a hard stop on the daily queue so a backlog after a missed
  week doesn't present you with 400 cards and end the habit.
- **`desired_retention`** — FSRS's target recall probability, default 0.90. Lowering it
  to 0.85 meaningfully cuts review volume at a modest cost in retention. Exposed so a
  heavy week can be survived rather than skipped.

Backlogs are spread rather than dumped: when overdue cards exceed the cap, the excess is
rescheduled across following days instead of stacking.

## 8. Evaluation (H3)

**Assignment.** Every card is randomly assigned at creation to `learned` or `baseline`
(SM-2, fixed intervals), stratified by topic. Assignment is *within* user, so
motivation, time available, and exam pressure cancel out.

**Primary metric — calibration of predicted recall.** For held-out reviews, compare
predicted `p(recall)` against observed outcomes: log-loss, Brier score, and a
reliability curve. This measures the model directly and needs no arm comparison, which
matters because it is the metric most likely to reach significance.

**Secondary — observed recall at matched intervals**, and reviews needed per card to
reach a target stability.

**Splitting, which is where these projects usually cheat.** Hold out **by time** (the
final week) and **by card**. Never split randomly inside a card's own review sequence —
later reviews depend on earlier ones and a random split leaks the answer. Expect the
first honest number to be much worse than the leaky one.

**Power, stated up front:** with 3 users over ~4 weeks, the arm comparison is
underpowered to detect realistic retention differences. Calibration is the metric likely
to be conclusive. Reporting "inconclusive on retention, well-calibrated on prediction"
is a real and acceptable result.

## 9. Milestones

| Week | Deliverable | Done when |
|---|---|---|
| 1 | Ingest + generation + verification pipeline | Several hundred *accepted* questions from one real course, each traceable to a page, with measured API spend |
| 2 | FastAPI + SQLite + Next.js review UI, FSRS with default parameters, daily load caps, Anki export, 3 accounts live on the VPS | All three are reviewing daily — **review collection starts here, and this is the critical path** — and the deck already exports |
| 3 | Hierarchical fit, baseline arm, nightly refit cron | Fitted parameters differ from defaults and improve held-out log-loss |
| 4 | Evaluation, reliability curves, written results; Flutter client if time allows | An honest write-up, including whichever parts failed |

The scheduling of week 2 is deliberate. Every result in weeks 3 and 4 is a function of
how many reviews exist, so the review loop must go live as early as possible even while
ugly. **Data collection is the long pole, not code.**

## 10. Risks

| Risk | Mitigation |
|---|---|
| Too few reviews to fit anything | Start collecting week 2; hierarchical shrinkage degrades gracefully to the population prior; lead with calibration |
| Bad questions kill adoption in week 1 | Verification gates + human approve queue before anyone sees a card |
| API cost runs away | `gen_runs` records tokens and estimated cost per run; a hard per-source cap; generation is a batch job, never in a request path |
| DeepSeek outage or rate limits mid-ingest | Ingest is resumable per chunk; failures leave the source partially generated rather than lost |
| Tests that cost money | All network calls behind one adapter, recorded fixtures in CI |
| Python 3.14 has no torch wheels | Pin Python 3.12 via `uv`; CPU-only torch build. Budgeted in week 1 |
| LLM judging LLM is circular | Closed-book check is independent evidence; human spot-checks all month |
| VPS is already shared | Small footprint: SQLite + a CPU fit measured in seconds. Watch RAM against the MC bots and manhwamaniacs |
| Exam dates don't align with the month | Usage may be uneven; report review counts honestly rather than smoothing them |
| MATHS is derivation-heavy, where flashcards help least | Start ingest with the recall-heavy courses; treat MATHS cards as a formula/condition layer under practice, never a replacement for solving problems |
| Friends stop using it | 3 users is fragile by construction. Keep the daily loop under 10 minutes |

## 11. Environment (probed 2026-09-04)

- **No GPU is used.** The laptop's RTX 5070 (8 GB) goes untouched; the RTX 3090 Ti on
  the other machine is out of scope entirely.
- Docker, node (v22 userspace), git present on the laptop. `~/code` is empty; the
  project lives at `~/code/recall`.
- **Only Python 3.14.7 is installed**, with no `pip`, `uv`, or `conda` on PATH. PyTorch
  publishes no 3.14 wheels — install `uv` and pin 3.12 for the backend environment.
- VPS: 2 vCPU / 3.8 GB RAM, Ubuntu 26.04, already running the MC bots and manhwamaniacs
  behind a shared Caddy + cloudflared. Recall joins as another compose project on that
  network. Storage need is small (SQLite + source PDFs, a few GB); the 50 GB disk at
  `/srv/manhwamaniacs` is dedicated to that project, so Recall's state goes on the
  system disk unless you decide otherwise.

## 12. Deferred

- Flutter client with offline review queue (reuse the progress-outbox pattern from aistudio).
- Image/diagram questions.
- Handwriting OCR ingest.
- Sharing decks between users — currently each user's cards are their own.
