"use client";

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

/**
 * A container whose height follows its content on a soft, bounce-free spring.
 *
 * The content renders at natural height on the server (no CLS); once mounted,
 * a ResizeObserver keeps the measured height in sync, so anything that grows
 * or shrinks inside — a table re-shaped by a selection, an explanation
 * replacing its skeleton — settles instead of snapping. `openFromZero` starts
 * collapsed and springs open on mount, for content that appears in place.
 *
 * Reduced motion tracks the height with no animation at all.
 */
export function HeightSpring({
  children,
  className = "",
  openFromZero = false,
}: {
  children: ReactNode;
  className?: string;
  openFromZero?: boolean;
}) {
  const inner = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | null>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const el = inner.current;
    if (!el) return;
    // ResizeObserver callbacks are asynchronous, so this never sets state
    // during render or synchronously inside the effect.
    const ro = new ResizeObserver(() => {
      setHeight(el.offsetHeight);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <motion.div
      className={`overflow-hidden ${className}`}
      initial={openFromZero && !reduced ? { height: 0, opacity: 0 } : false}
      animate={
        height !== null ? { height, opacity: 1 } : { opacity: 1 }
      }
      transition={
        reduced
          ? { duration: 0 }
          : { type: "spring", stiffness: 360, damping: 38, mass: 0.9 }
      }
    >
      <div ref={inner}>{children}</div>
    </motion.div>
  );
}
