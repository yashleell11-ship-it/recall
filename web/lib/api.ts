/**
 * The only place in the app that knows a network exists.
 *
 * One function per endpoint in docs/CONTRACT.md, every one of them typed.
 * NEXT_PUBLIC_MOCK=1 swaps the whole surface for lib/mock.ts, which is how the
 * client is developed and verified while the Python API is being written.
 */

import * as mock from "./mock";
import type {
  DecideAction,
  DecideResponse,
  Grade,
  PendingResponse,
  QueueResponse,
  ReviewResponse,
  Settings,
  SettingsPatch,
  Source,
  Stats,
  Topic,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export const MOCK = process.env.NEXT_PUBLIC_MOCK === "1";

export class ApiError extends Error {
  readonly status: number;
  readonly path: string;

  constructor(status: number, path: string, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }
}

/** Turn anything thrown by fetch or the API into one readable sentence. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.status === 0
      ? `Could not reach the API at ${API_BASE}.`
      : `${err.message} (${err.status})`;
  }
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, path, `Could not reach the API at ${API_BASE}.`);
  }

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
