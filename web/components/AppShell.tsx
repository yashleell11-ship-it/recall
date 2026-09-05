"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { MOCK } from "@/lib/api";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import { buildDefaultActions } from "@/lib/palette";
import { useSkin } from "@/lib/skin";
import { CommandPalette, ToastProvider, useToast } from "./rich";
import { ShortcutsOverlay } from "./Shortcuts";
import { ThemeToggle, useThemeMode } from "./ThemeToggle";
import type { ThemeMode } from "./ThemeToggle";
import { Kbd } from "./ui";

const NAV = [
  { href: "/", label: "Today" },
  { href: "/test", label: "Test" },
  { href: "/approve", label: "Approve" },
  { href: "/upload", label: "Upload" },
  { href: "/sources", label: "Sources" },
  { href: "/settings", label: "Settings" },
];

/** `g` then a letter. Vim's idiom, and it keeps single letters free for pages. */
const GOTO: Record<string, string> = {
  d: "/",
  r: "/review",
  t: "/test",
  a: "/approve",
  u: "/upload",
  o: "/sources",
  s: "/settings",
};

const FocusContext = createContext<((on: boolean) => void) | null>(null);

/**
 * Claim the whole viewport while the calling component is mounted with
 * `active`: the header hides, exactly as it does on /review.
 *
 * A route cannot decide this on its own because /test/[id] is two screens —
 * the paper, which wants nothing around it, and the result afterwards, which
 * wants the nav back.
 */
export function useFocusMode(active: boolean) {
  const claim = useContext(FocusContext);
  useEffect(() => {
    if (!claim) return;
    claim(active);
    return () => claim(false);
  }, [claim, active]);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      <AppShellInner>{children}</AppShellInner>
    </ToastProvider>
  );
}

/** Everything below the toast layer, so the shell itself can raise toasts. */
function AppShellInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const toast = useToast();
  const [help, setHelp] = useState(false);
  const [claimed, setClaimed] = useState(false);
  const { mode, cycle } = useThemeMode();
  const { skin, toggle: toggleSkin } = useSkin();

  const pendingG = useRef(false);
  const gTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeNav = useRef<HTMLAnchorElement>(null);

  const closeHelp = useCallback(() => setHelp(false), []);

  // The palette names theme states outright; the store only knows how to
  // cycle. Stepping the cycle the right number of times keeps the store —
  // and everything subscribed to it — honest.
  const setTheme = useCallback(
    (target: ThemeMode) => {
      const order: ThemeMode[] = ["system", "light", "dark"];
      let steps = (order.indexOf(target) - order.indexOf(mode) + 3) % 3;
      while (steps-- > 0) cycle();
    },
    [cycle, mode],
  );

  // Phosphor is committed-dark, so the light/dark actions vanish under it —
  // exactly as the header's theme control does. The skin switcher itself is
  // always on offer.
  const paletteActions = useMemo(() => {
    const base = buildDefaultActions({
      push: (href) => router.push(href),
      setTheme,
      toast,
    });
    const actions =
      skin === "phosphor" ? base.filter((a) => a.section !== "Theme") : base;
    const other = skin === "phosphor" ? "ember" : "phosphor";
    return [
      ...actions,
      {
        id: "skin-switch",
        title: `Switch skin — ${other}`,
        section: "Theme",
        keywords: "skin phosphor ember appearance design language look",
        perform: () => toggleSkin(),
      },
    ];
  }, [router, setTheme, toast, skin, toggleSkin]);

  // Six destinations do not fit across a phone, so the strip scrolls — and the
  // page you are on has to be the part of it you can see.
  useEffect(() => {
    activeNav.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [pathname]);

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
        // The binding survives every skin, but Phosphor is committed-dark:
        // under it the theme toggle is inert, so `t` deliberately does
        // nothing rather than silently cycling an invisible setting.
        if (skin === "ember") cycle();
      }
    }

    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [router, cycle, help, skin]);

  // Focus mode: the review screen carries no chrome at all, and a paper in
  // progress claims the same treatment for as long as it is being sat.
  const focus = pathname === "/review" || claimed;

  return (
    <FocusContext.Provider value={setClaimed}>
      <div aria-hidden="true" className="grain" />

      {!focus && (
        <header className="border-b border-line bg-surface sticky top-0 z-30 header-elevated">
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
                    ref={active ? activeNav : undefined}
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
              <button
                onClick={toggleSkin}
                title="Skin: phosphor, ember"
                aria-label={`Skin: ${skin}. Click to switch.`}
                className="h-6 px-1.5 rounded-xs border border-transparent
                  hover:border-line text-[10px] font-medium tracking-[0.12em]
                  text-fg-3 hover:text-fg-2 transition-colors duration-[90ms]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {skin === "phosphor" ? "PHOSPHOR" : "EMBER"}
              </button>
              {skin === "ember" && <ThemeToggle mode={mode} onCycle={cycle} />}
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

      <CommandPalette actions={paletteActions} />
    </FocusContext.Provider>
  );
}
