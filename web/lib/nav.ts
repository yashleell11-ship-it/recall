"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Whether the sidebar shows labels or just a rail.
 *
 * Same shape as the skin and theme stores: localStorage is an external store,
 * read through useSyncExternalStore rather than an effect, so the value is
 * available at first client render instead of arriving a frame later — and so
 * the server snapshot is honest about not knowing.
 */

export const NAV_COLLAPSED_KEY = "recall.nav.collapsed";

let current: boolean | null = null;
const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return localStorage.getItem(NAV_COLLAPSED_KEY) === "1";
  } catch {
    return false; // private mode, or storage disabled
  }
}

function getSnapshot(): boolean {
  if (current === null) current = read();
  return current;
}

/** The server has no idea; expanded is the honest default. */
function getServerSnapshot(): boolean {
  return false;
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

export function setCollapsed(next: boolean): void {
  current = next;
  try {
    localStorage.setItem(NAV_COLLAPSED_KEY, next ? "1" : "0");
  } catch {
    /* ignore */
  }
  for (const l of listeners) l();
}

export function useNavCollapsed() {
  const collapsed = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const toggle = useCallback(() => setCollapsed(!getSnapshot()), []);
  return { collapsed, toggle };
}
