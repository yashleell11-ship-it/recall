"use client";

import { useCallback, useSyncExternalStore } from "react";

export type ThemeMode = "system" | "light" | "dark";

export const THEME_KEY = "recall.theme";

const ORDER: ThemeMode[] = ["system", "light", "dark"];

export function applyTheme(mode: ThemeMode) {
  const root = document.documentElement;
  if (mode === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", mode);
}

function readStored(): ThemeMode {
  try {
    const v = localStorage.getItem(THEME_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* private mode, or storage disabled */
  }
  return "system";
}

/* localStorage is an external store, so it is read through the hook React
   provides for external stores rather than mirrored into an effect. */

let current: ThemeMode | null = null;
const listeners = new Set<() => void>();

function getSnapshot(): ThemeMode {
  if (current === null) current = readStored();
  return current;
}

function getServerSnapshot(): ThemeMode {
  return "system";
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

function setMode(next: ThemeMode) {
  current = next;
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch {
    /* ignore */
  }
  applyTheme(next);
  for (const l of listeners) l();
}

export function useThemeMode() {
  const mode = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const cycle = useCallback(() => {
    setMode(ORDER[(ORDER.indexOf(getSnapshot()) + 1) % ORDER.length]);
  }, []);
  return { mode, cycle };
}

/**
 * Three states, spelled out. An icon can only ever show two, and "system" is
 * the state people most often want to confirm.
 */
export function ThemeToggle({
  mode,
  onCycle,
}: {
  mode: ThemeMode;
  onCycle: () => void;
}) {
  return (
    <button
      onClick={onCycle}
      title="Theme: system, light, dark (t)"
      aria-label={`Theme: ${mode}. Click to change.`}
      className="label h-6 px-1.5 rounded-xs border border-transparent hover:border-line hover:text-fg-2 transition-colors duration-[90ms]"
      style={{ minWidth: "3.9rem" }}
    >
      {mode}
    </button>
  );
}
