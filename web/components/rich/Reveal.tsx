"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

/**
 * Fade + 8px lift on mount, on a quick spring. Pass `index` when several
 * siblings reveal together: each waits 40ms longer than the last, which is
 * as much stagger as anything is allowed.
 *
 * Reduced motion renders the content in place, no animation at all.
 */
export function Reveal({
  children,
  index = 0,
  delay,
  className,
}: {
  children: ReactNode;
  /** Position among staggered siblings; 40ms apart. */
  index?: number;
  /** Explicit delay in seconds; overrides `index`. */
  delay?: number;
  className?: string;
}) {
  const reduced = useReducedMotion();

  return (
    <motion.div
      className={className}
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: "spring",
        stiffness: 420,
        damping: 34,
        mass: 0.9,
        delay: delay ?? index * 0.04,
      }}
    >
      {children}
    </motion.div>
  );
}
