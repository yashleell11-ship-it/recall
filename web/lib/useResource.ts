"use client";

import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "./api";

export interface Resource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** Refetch. Keeps whatever is already on screen until the new data lands. */
  reload: () => void;
}

interface State<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/**
 * Fetch-on-mount, refetch-on-key-change.
 *
 * `fetcher` must be stable — pass a module-level function or wrap it in
 * useCallback. Nothing is set synchronously inside the effect, so the loading
 * flag starts true and every later transition happens in a promise callback or
 * an event handler.
 */
export function useResource<T>(
  key: string,
  fetcher: () => Promise<T>,
): Resource<T> {
  const [state, setState] = useState<State<T>>({
    data: null,
    error: null,
    loading: true,
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    fetcher()
      .then((data) => {
        if (live) setState({ data, error: null, loading: false });
      })
      .catch((err: unknown) => {
        if (live) {
          setState((prev) => ({
            data: prev.data,
            error: errorMessage(err),
            loading: false,
          }));
        }
      });
    return () => {
      live = false;
    };
  }, [key, nonce, fetcher]);

  const reload = useCallback(() => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    setNonce((n) => n + 1);
  }, []);

  return { ...state, reload };
}
