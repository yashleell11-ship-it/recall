"use client";

import type { CSSProperties } from "react";

/**
 * A shimmering placeholder block. Size it exactly like the content it stands
 * in for — a skeleton that reserves the wrong space is worse than a spinner,
 * because the page jumps when the real thing arrives.
 *
 * The shimmer itself lives in globals.css (`.skeleton`): a transformed
 * pseudo-element, frozen automatically under reduced motion.
 */
export function Skeleton({
  className = "",
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return <div aria-hidden="true" className={`skeleton ${className}`} style={style} />;
}

/** Deterministic ragged-right widths, so SSR and client agree. */
const WIDTHS = ["100%", "92%", "96%", "85%", "98%", "89%"];

/**
 * A paragraph's worth of shimmer: n text lines, the last one short, the way
 * real prose ends.
 */
export function SkeletonText({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div aria-hidden="true" className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="skeleton h-3"
          style={{ width: i === lines - 1 ? "58%" : WIDTHS[i % WIDTHS.length] }}
        />
      ))}
    </div>
  );
}
