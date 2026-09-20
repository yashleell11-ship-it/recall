"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Which test the /test screen offers: Recall's own generated papers, or the
 * curated "Yash Made Test" MCQ bank.
 *
 * Same shape as lib/nav.ts, and for the same reason: localStorage is an
 * external store, read through useSyncExternalStore rather than an effect, so
 * the remembered mode is on screen at the first client render instead of
 * arriving a frame later as a flicker from Recall to Yash Made Test.
 */

export type TestMode = "recall" | "yash";

export const TEST_MODE_KEY = "recall.test.mode";

let current: TestMode | null = null;
const listeners = new Set<() => void>();

function read(): TestMode {
  try {
    return localStorage.getItem(TEST_MODE_KEY) === "yash" ? "yash" : "recall";
  } catch {
    return "recall"; // private mode, or storage disabled
  }
}

function getSnapshot(): TestMode {
  if (current === null) current = read();
  return current;
}

/** The server has no idea which mode this browser remembers. */
function getServerSnapshot(): TestMode {
  return "recall";
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

export function setTestMode(next: TestMode): void {
  current = next;
  try {
    localStorage.setItem(TEST_MODE_KEY, next);
  } catch {
    /* ignore */
  }
  for (const l of listeners) l();
}

export function useTestMode() {
  const mode = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const setMode = useCallback((next: TestMode) => setTestMode(next), []);
  return { mode, setMode };
}
