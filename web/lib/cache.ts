"use client";

/**
 * The read cache behind `useResource`, in its own module so `api.ts` can
 * invalidate it without importing the hook (which imports `api.ts` back).
 *
 * Module scope, which is to say: per browser tab, cleared by any full page
 * load. That is the whole reason it is safe to keep one user's data here —
 * every auth transition in this app is a hard `window.location.replace`, not a
 * client-side route change, so signing in as someone else starts from an empty
 * module. `clearCache` exists for the day that stops being true.
 */

export interface Entry {
  data: unknown;
  /** When it landed, so a caller can decide it is too fresh to re-fetch. */
  at: number;
}

export const cache = new Map<string, Entry>();
export const inflight = new Map<string, Promise<unknown>>();

/**
 * How long a cached value is treated as current enough to skip the network.
 *
 * Not a staleness policy — every write invalidates the whole cache, so a value
 * can only be stale if something changed outside this tab. It exists to stop
 * one cold load making the same request twice: the shell prefetches, the page
 * mounts a moment later, and without this it would immediately revalidate
 * data that arrived two hundred milliseconds ago.
 */
export const FRESH_MS = 15_000;

export function put(key: string, data: unknown): void {
  cache.set(key, { data, at: Date.now() });
}

export function fresh(key: string): boolean {
  const e = cache.get(key);
  return e !== undefined && Date.now() - e.at < FRESH_MS;
}

/** Drop cached responses. No arguments means all of them. */
export function invalidate(...keys: string[]): void {
  if (keys.length === 0) {
    cache.clear();
    return;
  }
  for (const k of keys) cache.delete(k);
}

/** Everything, including anything mid-flight. Call this on sign-out. */
export function clearCache(): void {
  cache.clear();
  inflight.clear();
}
