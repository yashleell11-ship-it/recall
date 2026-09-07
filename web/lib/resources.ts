"use client";

import { getSettings, getSources, getStats, getTests, getTopics } from "./api";
import { cache, inflight, put } from "./cache";
import type { Settings, Source, Stats, TestSummary, Topic } from "./types";

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
}

export async function fetchPicker(): Promise<PickerData> {
  const [topics, tests] = await Promise.all([getTopics(), getTests()]);
  return { topics, tests };
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
};

/** Which screen a path belongs to. Unlisted paths simply prefetch nothing. */
const ROUTE_KEY: Record<string, string> = {
  "/": "dashboard",
  "/test": "test-picker",
  "/sources": "sources",
  "/upload": "upload-context",
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
