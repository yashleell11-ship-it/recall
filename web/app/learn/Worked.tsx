"use client";

import { Panel } from "@/components/ui";
import type { LessonWorked } from "@/lib/types";

/**
 * One worked example, with its steps ALWAYS VISIBLE.
 *
 * They are deliberately not behind a "show working" control. That is exactly
 * the mistake that left `card_explanations` at zero rows — a teaching feature
 * nobody pressed the button for — and the steps are the whole reason the
 * pipeline refuses a lesson that has none.
 */
export function Worked({
  index,
  item,
  note,
}: {
  /** 1-based; matches the number the re-derivation's note refers to. */
  index: number;
  item: LessonWorked;
  /**
   * OPTIONAL / ADDITIVE. The note the re-derivation recorded about THIS
   * example, if it recorded one. It belongs on the derivation it doubts, not
   * as a banner over the page — but it is printed, not hidden behind hover:
   * there is no hover on a phone, and a caveat only a mouse can reach is not
   * a caveat.
   */
  note?: string;
}) {
  return (
    <Panel
      title={`Worked example ${index}`}
      aside={
        note ? <span className="prov">not confirmed</span> : undefined
      }
      bodyClassName="px-3.5 py-3"
    >
      <p className="k-text text-[16px] leading-snug font-medium text-fg">
        {item.question}
      </p>

      {/* A numbered ladder, one row per step, so a derivation reads as a
          derivation rather than as a paragraph with semicolons in it. */}
      <ol className="mt-3 border-t border-line">
        {item.steps.map((step, i) => (
          <li
            key={i}
            className="flex gap-3 py-2 border-b border-line last:border-b-0"
          >
            <span className="telemetry text-[10px] text-fg-3 w-4 shrink-0 pt-1">
              {i + 1}
            </span>
            <span className="k-text text-[15px] leading-[1.65] text-fg-2 whitespace-pre-line flex-1">
              {step}
            </span>
          </li>
        ))}
      </ol>

      {/* The terminus of the ladder, on the one heavier rule in the panel. */}
      <div className="mt-3 pt-3 border-t border-line-strong flex items-baseline gap-3">
        <span className="label shrink-0">Answer</span>
        <span className="k-answer text-fg font-medium">{item.answer}</span>
      </div>

      {/* Printed, not hovered. And deliberately no chip for the CONFIRMED
          case: this check re-solves the question cold and, on the six lessons
          written so far, every flag it raised turned out to be the check being
          wrong and the lesson right — twice with both attempts agreeing on the
          same wrong answer. A tick saying "confirmed" would be the one claim
          it has not earned, in the direction that costs a student marks. */}
      {note && (
        <p className="k-text text-[12.5px] leading-relaxed text-fg-3 mt-2.5">
          {note}
        </p>
      )}
    </Panel>
  );
}
