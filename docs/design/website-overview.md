# Recall — website overview for redesign

Live at **study.yashnas.xyz**. A private exam-prep web app for first-year B.Tech students at LPU (Lovely Professional University): the owner (Yash) plus a few friends, all on the same Semester-1 courses. Open signup but not a public product: 2–10 real users. A tool someone opens every morning for four years, not a landing page.

Companion handoff page with screenshots (private): https://claude.ai/artifact/Lire7QeS95fBZvyzqmvu6r

## What it does

1. **Ingest** course material: uploaded PDFs, typed notes, phone photos of slides (Tesseract OCR). With nothing uploaded, cards can be written from the model's own knowledge of a syllabus unit ("knowledge mode").
2. **Generate flashcards** (Q&A + cloze) through a verification pipeline: grounded in a verbatim quote, checked answerable and atomic, de-duplicated. Every card is model-authored and says so.
3. **Review** daily with FSRS 4.5: Again / Hard / Good / Easy, each button showing the interval it would set.
4. **Sit papers** shaped like LPU's exams: 30-mark class test (45 min), 40-mark mid-term (90 min, units 1–3), 100-mark end term (3 h), untimed "full day". Self-marked correct / partial / wrong / skipped (partial only on 2+ mark questions); every answer feeds the scheduler.
5. **Read lessons**: one per unit, AI-written offline via the CLI (no button, by design), with a coverage meter showing how much quotes the student's own material.
6. **Being built now: "Yash Made Test"**: a curated MCQ bank any user can sit, reshuffled per attempt, instant green/red reveal with a teaching note, per-topic breakdown, personal history, class leaderboard. Spec below. Nothing in it feeds the scheduler.

**Users:** 17–19, studying at night in a hostel; phone and laptop both matter. **Subjects** (`src/recall/lpu.py`; the picker must match these facts):

| Code | Name | Cr | Format | Units | ATT/CA/MTE/ETE | Notes |
|---|---|---|---|---|---|---|
| MTH165 | Mathematics for Engineers | 4 | mixed | 6 | 5/25/20/50 | CT1 units 1–2 · CT2 unit 4 · CT3 cumulative |
| CSE111 | Orientation to Computing | 3 | mcq | **7** | 30/70/0/0 | **no MTE, no ETE** — fully CA-driven; scheme unconfirmed (UI says so) |
| INT108 | Python Programming | 4 | practical | 6 | 5/50/0/45 | **no MTE**; best 3 of 4 CA |
| INT335 | Design Thinking | 2 | mcq | 6 | 5/25/20/50 | best 2 of 3 CA |
| MEC103 | Engineering Graphics | 3 | subjective | 6 | 5/25/20/50 | weights **unconfirmed** placeholder (UI says so) |
| CSE326 | Internet Programming | 2 | mixed | 6 | 5/45/0/50 | **no MTE**; best 2 of 3 CA |

Only MTH165, INT335 and MEC103 have a mid-term. **Latency:** server in Virginia, users in Punjab; every screen has a skeleton, a stale-while-revalidate cache, prefetch on hover. **Money:** generation costs API money ($1/user/day cap, 429 when over); every paid press is a separate explicit step. **Honesty rules:** AI text is always marked; cards with no uploaded source carry a second "no source" mark; a wrong exam structure shown as fact is treated as worse than none.

## Information architecture

Left sidebar (`--nav-w: 13rem`; collapses to a 3.25 rem rail, remembered per browser; off-canvas drawer below 768 px behind a 32 px `≡` button). Header row h-11: wordmark RECALL (11 px bold, 0.16 em; "R" when collapsed) + ‹/› collapse. Nav rows 13 px, h-9; active = semibold + surface-hover bg + a 4×16 px accent bar. Footer: "mock data" chip (dev), skin switcher (10 px mono caps), theme toggle (Ember only), `?` keycap (hidden below 640 px), "SIGN OUT · name" (⏻ when collapsed). No top header bar; before the session is known the shell shows only "signing in…".

| Route | Nav | What is on it | Chrome |
|---|---|---|---|
| `/` | Today | Five-figure metric strip (Due · New with budget bar · Reviewed today with cap ring · Again today · Day streak), one cap sentence, "By topic" table (rows open a topic-scoped review), 14-day bars with cap line, "Constellation" (one ring per subject, practice × retention), reviewed-today list, collection totals. Primary: **Start review N ↵** (accent gradient + faint glow), or "All clear" + streak ring, or "Cap reached for today". | sidebar |
| `/review` | Review | Focus mode. 2 px progress hairline, "1 / 50", Esc. One card on a "Flow Stack" (next two peek beneath). Provenance chips (topic · page, AI, no source, leech). Question → rule → answer → optional working. Footer: Show answer, then four grade buttons with keycap + interval. Cloze blanks flash on fill. End: session summary (held %, grade counts, per-topic, keep going / back). | none |
| `/learn` | Learn | One panel per subject listing all syllabus units, written or not; chips grounded / unverified + date. Empty state prints the CLI command (no button, by design). | sidebar |
| `/learn/[topic]/[unit]` | — | Reader: one measured column; chips, unit title, coverage meter + one-sentence warranty, "why" lede, numbered sections tagged *cited* (with verbatim quote block + file/page) or *model only*, two worked examples with all steps visible, "Check yourself" with hidden answers. Esc back, `r` review subject. | sidebar |
| `/test` | Test | Picker. Unfinished-papers banner (resume / close). Subject rail: card per subject with LPU weight-split bar (ATT→ETE ink ramp), credits, exam format, CA policy, study-plan advice, units disclosure (tick to scope, quiet per-unit *generate* link), chips that ARE start buttons (CA always, MTE only where LPU sets one, ETE only where it has weight). Below: cross-subject radio cards (class / end term / full day), "what this paper will contain" table, scoring, past papers, Start. | sidebar |
| `/test/[id]` | — | Exam session (focus): bar with Esc, paper name, answered count, saved dot, clock with draining ring (amber at 20 %, red at 5 %), Submit. Question with marks/topic/page/kind; reveal model answer; Wrong / Partial / Correct with marks; Skip, Mark, prev/next. Right rail: question palette (answered tinted, skipped struck, marked dotted, current ringed), legend, Submit paper, marks attempted, short-paper warning. Submit dialog: answered / skipped / never opened / marks. | none → sidebar |
| `/test/[id]` (result) | — | Display numeral "3.5 / 30 · 12 %", duration + verdict line, per-topic table sorted weakest first with held-% bars, "What to fix" list (red rail wrong, amber partial) with **Explain this** → violet "synapse rail": explanation, verbatim quote, page ref, cached note. `j k` move, `e` explain. | sidebar |
| `/upload` | Upload | "File it under" topic select (or new), drop zone with **Choose files** `f` / **Take a photo** `c` (back camera), per-file rows: progress bar, chunk/char counts, OCR warning, then Generate cards → "Spend it" confirm → running shimmer → done with counts + cost. Side panels: the three steps, OCR limits. | sidebar |
| `/sources` | Sources | Sortable table: file, topic, added, accepted, rejected, kept-% bar, cost; totals row. | sidebar |
| `/settings` | Settings | Three sliders + number inputs, save-as-you-move (Saving → Saved tick): new/day, daily cap, desired retention, each with a plain cost sentence. "Deep focus": Zen mode drone switch with six-bar visualizer. | sidebar |
| `/login` `/signup` | — | Only public screens: wordmark, one line, small panel, one accent button, swap link. | none |

Global overlays: command palette (Ctrl/⌘ K; 560 px `.glass` panel at 14 vh over a 4 px-blurred scrim — under Phosphor the panel adds the one 12 px glass blur; sections Navigate / Session / Theme with keycap hints at the right), shortcuts sheet (`?`, two-column groups), one toast at a time bottom-centre above the safe-area inset (h-10 pill, 6 px good/again dot, 3.5 s), submit dialog. Film grain over the viewport: 2.5 % (Phosphor, Ember light), 3.5 % (Ember dark), 0 (GitHub).

## Screen states (design each)

1. Today: normal · nothing due (All clear + streak ring) · cap reached · loading · error · no topics
2. Review: question · revealed · cloze · graded flash (pulse ring / headshake) · leech · unsaved retry · queue empty · summary
3. Learn: index · nothing written · reader grounded / unverified · section cited / model only · worked "not confirmed" · check yourself
4. Test picker: normal · unfinished paper · units ticked · generate writing/+12/failed · chip refused (422) · subject with no cards · weights not confirmed
5. Exam session: unrevealed · revealed · verdict chosen · marked · clock warn/danger · palette sheet (small screens) · submit dialog · already submitted · no questions · short paper
6. Result: normal · nothing missed · explanation loading / shown / no quote / error · time expired
7. **Yash Made Test picker**: normal · unit waiting for material · attempts empty · leaderboard empty · resume open attempt
8. **MCQ sitting**: unanswered · right · wrong with why-wrong · last question · finish early
9. **MCQ result**: normal · finished early (unanswered in missed list) · nothing answered (rank null) · retake
10. Upload: idle · no topic · drag over · uploading · done · rejected · OCR warning · generate confirm / running / done / error (503 no key)
11. Sources: table · empty. 12. Settings: saving / saved / not saved / zen on. 13. Login/Signup: normal · error · busy
14. Global: sidebar full / rail / drawer · palette · shortcuts · toasts · "signing in…" blank

## Design system today

Tokens are CSS custom properties on `<html data-skin data-theme>`, exposed to Tailwind v4 (`text-fg`, `bg-surface`, `border-line`, `text-good` …). Three **skins** redefine the same semantic tokens; cycle order Phosphor → GitHub → Ember; **default is Phosphor** (`web/app/layout.tsx`).

**The brief the current design was built to** (docs/CONTRACT.md): Anki's density, Linear's restraint, a terminal's calm. Near-monochrome; one accent only on the primary action, focus ring, active nav marker; grade buttons are the exception because colour is the meaning. One type family, hierarchy by size/weight. Radii 2–6 px, borders not shadows, flat. Almost no motion (card flip + queue advance, <150 ms). The review screen is the product and nearly empty. Keyboard first, keycaps on the buttons. Every card shows its source. Empty states: one plain sentence, no illustration. Forbidden: purple/indigo gradients, glassmorphism, blurred blobs, centred gradient heroes, emoji, rounded-2xl, shadows everywhere, untouched shadcn.

**Phosphor** (default, committed dark, "cyber-academic"): void `#060810`, layers `#0c101b` `#121828` `#171e31`; ink `#e9edf8` `#a5aec7` `#67718d`; lines steel at 11 % / 20 %. Ion cyan `#7de3f4` = the user's light (accent, easy); synapse violet `#a78bfa` = the AI's; bio `#6ee7a0` good, amber `#fbbf24` hard, flare `#fb7185` again. Newsreader serif for knowledge text, Inter for UI, JetBrains Mono for telemetry/labels/provenance (the Google Fonts link is loaded on every skin in `layout.tsx`; only this skin's `--font-sans/--font-mono/--k-face` use the faces). Labels become mono caps at 0.12 em. Laws: accent light ≤ 8 % of viewport, glow alpha ≤ .35, glass only on palette + transient overlays (12 px max, always with hairline), neon never body text. Light/dark toggle inert. Film grain 2.5 %.

**GitHub** (flat dark): `#0d1117` / `#161b22` / `#1c2128`, borders `#21262d` `#30363d`, ink `#e6edf3` `#7d8590` `#6e7681`, accent `#2f81f7` (hover `#58a6ff`), grades `#f85149` `#d29922` `#3fb950` `#58a6ff`, AI `#a371f7`. No grain, no serif, borders do the work.

**Ember** (light "paper" / dark "graphite"): bg `#faf9f6` / `#16151a`, surface `#fff` / `#1d1c22`, line `#e3e1d9` / `#2d2c34`, ink `#1b1a17` `#57554d` `#8a877c` / `#ebe8e2` `#a29fa8` `#726f7a`. Accent ember `#b04525` / `#e07a52`. Grades again `#a92f21`, hard `#86601a`, good `#2f6b3c`, easy `#2c5a86` (dark: `#ef8175` `#d6a556` `#74bf83` `#7fb0da`), each with a quiet tinted bg. AI violet `#6b4fa3` / `#9d8bcf`. System sans; system mono for keycaps, telemetry, provenance chips and the sidebar footer buttons. Film grain 2.5 % / 3.5 %. Elevation ladder bg → surface → raised → overlay with a luminous top hairline in dark. The only skin where `t` cycles system / light / dark.

**Type scale (all skins):** body 14 px/1.5 · h1 18 px 600 · `.label` 10 px 600 0.09 em uppercase · `.k-question` clamp(21–26 px) 500 · `.k-answer` 17 px · `.k-display` clamp(34–44 px) tabular · `.k-ai` italic in ink (never violet) · `.telemetry` 12.5 px mono tabular · `.prov` 11 px mono pill (`.prov--ai` is the only violet) · `.kbd` 10 px mono with 2 px bottom border · metric numerals 22/26 px tabular, −0.02 em.

**Shape/depth/motion:** radii 2 / 3 / 5 px (Phosphor review card 20 px); `.elev-1/2/3`, `.glass`; `.glow-behind` bloom + `.accent-grad` on the primary action; `.anim-reveal` 110 ms; springs (`motion`) for numbers/rows/bars; card exit 240 ms; correct = 700 ms pulse ring, again = 4 px headshake; skeletons shimmer, nothing spins; all collapse under reduced motion. Errors: red left rail + "Try again". Toast: one at a time, bottom-centre.

**Components (`web/components`, `web/components/rich`, per-route files):** Panel, Metric, MetricStrip, ActivityChart, Constellation, ProgressRing, AnimatedNumber, Reveal, Skeleton, Toast, CommandPalette, ShortcutsOverlay, Kbd (grade tone), TopicCode, KindTag, Provenance (AI / no source), StatusChip, Warranty (coverage meter), SubjectRail (scheme bar), QuestionPalette + PaletteLegend, HeightSpring, ZenVisualizer, Loading / ErrorState / EmptyState. No icon set anywhere.

## Keyboard map

Anywhere: `?` sheet · Ctrl/⌘ K palette · `g` then `d r l t u o s` · `\` rail · `t` theme (Ember only). Today: ↵ start. Review: Space reveal then Good · 1–4 grades · Esc. Picker: 1–3 paper kind · ↵. Paper: Space · 1/2/3 wrong/partial/correct · `s` skip · `m` mark · `j k ← →` · Home/End · `p` palette · ↵ submit · Esc leave (all saved). Result: `j k e`. Lesson: Esc, `r`. Upload: `f`, `c`. Settings: Tab, ↑↓. Shortcuts ignored in text fields.

## NEW: Yash Made Test (spec frozen in docs/CONTRACT.md + web/lib/types.ts; no code yet)

Second test mode behind a segmented switch at the top of `/test` (**Recall | Yash Made Test**, remembered per browser). A shared, hand-curated bank (same for every user); every attempt draws `min(length, available)` questions without replacement and shuffles each question's four options; the client only ever sees shown order. Nothing feeds the scheduler.

- **Subjects/units** come from a registry (`recall.mcq.registry.MCQ_UNITS`) that is **not written yet** — no unit labels or counts exist anywhere; do not design around specific ones. The contract only fixes the shape: every registered unit appears on the picker with its `count` of active questions, and count 0 renders "waiting for material" and cannot start. CSE111 is the first subject planned. Counts come from the seeded bank; nothing is fixed at 100. Lengths **30 · 60 · full**. Questions have a short topic label (e.g. "Linux"), kind *recall* | *situation*, 4 options, `explain` (2–4 sentences), `why_wrong` per option.
- **Picker:** subject → unit chips with counts (units may combine) → length → Start. "Your attempts" (score, length, date; resume open; close abandoned). **Class leaderboard** for exactly that subject+units+length: each user's best submitted attempt, name, score, %, duration, when; ranked by % then shorter time; top 25.
- **Sitting:** "Question 12 of 30", topic, kind, question, options A–D (keys 1–4 / A–D). First click is the answer; second click on that position is refused (409). Immediate reveal: chosen red if wrong + correct green (green if right), explanation, and when wrong the why-wrong note for the option picked. Running "correct so far". Next; **Finish & see score** any time: unanswered score 0 out of the number drawn (12/30 after twelve is an honest 12/30).
- **Result:** score/total, % (`round(100·score/total)`), duration, `by_topic`, **missed** = wrong OR unanswered (`chosen: null`) in attempt order with options/chosen/correct/explain/why_wrong, `rank {position, of}` on that selection's board (null if nothing answered), Retake (reshuffled), Back. The contract fixes no verdict line and no colour thresholds for topic bars; those are design decisions.
- **Endpoints:** GET `/api/mcq/subjects` · POST `/api/mcq/attempts` {subject_code, units, length} (422 bad selection / zero questions) · GET `/api/mcq/attempts/{id}` (404 not yours) · POST `…/answer` {position, chosen} → McqFeedback (409 / 422) · POST `…/submit` → McqResult · DELETE `…` (409 once submitted) · GET `/api/mcq/attempts` (mine, newest first) · GET `/api/mcq/leaderboard?subject_code=&units=1,2&length=30`.
- Wire shapes: `McqSubject {subject_code, label, units:[{unit,label,count}], lengths}`, `McqQuestion {position, topic, kind, question, options×4, answer: McqFeedback|null}`, `McqFeedback {position, chosen, correct_index, is_correct, explain, why_wrong ("" when right), answered, correct_so_far}`, `McqAttempt {attempt_id, subject_code, units, length, total, started_at, submitted_at, questions}`, `McqResult {attempt_id, score, total, answered, percent, duration_s, by_topic, missed, rank}`, `McqAttemptSummary`, `McqLeaderboardRow {user_id, name, score, total, percent, duration_s, submitted_at}`.
- Sitting route not fixed by the contract; `/test/mcq/[id]` is the working proposal.

## What a redesign must keep

Keyboard model + keycaps on controls; Esc always leaves, everything already saved. Review and exam own the viewport; result brings nav back. Grade/verdict colours pair with position + keycap (red-green safe). AI text visibly marked; "no source" a separate uncoloured mark; grounded vs unverified never look alike. Provenance on every card. Money explicit; generate never looks primary. Phone portrait for review, MCQ sitting, camera upload, picker; ≥ 44 px thumb targets. Skeleton per screen, no reflow on load; reduced motion. Empty/error states = one sentence + next step. No emoji, gradient heroes, glass stacks, centred body text.

## Where the current design is weakest

- Three skins is two too many; pick one identity and finish it.
- The Test picker carries too much (banner + 6 dense subject cards + paper cards + contents + scoring + past papers); the Recall | Yash Made Test switch makes hierarchy job one.
- Exam session is dense; the MCQ sitting should feel lighter and faster, not identical.
- Mobile collisions: 32 px ≡ button over page titles (under the product's own 44 px rule; the `?` keycap vanishes below 640 px); picker becomes a very long scroll; constellation and 14-day chart lose labels.
- Stale bits: the palette still lists "Go to Approve", lacks "Go to Learn", its skin action only knows Ember/Phosphor (not GitHub), and its Theme actions stay listed (inert) under the committed-dark GitHub skin (`web/lib/palette.ts`, `web/components/AppShell.tsx`); Upload has two dead links to `/approve` and its "What happens" step 3 promises "Nothing enters your rotation until you say so" — the approval gate was removed (`web/app/upload/page.tsx`); the "AI" chip is on every card (every card is model-written), so it carries no information.
- Lots of 10–11 px mono micro-copy on cards read at arm's length at night.
- Today is a report ("how much"), not an instruction ("what first").

## Stack / constraints

Next.js 16 App Router, React 19, Tailwind v4 (tokens in `web/app/globals.css` via `@theme inline`), `motion` springs; all pages client components. FastAPI + SQLite same origin at `/api/*`; contract `docs/CONTRACT.md`, types `web/lib/types.ts`; mock backend `NEXT_PUBLIC_MOCK=1` renders every screen (used for the captures; `recall-web-mock` in `~/.claude/launch.json`, port 3111). Theming via `data-skin` / `data-theme` on `<html>`, applied before first paint. Fonts: one Google Fonts link (Newsreader, Inter, JetBrains Mono) loaded on every skin but used only by Phosphor; Ember and GitHub sit on system stacks; new faces need real fallbacks. Base body 14 px. Breakpoints: sm 640 / md 768 (sidebar) / lg 1024 (exam palette aside, two-column grids) / xl 1280 (3-column subject rail). Sidebar geometry is CSS-owned (`--nav-w: 13rem`, rail `3.25rem`, breakpoint 768 px).
