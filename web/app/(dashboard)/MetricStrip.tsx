"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { AnimatedNumber, ProgressRing } from "@/components/rich";

/**
 * The day in one strip: five figures, every one of them sweeping to its value
 * on a spring. "Reviewed today" carries a ring against the daily cap; "New"
 * carries a slim bar against the new-card budget. Both are paint-only
 * animations, and both reserve their space from the first paint.
 */
export function MetricStrip({
  due,
  newCount,
  newLimit,
  reviewed,
  cap,
  again,
  streak,
  active,
}: {
  due: number;
  newCount: number;
  newLimit: number;
  reviewed: number;
  cap: number | null;
  again: number;
  streak: number;
  active: number;
}) {
  const heldNote =
    reviewed > 0
      ? `${Math.round((1 - again / reviewed) * 100)}% held`
      : undefined;

  return (
    <div className="panel shadow-elev-1 overflow-hidden">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 -ml-px -mt-px">
        <Cell
          index={0}
          value={due}
          label="Due"
          note="scheduled for today"
          emphasis
        />
        <Cell
          index={1}
          value={newCount}
          label="New"
          note={`limit ${newLimit}/day`}
          emphasis
          bar={newLimit > 0 ? Math.min(1, newCount / newLimit) : 0}
        />
        <Cell
          index={2}
          value={reviewed}
          label="Reviewed today"
          note={cap === null ? undefined : `of ${cap} allowed`}
          ring={
            cap !== null && cap > 0 ? (
              <ProgressRing
                value={Math.min(1, reviewed / cap)}
                size={36}
                thickness={3.5}
                label={`${reviewed} of ${cap} reviews used`}
              />
            ) : undefined
          }
        />
        <Cell index={3} value={again} label="Again today" note={heldNote} />
        <Cell
          index={4}
          value={streak}
          label="Day streak"
          note={`${active.toLocaleString()} cards in rotation`}
        />
      </div>
    </div>
  );
}

function Cell({
  index,
  value,
  label,
  note,
  emphasis = false,
  ring,
  bar,
}: {
  index: number;
  value: number;
  label: string;
  note?: string;
  emphasis?: boolean;
  /** Right slot: a small progress ring. */
  ring?: ReactNode;
  /** Bottom slot: a slim budget bar, 0..1. */
  bar?: number;
}) {
  const reduced = useReducedMotion();

  return (
    <div className="border-l border-t border-line px-3.5 py-2.5 min-w-0 flex items-center justify-between gap-3">
      <div className="min-w-0">
        {/* Under Phosphor these numerals are the strip's emission: ion at
            ≥18px (numerals only, per the spec's contrast table), with one
            faint glow well under the .35 alpha ceiling. The topic table
            below stays dense ink. Ember renders them exactly as before. */}
        <div
          className={`leading-none text-fg [[data-skin=phosphor]_&]:text-accent [[data-skin=phosphor]_&]:[text-shadow:0_0_16px_var(--accent-glow)] ${
            emphasis ? "text-[26px] font-semibold" : "text-[22px] font-medium"
          }`}
        >
          <AnimatedNumber
            value={value}
            delay={index * 0.04}
            className="tnum-display k-text"
          />
        </div>
        <div className="label mt-1.5 truncate">{label}</div>
        {note ? (
          <div className="text-[11px] text-fg-3 mt-0.5 truncate">{note}</div>
        ) : null}
        {bar !== undefined ? (
          <div
            aria-hidden="true"
            className="mt-1.5 h-[3px] w-full max-w-[72px] rounded-full bg-line overflow-hidden"
          >
            <motion.div
              className="h-full rounded-full bg-fg-3"
              style={{ transformOrigin: "0% 50%" }}
              initial={reduced ? false : { scaleX: 0 }}
              animate={{ scaleX: bar }}
              transition={
                reduced
                  ? { duration: 0 }
                  : { type: "spring", duration: 0.9, bounce: 0, delay: 0.15 }
              }
            />
          </div>
        ) : null}
      </div>
      {ring}
    </div>
  );
}
