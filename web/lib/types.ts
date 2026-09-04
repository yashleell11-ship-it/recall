/**
 * Wire types for the Recall HTTP API.
 *
 * These mirror `docs/CONTRACT.md` exactly. Where a field is marked OPTIONAL /
 * ADDITIVE it is not promised by the contract; the client uses it when the
 * server sends it and degrades gracefully when it does not.
 */

export type CardKind = "qa" | "cloze";

/** 1 = again, 2 = hard, 3 = good, 4 = easy. */
export type Grade = 1 | 2 | 3 | 4;

/** GET /api/topics */
export interface Topic {
  id: number;
  code: string;
  label: string;
  due: number;
  new: number;
  active: number;
  pending: number;
}

export interface QueueCard {
  id: number;
  kind: CardKind;
  question: string;
  answer: string;
  cloze_text: string | null;
  topic_code: string;
  page_ref: string;
  is_new: boolean;
  /**
   * OPTIONAL / ADDITIVE. Present in `card_state` server-side. When the API
   * includes them the grade buttons show exact intervals; otherwise they show
   * estimates, marked with a leading "≈".
   */
  stability?: number | null;
  difficulty?: number | null;
  /** OPTIONAL / ADDITIVE. Days since the last review, for the same purpose. */
  elapsed_days?: number | null;
}

/** GET /api/queue */
export interface QueueResponse {
  cards: QueueCard[];
  due_remaining: number;
  new_remaining: number;
  cap_reached: boolean;
}

/** POST /api/review */
export interface ReviewRequest {
  card_id: number;
  grade: Grade;
}

export interface ReviewResponse {
  card_id: number;
  interval_days: number;
  due_at: string;
  stability: number;
  difficulty: number;
}

export interface PendingCard {
  id: number;
  kind: CardKind;
  question: string;
  answer: string;
  cloze_text: string | null;
  topic_code: string;
  page_ref: string;
  source_filename: string;
}

/** GET /api/pending */
export interface PendingResponse {
  cards: PendingCard[];
  total: number;
}

export type DecideAction = "approve" | "reject";

/** POST /api/pending/decide */
export interface DecideRequest {
  ids: number[];
  action: DecideAction;
}

export interface DecideResponse {
  updated: number;
}

/** GET / PUT /api/settings */
export interface Settings {
  new_cards_per_day: number;
  daily_review_cap: number;
  desired_retention: number;
}

export type SettingsPatch = Partial<Settings>;

/**
 * `by_topic` is left open in the contract (`[...]`). Typed permissively so a
 * server that returns a richer row does not break the client, and every
 * consumer treats the fields as optional.
 */
export interface StatsTopic {
  code: string;
  label?: string | null;
  reviewed?: number | null;
  due?: number | null;
  new?: number | null;
}

export interface StatsDay {
  date: string;
  count: number;
}

/** GET /api/stats */
export interface Stats {
  today: { reviewed: number; again: number; streak: number };
  by_topic: StatsTopic[];
  last_14_days: StatsDay[];
  totals: { active: number; pending: number; sources: number };
}

/** GET /api/sources */
export interface Source {
  id: number;
  filename: string;
  topic_code: string;
  added_at: string;
  accepted: number;
  rejected: number;
  cost_estimate: number;
}
