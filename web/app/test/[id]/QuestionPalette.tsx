"use client";

import { motion, useReducedMotion } from "motion/react";
import type { TestQuestion, Verdict } from "@/lib/types";

export interface PaletteState {
  verdicts: Record<number, Verdict | null>;
  marked: Set<number>;
  visited: Set<number>;
}

/**
 * Cell appearance is the whole point of the palette, so it lives in one place.
 *
 * Answered cells all wear the same ion tint — answering is the user's act, so
 * it takes the user's light. The verdict itself stays out of the palette (it
 * is still spoken to screen readers, and the result view does the judging);
 * a wall of red cells mid-paper is an invigilator tapping the desk.
 */
function cellStyle(
  verdict: Verdict | null | undefined,
  visited: boolean,
): { fill: string | null; frame: React.CSSProperties } {
  switch (verdict) {
    case "correct":
    case "partial":
    case "wrong":
      return {
        fill: "var(--accent-quiet)",
        frame: { borderColor: "var(--line-strong)", color: "var(--fg-2)" },
      };
    case "skipped":
      return {
        fill: "var(--bg-sunken)",
        frame: {
          borderColor: "var(--line-strong)",
          color: "var(--fg-3)",
          textDecoration: "line-through",
        },
      };
    default:
      return {
        fill: null,
        frame: visited
          ? { borderColor: "var(--line-strong)", color: "var(--fg-2)" }
          : { borderColor: "var(--line)", color: "var(--fg-3)" },
      };
  }
}

const VERDICT_WORD: Record<string, string> = {
  correct: "correct",
  partial: "partial credit",
  wrong: "wrong",
  skipped: "skipped",
};

export function QuestionPalette({
  questions,
  state,
  current,
  onJump,
}: {
  questions: TestQuestion[];
  state: PaletteState;
  current: number;
  onJump: (ordinal: number) => void;
}) {
  const reduced = useReducedMotion();

  return (
    <div
      className="grid gap-1 p-2.5"
      style={{ gridTemplateColumns: "repeat(auto-fill, minmax(2.15rem, 1fr))" }}
      role="group"
      aria-label="Question palette"
    >
      {questions.map((q) => {
        const verdict = state.verdicts[q.ordinal];
        const isCurrent = q.ordinal === current;
        const isMarked = state.marked.has(q.ordinal);
        const { fill, frame } = cellStyle(verdict, state.visited.has(q.ordinal));
        return (
          <button
            key={q.ordinal}
            onClick={() => onJump(q.ordinal)}
            aria-current={isCurrent ? "true" : undefined}
            aria-label={`Question ${q.ordinal}, ${q.marks} ${
              q.marks === 1 ? "mark" : "marks"
            }${verdict ? `, ${VERDICT_WORD[verdict]}` : ", unanswered"}${
              isMarked ? ", marked for review" : ""
            }`}
            title={`Q${q.ordinal} · ${q.topic_code} · ${q.marks} ${
              q.marks === 1 ? "mark" : "marks"
            }`}
            className="telemetry relative h-9 sm:h-8 rounded-xs border text-[12px] font-medium
              flex items-center justify-center overflow-hidden
              transition-colors duration-[90ms] hover:border-fg-2"
            style={{
              ...frame,
              // Steady, breathing-free: the ring never animates, it is simply
              // on the cell you are on.
              ...(isCurrent
                ? {
                    boxShadow: "inset 0 0 0 2px var(--accent)",
                    color: "var(--fg)",
                  }
                : null),
            }}
          >
            {/* The verdict fill arrives with a quick spring; the key replays
                it when an answer is changed. Transform and opacity only. */}
            {fill && (
              <motion.span
                key={verdict}
                aria-hidden="true"
                className="absolute inset-0"
                style={{ background: fill }}
                initial={reduced ? false : { opacity: 0, scale: 0.55 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={
                  reduced
                    ? { duration: 0 }
                    : { type: "spring", duration: 0.15, bounce: 0 }
                }
              />
            )}
            <span className="relative">{q.ordinal}</span>
            {isMarked && (
              <span
                aria-hidden="true"
                className="absolute top-[3px] right-[3px] w-[5px] h-[5px] rounded-full"
                style={{ background: "var(--accent)" }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

export function PaletteLegend({
  questions,
  state,
}: {
  questions: TestQuestion[];
  state: PaletteState;
}) {
  const answered = questions.filter(
    (q) =>
      state.verdicts[q.ordinal] && state.verdicts[q.ordinal] !== "skipped",
  ).length;
  const skipped = questions.filter(
    (q) => state.verdicts[q.ordinal] === "skipped",
  ).length;
  const marked = state.marked.size;
  const left = questions.length - answered - skipped;

  const rows: { label: string; count: number; style: React.CSSProperties }[] = [
    {
      label: "answered",
      count: answered,
      style: {
        background: "var(--accent-quiet)",
        borderColor: "var(--line-strong)",
      },
    },
    {
      label: "skipped",
      count: skipped,
      style: {
        background: "var(--bg-sunken)",
        borderColor: "var(--line-strong)",
      },
    },
    {
      label: "untouched",
      count: left,
      style: { borderColor: "var(--line)" },
    },
    {
      label: "marked",
      count: marked,
      style: { borderColor: "var(--accent)" },
    },
  ];

  return (
    <div className="px-2.5 py-2 border-t border-line grid grid-cols-2 gap-x-3 gap-y-1">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-1.5 text-[11px]">
          <span
            aria-hidden="true"
            className="w-2.5 h-2.5 rounded-xs border shrink-0"
            style={r.style}
          />
          <span className="text-fg-3">{r.label}</span>
          <span className="telemetry text-[11px] text-fg-2 ml-auto">
            {r.count}
          </span>
        </div>
      ))}
    </div>
  );
}
