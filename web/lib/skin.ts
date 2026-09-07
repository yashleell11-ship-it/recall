"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * The skin store: which design language the product wears.
 *
 * "phosphor" — the Cyber-Academic identity: committed-dark void surfaces,
 *              serif knowledge text, emission accents. The default.
 * "ember"    — the original paper/graphite system, which keeps its own
 *              light/dark/system theme behaviour.
 * "github"   — GitHub's dark default. Flat, bordered, no grain, no serif:
 *              the palette a developer already has muscle memory for.
 *
 * Same shape as the theme store in ThemeToggle: localStorage is an external
 * store, read through useSyncExternalStore, applied to the <html> element as
 * a data-skin attribute. The root layout's bootstrap script applies a stored
 * choice before first paint, so there is never a flash of the other skin.
 */

export type Skin = "phosphor" | "ember" | "github";

/** Cycle order for the header control. */
export const SKINS: readonly Skin[] = ["phosphor", "github", "ember"] as const;

export const SKIN_KEY = "recall.skin";
export const DEFAULT_SKIN: Skin = "phosphor";

export function applySkin(skin: Skin): void {
  document.documentElement.setAttribute("data-skin", skin);
}

function readStored(): Skin {
  try {
    const v = localStorage.getItem(SKIN_KEY);
    if (v && (SKINS as readonly string[]).includes(v)) return v as Skin;
  } catch {
    /* private mode, or storage disabled */
  }
  return DEFAULT_SKIN;
}

let current: Skin | null = null;
const listeners = new Set<() => void>();

export function getSkin(): Skin {
  if (current === null) current = readStored();
  return current;
}

function getServerSnapshot(): Skin {
  return DEFAULT_SKIN;
}

export function subscribeSkin(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

export function setSkin(next: Skin): void {
  current = next;
  try {
    localStorage.setItem(SKIN_KEY, next);
  } catch {
    /* ignore */
  }
  applySkin(next);
  for (const l of listeners) l();
}

export function useSkin() {
  const skin = useSyncExternalStore(subscribeSkin, getSkin, getServerSnapshot);
  const toggle = useCallback(() => {
    const i = SKINS.indexOf(getSkin());
    setSkin(SKINS[(i + 1) % SKINS.length]);
  }, []);
  return { skin, setSkin, toggle };
}
