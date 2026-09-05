/**
 * The command palette's vocabulary.
 *
 * Actions are plain data plus a closure: the palette component renders and
 * filters them but knows nothing about routes, tests, or themes. The shell
 * builds the default set once with `buildDefaultActions`, handing in the
 * capabilities an action is allowed to touch — navigation, theme, toasts.
 */

import type { ThemeMode } from "@/components/ThemeToggle";
import { createTest, errorMessage } from "@/lib/api";
import type { TestKind } from "@/lib/types";

export interface PaletteAction {
  /** Stable, unique. Used as the React key and the aria id. */
  id: string;
  /** What the row says, and what the query matches against. */
  title: string;
  /** Group header the row sits under. Groups keep their first-seen order. */
  section: string;
  /** Extra text the query also matches, never shown. */
  keywords?: string;
  /** Keycaps rendered at the right edge of the row, e.g. ["g", "d"]. */
  hint?: string[];
  perform: () => void | Promise<void>;
}

export interface PaletteDeps {
  /** Navigate; the shell passes next/navigation's router.push. */
  push: (href: string) => void;
  /** Set the theme outright — the palette names states, it does not cycle. */
  setTheme: (mode: ThemeMode) => void;
  toast: (message: string, options?: { variant?: "success" | "error" }) => void;
}

/** Starts a paper and lands on it; failure surfaces as a toast, not a throw. */
function startTest(deps: PaletteDeps, kind: TestKind): Promise<void> {
  return createTest(kind)
    .then((paper) => deps.push(`/test/${paper.test_id}`))
    .catch((err: unknown) => {
      deps.toast(errorMessage(err), { variant: "error" });
    });
}

export function buildDefaultActions(deps: PaletteDeps): PaletteAction[] {
  return [
    // --- navigate ---------------------------------------------------------
    {
      id: "nav-today",
      title: "Go to Today",
      section: "Navigate",
      keywords: "home dashboard queue due",
      hint: ["g", "d"],
      perform: () => deps.push("/"),
    },
    {
      id: "nav-test",
      title: "Go to Test",
      section: "Navigate",
      keywords: "paper exam picker",
      hint: ["g", "t"],
      perform: () => deps.push("/test"),
    },
    {
      id: "nav-approve",
      title: "Go to Approve",
      section: "Navigate",
      keywords: "queue pending cards verify",
      hint: ["g", "a"],
      perform: () => deps.push("/approve"),
    },
    {
      id: "nav-upload",
      title: "Go to Upload",
      section: "Navigate",
      keywords: "pdf file photo scan",
      hint: ["g", "u"],
      perform: () => deps.push("/upload"),
    },
    {
      id: "nav-sources",
      title: "Go to Sources",
      section: "Navigate",
      keywords: "documents pdfs material",
      hint: ["g", "o"],
      perform: () => deps.push("/sources"),
    },
    {
      id: "nav-settings",
      title: "Go to Settings",
      section: "Navigate",
      keywords: "preferences options",
      hint: ["g", "s"],
      perform: () => deps.push("/settings"),
    },

    // --- session ----------------------------------------------------------
    {
      id: "start-review",
      title: "Start review session",
      section: "Session",
      keywords: "cards study flashcards due",
      hint: ["g", "r"],
      perform: () => deps.push("/review"),
    },
    {
      id: "start-class30",
      title: "Sit a class test — 30 marks",
      section: "Session",
      keywords: "sessional short paper exam start",
      perform: () => startTest(deps, "class30"),
    },
    {
      id: "start-endterm100",
      title: "Sit an end term — 100 marks",
      section: "Session",
      keywords: "final full paper exam start",
      perform: () => startTest(deps, "endterm100"),
    },
    {
      id: "start-fullday",
      title: "Sit a full-day paper — every active card",
      section: "Session",
      keywords: "marathon complete deck exam start",
      perform: () => startTest(deps, "fullday"),
    },

    // --- theme --------------------------------------------------------------
    {
      id: "theme-light",
      title: "Theme: light",
      section: "Theme",
      keywords: "paper appearance colour color mode",
      perform: () => deps.setTheme("light"),
    },
    {
      id: "theme-dark",
      title: "Theme: dark",
      section: "Theme",
      keywords: "graphite appearance colour color mode night",
      perform: () => deps.setTheme("dark"),
    },
    {
      id: "theme-system",
      title: "Theme: system",
      section: "Theme",
      keywords: "auto appearance colour color mode os",
      perform: () => deps.setTheme("system"),
    },
  ];
}
