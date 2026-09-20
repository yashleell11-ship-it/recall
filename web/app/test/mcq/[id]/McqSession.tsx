"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Skeleton } from "@/components/rich";
import { ErrorState, Kbd, KindTag, Loading, TopicCode } from "@/components/ui";
import {
  ApiError,
  errorMessage,
  getMcqAttempt,
  postMcqAnswer,
  submitMcqAttempt,
} from "@/lib/api";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import type { McqAttempt, McqFeedback, McqResult } from "@/lib/types";
import { McqResultView } from "./McqResultView";

const LETTERS = ["A", "B", "C", "D"];

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
      if (isTypingTarget(e) || hasModifier(e)) return;
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
    return (
      <main className="mx-auto max-w-[46rem] px-4 sm:px-6 py-6">
        <Skeleton className="h-1 w-full" />
        <Skeleton className="h-3 w-40 mt-4" />
        <Skeleton className="h-6 w-full mt-5" />
        <div className="mt-5 grid gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </div>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="mx-auto max-w-[46rem] px-4 sm:px-6 py-8">
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
      </main>
    );
  }

  if (result && attempt) {
    return <McqResultView result={result} attempt={attempt} />;
  }

  if (attempt && attempt.submitted_at !== null) {
    // Submitted, and the score is still on its way back.
    return (
      <main className="mx-auto max-w-[46rem] px-4 sm:px-6 py-8">
        <Loading label="Reading your score" />
      </main>
    );
  }

  if (!attempt || !question) {
    return (
      <main className="mx-auto max-w-[46rem] px-4 sm:px-6 py-8">
        <p className="text-[15px]">This attempt has no questions.</p>
        <div className="mt-4 text-[13px]">
          <Link href="/test" className="link">
            Back to Test
          </Link>
        </div>
      </main>
    );
  }

  const chosen = feedback?.chosen ?? null;
  const correctIndex = feedback?.correct_index ?? null;
  const progress = total > 0 ? answeredCount / total : 0;

  return (
    <main className="mx-auto max-w-[46rem] px-4 sm:px-6 py-5 pb-16">
      {/* --- where you are ------------------------------------------------ */}

      <div
        className="h-1 w-full rounded-xs bg-line overflow-hidden"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={answeredCount}
        aria-label="Questions answered"
      >
        <motion.span
          className="block h-full bg-accent"
          initial={reduced ? false : { width: 0 }}
          animate={{ width: `${Math.round(progress * 100)}%` }}
          transition={
            reduced ? { duration: 0 } : { type: "spring", duration: 0.5, bounce: 0 }
          }
        />
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 mt-2.5">
        <p className="telemetry text-[11.5px] text-fg-3">
          <span className="text-fg-2 font-medium">
            Q{idx + 1} of {total}
          </span>
          <span className="mx-1.5">·</span>
          {correctCount} correct so far
        </p>
        <Link
          href="/test"
          className="text-[11.5px] text-fg-3 hover:text-fg-2 transition-colors duration-[90ms]"
        >
          leave — every answer is saved
        </Link>
      </div>

      {/* --- the question -------------------------------------------------- */}

      <div className="flex items-center gap-2 mt-5">
        <TopicCode code={question.topic} />
        {question.difficulty ? <KindTag kind={question.difficulty} /> : null}
        {question.kind === "situation" ? <KindTag kind="scenario" /> : null}
      </div>

      <h1 className="k-text text-[19px] sm:text-[21px] font-medium leading-snug mt-2">
        {question.question}
      </h1>

      {/* --- the options --------------------------------------------------- */}

      <div className="grid gap-2 mt-4" role="group" aria-label="Options">
        {question.options.map((option, i) => {
          const isCorrect = correctIndex !== null && i === correctIndex;
          const isChosenWrong = chosen === i && !feedback?.is_correct;
          const revealed = feedback !== null;

          const style = isCorrect
            ? {
                background: "var(--g-good-bg)",
                borderColor: "var(--g-good)",
              }
            : isChosenWrong
              ? {
                  background: "var(--g-again-bg)",
                  borderColor: "var(--g-again)",
                }
              : undefined;

          return (
            <motion.button
              key={i}
              type="button"
              disabled={revealed || busy}
              onClick={() => answer(i)}
              whileTap={reduced || revealed ? undefined : { scale: 0.995 }}
              transition={{ type: "spring", stiffness: 500, damping: 30 }}
              aria-label={`${LETTERS[i]}. ${option}`}
              className={`w-full text-left flex items-start gap-3 px-3 py-2.5 min-h-[44px]
                rounded-sm border text-[14px] leading-snug
                transition-[border-color,background-color,opacity] duration-[120ms]
                disabled:pointer-events-none
                ${
                  revealed
                    ? isCorrect || isChosenWrong
                      ? "text-fg"
                      : "border-line bg-surface text-fg-3 opacity-60"
                    : "border-line bg-surface text-fg hover:border-line-strong hover:bg-surface-hover"
                }`}
              style={style}
            >
              <span
                className="telemetry text-[11px] shrink-0 mt-[3px] font-semibold"
                style={
                  isCorrect
                    ? { color: "var(--g-good)" }
                    : isChosenWrong
                      ? { color: "var(--g-again)" }
                      : undefined
                }
              >
                {LETTERS[i]}
              </span>
              <span className="k-text">{option}</span>
            </motion.button>
          );
        })}
      </div>

      {answerError && (
        <div className="mt-3">
          <ErrorState message={answerError} />
        </div>
      )}

      {/* --- the teaching note --------------------------------------------- */}

      {feedback && (
        <div
          className="anim-reveal mt-4 pl-3 border-l-2 py-1"
          style={{
            borderLeftColor: feedback.is_correct
              ? "var(--g-good)"
              : "var(--g-again)",
          }}
        >
          <p
            className="text-[13px] font-semibold"
            style={{
              color: feedback.is_correct ? "var(--g-good)" : "var(--g-again)",
            }}
          >
            {feedback.is_correct
              ? "Correct."
              : `Not quite — you picked ${LETTERS[feedback.chosen]}.`}
          </p>

          <p className="k-text text-[13.5px] text-fg leading-[1.6] mt-1.5 max-w-prose">
            {feedback.explain}
          </p>

          {!feedback.is_correct && feedback.why_wrong ? (
            <div className="mt-2.5 pt-2.5 border-t border-line max-w-prose">
              <p className="label">Why {LETTERS[feedback.chosen]} is wrong</p>
              <p className="k-text text-[13.5px] text-fg-2 leading-[1.6] mt-1">
                {feedback.why_wrong}
              </p>
            </div>
          ) : null}
        </div>
      )}

      {/* --- moving on ------------------------------------------------------ */}

      {submitError && (
        <div className="mt-4">
          <ErrorState message={submitError} onRetry={finish} />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 mt-6">
        {idx < total - 1 ? (
          <motion.button
            onClick={goNext}
            whileTap={reduced ? undefined : { scale: 0.98 }}
            transition={{ type: "spring", stiffness: 500, damping: 30 }}
            className="inline-flex items-center gap-2.5 h-9 px-4 rounded-sm text-[13px]
              font-semibold border border-accent bg-accent text-accent-fg
              hover:bg-accent-hover hover:border-accent-hover
              transition-colors duration-[90ms]"
          >
            Next question
            <Kbd>&crarr;</Kbd>
          </motion.button>
        ) : null}

        <button
          onClick={finish}
          disabled={submitting}
          className="inline-flex items-center gap-2 h-9 px-4 rounded-sm text-[13px]
            font-medium border border-line bg-surface hover:border-line-strong
            hover:bg-surface-hover transition-colors duration-[90ms]
            disabled:opacity-50 disabled:pointer-events-none"
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
    </main>
  );
}
