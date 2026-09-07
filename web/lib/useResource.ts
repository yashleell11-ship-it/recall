"use client";

import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "./api";
import { cache, fresh, inflight, put } from "./cache";

export interface Resource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** True while a cached value is on screen and a fresher one is on the way. */
  revalidating: boolean;
  /** Refetch. Keeps whatever is already on screen until the new data lands. */
  reload: () => void;
}

interface State<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  revalidating: boolean;
}

/**
 * Fetch-on-mount, refetch-on-key-change, with a stale-while-revalidate cache.
 *
 * The app is served from a VPS in Virginia to a student in Punjab. Every
 * request costs a quarter of a second before the server has done anything at
 * all, and the old version of this hook paid that on every single navigation —
 * bounce Today → Review → Today and you watched three skeletons for data that
 * had not changed. Now the second visit paints from cache in the same frame
 * and the network round trip happens behind it.
 *
 * Stale data is shown, not hidden. `revalidating` says so, so a screen that
 * cares can dim itself; most do not care, because a review count that is four
 * seconds old is not a lie worth a spinner.
 *
 * `fetcher` must be stable — pass a module-level function or wrap it in
 * useCallback.
 */
export function useResource<T>(
  key: string,
  fetcher: () => Promise<T>,
): Resource<T> {
  const cached = cache.get(key)?.data as T | undefined;
  const [state, setState] = useState<State<T>>({
    data: cached ?? null,
    error: null,
    loading: cached === undefined,
    // Fresh means the effect below will not re-fetch, so nothing is on the
    // way and this must not claim otherwise.
    revalidating: cached !== undefined && !fresh(key),
  });
  const [nonce, setNonce] = useState(0);

  // The key the current state belongs to. Without this, switching topic
  // shows the previous topic's numbers for a frame before the effect runs —
  // React's own "adjusting state when a prop changes" pattern, which is a
  // render-phase setState and a re-render before anything is committed.
  const [shownKey, setShownKey] = useState(key);
  if (shownKey !== key) {
    setShownKey(key);
    const next = cache.get(key)?.data as T | undefined;
    setState({
      data: next ?? null,
      error: null,
      loading: next === undefined,
      revalidating: next !== undefined && !fresh(key),
    });
  }

  useEffect(() => {
    let live = true;

    // Just-arrived data is not revalidated. On a cold load the shell has
    // already prefetched this key; asking again a moment later would double
    // every request on the slowest path in the app.
    if (fresh(key) && !inflight.has(key)) return;

    // Two components asking for the same thing at the same time is one
    // request, not two — the dashboard and the shell both want the topic
    // list on a cold load.
    let request = inflight.get(key) as Promise<T> | undefined;
    if (request === undefined) {
      request = fetcher();
      inflight.set(key, request);
      void request.finally(() => {
        if (inflight.get(key) === request) inflight.delete(key);
      });
    }

    request
      .then((data) => {
        put(key, data);
        if (live) setState({ data, error: null, loading: false,
                            revalidating: false });
      })
      .catch((err: unknown) => {
        if (!live) return;
        // A failed revalidation leaves the cached data on screen. It is old,
        // but it is real, and blanking the page because one poll failed is
        // worse than showing yesterday's count.
        setState((prev) => ({
          data: prev.data,
          error: errorMessage(err),
          loading: false,
          revalidating: false,
        }));
      });

    return () => {
      live = false;
    };
  }, [key, nonce, fetcher]);

  const reload = useCallback(() => {
    cache.delete(key);
    inflight.delete(key);
    setState((prev) => ({
      ...prev,
      // Keep what is on screen; this is a refresh, not a teardown.
      loading: prev.data === null,
      revalidating: prev.data !== null,
      error: null,
    }));
    setNonce((n) => n + 1);
  }, [key]);

  return { ...state, reload };
}
