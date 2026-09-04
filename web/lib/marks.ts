/**
 * Marks per card, from docs/CONTRACT.md.
 *
 * The server assembles the paper and sends `marks` with every question, so
 * nothing on the exam screen computes this. It exists for the two places that
 * have no paper yet: the fixture backend, and the pre-flight estimate on /test.
 */

import type { CardKind } from "./types";

/** Every card is worth at least this, so a paper of N marks has at most N questions. */
export const MIN_MARKS = 1;
/** No card is worth more, so a paper of N marks has at least ceil(N / 5) questions. */
export const MAX_MARKS = 5;

export function marksFor(kind: CardKind, answer: string): number {
  if (kind === "cloze") return 1;
  const words = answer.trim().split(/\s+/).filter(Boolean).length;
  if (words <= 4) return 1;
  if (words <= 12) return 2;
  return MAX_MARKS;
}

/** How much a verdict is actually worth, out of `marks`. Partial scores half. */
export function scoreFor(verdict: string | null, marks: number): number {
  if (verdict === "correct") return marks;
  if (verdict === "partial") return marks / 2;
  return 0;
}

export const PAPER_LABEL: Record<string, string> = {
  class30: "Class test",
  endterm100: "End term",
  fullday: "Full day",
};
