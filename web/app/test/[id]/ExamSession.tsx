"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFocusMode } from "@/components/AppShell";
import { ClozePrompt, clozeShowsAnswer } from "@/components/CardText";
import { Kbd, KindTag } from "@/components/ui";
import {
  errorMessage,
  getTest,
  getTests,
  postAnswer,
  submitTest,
} from "@/lib/api";
import { parseCloze } from "@/lib/cloze";
import { formatDuration, mediumDate, plural } from "@/lib/format";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import { PAPER_LABEL, scoreFor } from "@/lib/marks";
import type { TestPaper, TestResult, TestSummary, Verdict } from "@/lib/types";
import {
  PaletteLegend,
  QuestionPalette,
  type PaletteState,
} from "./QuestionPalette";
import { ResultView } from "./ResultView";

/**
 * Worst to best, left to right, and keyed 1/2/3 so the fingers that learned the
 * review screen already know them: 1 is again/wrong, 2 is hard/partial, 3 is
 * good/correct. That is also exactly the grade the server records.
 */
const VERDICTS: {
  verdict: Verdict;
  key: string;
  label: string;
  tone: "again" | "hard" | "good";
  /** Partial credit is only offered where the contract allows it. */
  minMarks: number;
}[] = [
  { verdict: "wrong", key: "1", label: "Wrong", tone: "again", minMarks: 1 },
  { verdict: "partial", key: "2", label: "Partial", tone: "hard", minMarks: 2 },
  { verdict: "correct", key: "3", label: "Correct", tone: "good", minMarks: 1 },
];

/** Under five minutes the clock stops being furniture. */
const URGENT_S = 300;

function clock(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** Marks print as 7 and 7.5, never 7.0. */
function marks(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/* --- what the server does not store -------------------------------------- */

interface Scratch {
  marked: number[];
  current: number;
}

/**
 * Mark-for-review and the question you were on are navigation aids, not
 * answers, so the contract has nowhere to put them. They live in this browser
 * instead — which is enough, because a paper is resumed on the machine it was
 * started on, and losing them costs nothing that was graded.
 */
function scratchKey(id: number): string {
  return `recall.test.${id}`;
}

function readScratch(id: number): Scratch | null {
  try {
    const raw = localStorage.getItem(scratchKey(id));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Scratch>;
    return {
      marked: Array.isArray(parsed.marked)
        ? parsed.marked.filter((n): n is number => typeof n === "number")
        : [],
      current: typeof parsed.current === "number" ? parsed.current : 1,
    };
  } catch {
    return null;
  }
}

interface PendingAnswer {
  ordinal: number;
  verdict: Verdict;
  seconds: number;
}

export function ExamSession({ id }: { id: number }) {
  const router = useRouter();
  const [paper, setPaper] = useState<TestPaper | null>(null);
  const [startedMs, setStartedMs] = useState<number | null>(null);
  /** Set when this paper was already submitted before the page was opened. */
  const [finished, setFinished] = useState<TestSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const [current, setCurrent] = useState(1);
  const [verdicts, setVerdicts] = useState<Record<number, Verdict | null>>({});
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [marked, setMarked] = useState<Set<number>>(new Set());
  const [visited, setVisited] = useState<Set<number>>(new Set());

  const [unsaved, setUnsaved] = useState<PendingAnswer[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [paletteOpen, setPaletteOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<TestResult | null>(null);
  const [expired, setExpired] = useState(false);

  const [now, setNow] = useState(0);

  // Time on each question is accumulated across visits, so leaving a question
  // and coming back reports the total thinking time rather than the last look.
  // Set when the paper opens; nothing reads it before then.
  const enteredAt = useRef(0);
  const spent = useRef<Record<number, number>>({});
  const submitted = useRef(false);

  // Claimed while the paper is opening too, so the header does not flash in
  // and out between the loading line and the first question.
  useFocusMode(result === null && finished === null && loadError === null);

  /* --- load ------------------------------------------------------------- */

  useEffect(() => {
    let live = true;
    // The paper itself carries no start time, so the clock comes from the
    // index. If the index is unreachable the paper still opens; only the
    // countdown loses its anchor.
    Promise.all([getTest(id), getTests().catch((): TestSummary[] => [])])
      .then(([p, list]) => {
        if (!live) return;
        const summary = list.find((t) => t.id === id) ?? null;
        const started = summary ? Date.parse(summary.started_at) : NaN;

        const seen = new Set<number>();
        const v: Record<number, Verdict | null> = {};
        for (const q of p.questions) {
          v[q.ordinal] = q.verdict;
          if (q.verdict) seen.add(q.ordinal);
        }

        const scratch = readScratch(id);
        const resumeAt =
          scratch && p.questions.some((q) => q.ordinal === scratch.current)
            ? scratch.current
            : (p.questions.find((q) => !q.verdict)?.ordinal ?? 1);

        setStartedMs(Number.isNaN(started) ? Date.now() : started);
        setFinished(summary && summary.duration_s ? summary : null);
        setVerdicts(v);
        setRevealed(seen);
        setVisited(new Set([...seen, resumeAt]));
        setMarked(new Set(scratch?.marked ?? []));
        setCurrent(resumeAt);
        setPaper(p);
        setNow(Date.now());
        enteredAt.current = Date.now();
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if (live) setLoadError(errorMessage(err));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [id, reloadNonce]);

  useEffect(() => {
    if (!paper || result) return;
    try {
      localStorage.setItem(
        scratchKey(id),
        JSON.stringify({ marked: [...marked], current } satisfies Scratch),
      );
    } catch {
      /* private mode, or storage disabled — the answers are on the server */
    }
  }, [id, paper, marked, current, result]);

  /* --- the clock -------------------------------------------------------- */

  const limitS = paper?.time_limit_s || null;
  const deadline = limitS && startedMs !== null ? startedMs + limitS * 1000 : null;
  const remainingMs = deadline !== null && now > 0 ? deadline - now : null;

  /* --- moving around ---------------------------------------------------- */

  const questions = useMemo(() => paper?.questions ?? [], [paper]);
  const question = questions.find((q) => q.ordinal === current) ?? null;

  const goTo = useCallback(
    (ordinal: number) => {
      if (ordinal === current) return;
      spent.current[current] =
        (spent.current[current] ?? 0) + (Date.now() - enteredAt.current);
      enteredAt.current = Date.now();
      setCurrent(ordinal);
      setVisited((v) => new Set(v).add(ordinal));
    },
    [current],
  );

  const step = useCallback(
    (delta: number) => {
      if (questions.length === 0) return;
      const i = questions.findIndex((q) => q.ordinal === current);
      const next = questions[Math.min(questions.length - 1, Math.max(0, i + delta))];
      if (next) goTo(next.ordinal);
    },
    [questions, current, goTo],
  );

  /** Save-and-next: the following question, or the first one still open. */
  const advance = useCallback(() => {
    const next = questions.find((q) => q.ordinal > current);
    if (next) {
      goTo(next.ordinal);
      return;
    }
    const open = questions.find(
      (q) => q.ordinal !== current && !verdicts[q.ordinal],
    );
    if (open) goTo(open.ordinal);
  }, [questions, current, verdicts, goTo]);

  /* --- answering -------------------------------------------------------- */

  const answer = useCallback(
    (verdict: Verdict) => {
      if (!question || result) return;
      if (verdict === "partial" && question.marks < 2) return;

      const ordinal = question.ordinal;
      const seconds = Math.max(
        1,
        Math.round(
          ((spent.current[ordinal] ?? 0) + (Date.now() - enteredAt.current)) /
            1000,
        ),
      );
      spent.current[ordinal] = 0;
      enteredAt.current = Date.now();

      setVerdicts((v) => ({ ...v, [ordinal]: verdict }));
      setRevealed((r) => new Set(r).add(ordinal));
      // One request per verdict, sent as it is given: a closed tab, a dead
      // battery or a train tunnel can then cost at most the current question.
      void postAnswer(id, ordinal, verdict, seconds)
        .then(() => {
          // This verdict superseded whatever was queued for this question, so
          // the old one must leave the queue: replaying it on Retry would
          // overwrite the verdict the server has just accepted.
          setUnsaved((u) => u.filter((a) => a.ordinal !== ordinal));
        })
        .catch((err: unknown) => {
          setUnsaved((u) => [
            ...u.filter((a) => a.ordinal !== ordinal),
            { ordinal, verdict, seconds },
          ]);
          setSaveError(errorMessage(err));
        });
      advance();
    },
    [question, result, id, advance],
  );

  const retrySaves = useCallback(() => {
    const batch = unsaved;
    setUnsaved([]);
    setSaveError(null);
    Promise.all(
      batch.map((a) => postAnswer(id, a.ordinal, a.verdict, a.seconds)),
    ).catch((err: unknown) => {
      setUnsaved(batch);
      setSaveError(errorMessage(err));
    });
  }, [unsaved, id]);

  const toggleMark = useCallback(() => {
    if (!question) return;
    setMarked((m) => {
      const next = new Set(m);
      if (!next.delete(question.ordinal)) next.add(question.ordinal);
      return next;
    });
  }, [question]);

  /* --- submitting ------------------------------------------------------- */

  const submit = useCallback(
    (byExpiry: boolean) => {
      if (submitted.current) return;
      submitted.current = true;
      setSubmitting(true);
      setConfirming(false);
      setPaletteOpen(false);
      setSubmitError(null);
      if (byExpiry) setExpired(true);

      submitTest(id)
        .then((r) => {
          setResult(r);
          try {
            localStorage.removeItem(scratchKey(id));
          } catch {
            /* nothing to clean up */
          }
        })
        .catch((err: unknown) => {
          submitted.current = false;
          setSubmitting(false);
          setSubmitError(errorMessage(err));
        });
    },
    [id],
  );

  // One second at a time, and the clock is what ends the paper: when the
  // deadline passes it submits as the paper stands, the way an invigilator
  // collects it, and the result says the time ran out.
  useEffect(() => {
    if (deadline === null || result || finished) return;
    const t = setInterval(() => {
      const at = Date.now();
      setNow(at);
      if (at >= deadline) submit(true);
    }, 1000);
    return () => clearInterval(t);
  }, [deadline, result, finished, submit]);

  /* --- keyboard --------------------------------------------------------- */

  useEffect(() => {
    if (!paper || result || finished) return;

    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e) || hasModifier(e)) return;

      if (confirming) {
        if (e.key === "Escape") {
          e.preventDefault();
          setConfirming(false);
        } else if (e.key === "Enter") {
          e.preventDefault();
          submit(false);
        }
        return;
      }

      // The sheet is modal: nothing behind it should answer a question while
      // it is covering the paper.
      if (paletteOpen) {
        if (e.key === "Escape" || e.key === "p") {
          e.preventDefault();
          setPaletteOpen(false);
        }
        return;
      }

      switch (e.key) {
        case "Escape":
          // Nothing to warn about: every verdict was sent when it was given.
          e.preventDefault();
          router.push("/test");
          return;
        case " ":
          e.preventDefault();
          if (question) setRevealed((r) => new Set(r).add(question.ordinal));
          return;
        case "Enter":
          e.preventDefault();
          setConfirming(true);
          return;
        case "1":
        case "2":
        case "3": {
          if (!question || !revealed.has(question.ordinal)) return;
          const choice = VERDICTS.find((v) => v.key === e.key);
          if (!choice || question.marks < choice.minMarks) return;
          e.preventDefault();
          answer(choice.verdict);
          return;
        }
        case "s":
          e.preventDefault();
          answer("skipped");
          return;
        case "m":
          e.preventDefault();
          toggleMark();
          return;
        case "p":
          e.preventDefault();
          // At lg and wider the palette is already on screen; opening the
          // sheet there would put up a modal that `lg:hidden` never paints.
          if (window.matchMedia("(max-width: 1023.98px)").matches) {
            setPaletteOpen(true);
          }
          return;
        case "j":
        case "ArrowRight":
        case "ArrowDown":
          e.preventDefault();
          step(1);
          return;
        case "k":
        case "ArrowLeft":
        case "ArrowUp":
          e.preventDefault();
          step(-1);
          return;
        case "Home":
          e.preventDefault();
          if (questions[0]) goTo(questions[0].ordinal);
          return;
        case "End":
          e.preventDefault();
          if (questions.length) goTo(questions[questions.length - 1].ordinal);
          return;
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    paper,
    result,
    finished,
    confirming,
    paletteOpen,
    question,
    revealed,
    questions,
    answer,
    step,
    goTo,
    toggleMark,
    submit,
    router,
  ]);

  /* --- derived ---------------------------------------------------------- */

  const state: PaletteState = { verdicts, marked, visited };

  const tally = useMemo(() => {
    let answered = 0;
    let skipped = 0;
    let attemptedMarks = 0;
    let obtained = 0;
    for (const q of questions) {
      const v = verdicts[q.ordinal];
      if (v === "skipped") skipped++;
      else if (v) {
        answered++;
        attemptedMarks += q.marks;
        obtained += scoreFor(v, q.marks);
      }
    }
    return {
      answered,
      skipped,
      attemptedMarks,
      obtained,
      untouched: questions.length - answered - skipped,
    };
  }, [questions, verdicts]);

  const totalMarks = paper?.total_marks ?? 0;
  const allDone = questions.length > 0 && tally.untouched === 0;

  /* --- states ----------------------------------------------------------- */

  if (loading) {
    return (
      <Centered>
        <p className="text-[13px] text-fg-3">Opening the paper&hellip;</p>
      </Centered>
    );
  }

  if (loadError) {
    return (
      <Centered>
        <p
          className="text-[14px] pl-3 border-l-2"
          style={{ borderColor: "var(--g-again)" }}
        >
          {loadError}
        </p>
        <div className="flex gap-4 mt-5 text-[13px]">
          <button
            onClick={() => {
              setLoading(true);
              setReloadNonce((n) => n + 1);
            }}
            className="link"
          >
            Try again
          </button>
          <Link href="/test" className="link text-fg-2">
            Back to papers
          </Link>
        </div>
      </Centered>
    );
  }

  if (result && paper) {
    return <ResultView result={result} kind={paper.kind} expired={expired} />;
  }

  if (finished && paper) {
    return (
      <main className="mx-auto max-w-[46rem] px-4 sm:px-6 py-8">
        <p className="label">{PAPER_LABEL[paper.kind] ?? paper.kind}</p>
        <h1 className="text-[18px] font-semibold mt-2">
          This paper was already submitted.
        </h1>
        <p className="text-[13px] text-fg-2 mt-2 max-w-prose">
          You scored{" "}
          <span className="tnum font-medium text-fg">
            {marks(finished.obtained_marks)} / {finished.total_marks}
          </span>{" "}
          on {mediumDate(finished.started_at)}
          {finished.duration_s
            ? `, in ${formatDuration(finished.duration_s * 1000)}`
            : ""}
          . Its answers are recorded and the scheduler has already moved those
          cards, so it cannot be sat again.
        </p>
        <div className="flex flex-wrap gap-4 mt-5 text-[13px]">
          <Link href="/test" className="link">
            Sit another paper
          </Link>
          <Link href="/review" className="link text-fg-2">
            Review now
          </Link>
          <Link href="/" className="link text-fg-2">
            Back to today
          </Link>
        </div>
      </main>
    );
  }

  if (!paper || !question) {
    return (
      <Centered>
        <p className="text-[15px]">This paper has no questions.</p>
        <p className="text-[13px] text-fg-2 mt-2 max-w-sm">
          Your deck had nothing to draw from when it was assembled. Approve some
          pending cards, then start a new paper.
        </p>
        <div className="flex gap-4 mt-5 text-[13px]">
          <Link href="/approve" className="link">
            Approve queue
          </Link>
          <Link href="/test" className="link text-fg-2">
            Back to papers
          </Link>
        </div>
      </Centered>
    );
  }

  const isRevealed = revealed.has(question.ordinal);
  const solved = question.cloze_text ? parseCloze(question.cloze_text) : null;
  const answerIsRedundant = !!solved && clozeShowsAnswer(solved, question.answer);
  const chosen = verdicts[question.ordinal] ?? null;
  const urgent = remainingMs !== null && remainingMs <= URGENT_S * 1000;

  const palette = (
    <>
      <div className="flex items-baseline justify-between gap-2 px-2.5 h-9 border-b border-line bg-sunken shrink-0">
        <h2 className="label">Questions</h2>
        <span className="text-[11px] text-fg-3 tnum">
          {tally.answered + tally.skipped} / {questions.length}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        <QuestionPalette
          questions={questions}
          state={state}
          current={current}
          onJump={(o) => {
            goTo(o);
            setPaletteOpen(false);
          }}
        />
      </div>
      <div className="shrink-0">
        <PaletteLegend questions={questions} state={state} />
        <div className="px-2.5 pt-2.5 border-t border-line pb-[max(0.625rem,env(safe-area-inset-bottom))]">
          <button
            onClick={() => setConfirming(true)}
            disabled={submitting}
            className="w-full inline-flex items-center justify-center gap-2 h-9 rounded-sm
              text-[13px] font-semibold bg-accent text-accent-fg border border-accent
              hover:bg-accent-hover hover:border-accent-hover transition-colors duration-[90ms]
              disabled:opacity-40 disabled:pointer-events-none"
          >
            {submitting ? "Submitting…" : "Submit paper"}
            <Kbd>&crarr;</Kbd>
          </button>
          <p className="text-[11px] text-fg-3 mt-1.5 tnum">
            {tally.attemptedMarks} of {totalMarks} marks attempted
          </p>
        </div>
      </div>
    </>
  );

  return (
    <div className="h-dvh flex flex-col">
      {/* --- invigilator's bar --------------------------------------------- */}

      <header className="shrink-0 h-11 border-b border-line bg-surface flex items-center gap-3 px-3 sm:px-4">
        <Link
          href="/test"
          title="Leave — everything is saved"
          className="flex items-center gap-1.5 text-[11px] text-fg-3 hover:text-fg-2 transition-colors duration-[90ms] shrink-0"
        >
          <Kbd>Esc</Kbd>
          <span className="hidden md:inline">leave</span>
        </Link>

        <span className="hidden sm:block text-[13px] font-semibold shrink-0">
          {PAPER_LABEL[paper.kind] ?? paper.kind}
        </span>

        <span className="text-[11px] text-fg-3 tnum shrink-0">
          <span className="text-fg-2 font-medium">
            {tally.answered + tally.skipped}
          </span>
          /{questions.length}
          <span className="hidden sm:inline"> answered</span>
        </span>

        <div className="ml-auto flex items-center gap-2 sm:gap-3 shrink-0">
          {remainingMs !== null ? (
            <span
              role="timer"
              aria-live="off"
              title={`${clock(remainingMs)} left of ${Math.round(
                (limitS ?? 0) / 60,
              )} minutes`}
              className={`tnum text-[15px] leading-none tabular-nums ${
                urgent ? "font-semibold" : "font-medium text-fg-2"
              }`}
              style={urgent ? { color: "var(--g-again)" } : undefined}
            >
              {clock(remainingMs)}
            </span>
          ) : (
            <span className="text-[11px] text-fg-3 hidden sm:inline">
              no time limit
            </span>
          )}

          <button
            onClick={() => setPaletteOpen(true)}
            className="lg:hidden h-8 px-2.5 rounded-sm border border-line text-[12px]
              hover:border-line-strong hover:bg-surface-hover transition-colors duration-[90ms]"
          >
            Palette
          </button>

          <button
            onClick={() => setConfirming(true)}
            disabled={submitting}
            className="h-8 px-3 rounded-sm text-[12.5px] font-semibold
              bg-accent text-accent-fg border border-accent hover:bg-accent-hover
              hover:border-accent-hover transition-colors duration-[90ms]
              disabled:opacity-40 disabled:pointer-events-none"
          >
            {submitting ? "Submitting…" : "Submit"}
          </button>
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        {/* --- the question ------------------------------------------------ */}

        <section className="flex-1 flex flex-col min-w-0">
          {/* my-auto rather than justify-center: it centres a short question
              and collapses to nothing when a long one has to scroll. */}
          <main className="flex-1 overflow-y-auto flex flex-col px-4 sm:px-6 py-5 sm:py-7">
            <article
              key={question.ordinal}
              className="w-full max-w-[38rem] mx-auto my-auto anim-advance"
            >
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-fg-3 mb-4">
                <span className="text-[13px] font-semibold text-fg tnum leading-none">
                  Q{question.ordinal}
                </span>
                <span className="tnum font-medium text-fg-2">
                  {question.marks} {plural(question.marks, "mark")}
                </span>
                <span>·</span>
                <span className="font-semibold tracking-[0.05em] text-fg-2">
                  {question.topic_code}
                </span>
                <span>{question.page_ref}</span>
                <KindTag kind={question.kind} />
                {marked.has(question.ordinal) && (
                  <span
                    className="inline-flex items-center gap-1 px-1.5 py-px rounded-xs border text-[10px] font-semibold uppercase tracking-[0.08em]"
                    style={{
                      borderColor: "var(--accent)",
                      background: "var(--accent-quiet)",
                      color: "var(--accent)",
                    }}
                  >
                    marked
                  </span>
                )}
              </div>

              {solved ? (
                <ClozePrompt
                  segments={solved}
                  revealed={isRevealed}
                  className="text-[clamp(1.1rem,1rem+0.9vw,1.45rem)] leading-[1.55]"
                />
              ) : (
                <h1 className="text-[clamp(1.1rem,1rem+0.9vw,1.45rem)] leading-[1.5] font-normal">
                  {question.question}
                </h1>
              )}

              {isRevealed && (!solved || !answerIsRedundant) && (
                <div className="mt-6 pt-5 border-t border-line anim-reveal">
                  <p className="label mb-2">
                    {solved ? "Note" : "Model answer"}
                  </p>
                  <p className="text-[clamp(0.95rem,0.9rem+0.4vw,1.1rem)] leading-[1.6]">
                    {question.answer}
                  </p>
                </div>
              )}

              {chosen && (
                <p className="mt-5 text-[12px] text-fg-3">
                  Recorded as{" "}
                  <span
                    className="font-semibold"
                    style={
                      chosen === "skipped"
                        ? undefined
                        : {
                            color: `var(--g-${
                              VERDICTS.find((v) => v.verdict === chosen)?.tone
                            })`,
                          }
                    }
                  >
                    {chosen}
                  </span>
                  {chosen === "skipped"
                    ? " — no marks, and no review recorded."
                    : ` — ${marks(scoreFor(chosen, question.marks))} of ${
                        question.marks
                      }. Pick again to change it.`}
                </p>
              )}
            </article>
          </main>

          {/* Driven by the queue, not by the last message: a question that was
              re-answered successfully empties the queue, and there is then
              nothing left to warn about or to retry. */}
          {saveError && unsaved.length > 0 && (
            <div className="shrink-0 px-4 sm:px-6 pb-2">
              <div className="max-w-[38rem] mx-auto flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[12px]">
                <span
                  className="pl-2 border-l-2 text-fg-2"
                  style={{ borderColor: "var(--g-again)" }}
                >
                  {unsaved.length} {plural(unsaved.length, "answer")} not saved —{" "}
                  {saveError}
                </span>
                <button onClick={retrySaves} className="link text-fg-2 shrink-0">
                  Retry
                </button>
              </div>
            </div>
          )}

          {submitError && (
            <div className="shrink-0 px-4 sm:px-6 pb-2">
              <p
                className="max-w-[38rem] mx-auto pl-2 border-l-2 text-[12px] text-fg-2"
                style={{ borderColor: "var(--g-again)" }}
                role="alert"
              >
                {submitError}
              </p>
            </div>
          )}

          {/* --- answering ---------------------------------------------- */}

          <footer className="shrink-0 px-4 sm:px-6 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-1">
            <div className="max-w-[38rem] mx-auto">
              <div className="flex items-center gap-2 mb-2">
                <button
                  onClick={() => answer("skipped")}
                  className="h-9 px-3 rounded-sm border border-line bg-surface text-[12.5px]
                    hover:border-line-strong hover:bg-surface-hover transition-colors duration-[90ms]
                    flex items-center gap-1.5"
                >
                  Skip
                  <Kbd>s</Kbd>
                </button>
                <button
                  onClick={toggleMark}
                  aria-pressed={marked.has(question.ordinal)}
                  className="h-9 px-3 rounded-sm border bg-surface text-[12.5px]
                    hover:bg-surface-hover transition-colors duration-[90ms]
                    flex items-center gap-1.5"
                  style={
                    marked.has(question.ordinal)
                      ? {
                          borderColor: "var(--accent)",
                          color: "var(--accent)",
                          background: "var(--accent-quiet)",
                        }
                      : undefined
                  }
                >
                  {marked.has(question.ordinal) ? "Unmark" : "Mark"}
                  <Kbd>m</Kbd>
                </button>

                <div className="ml-auto flex items-center gap-1.5">
                  <button
                    onClick={() => step(-1)}
                    disabled={question.ordinal === questions[0]?.ordinal}
                    aria-label="Previous question"
                    className="h-9 w-9 rounded-sm border border-line bg-surface text-[13px]
                      hover:border-line-strong hover:bg-surface-hover transition-colors duration-[90ms]
                      disabled:opacity-35 disabled:pointer-events-none"
                  >
                    &larr;
                  </button>
                  <button
                    onClick={() => step(1)}
                    disabled={
                      question.ordinal === questions[questions.length - 1]?.ordinal
                    }
                    aria-label="Next question"
                    className="h-9 w-9 rounded-sm border border-line bg-surface text-[13px]
                      hover:border-line-strong hover:bg-surface-hover transition-colors duration-[90ms]
                      disabled:opacity-35 disabled:pointer-events-none"
                  >
                    &rarr;
                  </button>
                </div>
              </div>

              {!isRevealed ? (
                <button
                  onClick={() =>
                    setRevealed((r) => new Set(r).add(question.ordinal))
                  }
                  className="w-full min-h-[60px] rounded-sm border border-line bg-surface
                    hover:border-line-strong hover:bg-surface-hover transition-colors duration-[90ms]
                    flex items-center justify-center gap-2.5 text-[14px] font-medium"
                >
                  Show answer
                  <Kbd>Space</Kbd>
                </button>
              ) : (
                <div
                  className={`grid gap-1.5 ${
                    question.marks >= 2 ? "grid-cols-3" : "grid-cols-2"
                  }`}
                >
                  {VERDICTS.filter((v) => question.marks >= v.minMarks).map(
                    (v) => {
                      const active = chosen === v.verdict;
                      // Longhands only: swapping `borderColor` in and out
                      // beside `borderTopColor` is the shorthand conflict React
                      // warns about.
                      const edge = active ? `var(--g-${v.tone})` : "var(--line)";
                      return (
                        <button
                          key={v.verdict}
                          onClick={() => answer(v.verdict)}
                          aria-pressed={active}
                          className="min-h-[60px] rounded-sm border bg-surface
                            hover:bg-surface-hover active:bg-surface-hover
                            transition-colors duration-[90ms]
                            flex flex-col items-center justify-center gap-1 px-1"
                          style={{
                            borderTopWidth: 2,
                            borderTopColor: `var(--g-${v.tone})`,
                            borderRightColor: edge,
                            borderBottomColor: edge,
                            borderLeftColor: edge,
                            backgroundColor: active
                              ? `var(--g-${v.tone}-bg)`
                              : undefined,
                          }}
                        >
                          <Kbd tone={v.tone}>{v.key}</Kbd>
                          <span className="text-[12.5px] font-medium leading-none">
                            {v.label}
                          </span>
                          <span className="text-[11px] text-fg-3 tnum leading-none">
                            {marks(scoreFor(v.verdict, question.marks))} of{" "}
                            {question.marks}
                          </span>
                        </button>
                      );
                    },
                  )}
                </div>
              )}

              {allDone && (
                <p className="text-[12px] text-fg-3 mt-2 text-center">
                  Every question has a verdict.{" "}
                  <button
                    onClick={() => setConfirming(true)}
                    className="link text-fg-2"
                  >
                    Submit the paper
                  </button>
                  .
                </p>
              )}
            </div>
          </footer>
        </section>

        {/* --- palette ----------------------------------------------------- */}

        <aside className="hidden lg:flex flex-col w-[17rem] border-l border-line bg-surface shrink-0">
          {palette}
        </aside>
      </div>

      {paletteOpen && (
        <div
          className="fixed inset-0 z-40 lg:hidden flex flex-col bg-surface"
          role="dialog"
          aria-modal="true"
          aria-label="Question palette"
        >
          <div className="flex items-center justify-between px-3 h-11 border-b border-line shrink-0">
            <span className="text-[13px] font-semibold">
              {PAPER_LABEL[paper.kind] ?? paper.kind}
            </span>
            <button
              onClick={() => setPaletteOpen(false)}
              className="h-9 px-3 rounded-sm border border-line text-[12.5px]
                hover:bg-surface-hover transition-colors duration-[90ms]"
            >
              Close
            </button>
          </div>
          {palette}
        </div>
      )}

      {confirming && (
        <SubmitConfirm
          tally={tally}
          total={questions.length}
          totalMarks={totalMarks}
          unsaved={unsaved.length}
          remainingMs={remainingMs}
          onCancel={() => setConfirming(false)}
          onSubmit={() => submit(false)}
        />
      )}
    </div>
  );
}

/* --- pieces -------------------------------------------------------------- */

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-[70dvh] flex flex-col items-center justify-center px-6">
      <div className="w-full max-w-[36rem]">{children}</div>
    </div>
  );
}

function SubmitConfirm({
  tally,
  total,
  totalMarks,
  unsaved,
  remainingMs,
  onCancel,
  onSubmit,
}: {
  tally: {
    answered: number;
    skipped: number;
    untouched: number;
    attemptedMarks: number;
    obtained: number;
  };
  total: number;
  totalMarks: number;
  unsaved: number;
  remainingMs: number | null;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.focus({ preventScroll: true });
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "color-mix(in srgb, var(--bg) 93%, transparent)" }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Submit this paper"
        className="panel w-full max-w-md outline-none"
      >
        <header className="px-3 h-9 border-b border-line bg-sunken flex items-center">
          <h2 className="label">Submit this paper</h2>
        </header>

        <div className="px-3.5 py-3">
          <dl className="text-[13px]">
            {[
              ["Answered", `${tally.answered} of ${total}`],
              ["Skipped", String(tally.skipped)],
              ["Never opened", String(tally.untouched)],
              ["Marks attempted", `${tally.attemptedMarks} of ${totalMarks}`],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-baseline justify-between gap-3 py-[3px]"
              >
                <dt className="text-fg-2">{label}</dt>
                <dd className="tnum font-medium">{value}</dd>
              </div>
            ))}
          </dl>

          <p className="text-[12.5px] text-fg-2 mt-3 pt-2.5 border-t border-line leading-snug">
            {tally.untouched > 0 ? (
              <>
                <span className="font-semibold text-fg">
                  {tally.untouched} {plural(tally.untouched, "question")} you
                  never opened
                </span>{" "}
                will score nothing and record no review, the same as a skip.{" "}
              </>
            ) : null}
            Everything you answered goes to the scheduler now: wrong comes back
            tomorrow, correct moves further out. This cannot be undone.
          </p>

          {unsaved > 0 && (
            <p
              className="text-[12.5px] mt-2.5 pl-2 border-l-2"
              style={{ borderColor: "var(--g-again)" }}
            >
              {unsaved} {plural(unsaved, "answer")} never reached the server and
              will not be counted. Retry them first.
            </p>
          )}

          {remainingMs !== null && (
            <p className="text-[12px] text-fg-3 mt-2.5 tnum">
              {clock(remainingMs)} still on the clock.
            </p>
          )}
        </div>

        <footer className="px-3.5 py-2.5 border-t border-line flex items-center gap-2">
          <button
            onClick={onSubmit}
            className="inline-flex items-center gap-2.5 h-9 px-4 rounded-sm text-[13px] font-semibold
              bg-accent text-accent-fg border border-accent hover:bg-accent-hover
              hover:border-accent-hover transition-colors duration-[90ms]"
          >
            Submit and see the result
            <Kbd>&crarr;</Kbd>
          </button>
          <button
            onClick={onCancel}
            className="inline-flex items-center gap-2 h-9 px-3 rounded-sm text-[13px] font-medium
              border border-line bg-surface hover:border-line-strong hover:bg-surface-hover
              transition-colors duration-[90ms]"
          >
            Keep going
            <Kbd>Esc</Kbd>
          </button>
        </footer>
      </div>
    </div>
  );
}
