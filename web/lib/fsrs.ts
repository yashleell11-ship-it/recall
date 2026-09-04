/**
 * FSRS-4.5, ported from `recall.schedule.fsrs` so the four grade buttons can
 * show the interval each one would produce *before* the review is committed.
 *
 * The server is still the authority: /api/review returns the real interval and
 * the real memory state, and the client caches that state so a card seen twice
 * in one session is priced exactly.
 *
 * Kept deliberately in step with the Python module. Grades: 1..4.
 */

import type { Grade } from "./types";

export const DEFAULT_PARAMS: readonly number[] = [
  0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031, 1.6474,
  0.1367, 1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755,
];

const DECAY = -0.5;
const FACTOR = 19 / 81;

export interface MemoryState {
  stability: number;
  difficulty: number;
}

const clampDifficulty = (d: number) => Math.min(Math.max(d, 1), 10);

/** Probability of recall after `elapsedDays` given `stability`. */
export function retrievability(elapsedDays: number, stability: number): number {
  if (stability <= 0) return 0;
  return Math.pow(1 + (FACTOR * elapsedDays) / stability, DECAY);
}

function initialDifficulty(grade: Grade, w = DEFAULT_PARAMS): number {
  return clampDifficulty(w[4] - Math.exp(w[5] * (grade - 1)) + 1);
}

export function initialState(grade: Grade, w = DEFAULT_PARAMS): MemoryState {
  return {
    stability: Math.max(w[grade - 1], 0.1),
    difficulty: initialDifficulty(grade, w),
  };
}

export function nextState(
  state: MemoryState,
  grade: Grade,
  elapsedDays: number,
  w = DEFAULT_PARAMS,
): MemoryState {
  const r = retrievability(elapsedDays, state.stability);

  const drifted = state.difficulty - w[6] * (grade - 3);
  const difficulty = clampDifficulty(
    w[7] * initialDifficulty(4, w) + (1 - w[7]) * drifted,
  );

  let stability: number;
  if (grade === 1) {
    stability =
      w[11] *
      Math.pow(state.difficulty, -w[12]) *
      (Math.pow(state.stability + 1, w[13]) - 1) *
      Math.exp((1 - r) * w[14]);
  } else {
    const hardPenalty = grade === 2 ? w[15] : 1;
    const easyBonus = grade === 4 ? w[16] : 1;
    stability =
      state.stability *
      (1 +
        Math.exp(w[8]) *
          (11 - state.difficulty) *
          Math.pow(state.stability, -w[9]) *
          (Math.exp((1 - r) * w[10]) - 1) *
          hardPenalty *
          easyBonus);
  }

  return { stability: Math.max(stability, 0.1), difficulty };
}

/** Days until p(recall) falls to `desiredRetention`. */
export function intervalDays(
  stability: number,
  desiredRetention: number,
): number {
  const r = Math.min(Math.max(desiredRetention, 0.5), 0.99);
  return (stability / FACTOR) * (Math.pow(r, 1 / DECAY) - 1);
}

/**
 * The four intervals a card would receive, one per grade.
 *
 * `state` null means the card has never been reviewed (a new card), which FSRS
 * prices exactly from the first-rating table. A review card whose state the
 * server did not send is priced from a placeholder state and flagged
 * `estimated` so the UI can say so rather than quietly inventing a number.
 */
export interface GradePreview {
  grade: Grade;
  days: number;
  estimated: boolean;
}

/** Stand-in for a due review card of unknown state: average difficulty, and a
 *  stability that puts it right at the retention threshold today. */
const PLACEHOLDER: MemoryState = { stability: 7, difficulty: 5 };

export function previewIntervals(
  state: MemoryState | null,
  isNew: boolean,
  elapsedDays: number,
  desiredRetention: number,
): GradePreview[] {
  const grades: Grade[] = [1, 2, 3, 4];

  if (isNew && !state) {
    return grades.map((grade) => ({
      grade,
      days: intervalDays(initialState(grade).stability, desiredRetention),
      estimated: false,
    }));
  }

  const estimated = !state;
  const base = state ?? PLACEHOLDER;
  return grades.map((grade) => ({
    grade,
    days: intervalDays(
      nextState(base, grade, elapsedDays).stability,
      desiredRetention,
    ),
    estimated,
  }));
}

/** Compact human interval: 12m, 4h, 3d, 2.1mo, 1.4y. */
export function formatInterval(days: number): string {
  if (!Number.isFinite(days) || days <= 0) return "—";
  if (days < 1 / 24) return `${Math.max(1, Math.round(days * 1440))}m`;
  if (days < 1) return `${Math.round(days * 24)}h`;
  if (days < 30) return `${Math.round(days)}d`;
  if (days < 365) return `${(days / 30.44).toFixed(1)}mo`;
  return `${(days / 365.25).toFixed(1)}y`;
}
