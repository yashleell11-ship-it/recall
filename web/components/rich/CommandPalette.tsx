"use client";

import { motion, useReducedMotion } from "motion/react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import type { PaletteAction } from "@/lib/palette";

/**
 * Cmd+K / Ctrl+K. One text field, every destination and action in the
 * product, substring matching, arrows + Enter. While it is open it owns the
 * keyboard outright: its window listener registers before the shell's (child
 * effects run first) and stops propagation, and everything typed lands in
 * the input, which the shell's shortcut handler already ignores.
 *
 * The scrim below carries the product's single permitted backdrop-blur.
 */

const OPEN_EVENT = "recall:command-palette";

/** Ask the mounted palette to open — for buttons that want to point at it. */
export function openCommandPalette(): void {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT));
}

/* Client-only facts, read the way React wants external facts read: through
   useSyncExternalStore, with a server snapshot for the SSR pass. */
const noSubscription = () => () => {};
const isMacClient = () => /Mac|iPhone|iPad|iPod/.test(navigator.platform);
const falseOnServer = () => false;
const trueOnClient = () => true;

/** "⌘K" on a Mac, "Ctrl K" everywhere else. Resolved on the client. */
export function useCommandKeyLabel(): string {
  const isMac = useSyncExternalStore(noSubscription, isMacClient, falseOnServer);
  return isMac ? "⌘K" : "Ctrl K";
}

export function CommandPalette({ actions }: { actions: PaletteAction[] }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(0);

  const reduced = useReducedMotion();
  const inputRef = useRef<HTMLInputElement>(null);
  const prevFocus = useRef<HTMLElement | null>(null);

  const keyLabel = useCommandKeyLabel();

  // Portals need a document; the server pass renders nothing.
  const mounted = useSyncExternalStore(noSubscription, trueOnClient, falseOnServer);

  const show = useCallback(() => {
    setQuery("");
    setSel(0);
    setOpen(true);
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
  }, []);

  // The global chord, plus Escape while open. Capture phase, registered
  // before the shell's own capture listener (child effects run first), and
  // stopping propagation so nothing underneath ever reacts to these keys.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (
        (e.key === "k" || e.key === "K") &&
        (e.metaKey || e.ctrlKey) &&
        !e.altKey &&
        !e.shiftKey
      ) {
        e.preventDefault();
        e.stopPropagation();
        if (open) close();
        else show();
        return;
      }
      if (open && e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        close();
      }
    }
    window.addEventListener("keydown", onKey, { capture: true });
    return () =>
      window.removeEventListener("keydown", onKey, { capture: true });
  }, [open, close, show]);

  // Buttons elsewhere can open it without owning any state.
  useEffect(() => {
    window.addEventListener(OPEN_EVENT, show);
    return () => window.removeEventListener(OPEN_EVENT, show);
  }, [show]);

  // Focus in on open, back out on close; lock the page scroll meanwhile.
  useEffect(() => {
    if (!open) return;
    prevFocus.current = document.activeElement as HTMLElement | null;
    const prevOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.documentElement.style.overflow = prevOverflow;
      prevFocus.current?.focus?.();
      prevFocus.current = null;
    };
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    return actions.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        (a.keywords ? a.keywords.toLowerCase().includes(q) : false),
    );
  }, [actions, query]);

  // Keep the selected row on screen while arrowing through a long list.
  useEffect(() => {
    if (!open) return;
    const a = filtered[sel];
    if (!a) return;
    document
      .getElementById(`cp-${a.id}`)
      ?.scrollIntoView({ block: "nearest" });
  }, [sel, open, filtered]);

  const run = useCallback(
    (action: PaletteAction) => {
      close();
      void action.perform();
    },
    [close],
  );

  function onInputKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (filtered.length) setSel((s) => (s + 1) % filtered.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (filtered.length) setSel((s) => (s - 1 + filtered.length) % filtered.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const a = filtered[sel];
      if (a) run(a);
    } else if (e.key === "Tab") {
      // The palette owns the keyboard; there is nowhere for focus to go.
      e.preventDefault();
    }
  }

  if (!mounted || !open) return null;

  const activeId = filtered[sel] ? `cp-${filtered[sel].id}` : undefined;

  // Opening animates; closing is instant. Deliberate: dismissal should feel
  // like a decision taking effect, not a curtain coming down — and an exit
  // animation would have to survive the route change an action just started.
  return createPortal(
    (
        <motion.div
          className="fixed inset-0 z-[60] scrim-blur flex items-start justify-center px-4 pt-[14vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: reduced ? 0.05 : 0.12, ease: "easeOut" }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) close();
          }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            className="w-full max-w-[560px] elev-3 rounded-md overflow-hidden"
            initial={reduced ? false : { opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={
              reduced
                ? { duration: 0.05 }
                : { type: "spring", stiffness: 560, damping: 38, mass: 0.8 }
            }
          >
            <input
              ref={inputRef}
              autoFocus
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSel(0);
              }}
              onKeyDown={onInputKey}
              placeholder="Type a command…"
              spellCheck={false}
              autoComplete="off"
              role="combobox"
              aria-expanded="true"
              aria-controls="cp-list"
              aria-activedescendant={activeId}
              className="w-full h-11 px-3.5 bg-transparent outline-none border-b border-line text-[14px] text-fg placeholder:text-fg-3"
              style={{ boxShadow: "none" }}
            />

            <div
              id="cp-list"
              role="listbox"
              aria-label="Commands"
              className="max-h-[min(420px,55vh)] overflow-y-auto overscroll-contain py-1.5"
            >
              {filtered.length === 0 ? (
                <div className="px-3.5 py-6 text-[13px] text-fg-3">
                  Nothing matches &ldquo;{query.trim()}&rdquo;.
                </div>
              ) : (
                filtered.map((a, i) => {
                  const header =
                    i === 0 || filtered[i - 1].section !== a.section ? (
                      <div className="label px-3.5 pt-2.5 pb-1" aria-hidden="true">
                        {a.section}
                      </div>
                    ) : null;
                  const selected = i === sel;
                  return (
                    <div key={a.id}>
                      {header}
                      <button
                        id={`cp-${a.id}`}
                        role="option"
                        aria-selected={selected}
                        tabIndex={-1}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => run(a)}
                        onMouseEnter={() => setSel(i)}
                        className={`w-full flex items-center gap-3 px-3.5 h-9 text-left text-[13px] ${
                          selected
                            ? "bg-surface-hover text-fg"
                            : "text-fg-2"
                        }`}
                        style={
                          selected
                            ? { boxShadow: "inset 2px 0 0 var(--accent)" }
                            : undefined
                        }
                      >
                        <span className="min-w-0 truncate">
                          <Highlight title={a.title} query={query} />
                        </span>
                        {a.hint ? (
                          <span
                            className="ml-auto flex items-center gap-1 shrink-0"
                            aria-hidden="true"
                          >
                            {a.hint.map((k, j) => (
                              <kbd key={j} className="kbd">
                                {k}
                              </kbd>
                            ))}
                          </span>
                        ) : null}
                      </button>
                    </div>
                  );
                })
              )}
            </div>

            <footer className="flex items-center gap-3.5 px-3.5 h-8 border-t border-line text-[11px] text-fg-3">
              <span className="flex items-center gap-1">
                <kbd className="kbd">↑</kbd>
                <kbd className="kbd">↓</kbd>
                navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="kbd">↵</kbd>
                run
              </span>
              <span className="flex items-center gap-1">
                <kbd className="kbd">esc</kbd>
                close
              </span>
              <span className="ml-auto hidden sm:inline">{keyLabel} toggles</span>
            </footer>
          </motion.div>
        </motion.div>
    ),
    document.body,
  );
}

/** The matched substring set in the ink weight; the rest stays quiet. */
function Highlight({ title, query }: { title: string; query: string }): ReactNode {
  const q = query.trim().toLowerCase();
  if (!q) return title;
  const idx = title.toLowerCase().indexOf(q);
  if (idx === -1) return title;
  return (
    <>
      {title.slice(0, idx)}
      <span className="font-semibold text-fg">
        {title.slice(idx, idx + q.length)}
      </span>
      {title.slice(idx + q.length)}
    </>
  );
}
