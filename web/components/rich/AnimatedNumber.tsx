"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";

/**
 * A number that sweeps to its value with a spring — on mount from zero, and
 * on every change from wherever it currently sits.
 *
 * The server renders the final value, so the page is correct without
 * JavaScript and reserves its full width from the first paint. Frames are
 * written straight to the DOM node; React never re-renders mid-flight.
 * Reduced motion snaps instead of sweeping.
 */
export function AnimatedNumber({
  value,
  format = defaultFormat,
  delay = 0,
  className = "",
}: {
  value: number;
  /** Turns each frame's interpolated value into text. Rounds by default. */
  format?: (n: number) => string;
  /** Seconds to hold before the sweep starts. */
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();
  /** What is on screen right now, so a change animates from there, not 0. */
  const shown = useRef<number | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const from = shown.current ?? 0;
    shown.current = value;

    if (reduced || from === value) {
      el.textContent = format(value);
      return;
    }

    const controls = animate(from, value, {
      type: "spring",
      stiffness: 90,
      damping: 26,
      mass: 1,
      delay,
      onUpdate: (v) => {
        el.textContent = format(v);
      },
    });
    return () => controls.stop();
  }, [value, format, delay, reduced]);

  return (
    <span ref={ref} className={`tnum ${className}`}>
      {format(value)}
    </span>
  );
}

function defaultFormat(n: number): string {
  return Math.round(n).toLocaleString("en-US");
}
