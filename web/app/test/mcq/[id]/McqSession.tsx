"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Skeleton } from "@/components/rich";
import { ErrorState, Kbd, Loading } from "@/components/ui";
import {
  ApiError,
  errorMessage,
  getMcqAttempt,
  postMcqAnswer,
  submitMcqAttempt,
} from "@/lib/api";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import type { McqAttempt, McqFeedback, McqResult } from "@/lib/types";
import { McqCode, McqResultView, optionTextClass } from "./McqResultView";
import s from "./mcq.module.css";

const LETTERS = ["A", "B", "C", "D"];

/**
 * Past this many questions the segmented strip stops being one tick per
 * question and becomes a continuous bar with counts. Sixty is where a tick
 * still reads on a phone; the presets are 10/20/30/60, so every preset but
 * Full keeps its ticks.
 */
const TICK_LIMIT = 60;

/** What the strip shows for one drawn question. */
type TickState = "correct" | "wrong" | "pending";

/** Feedback for every position the server has already recorded. */
function recorded(attempt: McqAttempt): Record<number, McqFeedback> {
  const out: Record<number, McqFeedback> = {};
  for (const q of attempt.questions) {
    if (q.answer) out[q.position] = q.answer;
  }
  return out;
}

/**
 * One question at a time, revealed the moment it is answered.
 *
 * Deliberately lighter than the exam screen: no clock, no question palette,
 * no mark-for-review. This test is for learning the material, so the reveal
 * and the note under it are the whole interaction — the first click is the
 * answer and the server refuses a second, which is what makes the score
 * honest.
 */
export function McqSession({ id }: { id: number }) {
  const reduced = useReducedMotion();

  const [attempt, setAttempt] = useState<McqAttempt | null>(null);
  const [answers, setAnswers] = useState<Record<number, McqFeedback>>({});
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const [busy, setBusy] = useState(false);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<McqResult | null>(null);

  /** A submitted attempt is scored once on open; the server hands back what
   *  it stored rather than re-scoring, so this is safe — but asking twice
   *  would still be a wasted round trip on the slowest link in the app. */
  const askedResult = useRef(false);

  useEffect(() => {
    let live = true;
    getMcqAttempt(id)
      .then((a) => {
        if (!live) return;
        setAttempt(a);
        setAnswers(recorded(a));
        const open = a.questions.findIndex((q) => !q.answer);
        setIdx(open >= 0 ? open : 0);
        setLoadError(null);

        if (a.submitted_at !== null && !askedResult.current) {
          askedResult.current = true;
          submitMcqAttempt(id)
            .then((r) => {
              if (live) setResult(r);
            })
            .catch((err: unknown) => {
              if (live) setLoadError(errorMessage(err));
            });
        }
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

  const questions = useMemo(() => attempt?.questions ?? [], [attempt]);
  const total = questions.length;
  const question = questions[idx] ?? null;
  const feedback = question ? (answers[question.position] ?? null) : null;

  const answeredCount = Object.keys(answers).length;
  const correctCount = Object.values(answers).filter((f) => f.is_correct).length;

  /** One entry per drawn question, in draw order — what the strip paints. */
  const ticks = useMemo<TickState[]>(
    () =>
      questions.map((q) => {
        const fb = answers[q.position];
        if (!fb) return "pending";
        return fb.is_correct ? "correct" : "wrong";
      }),
    [questions, answers],
  );

  const goNext = useCallback(() => {
    setIdx((i) => Math.min(i + 1, Math.max(0, total - 1)));
  }, [total]);

  const goPrev = useCallback(() => {
    setIdx((i) => Math.max(0, i - 1));
  }, []);

  const answer = useCallback(
    (chosen: number) => {
      if (!question || result || busy) return;
      if (answers[question.position]) return;
      const position = question.position;
      setBusy(true);
      setAnswerError(null);
      postMcqAnswer(id, position, chosen)
        .then((fb) => {
          setAnswers((prev) => ({ ...prev, [position]: fb }));
        })
        .catch((err: unknown) => {
          // 409 means this position was already answered — another tab, or a
          // double click that beat the guard. The server's record wins, so
          // re-read the attempt and carry on from what it says.
          if (err instanceof ApiError && err.status === 409) {
            return getMcqAttempt(id)
              .then((a) => {
                setAttempt(a);
                setAnswers(recorded(a));
              })
              .catch((again: unknown) => {
                setAnswerError(errorMessage(again));
              });
          }
          setAnswerError(errorMessage(err));
        })
        .finally(() => setBusy(false));
    },
    [id, question, answers, result, busy],
  );

  const finish = useCallback(() => {
    if (!attempt || result || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    askedResult.current = true;
    submitMcqAttempt(id)
      .then(setResult)
      .catch((err: unknown) => {
        setSubmitError(errorMessage(err));
        setSubmitting(false);
      });
  }, [id, attempt, result, submitting]);

  useEffect(() => {
    if (result || !question) return;
    function onKey(e: KeyboardEvent) {
      // Never while the focus is in a field: the picker has a number box, and
      // "typing 3 answers question 3" is the classic bug on this screen.
      if (isTypingTarget(e) || hasModifier(e)) return;
      // The arrow keys belong to a focused code block that is wider than its
      // box: they are how a keyboard reaches the end of a long line. A block
      // that fits has nothing to scroll, and swallowing the keys there would
      // leave them doing nothing at all — so they move between questions,
      // as they do everywhere else.
      if (
        (e.key === "ArrowLeft" || e.key === "ArrowRight") &&
        e.target instanceof Element
      ) {
        const block = e.target.closest("[data-mcq-code]");
        if (block && block.scrollWidth > block.clientWidth) return;
      }
      const revealed = !!(question && answers[question.position]);

      // One character only. `"1234".indexOf(e.key)` is 0 for an empty key —
      // and a key CAN arrive empty (synthetic events, some IME and remote
      // keyboards) — which would silently lock in option A on a question the
      // user never answered, and the server refuses to take it back.
      if (!revealed && e.key.length === 1) {
        const n = "1234".indexOf(e.key);
        if (n >= 0) {
          e.preventDefault();
          answer(n);
          return;
        }
        const letter = "abcd".indexOf(e.key.toLowerCase());
        if (letter >= 0) {
          e.preventDefault();
          answer(letter);
          return;
        }
      }

      if (e.key === "Enter" || e.key === "ArrowRight") {
        e.preventDefault();
        goNext();
        return;
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        goPrev();
        return;
      }
      if (e.key.toLowerCase() === "f") {
        e.preventDefault();
        finish();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [answer, answers, finish, goNext, goPrev, question, result]);

  /* --- states ---------------------------------------------------------- */

  if (loading) {
    // Shaped like the sitting it stands in for — strip, chips, question,
    // four options — so nothing jumps when the attempt arrives.
    return (
      <main className={s.screen}>
        <header className={s.column}>
          <Skeleton className="h-3 w-44" />
          <Skeleton className="h-1.5 w-full mt-3" />
        </header>
        <div className={s.stage}>
          <div className={`${s.column} ${s.card}`} aria-hidden="true">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-7 w-full mt-4" />
            <Skeleton className="h-7 w-2/3 mt-2" />
            <div className="grid gap-2 mt-6">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-[3.25rem] w-full" />
              ))}
            </div>
          </div>
        </div>
        <p className="telemetry text-[11px] text-fg-3" role="status">
          Opening the test&hellip;
        </p>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className={s.screen}>
        <div className={s.stage}>
          <div className={s.column}>
            <ErrorState
              message={loadError}
              onRetry={() => {
                setLoading(true);
                setLoadError(null);
                // The score request is what usually failed here, and the guard
                // that stops it being asked twice would otherwise stop the retry
                // asking at all — leaving "Reading your score" on screen forever.
                askedResult.current = false;
                setReloadNonce((n) => n + 1);
              }}
            />
            <div className="mt-4 text-[13px]">
              <Link href="/test" className="link">
                Back to Test
              </Link>
            </div>
          </div>
        </div>
      </main>
    );
  }

  if (result && attempt) {
    return <McqResultView result={result} attempt={attempt} />;
  }

  if (attempt && attempt.submitted_at !== null) {
    // Submitted, and the score is still on its way back.
    return (
      <main className={s.screen}>
        <div className={s.stage}>
          <div className={s.column}>
            <Loading label="Reading your score" />
          </div>
        </div>
      </main>
    );
  }

  if (!attempt || !question) {
    return (
      <main className={s.screen}>
        <div className={s.stage}>
          <div className={s.column}>
            <p className="text-[15px]">This attempt has no questions.</p>
            <div className="mt-4 text-[13px]">
              <Link href="/test" className="link">
                Back to Test
              </Link>
            </div>
          </div>
        </div>
      </main>
    );
  }

  const chosen = feedback?.chosen ?? null;
  const correctIndex = feedback?.correct_index ?? null;
  const answered = feedback !== null;
  const onLast = idx >= total - 1;

  return (
    <main className={s.screen}>
      {/* --- where you are ------------------------------------------------ */}

      <header className={s.column}>
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 mb-2">
          <p className="telemetry text-[11.5px] text-fg-3">
            <span className="font-semibold tracking-[0.06em] text-fg-2">
              {attempt.subject_code}
            </span>
            <span className="mx-1.5">·</span>
            <span className="tnum font-medium text-fg">Q{idx + 1}</span>
            <span className="tnum"> / {total}</span>
            <span className="mx-1.5">·</span>
            <span className="tnum">{correctCount}</span> correct
          </p>
          <Link
            href="/test"
            className="text-[11.5px] text-fg-3 hover:text-fg-2 transition-colors duration-[90ms]"
          >
            leave — every answer is saved
          </Link>
        </div>

        <ProgressStrip ticks={ticks} current={idx} />
      </header>

      {/* --- the question -------------------------------------------------- */}

      <div className={s.stage}>
        <motion.article
          key={question.position}
          className={`${s.column} ${s.card}`}
          initial={reduced ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 34, mass: 0.9 }}
        >
          <div className={s.chipRow}>
            <span className={s.chip}>{question.topic}</span>
            <span className={s.chipMuted}>{question.difficulty}</span>
            {question.kind === "situation" ? (
              <span className={s.chipMuted}>scenario</span>
            ) : null}
          </div>

          <h1 className={`k-question ${s.question}`}>{question.question}</h1>

          {/* The program the question is about, verbatim — between the
              question and the options, where it is read. */}
          <McqCode code={question.code} />

          {/* --- the options ----------------------------------------------- */}

          <div className={s.optionList} role="group" aria-label="Options">
            {question.options.map((option, i) => {
              const isCorrect = correctIndex !== null && i === correctIndex;
              const isChosenWrong = chosen === i && !feedback?.is_correct;
              const state = !answered
                ? ""
                : isCorrect
                  ? s.isCorrect
                  : isChosenWrong
                    ? s.isWrong
                    : s.isDimmed;
              const mark = !answered
                ? null
                : isCorrect
                  ? "correct"
                  : isChosenWrong
                    ? "your pick"
                    : null;

              return (
                <motion.button
                  key={i}
                  type="button"
                  disabled={answered || busy}
                  onClick={() => answer(i)}
                  whileTap={reduced || answered ? undefined : { scale: 0.995 }}
                  transition={{ type: "spring", stiffness: 500, damping: 30 }}
                  aria-label={`${LETTERS[i]}. ${option}${
                    mark ? ` — ${mark === "correct" ? "correct answer" : "your answer, wrong"}` : ""
                  }`}
                  className={`${s.option} ${state}`}
                >
                  <span className={s.optionLetter} aria-hidden="true">
                    {LETTERS[i]}
                  </span>
                  <span className={optionTextClass(question.options_mono)}>
                    {option}
                  </span>
                  {mark ? (
                    <span className={s.optionMark} aria-hidden="true">
                      {mark}
                    </span>
                  ) : null}
                </motion.button>
              );
            })}
          </div>

          {answerError && (
            <div className="mt-3">
              <ErrorState message={answerError} />
            </div>
          )}

          {/* --- the reveal ------------------------------------------------- */}

          {/* The slot is always mounted so the live region exists before the
              answer lands; only its contents animate in. */}
          <div className={s.revealSlot} role="status" aria-live="polite">
            {feedback && (
              <div className={s.reveal}>
                <p
                  className={`${s.verdictLine} ${
                    feedback.is_correct ? s.isCorrect : s.isWrong
                  }`}
                >
                  {feedback.is_correct
                    ? "Correct."
                    : `Not quite — you picked ${LETTERS[feedback.chosen]}.`}
                  {!feedback.is_correct && (
                    <span className={s.verdictAside}>
                      {LETTERS[feedback.correct_index]} was right.
                    </span>
                  )}
                </p>

                <p className={s.teach}>{feedback.explain}</p>

                {!feedback.is_correct && feedback.why_wrong ? (
                  <div className={s.whyWrong}>
                    <p className={s.whyWrongLabel}>
                      Why {LETTERS[feedback.chosen]} is wrong
                    </p>
                    <p className={s.whyWrongText}>{feedback.why_wrong}</p>
                  </div>
                ) : null}
              </div>
            )}
          </div>

          {/* --- the keyboard, on the screen -------------------------------- */}

          <div className={s.hint}>
            <span className={s.hintGroup}>
              <Kbd>1</Kbd>
              <span aria-hidden="true">–</span>
              <Kbd>4</Kbd>
            </span>
            <span>or</span>
            <span className={s.hintGroup}>
              <Kbd>a</Kbd>
              <span aria-hidden="true">–</span>
              <Kbd>d</Kbd>
            </span>
            <span>answer</span>
            <span className={s.hintSep} aria-hidden="true">
              ·
            </span>
            <span className={s.hintGroup}>
              <Kbd>&crarr;</Kbd>
              <span>next</span>
            </span>
            <span className={s.hintSep} aria-hidden="true">
              ·
            </span>
            <span className={s.hintGroup}>
              <Kbd>f</Kbd>
              <span>finish</span>
            </span>
          </div>
        </motion.article>
      </div>

      {/* --- moving on ------------------------------------------------------ */}

      <footer className={`${s.column} ${s.actionsDock}`}>
        {submitError && (
          <div className="mb-3">
            <ErrorState message={submitError} onRetry={finish} />
          </div>
        )}

        <div className={s.actions}>
          {!onLast ? (
            <motion.button
              onClick={goNext}
              whileTap={reduced ? undefined : { scale: 0.98 }}
              transition={{ type: "spring", stiffness: 500, damping: 30 }}
              /* The accent only arrives once the question is answered: before
                 that it would out-shout the options, which are the control
                 that matters. */
              className={
                answered
                  ? "accent-grad glow-accent-hover inline-flex items-center gap-2.5 h-11 px-4 rounded-sm text-[13px] font-semibold border border-accent"
                  : "inline-flex items-center gap-2.5 h-11 px-4 rounded-sm text-[13px] font-medium border border-line bg-surface text-fg-2 hover:border-line-strong hover:bg-surface-hover hover:text-fg transition-colors duration-[90ms]"
              }
            >
              Next question
              <Kbd>&crarr;</Kbd>
            </motion.button>
          ) : null}

          <button
            onClick={finish}
            disabled={submitting}
            className={`inline-flex items-center gap-2 h-11 px-4 rounded-sm text-[13px]
              font-medium border bg-surface transition-colors duration-[90ms]
              disabled:opacity-50 disabled:pointer-events-none ${
                answered && onLast
                  ? "border-accent text-accent hover:bg-accent-quiet"
                  : "border-line hover:border-line-strong hover:bg-surface-hover"
              }`}
          >
            {submitting
              ? "Scoring…"
              : `Finish & see score (${answeredCount} answered)`}
            <Kbd>f</Kbd>
          </button>

          {answeredCount < total && (
            <p className="text-[12px] text-fg-3">
              Unanswered questions score 0, out of all {total}.
            </p>
          )}
        </div>
      </footer>
    </main>
  );
}

/* --- the strip ------------------------------------------------------------ */

/**
 * One tick per drawn question, filling with the verdict colours as they are
 * answered and marked in the accent where you are standing. Past TICK_LIMIT
 * the ticks would be slivers, so it collapses to one continuous bar with the
 * counts spelled out beside it — the same information, still readable.
 *
 * Presentational: the ticks are not buttons, because nothing on this screen
 * jumps to an arbitrary question. The wrapper carries the progress semantics.
 */
function ProgressStrip({
  ticks,
  current,
}: {
  ticks: TickState[];
  current: number;
}) {
  const total = ticks.length;
  const correct = ticks.filter((t) => t === "correct").length;
  const wrong = ticks.filter((t) => t === "wrong").length;
  const answered = correct + wrong;

  const semantics = {
    role: "progressbar" as const,
    "aria-valuemin": 0,
    "aria-valuemax": total,
    "aria-valuenow": answered,
    "aria-label": "Questions answered",
    "aria-valuetext": `${answered} of ${total} answered, ${correct} correct`,
  };

  if (total > TICK_LIMIT) {
    const pct = (n: number) => (total > 0 ? (100 * n) / total : 0);
    return (
      <div>
        <div className={s.progressBar} {...semantics}>
          <span
            className={s.barGood}
            style={{ width: `${pct(correct)}%` }}
            aria-hidden="true"
          />
          <span
            className={s.barWrong}
            style={{ width: `${pct(wrong)}%` }}
            aria-hidden="true"
          />
          <span
            className={s.barCursor}
            style={{ left: `calc(${pct(current + 0.5)}% - 1px)` }}
            aria-hidden="true"
          />
        </div>
        <p className="telemetry text-[11px] text-fg-3 mt-1.5">
          <span className="tnum" style={{ color: "var(--g-good)" }}>
            {correct}
          </span>{" "}
          right
          <span className="mx-1.5">·</span>
          <span className="tnum" style={{ color: "var(--g-again)" }}>
            {wrong}
          </span>{" "}
          wrong
          <span className="mx-1.5">·</span>
          <span className="tnum">{total - answered}</span> to go
        </p>
      </div>
    );
  }

  return (
    <div className={s.progressStrip} {...semantics}>
      {ticks.map((t, i) => (
        <span
          key={i}
          aria-hidden="true"
          className={`${s.tick} ${
            t === "correct"
              ? s.tickCorrect
              : t === "wrong"
                ? s.tickWrong
                : s.tickPending
          } ${i === current ? s.tickCurrent : ""}`}
        />
      ))}
    </div>
  );
}
