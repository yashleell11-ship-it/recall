"use client";

import type { ClozeSegment } from "@/lib/cloze";

/**
 * A cloze sentence and its deletions.
 *
 * Shared by the review screen and the exam so the two cannot drift. Before the
 * reveal a deletion is a blank roughly as wide as what is missing — showing its
 * hint if it has one; after the reveal the text sits in place and is underlined,
 * so the eye lands on exactly what was being tested.
 */
export function ClozePrompt({
  segments,
  revealed,
  className = "",
}: {
  segments: ClozeSegment[];
  revealed: boolean;
  className?: string;
}) {
  return (
    <p className={className}>
      {segments.map((seg, i) =>
        seg.kind === "text" ? (
          <span key={i}>{seg.text}</span>
        ) : revealed ? (
          <span key={i} className="border-b-2 border-fg font-medium anim-reveal">
            {seg.text}
          </span>
        ) : (
          <span
            key={i}
            className="inline-block border-b-2 border-fg-3 align-bottom text-center"
            style={{
              minWidth: `${Math.min(
                16,
                Math.max(3.5, seg.text.length * 0.6),
              )}ch`,
            }}
          >
            {seg.hint ? (
              <span className="text-fg-3 italic text-[0.8em]">{seg.hint}</span>
            ) : (
              <span aria-label="blank">&nbsp;</span>
            )}
          </span>
        ),
      )}
    </p>
  );
}

/**
 * True when the solved sentence already contains the answer field verbatim, in
 * which case printing the answer underneath it is repetition.
 */
export function clozeShowsAnswer(
  segments: ClozeSegment[],
  answer: string,
): boolean {
  return segments
    .map((s) => s.text)
    .join("")
    .includes(answer.trim());
}
