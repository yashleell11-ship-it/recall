"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

/**
 * An SVG progress ring whose arc sweeps to its value with a bounce-free
 * spring. `value` is a fraction, 0 to 1. Whatever is passed as children sits
 * centred inside the ring — a score, a percentage, nothing.
 *
 * Only stroke-dashoffset animates: paint, never layout. Reduced motion draws
 * the arc at its final length immediately.
 */
export function ProgressRing({
  value,
  size = 64,
  thickness = 4,
  color = "var(--accent)",
  track = "var(--line)",
  children,
  className = "",
  label,
}: {
  /** Fraction of the ring to fill, 0 to 1. Clamped. */
  value: number;
  /** Outer diameter in px. */
  size?: number;
  /** Stroke width in px. */
  thickness?: number;
  /** Arc colour. Any CSS colour; defaults to the ember. */
  color?: string;
  /** Track colour behind the arc. */
  track?: string;
  /** Centre slot. */
  children?: ReactNode;
  className?: string;
  /** Accessible name; defaults to the value as a percentage. */
  label?: string;
}) {
  const reduced = useReducedMotion();
  const clamped = Math.min(1, Math.max(0, value));
  const r = (size - thickness) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - clamped);

  return (
    <div
      role="img"
      aria-label={label ?? `${Math.round(clamped * 100)}%`}
      className={`relative inline-flex items-center justify-center shrink-0 ${className}`}
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-90"
        aria-hidden="true"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={track}
          strokeWidth={thickness}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={reduced ? false : { strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={
            reduced
              ? { duration: 0 }
              : { type: "spring", duration: 0.9, bounce: 0 }
          }
        />
      </svg>
      {children ? (
        <div className="absolute inset-0 flex items-center justify-center">
          {children}
        </div>
      ) : null}
    </div>
  );
}
