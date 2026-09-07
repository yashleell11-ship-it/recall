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

/** One subject's assessment weight split, in marks out of 100. */
export interface SubjectScheme {
  attendance: number;
  ca: number;
  mte: number;
  ete: number;
}

/**
 * OPTIONAL / ADDITIVE. Real LPU subject facts, carried by GET /api/topics
 * items once the database has been seeded with the programme registry
 * (`recall.lpu`). An unseeded database sends null, and every consumer must
 * degrade to code + label alone.
 */
export interface TopicMeta {
  full_name: string;
  credits: number;
  /** The six syllabus units, in order. MTE covers 1–3; ETE covers all six. */
  units: string[];
  scheme: SubjectScheme;
  ca_policy: string;
  /** INT108 and CSE326 carry no mid-term at LPU; offering one is an error. */
  mte_exists: boolean;
  exam_format: string;
}

/** GET /api/topics */
export interface Topic {
  id: number;
  code: string;
  label: string;
  due: number;
  new: number;
  active: number;
  pending: number;
  /** OPTIONAL / ADDITIVE. See TopicMeta. */
  meta?: TopicMeta | null;
}

/**
 * Where a card came from. 'upload' is grounded in a verbatim quote from a file
 * the student uploaded; 'knowledge' was written from the model's own knowledge
 * of a syllabus unit, with no source to check it against. The UI must show the
 * difference — the two carry very different warranties.
 */
export type CardOrigin = "upload" | "knowledge";

export interface QueueCard {
  id: number;
  kind: CardKind;
  question: string;
  answer: string;
  cloze_text: string | null;
  topic_code: string;
  page_ref: string;
  is_new: boolean;
  /** OPTIONAL / ADDITIVE: absent on servers older than knowledge mode. */
  origin?: CardOrigin;
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
  /** OPTIONAL / ADDITIVE: absent on servers older than knowledge mode. */
  origin?: CardOrigin;
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
  id: number;
  code: string;
  label: string;
  due: number;
  new: number;
  active: number;
  pending: number;
  /** Not returned by the API today; kept optional for older mock fixtures. */
  reviewed?: number | null;
  /** OPTIONAL / ADDITIVE. See TopicMeta. */
  meta?: TopicMeta | null;
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

/* --- test mode ----------------------------------------------------------- */

/**
 * `mte40` is the LPU mid-term: 40 marks, 90 minutes, units 1–3. The server
 * refuses it (422) for a topic whose meta says `mte_exists: false`.
 */
export type TestKind = "class30" | "mte40" | "endterm100" | "fullday";

/** What the person claims about their own answer. `null` = not attempted yet. */
export type Verdict = "correct" | "partial" | "wrong" | "skipped";

export interface TestQuestion {
  ordinal: number;
  card_id: number;
  kind: CardKind;
  question: string;
  answer: string;
  cloze_text: string | null;
  marks: number;
  topic_code: string;
  page_ref: string;
  verdict: Verdict | null;
}

/** POST /api/tests and GET /api/tests/{id} */
export interface TestPaper {
  test_id: number;
  kind: TestKind;
  total_marks: number;
  /** null (or 0) for `fullday`, which has no limit. */
  time_limit_s: number | null;
  questions: TestQuestion[];
}

export interface TestTopicScore {
  topic_code: string;
  obtained: number;
  total: number;
}

/** POST /api/tests/{id}/submit */
export interface TestResult {
  obtained_marks: number;
  total_marks: number;
  /**
   * The contract does not fix the scale (0–1 or 0–100), so nothing in the
   * client reads it — every percentage on screen is derived from
   * obtained_marks / total_marks, which cannot disagree with the marks printed
   * beside it.
   */
  percent: number;
  duration_s: number;
  by_topic: TestTopicScore[];
  wrong: TestQuestion[];
  partial: TestQuestion[];
}

/** GET /api/tests */
export interface TestSummary {
  id: number;
  kind: TestKind;
  started_at: string;
  obtained_marks: number;
  total_marks: number;
  /**
   * OPTIONAL / ADDITIVE null: a paper that has been started but not submitted
   * has no duration yet. The client treats null or 0 as "still open" and offers
   * to resume it.
   */
  duration_s: number | null;
}

/* --- teaching ------------------------------------------------------------ */

/** POST /api/teach/explain */
export interface Explanation {
  explanation: string;
  source_quote: string;
  page_ref: string;
  topic_code: string;
  cached: boolean;
}

/* --- upload -------------------------------------------------------------- */

/** POST /api/sources/upload */
export interface UploadResponse {
  source_id: number;
  filename: string;
  kind: string;
  chunks: number;
  text_chars: number;
  /** Present when OCR output looks too sparse for the image it came from. */
  warning?: string | null;
}

/** POST /api/sources/{id}/generate */
export interface GenerateResponse {
  accepted: number;
  rejected: number;
  cost_usd: number;
  stopped_early: boolean;
}

/* --- auth ---------------------------------------------------------------- */

/** GET /api/auth/me, POST /api/auth/register, POST /api/auth/login */
export interface AuthUser {
  id: number;
  name: string;
  email: string;
}
