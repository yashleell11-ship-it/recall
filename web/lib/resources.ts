"use client";

import {
  getLessonIndex,
  getQueue,
  getSettings,
  getSources,
  getStats,
  getStudyPlan,
  getTests,
  getTopics,
} from "./api";
import { cache, fresh, inflight, invalidate, put } from "./cache";
import type {
  QueueResponse,
  Settings,
  Source,
  Stats,
  TestSummary,
  Topic,
  StudyPlanEntry,
} from "./types";

/**
 * The data each screen needs, keyed, in one place — so the shell can start
 * fetching it before the screen exists.
 *
 * The shell will not paint a gated page until GET /api/auth/me has answered,
 * which is right: a flash of someone else's dashboard shape is worse than a
 * blank moment. But the page's own fetch used to wait on that too, purely
 * because an unmounted component runs no effects. Two round trips in series,
 * on a link between Punjab and Virginia, before a single number appeared.
 *
 * They do not have to be in series. Both requests carry the same session
 * cookie and the server scopes every row by it, so a fetch that starts before
 * the identity is confirmed cannot return the wrong person's data — the worst
 * case is a 401 on a request whose page was about to be redirected away from
 * anyway. So the shell fires both at once and the page, when it finally
 * mounts, finds the answer already in hand or already in flight.
 */

export interface DashboardData {
  topics: Topic[];
  stats: Stats;
  settings: Settings;
}

export async function fetchDashboard(): Promise<DashboardData> {
  const [topics, stats, settings] = await Promise.all([
    getTopics(),
    getStats(),
    getSettings(),
  ]);
  return { topics, stats, settings };
}

export interface PickerData {
  topics: Topic[];
  tests: TestSummary[];
  /** OPTIONAL / ADDITIVE: absent on a server that predates the study plan, in
   *  which case the subject cards simply carry no advice line. */
  plan?: StudyPlanEntry[];
}

export async function fetchPicker(): Promise<PickerData> {
  // Folded into the existing bundle rather than given a cache key of its own:
  // it is read on exactly one screen, at the same moment as the other two, and
  // a third key would mean a third prefetch to keep in step.
  const [topics, tests, plan] = await Promise.all([
    getTopics(),
    getTests(),
    // Advice is the least important thing on this screen. A server that cannot
    // produce it must not stop the paper picker from rendering.
    getStudyPlan().catch(() => undefined),
  ]);
  return { topics, tests, plan };
}

export interface UploadContext {
  topics: Topic[];
  sources: Source[];
}

export async function fetchUploadContext(): Promise<UploadContext> {
  const [topics, sources] = await Promise.all([getTopics(), getSources()]);
  return { topics, sources };
}

/** Cache key → fetcher, for every screen that uses `useResource`. */
const RESOURCES: Record<string, () => Promise<unknown>> = {
  dashboard: fetchDashboard,
  "test-picker": fetchPicker,
  sources: getSources,
  "upload-context": fetchUploadContext,
  learn: getLessonIndex,
};

/** Which screen a path belongs to. Unlisted paths simply prefetch nothing. */
const ROUTE_KEY: Record<string, string> = {
  "/": "dashboard",
  "/test": "test-picker",
  "/sources": "sources",
  "/upload": "upload-context",
  // The reader's own key is per-unit (`lesson:MTH165:1`) and deliberately not
  // here: there is nothing to prefetch until the path names a unit, and a
  // registry entry that can never fire reads as a bug.
  "/learn": "learn",
};

/**
 * Start the fetch for `pathname` now, if it is not already answered or in
 * flight. Returns nothing and throws nothing: a failure here is not an error,
 * it is a prefetch that did not pay off, and the page will ask again.
 */
export function prefetchFor(pathname: string): void {
  const key = ROUTE_KEY[pathname];
  if (!key || cache.has(key) || inflight.has(key)) return;

  const request = RESOURCES[key]();
  inflight.set(key, request);
  request
    .then((data) => {
      put(key, data);
    })
    .catch(() => {
      /* the page will surface it properly when it mounts and asks */
    })
    .finally(() => {
      if (inflight.get(key) === request) inflight.delete(key);
    });
}

/* --- the review queue: prefetched on intent, consumed once --------------- */
/*
 * The review screen is not on ROUTE_KEY above because it does not behave
 * like the other four. It owns mutable session state — the queue drains as
 * you answer, cards get pulled in mid-session by `loadMore` — so treating its
 * data as a long-lived cache entry that silently revalidates underneath an
 * active session is asking for a card to reappear or vanish while someone is
 * answering it. What this gives it instead is narrower and safer: a one-shot
 * head start. The moment intent is clear — a hover on "Start review", a key
 * press, a click on a topic row — the fetch begins. The review screen either
 * finds it waiting (or already in flight) and uses it once, or finds nothing
 * and fetches exactly as it always has. Nothing here is revalidated, and
 * nothing here is written back to by the session.
 */

function reviewQueueKey(topic?: string): string {
  return `review:${topic ?? ""}`;
}

/** Start the fetch for a review queue before the review screen exists. Safe
 * to call from a hover handler — a hover that never turns into a click just
 * means one request that nobody read the answer to. */
export function prefetchReviewQueue(topic?: string): void {
  const key = reviewQueueKey(topic);
  if (cache.has(key) || inflight.has(key)) return;
  const request = Promise.all([getQueue(topic, 50), getSettings()]);
  inflight.set(key, request);
  request
    .then((data) => {
      put(key, data);
    })
    .catch(() => {
      /* the review screen's own fetch will surface the error */
    })
    .finally(() => {
      if (inflight.get(key) === request) inflight.delete(key);
    });
}

/**
 * Take a waiting prefetch for `topic`, if there is a fresh one. Returns null
 * — not a rejected promise — when there is nothing to take, so the caller's
 * fallback is a plain `if`, not a `catch`.
 *
 * Consuming removes it from the shared cache immediately either way: once
 * the review screen has it, this copy is stale by definition — the session
 * is about to start mutating a queue the cache knows nothing about.
 */
export function consumeReviewQueuePrefetch(
  topic?: string,
): Promise<[QueueResponse, Settings]> | null {
  const key = reviewQueueKey(topic);
  if (cache.has(key)) {
    const value = fresh(key)
      ? (cache.get(key)!.data as [QueueResponse, Settings])
      : null;
    invalidate(key);
    if (value) return Promise.resolve(value);
    return null;
  }
  const pending = inflight.get(key);
  if (pending) {
    inflight.delete(key);
    return pending as Promise<[QueueResponse, Settings]>;
  }
  return null;
}
