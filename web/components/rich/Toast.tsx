"use client";

import { motion, useReducedMotion } from "motion/react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

export type ToastVariant = "success" | "error";

export interface ToastOptions {
  variant?: ToastVariant;
}

/** Fire a toast. Returns nothing; toasts are fire-and-forget by design. */
export type ToastFn = (message: string, options?: ToastOptions) => void;

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
}

const ToastContext = createContext<ToastFn | null>(null);

export function useToast(): ToastFn {
  const fn = useContext(ToastContext);
  if (!fn) {
    throw new Error("useToast must be called inside <ToastProvider>.");
  }
  return fn;
}

const DISMISS_MS = 3500;
const EXIT_MS = 180;

/**
 * One toast at a time, bottom-centre, springs in, dismisses itself after
 * 3.5 seconds. A second toast replaces the first rather than stacking —
 * a queue of old news is not feedback, it is clutter.
 *
 * The exit is driven by our own timers rather than AnimatePresence: the
 * removal must land even if a route transition is in flight when the clock
 * runs out.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [item, setItem] = useState<ToastItem | null>(null);
  const [leaving, setLeaving] = useState(false);
  const nextId = useRef(0);
  const reduced = useReducedMotion();

  const toast = useCallback<ToastFn>((message, options) => {
    setLeaving(false);
    setItem({
      id: ++nextId.current,
      message,
      variant: options?.variant ?? "success",
    });
  }, []);

  // Keyed on the item so a replacement restarts the clock.
  useEffect(() => {
    if (!item) return;
    const fade = setTimeout(() => setLeaving(true), DISMISS_MS - EXIT_MS);
    const drop = setTimeout(() => setItem(null), DISMISS_MS);
    return () => {
      clearTimeout(fade);
      clearTimeout(drop);
    };
  }, [item]);

  return (
    <ToastContext.Provider value={toast}>
      {children}

      <div
        className="fixed inset-x-0 z-[70] flex justify-center px-4 pointer-events-none"
        style={{ bottom: "max(1rem, env(safe-area-inset-bottom))" }}
      >
        {item && (
          <motion.div
            key={item.id}
            role="status"
            aria-live="polite"
            initial={
              reduced ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.97 }
            }
            animate={
              leaving
                ? reduced
                  ? { opacity: 0 }
                  : { opacity: 0, y: 8, scale: 0.98 }
                : { opacity: 1, y: 0, scale: 1 }
            }
            transition={
              reduced
                ? { duration: 0.1 }
                : leaving
                  ? { duration: EXIT_MS / 1000, ease: "easeIn" }
                  : { type: "spring", stiffness: 480, damping: 34 }
            }
            className="elev-3 rounded-md pointer-events-auto flex items-center gap-2.5 pl-3 pr-3.5 h-10 max-w-[calc(100vw-2rem)]"
          >
            <span
              aria-hidden="true"
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{
                background:
                  item.variant === "error" ? "var(--g-again)" : "var(--g-good)",
              }}
            />
            <span className="text-[13px] text-fg leading-snug truncate">
              {item.message}
            </span>
          </motion.div>
        )}
      </div>
    </ToastContext.Provider>
  );
}
