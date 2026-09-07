/**
 * The only place in the app that knows a network exists.
 *
 * One function per endpoint in docs/CONTRACT.md, every one of them typed.
 * NEXT_PUBLIC_MOCK=1 swaps the whole surface for lib/mock.ts, which is how the
 * client is developed and verified while the Python API is being written.
 */

import * as mock from "./mock";
import type {
  AuthUser,
  DecideAction,
  DecideResponse,
  Explanation,
  GenerateResponse,
  Grade,
  PendingResponse,
  QueueResponse,
  ReviewResponse,
  Settings,
  SettingsPatch,
  Source,
  Stats,
  TestKind,
  TestPaper,
  TestResult,
  TestSummary,
  Topic,
  UploadResponse,
  Verdict,
} from "./types";

import { API_BASE, ApiError, errorMessage, MOCK } from "./http";
import { invalidate } from "./cache";

// Re-exported so this stays the one module the rest of the app imports from.
export { API_BASE, ApiError, errorMessage, MOCK };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Any write makes every cached read suspect. Invalidating the lot is blunt
  // and correct: there are four cached keys in the whole app, they are cheap
  // to refetch, and the alternative — a hand-maintained map from endpoint to
  // the screens it affects — is a stale-data bug waiting to be written.
  const writes = !!init?.method && init.method.toUpperCase() !== "GET";

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      // The session cookie has to ride along. In production the page and the
      // API share one origin, where fetch's default ("same-origin") would
      // already send it; this exists for local dev, where the frontend and
      // backend are on different ports and the default silently drops it.
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, path, `Could not reach the API at ${API_BASE}.`);
  }

  if (writes && res.ok) invalidate();

  if (!res.ok) {
    // The contract promises {"detail": "..."} on every error.
    let detail = res.statusText || "Request failed";
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* a non-JSON error body is still an error */
    }
    throw new ApiError(res.status, path, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

/* --- auth ---------------------------------------------------------------- */

/** GET /api/auth/me — 401 when there is no valid session. */
export function getMe(): Promise<AuthUser> {
  if (MOCK) return mock.getMe();
  return request<AuthUser>("/api/auth/me");
}

/** POST /api/auth/register — 422 when the name or email is taken. */
export function postRegister(
  name: string,
  email: string,
  password: string,
): Promise<AuthUser> {
  if (MOCK) return mock.postRegister(name, email, password);
  return request<AuthUser>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });
}

/** POST /api/auth/login — 401 for a wrong password OR an unknown email. */
export function postLogin(email: string, password: string): Promise<AuthUser> {
  if (MOCK) return mock.postLogin(email, password);
  return request<AuthUser>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

/** POST /api/auth/logout */
export function postLogout(): Promise<{ ok: true }> {
  if (MOCK) return mock.postLogout();
  return request<{ ok: true }>("/api/auth/logout", { method: "POST" });
}

/* --- endpoints ----------------------------------------------------------- */

/** GET /api/topics */
export function getTopics(): Promise<Topic[]> {
  if (MOCK) return mock.getTopics();
  return request<Topic[]>("/api/topics");
}

/** GET /api/queue?topic=&limit= */
export function getQueue(
  topic?: string,
  limit?: number,
): Promise<QueueResponse> {
  if (MOCK) return mock.getQueue(topic, limit);
  return request<QueueResponse>(`/api/queue${qs({ topic, limit })}`);
}

/** POST /api/review */
export function postReview(
  cardId: number,
  grade: Grade,
): Promise<ReviewResponse> {
  if (MOCK) return mock.postReview(cardId, grade);
  return request<ReviewResponse>("/api/review", {
    method: "POST",
    body: JSON.stringify({ card_id: cardId, grade }),
  });
}

/** GET /api/pending?limit=&offset=&topic= */
export function getPending(
  limit = 50,
  offset = 0,
  topic?: string,
): Promise<PendingResponse> {
  if (MOCK) return mock.getPending(limit, offset, topic);
  return request<PendingResponse>(`/api/pending${qs({ limit, offset, topic })}`);
}

/** POST /api/pending/decide — one request per action, whatever the batch size. */
export function postDecide(
  ids: number[],
  action: DecideAction,
): Promise<DecideResponse> {
  if (MOCK) return mock.postDecide(ids, action);
  return request<DecideResponse>("/api/pending/decide", {
    method: "POST",
    body: JSON.stringify({ ids, action }),
  });
}

/** GET /api/settings */
export function getSettings(): Promise<Settings> {
  if (MOCK) return mock.getSettings();
  return request<Settings>("/api/settings");
}

/** PUT /api/settings — accepts any subset, returns the full settings. */
export function putSettings(patch: SettingsPatch): Promise<Settings> {
  if (MOCK) return mock.putSettings(patch);
  return request<Settings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

/** GET /api/stats */
export function getStats(): Promise<Stats> {
  if (MOCK) return mock.getStats();
  return request<Stats>("/api/stats");
}

/** GET /api/sources */
export function getSources(): Promise<Source[]> {
  if (MOCK) return mock.getSources();
  return request<Source[]>("/api/sources");
}

/* --- test mode ----------------------------------------------------------- */

/** POST /api/tests — assembles a paper and starts the clock. */
export function createTest(
  kind: TestKind,
  topicCode?: string,
): Promise<TestPaper> {
  if (MOCK) return mock.createTest(kind, topicCode);
  return request<TestPaper>("/api/tests", {
    method: "POST",
    body: JSON.stringify({ kind, topic_code: topicCode }),
  });
}

/** GET /api/tests/{id} — the same paper with its recorded verdicts, for resuming. */
export function getTest(id: number): Promise<TestPaper> {
  if (MOCK) return mock.getTest(id);
  return request<TestPaper>(`/api/tests/${id}`);
}

/** POST /api/tests/{id}/answer — one call per verdict, so a closed tab loses nothing. */
export function postAnswer(
  id: number,
  ordinal: number,
  verdict: Verdict,
  seconds: number,
): Promise<{ ok: true }> {
  if (MOCK) return mock.postAnswer(id, ordinal, verdict, seconds);
  return request<{ ok: true }>(`/api/tests/${id}/answer`, {
    method: "POST",
    body: JSON.stringify({ ordinal, verdict, seconds }),
  });
}

/** POST /api/tests/{id}/submit — scores the paper and feeds the scheduler. */
export function submitTest(id: number): Promise<TestResult> {
  if (MOCK) return mock.submitTest(id);
  return request<TestResult>(`/api/tests/${id}/submit`, { method: "POST" });
}

/**
 * POST /api/topics/{code}/paper — sit a real paper for a subject, generating
 * whatever the deck cannot cover first.
 *
 * The difference from createTest: that one assembles from what exists and
 * returns an empty paper when the deck is empty. This one fills the gap, so
 * "no questions" stops being a possible outcome. Costs money, and 429s when
 * the day's budget is spent.
 */
export function sitPaper(
  topicCode: string,
  kind: TestKind,
): Promise<TestPaper> {
  if (MOCK) return mock.createTest(kind, topicCode);
  return request<TestPaper>(
    `/api/topics/${encodeURIComponent(topicCode)}/paper`,
    { method: "POST", body: JSON.stringify({ kind }) },
  );
}

/** GET /api/tests */
export function getTests(): Promise<TestSummary[]> {
  if (MOCK) return mock.getTests();
  return request<TestSummary[]>("/api/tests");
}

/* --- teaching ------------------------------------------------------------ */

/** POST /api/teach/explain — 422 when the model could not cite its source. */
export function postExplain(cardId: number): Promise<Explanation> {
  if (MOCK) return mock.postExplain(cardId);
  return request<Explanation>("/api/teach/explain", {
    method: "POST",
    body: JSON.stringify({ card_id: cardId }),
  });
}

/* --- upload -------------------------------------------------------------- */

export const ACCEPTED_EXTENSIONS = [
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".txt",
  ".md",
];

export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

/**
 * POST /api/sources/upload.
 *
 * XMLHttpRequest rather than fetch: this is the one request in the app whose
 * progress matters, and fetch cannot report upload progress. A phone on a
 * tunnelled connection pushing a 20 MB scan needs the bar to move.
 */
export function uploadSource(
  file: File,
  topicCode: string,
  onProgress?: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<UploadResponse> {
  if (MOCK) return mock.uploadSource(file, topicCode, onProgress, signal);

  const path = "/api/sources/upload";
  return new Promise<UploadResponse>((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    form.append("topic_code", topicCode);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    // Same reason as request()'s credentials: "include" — the session cookie
    // has to survive local dev's cross-port setup.
    xhr.withCredentials = true;
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total);
    });

    xhr.addEventListener("load", () => {
      // The bytes are gone; anything left is the server thinking.
      onProgress?.(1);
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText) as unknown;
      } catch {
        /* a non-JSON body is still a response */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as UploadResponse);
        return;
      }
      const detail = (body as { detail?: unknown } | null)?.detail;
      reject(
        new ApiError(
          xhr.status,
          path,
          typeof detail === "string" ? detail : xhr.statusText || "Upload failed",
        ),
      );
    });

    xhr.addEventListener("error", () =>
      reject(new ApiError(0, path, `Could not reach the API at ${API_BASE}.`)),
    );
    xhr.addEventListener("abort", () =>
      reject(new ApiError(0, path, "Upload cancelled.")),
    );

    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    xhr.send(form);
  });
}

/** POST /api/sources/{id}/generate — the step that spends money. */
export function generateCards(sourceId: number): Promise<GenerateResponse> {
  if (MOCK) return mock.generateCards(sourceId);
  return request<GenerateResponse>(`/api/sources/${sourceId}/generate`, {
    method: "POST",
  });
}

/**
 * POST /api/topics/{code}/generate — cards for one syllabus unit with nothing
 * uploaded. Same response shape as generateCards; also spends money, and 429s
 * when the account is over its daily cap.
 */
export function generateFromKnowledge(
  topicCode: string,
  unit: number,
  count?: number,
): Promise<GenerateResponse> {
  if (MOCK) return mock.generateFromKnowledge(topicCode, unit, count);
  return request<GenerateResponse>(
    `/api/topics/${encodeURIComponent(topicCode)}/generate`,
    { method: "POST", body: JSON.stringify({ unit, ...(count ? { count } : {}) }) },
  );
}
