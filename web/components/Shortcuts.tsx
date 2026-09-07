"use client";

import { useEffect, useRef } from "react";
import { Kbd } from "./ui";

export interface ShortcutRow {
  keys: string[];
  /** Rendered between keys, e.g. "then" or "/". */
  joiner?: string;
  description: string;
}

export interface ShortcutGroup {
  title: string;
  rows: ShortcutRow[];
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Anywhere",
    rows: [
      { keys: ["?"], description: "Show this list" },
      { keys: ["Esc"], description: "Close this list" },
      { keys: ["g", "d"], joiner: "then", description: "Go to today" },
      { keys: ["g", "r"], joiner: "then", description: "Start a review session" },
      { keys: ["g", "t"], joiner: "then", description: "Go to test" },
      { keys: ["g", "u"], joiner: "then", description: "Go to upload" },
      { keys: ["g", "o"], joiner: "then", description: "Go to sources" },
      { keys: ["g", "s"], joiner: "then", description: "Go to settings" },
      { keys: ["t"], description: "Cycle theme: system, light, dark" },
    ],
  },
  {
    title: "Today",
    rows: [{ keys: ["Enter"], description: "Start reviewing" }],
  },
  {
    title: "Review",
    rows: [
      { keys: ["Space"], description: "Show the answer" },
      { keys: ["1"], description: "Again" },
      { keys: ["2"], description: "Hard" },
      { keys: ["3"], description: "Good" },
      { keys: ["4"], description: "Easy" },
      { keys: ["Space"], description: "Good, once the answer is showing" },
      { keys: ["Esc"], description: "Leave the session" },
    ],
  },
  {
    title: "Pick a paper",
    rows: [
      { keys: ["1", "3"], joiner: "…", description: "Choose class, end term, full day" },
      { keys: ["Enter"], description: "Start the paper" },
    ],
  },
  {
    title: "Sitting a paper",
    rows: [
      { keys: ["Space"], description: "Reveal the answer" },
      { keys: ["1"], description: "Wrong" },
      { keys: ["2"], description: "Partial — only on 2+ mark questions" },
      { keys: ["3"], description: "Correct" },
      { keys: ["s"], description: "Skip: no marks, and no review recorded" },
      { keys: ["m"], description: "Mark for review, and unmark" },
      { keys: ["j", "k"], joiner: "/", description: "Next / previous question" },
      { keys: ["←", "→"], joiner: "/", description: "Next / previous question" },
      { keys: ["Home", "End"], joiner: "/", description: "First / last question" },
      { keys: ["p"], description: "Open the question palette" },
      { keys: ["Enter"], description: "Submit the paper" },
      { keys: ["Esc"], description: "Leave — every answer is already saved" },
    ],
  },
  {
    title: "After a paper",
    rows: [
      { keys: ["j", "k"], joiner: "/", description: "Move through what you missed" },
      { keys: ["e"], description: "Explain the focused question" },
    ],
  },
  {
    title: "Upload",
    rows: [
      { keys: ["f"], description: "Choose files" },
      { keys: ["c"], description: "Take a photo" },
    ],
  },
  {
    title: "Settings",
    rows: [
      { keys: ["Tab"], description: "Move between fields" },
      { keys: ["↑", "↓"], joiner: "/", description: "Adjust the focused field" },
    ],
  },
];

function Row({ row }: { row: ShortcutRow }) {
  return (
    <div className="flex items-baseline gap-3 py-[2px]">
      <span className="flex items-center gap-1 shrink-0 w-[104px]">
        {row.keys.map((k, i) => (
          <span key={k + i} className="flex items-center gap-1">
            {i > 0 && row.joiner ? (
              <span className="text-[10px] text-fg-3">{row.joiner}</span>
            ) : null}
            <Kbd>{k}</Kbd>
          </span>
        ))}
      </span>
      <span className="text-[13px] text-fg-2 leading-snug">{row.description}</span>
    </div>
  );
}

export function ShortcutsOverlay({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // preventScroll: focusing a panel taller than the viewport would otherwise
    // scroll the backdrop and eat the top gap.
    ref.current?.focus({ preventScroll: true });
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center p-4 sm:p-8 overflow-auto"
      style={{ background: "color-mix(in srgb, var(--bg) 93%, transparent)" }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        className="panel w-full max-w-4xl outline-none my-auto"
      >
        <header className="flex items-center justify-between px-3 h-9 border-b border-line bg-sunken">
          <h2 className="label">Keyboard shortcuts</h2>
          <button
            onClick={onClose}
            className="text-[11px] text-fg-3 hover:text-fg flex items-center gap-1.5"
          >
            <Kbd>Esc</Kbd>
            close
          </button>
        </header>

        <div className="px-4 py-3.5 grid gap-x-10 gap-y-4 sm:grid-cols-2">
          {SHORTCUT_GROUPS.map((g) => (
            <section key={g.title}>
              <h3 className="label mb-1.5">{g.title}</h3>
              <div className="border-t border-line pt-1.5">
                {g.rows.map((r, i) => (
                  <Row key={i} row={r} />
                ))}
              </div>
            </section>
          ))}
        </div>

        <footer className="px-4 py-2.5 border-t border-line text-[12px] text-fg-3">
          Shortcuts are ignored while a text field has focus.
        </footer>
      </div>
    </div>
  );
}
