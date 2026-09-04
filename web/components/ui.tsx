"use client";

import type { ReactNode } from "react";

/* --- keycap -------------------------------------------------------------- */

export function Kbd({
  children,
  tone,
}: {
  children: ReactNode;
  /** Grade keys borrow the grade's hue; everything else stays monochrome. */
  tone?: "again" | "hard" | "good" | "easy";
}) {
  const toneStyle = tone
    ? {
        color: `var(--g-${tone})`,
        background: `var(--g-${tone}-bg)`,
        borderColor: "currentColor",
      }
    : undefined;
  return (
    <kbd className="kbd" style={toneStyle}>
      {children}
    </kbd>
  );
}

/* --- surfaces ------------------------------------------------------------ */

export function Panel({
  title,
  aside,
  children,
  className = "",
  bodyClassName = "",
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`panel overflow-hidden ${className}`}>
      {(title || aside) && (
        <header className="flex items-baseline justify-between gap-3 px-3 h-9 border-b border-line bg-sunken">
          <h2 className="label">{title}</h2>
          {aside ? <div className="text-[11px] text-fg-3 tnum">{aside}</div> : null}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/* --- async states -------------------------------------------------------- */

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="px-3 py-6 text-[13px] text-fg-3">{label}&hellip;</div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="px-3 py-4 border-l-2 bg-surface"
      style={{ borderLeftColor: "var(--g-again)" }}
      role="alert"
    >
      <p className="text-[13px] text-fg">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 text-[12px] text-fg-2 underline underline-offset-2 hover:text-fg"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="px-3 py-8 max-w-prose">
      <p className="text-[13px] text-fg-2">{children}</p>
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

/* --- data display -------------------------------------------------------- */

/** A number and its label. Deliberately not a card: no box, no icon. */
export function Metric({
  value,
  label,
  emphasis = false,
  note,
}: {
  value: ReactNode;
  label: string;
  emphasis?: boolean;
  note?: string;
}) {
  return (
    <div className="px-3.5 py-2.5 min-w-0">
      <div
        className={`tnum leading-none ${
          emphasis
            ? "text-[26px] font-semibold text-fg"
            : "text-[22px] font-medium text-fg"
        }`}
      >
        {value}
      </div>
      <div className="label mt-1.5 truncate">{label}</div>
      {note ? (
        <div className="text-[11px] text-fg-3 mt-0.5 truncate">{note}</div>
      ) : null}
    </div>
  );
}

/** Topic code — small, tracked, never coloured. */
export function TopicCode({ code }: { code: string }) {
  return (
    <span className="text-[11px] font-semibold tracking-[0.06em] text-fg">
      {code}
    </span>
  );
}

export function KindTag({ kind }: { kind: string }) {
  return (
    <span className="inline-block px-1 py-px rounded-xs border border-line text-[9px] font-semibold tracking-[0.08em] uppercase text-fg-3 leading-[1.3]">
      {kind}
    </span>
  );
}
