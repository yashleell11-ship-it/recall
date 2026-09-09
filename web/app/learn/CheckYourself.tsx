"use client";

import { useCallback, useState } from "react";
import type { LessonCheck } from "@/lib/types";

/**
 * Retrieval practice inside a reading screen.
 *
 * The answers are hidden until asked for, which is the one place on this page
 * something is hidden and the one place it is right: an answer sitting under
 * its question is not a test, it is more prose. `reveal all` exists for the
 * second read-through, when you want the whole thing as a summary.
 */
export function CheckYourself({ items }: { items: LessonCheck[] }) {
  const [revealAll, setRevealAll] = useState(false);
  // Per-item overrides. Cleared whenever the bulk control is used, so
  // "reveal all" really does reveal all rather than only the untouched ones.
  const [open, setOpen] = useState<Record<number, boolean>>({});

  const toggleAll = useCallback(() => {
    setOpen({});
    setRevealAll((prev) => !prev);
  }, []);

  return (
    <section className="mt-10">
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <h2 className="label">Check yourself</h2>
        <button
          type="button"
          onClick={toggleAll}
          className="text-[12px] text-fg-3 hover:text-fg-2 underline underline-offset-2
            transition-colors duration-[90ms]"
        >
          {revealAll ? "hide all" : "reveal all"}
        </button>
      </div>

      <div className="panel divide-y divide-line">
        {items.map((c, i) => (
          <details
            key={i}
            className="group px-3.5 py-3"
            open={open[i] ?? revealAll}
            onToggle={(e) => {
              // Read synchronously: React runs the updater after the handler
              // returns, by which point `currentTarget` is null.
              const isOpen = e.currentTarget.open;
              setOpen((prev) => ({ ...prev, [i]: isOpen }));
            }}
          >
            <summary className="cursor-pointer select-none list-none flex items-baseline gap-3 [&::-webkit-details-marker]:hidden">
              <span className="telemetry text-[10px] text-fg-3 w-4 shrink-0">
                {i + 1}
              </span>
              <span className="k-text text-[15.5px] leading-snug text-fg flex-1">
                {c.question}
              </span>
              <span className="label shrink-0 group-open:opacity-0 transition-opacity duration-[90ms]">
                show
              </span>
            </summary>
            <div className="anim-reveal mt-3 ml-[1.75rem] max-w-[62ch]">
              <p className="k-answer text-fg">{c.answer}</p>
              <p className="label mt-3">What it tests</p>
              <p className="k-text text-[13px] leading-relaxed text-fg-2 mt-1">
                {c.why}
              </p>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
