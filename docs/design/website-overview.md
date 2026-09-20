# Recall — website overview for redesign

Live at **study.yashnas.xyz**. A private exam-prep web app for LPU (Lovely Professional University) first-year B.Tech students — the owner (Yash) plus a few friends. Open signup, but not a public product: 2–10 real users, all on the same six Semester-1 courses.

## What the product does

1. **Ingest** course material — uploaded PDFs / phone photos of slides (OCR), or a unit written from the model's own knowledge of the LPU syllabus.
2. **Generate flashcards** that are verified before they reach the student (grounded in the source, fact-checked).
3. **Review** them daily with a spaced-repetition scheduler (FSRS-style, fitted to the user).
4. **Sit practice papers** shaped like LPU's real exams (30-mark class test, 40-mark mid-term, 100-mark end term), self-marked, results fed back into the scheduler.
5. **Read lessons** per unit, AI-written and grounded, when a topic is not understood.
6. **NEW — "Yash Made Test"**: a hand-curated MCQ bank (100 questions per unit) any user can sit; shuffled every attempt, instant right/wrong feedback with a detailed explanation, per-topic breakdown, class leaderboard. Being built now, described fully below.

## Who uses it and where

- Students, 17–19, studying at night in a hostel. Phone on Wi-Fi and laptop both matter; the camera-upload flow is phone-first.
- Server is in Virginia, users are in Punjab — perceived speed matters. Screens use skeletons and a stale-while-revalidate cache so navigation feels instant.
- Desktop users are keyboard-first: grading with 1–4, `g` + letter to jump between pages, Ctrl/Cmd+K command palette, full-focus review mode that hides the header.

## Stack (for what is realistic to change)

Next.js 16 (App Router) + Tailwind v4 + `motion` for springs. FastAPI + SQLite behind the same origin (`/api/*`). Everything is server-rendered shell + client components; theming is CSS custom properties on `<html data-skin data-theme>`.

## Information architecture

Left sidebar (collapsible to an icon rail; a drawer on mobile) with seven entries, in this order:

| Route | Name | What is on it |
|---|---|---|
| `/` | Today | Cards due now, streak, today's load vs the daily cap, one mastery ring per subject ("constellation"), primary "Start review" action. |
| `/review` | Review | One card at a time: question → reveal → grade **Again / Hard / Good / Easy** (keys 1–4), suspend, "explain this". Full-focus layout, header hidden. Cloze cards render inline blanks. |
| `/learn` | Learn | Subject → unit → a multi-page lesson. Reader with page navigation; AI-written content is visually marked. |
| `/test` | Test | **Picker:** subject rail (six subjects, each with chips for the exam types it really has — CA / MTE / ETE — and tick-boxes for units covered in class), then paper type (30-mark class test · 40-mark MTE · 100-mark end term · full day), open/unfinished papers, "Sit paper". **Session** (`/test/[id]`): clock, question palette, each question self-marked correct / partial / wrong / skipped, with the worked answer shown after marking. **Result:** marks, %, per-topic bars, lists of wrong and partial answers with "explain this". |
| `/upload` | Upload | Drop a PDF or take a photo → OCR → text preview → generate cards (a separate, paid press). |
| `/sources` | Sources | Every uploaded file with its generation run: cards kept / rejected, cost. |
| `/settings` | Settings | New cards per day, daily review cap, desired retention; skin + theme toggles live in the sidebar footer. |
| `/login`, `/signup` | — | The only public screens. |

Global chrome: sidebar footer holds the skin toggle and theme toggle; toasts bottom-right; command palette (Cmd/Ctrl+K) lists every page and action.

## NEW: "Yash Made Test" — the area being added

Lives inside **Test** behind a segmented switch at the top of the page: **Recall | Yash Made Test**. The choice is remembered.

**Picker**
- Subject (CSE111 "Orientation to Computing" first; more later).
- Unit chips: **Unit 1** (100 questions) · **Unit 2** (100, coming — shows "waiting for material" until seeded) · **Units 1–2 combined** (200).
- Length chips: **30** · **60** · **Full**.
- Start button.
- "Your attempts": recent sittings with score, length, date, and a resume link for an unfinished one.
- **Class leaderboard**: best score per person for the chosen unit/length, name + % + when.

**Sitting** (`/test/mcq/[id]`)
- One question at a time. Topic tag (e.g. "Linux & WSL"), "Question 12 of 30", question text, four options A–D (keys 1–4 / A–D). Some questions are short scenarios ("You are in /home/student and run …").
- Click an option → it turns **green** if correct; if wrong it turns **red** and the correct one turns green. Below: a 2–4 sentence explanation of the right answer, plus one line on *why the option you picked* is wrong.
- Progress bar with "correct so far", **Next question**, and **Finish & see score** available at any point.

**Result**
- Big score (e.g. 24/30) and %, one-line verdict, per-topic bars (green ≥80%, amber ≥50%, red below), list of missed questions with their explanations, leaderboard position, **Retake (reshuffled)**, **Back**.

## Current design system (what exists today)

Two skins, switchable in the sidebar footer:

**Ember** (default): light "paper" / dark "graphite" pair.
- Ground `#faf9f6` (paper) / `#16151a` (graphite, deliberately not black); surfaces one step lighter; hairline rules `#e3e1d9` / `#2d2c34`; ink `#1b1a17` / `#ebe8e2` with two muted steps.
- **One accent — ember `#b04525`** (dark `#e07a52`) — spent only on the primary action, the focus ring, and the active nav marker. Nothing else is coloured.
- Exception: the four grade colours (again red · hard amber · good green · easy blue, each with a quiet tinted background) — colour is the meaning there.
- **AI voice** violet `#6b4fa3`: marks content the model produced (lessons, explanations). Never used for anything the user does.
- Radii are tiny (2–5 px). Elevation is a system: bg → surface → raised → overlay, each with a slightly stronger ambient shadow and a luminous top hairline in dark. A faint film grain sits over the ground.
- Typography: a single sans for UI; mono for subject codes and keyboard hints.

**Phosphor**: a committed-dark "cyber-academic" skin — void-scale surfaces, **ion cyan** as the user's light, **synapse violet** for AI-only content, verdict colours bio (right) / flare (wrong). Serif (Newsreader) for the knowledge text — questions, answers, explanations — Inter for UI, JetBrains Mono for code. Rules it lives by: a 90/8/2 emission budget (90% dark surface, 8% cool light, 2% hot accent), at most two layers of glass, motion only when physics justifies it.

Shared components: AnimatedNumber (springs to a value), ProgressRing (SVG arc), Reveal (fade-and-lift with 40 ms stagger), Skeleton, Toast, CommandPalette, Panel, Metric (label + big number), TopicCode, KindTag, Kbd, EmptyState / ErrorState / Loading.

## Constraints a redesign must keep

- Keyboard flows: 1–4 grading, 1–4 / A–D answering MCQs, `g`+letter navigation, Cmd/Ctrl+K palette, Esc to leave focus mode.
- Single-accent discipline; grade/verdict colours carry meaning and must stay distinguishable (also for red-green colour-blindness — pair colour with position/icon).
- AI-produced content must stay visibly distinct from the user's own material.
- Works on a phone in portrait: review, MCQ sitting and camera upload are the phone flows.
- Fast first paint; every screen has a skeleton state.
- No emoji, no purple-to-blue gradient heroes, no glassmorphism stacks, no centred body text.

## Where the current design is weakest (honest notes)

- The Test picker carries a lot at once — subject rail, exam-type chips, unit ticks, open papers — and the new Recall | Yash Made Test switch adds a second mode on top. This screen most needs a clear hierarchy.
- Two skins (Ember, Phosphor) each with their own rules is a lot to maintain; a redesign could pick one identity and do it fully.
- The exam session and result screens are dense (palette + clock + marking + working); the MCQ sitting should feel lighter and faster than the self-marked paper, not identical to it.
- Dashboard mastery rings read well on desktop but stack awkwardly on phones.

## Screens to design (with states)

1. Today — normal · nothing due · loading · error
2. Review — question · revealed · graded flash · queue empty · suspended toast
3. Learn — subject/unit index · reader page · generating lesson · empty
4. Test picker (Recall mode) — normal · unfinished paper present · subject with no cards
5. Test session — answering · marked · time nearly up · submitted
6. Test result — normal · perfect score · nothing answered
7. **Yash Made Test picker** — normal · Unit 2 not yet available · leaderboard empty
8. **MCQ sitting** — unanswered · answered right · answered wrong (with why-wrong note) · last question
9. **MCQ result** — normal · partial (finished early) · retake
10. Upload — idle · OCR running · text preview · generating · done
11. Sources — list · empty
12. Settings — normal · saved toast
13. Login / Signup — normal · error
14. Global — sidebar full / rail / mobile drawer · command palette · toasts
