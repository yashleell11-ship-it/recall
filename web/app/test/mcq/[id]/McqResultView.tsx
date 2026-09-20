"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useCallback, useState } from "react";
import { AnimatedNumber, ProgressRing } from "@/components/rich";
import { KindTag, TopicCode } from "@/components/ui";
import { createMcqAttempt, errorMessage } from "@/lib/api";
import { formatDuration, plural } from "@/lib/format";
import type { McqAttempt, McqResult } from "@/lib/types";

const LETTERS = ["A", "B", "C", "D"];

/** One line, and it has to be worth reading: what to do next, not praise. */
function verdict(percent: number): string {
  if (percent >= 80) return "Ready.";
  if (percent >= 60) return "Solid — revisit the weak topics.";
  return "Go back to the material for the topics below.";
}

/** A topic bar earns its colour: good at 80%, hard at 50%, again below. */
function toneFor(ratio: number): string {
  if (ratio >= 0.8) return "var(--g-good)";
  if (ratio >= 0.5) return "var(--g-hard)";
  return "var(--g-again)";
}

export function McqResultView({
  result,
  attempt,
}: {
  result: McqResult;
  attempt: McqAttempt;
}) {
  const router = useRouter();
  const reduced = useReducedMotion();
  const [retaking, setRetaking] = useState(false);
  const [retakeError, setRetakeError] = useState<string | null>(null);

  const percent =
    result.total > 0 ? Math.round((100 * result.score) / result.total) : 0;

  const retake = useCallback(() => {
    if (retaking) return;
    setRetaking(true);
    setRetakeError(null);
    createMcqAttempt(attempt.subject_code, attempt.units, attempt.length)
      .then((a) => router.push(`/test/mcq/${a.attempt_id}`))
      .catch((err: unknown) => {
        setRetakeError(errorMessage(err));
        setRetaking(false);
      });
  }, [attempt, retaking, router]);

  return (
    <main className="mx-auto max-w-[46rem] px-4 sm:px-6 py-6 pb-16">
      <p className="label">Yash Made Test · result</p>

      {/* --- the score ----------------------------------------------------- */}

      <div className="flex items-center gap-5 mt-3">
        <div className="min-w-0">
          <h1 className="k-display tnum">
            <AnimatedNumber value={result.score} />
            <span className="text-fg-3 font-normal"> / {result.total}</span>
          </h1>
          <p className="text-[14px] font-medium mt-1.5">{verdict(percent)}</p>
          <p className="telemetry text-[12px] text-fg-3 mt-1">
            <TopicCode code={attempt.subject_code} />
            <span className="mx-1.5">·</span>
            {plural(attempt.units.length, "unit")} {attempt.units.join(", ")}
            <span className="mx-1.5">·</span>
            {formatDuration(result.duration_s * 1000)}
          </p>
        </div>

        <ProgressRing
          value={result.total > 0 ? result.score / result.total : 0}
          size={84}
          thickness={5}
          color={toneFor(result.total > 0 ? result.score / result.total : 0)}
          label={`${percent} percent`}
          className="ml-auto shrink-0"
        >
          <span className="tnum text-[17px] font-semibold">{percent}%</span>
        </ProgressRing>
      </div>

      {result.answered < result.total && (
        <p className="text-[12.5px] text-fg-2 mt-3 pl-3 border-l-2 border-l-line-strong max-w-prose">
          You answered {result.answered} of {result.total}. The{" "}
          {result.total - result.answered} you left score 0 — the total is what
          the attempt drew, so this is an honest {result.score}/{result.total}.
        </p>
      )}

      {result.rank && (
        <p className="telemetry text-[12px] text-fg-2 mt-3">
          #{result.rank.position} of {result.rank.of} on this board
        </p>
      )}

      {/* --- by topic ------------------------------------------------------ */}

      {result.by_topic.length > 0 && (
        <section className="mt-6">
          <h2 className="label mb-2">By topic</h2>
          <div className="panel overflow-hidden">
            {[...result.by_topic]
              .sort(
                (a, b) =>
                  a.correct / Math.max(1, a.total) -
                  b.correct / Math.max(1, b.total),
              )
              .map((t) => {
                const ratio = t.total > 0 ? t.correct / t.total : 0;
                return (
                  <div
                    key={t.topic}
                    className="flex items-center gap-3 px-3 py-2 border-b border-line last:border-b-0"
                  >
                    <span className="text-[13px] font-medium truncate w-[34%] shrink-0">
                      {t.topic}
                    </span>
                    <span className="block h-1.5 flex-1 bg-line rounded-xs overflow-hidden">
                      <motion.span
                        className="block h-full"
                        style={{ background: toneFor(ratio) }}
                        initial={reduced ? false : { width: 0 }}
                        animate={{ width: `${Math.round(ratio * 100)}%` }}
                        transition={
                          reduced
                            ? { duration: 0 }
                            : { type: "spring", duration: 0.7, bounce: 0 }
                        }
                      />
                    </span>
                    <span className="telemetry text-[11.5px] text-fg-2 tnum shrink-0 w-12 text-right">
                      {t.correct}/{t.total}
                    </span>
                  </div>
                );
              })}
          </div>
        </section>
      )}

      {/* --- the review sheet ---------------------------------------------- */}

      {result.missed.length === 0 ? (
        <div className="panel mt-6 px-3.5 py-5 max-w-prose">
          <p className="text-[14px]">Nothing missed. Every question was right.</p>
          <p className="text-[13px] text-fg-2 mt-1.5">
            Retake it later — the draw and the options are shuffled again, so
            it is the material you are remembering, not the layout.
          </p>
        </div>
      ) : (
        <section className="mt-7">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pl-3 border-l-2 border-l-accent">
            <h2 className="text-[16px] font-semibold">What to fix</h2>
            <p className="text-[12px] text-fg-3">
              {result.missed.length}{" "}
              {plural(result.missed.length, "question")} wrong or unanswered
            </p>
          </div>

          <ul className="panel mt-3.5 overflow-hidden">
            {result.missed.map((m) => (
              <li
                key={m.position}
                className="px-3.5 py-3 border-b border-line last:border-b-0 border-l-2"
                style={{ borderLeftColor: "var(--g-again)" }}
              >
                <div className="telemetry flex items-center gap-2 text-[11px] text-fg-3 mb-1.5">
                  <span className="tnum text-fg-2 font-medium">
                    Q{m.position}
                  </span>
                  <span className="font-semibold tracking-[0.05em] text-fg-2">
                    {m.topic}
                  </span>
                  {m.chosen === null ? <KindTag kind="unanswered" /> : null}
                </div>

                <p className="k-text text-[15px] font-medium leading-snug">
                  {m.question}
                </p>

                <div className="mt-2 grid gap-1 text-[13.5px]">
                  {m.chosen !== null ? (
                    <p className="k-text" style={{ color: "var(--g-again)" }}>
                      <span className="telemetry text-[11px] mr-2">
                        {LETTERS[m.chosen]}
                      </span>
                      {m.options[m.chosen]}
                    </p>
                  ) : (
                    <p className="text-[12.5px] text-fg-3">
                      You did not answer this one.
                    </p>
                  )}
                  <p className="k-text" style={{ color: "var(--g-good)" }}>
                    <span className="telemetry text-[11px] mr-2">
                      {LETTERS[m.correct_index]}
                    </span>
                    {m.options[m.correct_index]}
                  </p>
                </div>

                <p className="k-text text-[13.5px] text-fg leading-[1.6] mt-2.5 max-w-prose">
                  {m.explain}
                </p>

                {m.chosen !== null && m.why_wrong ? (
                  <div className="mt-2 pt-2 border-t border-line max-w-prose">
                    <p className="label">Why {LETTERS[m.chosen]} is wrong</p>
                    <p className="k-text text-[13.5px] text-fg-2 leading-[1.6] mt-1">
                      {m.why_wrong}
                    </p>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      )}

      {retakeError && (
        <div
          className="mt-4 px-3 py-2 border-l-2 bg-surface text-[13px]"
          style={{ borderLeftColor: "var(--g-again)" }}
          role="alert"
        >
          {retakeError}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 mt-7">
        <motion.button
          onClick={retake}
          disabled={retaking}
          whileTap={reduced ? undefined : { scale: 0.98 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
          className="inline-flex items-center h-9 px-4 rounded-sm text-[13px] font-semibold
            border border-accent bg-accent text-accent-fg hover:bg-accent-hover
            hover:border-accent-hover transition-colors duration-[90ms]
            disabled:opacity-40 disabled:pointer-events-none"
        >
          {retaking ? "Shuffling…" : "Retake (reshuffled)"}
        </motion.button>
        <Link
          href="/test"
          className="inline-flex items-center h-9 px-4 rounded-sm text-[13px] font-medium
            border border-line bg-surface hover:border-line-strong hover:bg-surface-hover
            transition-colors duration-[90ms]"
        >
          Back to Test
        </Link>
      </div>
    </main>
  );
}
