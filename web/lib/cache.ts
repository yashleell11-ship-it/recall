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

export const cache = new Map<string, unknown>();
export const inflight = new Map<string, Promise<unknown>>();

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
