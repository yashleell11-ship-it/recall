"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { MOCK } from "@/lib/api";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import { ShortcutsOverlay } from "./Shortcuts";
import { ThemeToggle, useThemeMode } from "./ThemeToggle";
import { Kbd } from "./ui";

const NAV = [
  { href: "/", label: "Today" },
  { href: "/approve", label: "Approve" },
  { href: "/sources", label: "Sources" },
  { href: "/settings", label: "Settings" },
];

/** `g` then a letter. Vim's idiom, and it keeps single letters free for pages. */
const GOTO: Record<string, string> = {
  d: "/",
  r: "/review",
  a: "/approve",
  o: "/sources",
  s: "/settings",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [help, setHelp] = useState(false);
  const { mode, cycle } = useThemeMode();

  const pendingG = useRef(false);
  const gTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const closeHelp = useCallback(() => setHelp(false), []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // While the overlay is open it owns the keyboard entirely, so a page's
      // own handlers cannot fire underneath it.
      if (help) {
        if (e.key === "Escape" || e.key === "?") {
          e.preventDefault();
          setHelp(false);
        }
        e.stopPropagation();
        return;
      }

      if (isTypingTarget(e) || hasModifier(e)) return;

      if (e.key === "?") {
        e.preventDefault();
        e.stopPropagation();
        setHelp(true);
        return;
      }

      if (pendingG.current) {
        const target = GOTO[e.key.toLowerCase()];
        pendingG.current = false;
        if (gTimer.current) clearTimeout(gTimer.current);
        if (target) {
          e.preventDefault();
          e.stopPropagation();
          router.push(target);
          return;
        }
      }

      if (e.key === "g") {
        pendingG.current = true;
        if (gTimer.current) clearTimeout(gTimer.current);
        gTimer.current = setTimeout(() => {
          pendingG.current = false;
        }, 900);
        return;
      }

      if (e.key === "t") {
        e.preventDefault();
        e.stopPropagation();
        cycle();
      }
    }

    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [router, cycle, help]);

  // Focus mode: the review screen carries no chrome at all.
  const focus = pathname === "/review";

  return (
    <>
      {!focus && (
        <header className="border-b border-line bg-surface sticky top-0 z-30">
          <div className="mx-auto max-w-[1120px] px-4 h-11 flex items-center gap-5">
            <Link
              href="/"
              className="text-[11px] font-bold tracking-[0.16em] text-fg shrink-0"
            >
              RECALL
            </Link>

            <nav className="flex items-center gap-1 min-w-0 scroll-x">
              {NAV.map((item) => {
                const active =
                  item.href === "/"
                    ? pathname === "/"
                    : pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`px-2 h-11 flex items-center text-[13px] whitespace-nowrap
                      border-b-2 -mb-px transition-colors duration-[90ms]
                      ${
                        active
                          ? "text-fg font-semibold border-fg"
                          : "text-fg-2 font-normal border-transparent hover:text-fg"
                      }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            <div className="ml-auto flex items-center gap-2 shrink-0">
              {MOCK && (
                <span
                  className="label hidden sm:inline border border-line rounded-xs px-1.5 py-px"
                  title="Serving fixture data from lib/mock.ts"
                >
                  mock data
                </span>
              )}
              <ThemeToggle mode={mode} onCycle={cycle} />
              <button
                onClick={() => setHelp(true)}
                title="Keyboard shortcuts (?)"
                aria-label="Keyboard shortcuts"
                className="hidden sm:block"
              >
                <Kbd>?</Kbd>
              </button>
            </div>
          </div>
        </header>
      )}

      {children}

      {help && <ShortcutsOverlay onClose={closeHelp} />}
    </>
  );
}
