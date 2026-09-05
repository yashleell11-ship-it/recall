"use client";

import { motion, useReducedMotion } from "motion/react";
import type { CSSProperties, ReactNode } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatedNumber, Reveal, Skeleton, useToast } from "@/components/rich";
import { ErrorState } from "@/components/ui";
import { errorMessage, getSettings, putSettings } from "@/lib/api";
import type { Settings, SettingsPatch } from "@/lib/types";

type Status = "idle" | "saving" | "saved" | "error";

/** The value chip trails the thumb on a tight spring — a nudge, not a chase. */
const CHIP_SPRING = {
  type: "spring",
  stiffness: 520,
  damping: 36,
  mass: 0.7,
} as const;

const THUMB_PX = 14;

/**
 * The slider is still a native input — keyboard, screen reader, and focus
 * behaviour all come for free — with the track painted by the palette: the
 * ember on the travelled side, a hairline on the rest.
 */
const SLIDER_CSS = `
.range-slider {
  -webkit-appearance: none;
  appearance: none;
  display: block;
  width: 100%;
  height: 16px;
  margin: 0;
  padding: 0;
  background: transparent;
  cursor: pointer;
}
.range-slider::-webkit-slider-runnable-track {
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(
    to right,
    var(--accent) var(--fill, 0%),
    var(--line) var(--fill, 0%)
  );
}
.range-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: ${THUMB_PX}px;
  height: ${THUMB_PX}px;
  margin-top: -5.5px;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--line-strong);
  box-shadow: var(--shadow-1);
  transition: border-color 120ms ease-out, transform 120ms ease-out;
}
.range-slider:hover::-webkit-slider-thumb,
.range-slider:focus-visible::-webkit-slider-thumb {
  border-color: var(--accent);
}
.range-slider:active::-webkit-slider-thumb {
  transform: scale(1.15);
  border-color: var(--accent);
}
.range-slider::-moz-range-track {
  height: 3px;
  border-radius: 999px;
  background: var(--line);
}
.range-slider::-moz-range-progress {
  height: 3px;
  border-radius: 999px;
  background: var(--accent);
}
.range-slider::-moz-range-thumb {
  width: ${THUMB_PX}px;
  height: ${THUMB_PX}px;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--line-strong);
  box-shadow: var(--shadow-1);
  transition: border-color 120ms ease-out, transform 120ms ease-out;
}
.range-slider:hover::-moz-range-thumb,
.range-slider:focus-visible::-moz-range-thumb {
  border-color: var(--accent);
}
.range-slider:active::-moz-range-thumb {
  transform: scale(1.15);
  border-color: var(--accent);
}
`;

export default function SettingsPage() {
  const toast = useToast();
  const [draft, setDraft] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let live = true;
    getSettings()
      .then((s) => {
        if (!live) return;
        setDraft(s);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if (live) setLoadError(errorMessage(err));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [reloadNonce]);

  const reload = useCallback(() => {
    setLoading(true);
    setReloadNonce((n) => n + 1);
  }, []);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      if (savedTimer.current) clearTimeout(savedTimer.current);
    },
    [],
  );

  /** Save on change, debounced. No form, no Save button, no modal. */
  const change = useCallback(
    (patch: SettingsPatch) => {
      setDraft((d) => (d ? { ...d, ...patch } : d));
      setStatus("saving");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        putSettings(patch)
          .then((next) => {
            setDraft(next);
            setStatus("saved");
            if (savedTimer.current) clearTimeout(savedTimer.current);
            savedTimer.current = setTimeout(() => setStatus("idle"), 2400);
          })
          .catch((err: unknown) => {
            setStatus("error");
            toast(
              `${errorMessage(err)} The value on screen is not the value on the server.`,
              { variant: "error" },
            );
          });
      }, 450);
    },
    [toast],
  );

  const retentionPct = draft ? Math.round(draft.desired_retention * 100) : 90;
  const capMinutes = draft ? Math.round((draft.daily_review_cap * 8) / 60) : 0;

  return (
    <main className="mx-auto max-w-[680px] px-4 py-5">
      <style>{SLIDER_CSS}</style>

      <div className="flex items-end justify-between gap-4 mb-4">
        <div>
          <h1 className="text-[18px] font-semibold leading-none">Settings</h1>
          <p className="text-[13px] text-fg-2 mt-1.5">
            Changes save as you make them.
          </p>
        </div>
        <span className="h-5 flex items-center gap-1.5" aria-live="polite">
          {status === "saving" && <span className="label">Saving</span>}
          {status === "saved" && (
            <>
              <SavedTick />
              <span className="label" style={{ color: "var(--g-good)" }}>
                Saved
              </span>
            </>
          )}
          {status === "error" && (
            <span className="label" style={{ color: "var(--g-again)" }}>
              Not saved
            </span>
          )}
        </span>
      </div>

      {loadError && !draft ? (
        <ErrorState message={loadError} onRetry={reload} />
      ) : null}

      {loading && !draft ? (
        /* Three field-shaped placeholders, so the panel arrives in place. */
        <div
          className="panel divide-y divide-line"
          aria-busy="true"
          aria-label="Loading settings"
        >
          {[0, 1, 2].map((i) => (
            <div key={i} className="px-3.5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <Skeleton className="h-[15px] w-40" />
                  <Skeleton className="h-[13px] w-[85%] mt-2" />
                </div>
                <Skeleton className="h-8 w-[72px] shrink-0" />
              </div>
              <Skeleton className="h-[3px] w-full mt-[27px] rounded-full" />
              <Skeleton className="h-[13px] w-full mt-[25px]" />
              <Skeleton className="h-[13px] w-3/4 mt-2" />
              <Skeleton className="h-3 w-56 mt-2.5" />
            </div>
          ))}
        </div>
      ) : null}

      {draft && (
        <Reveal>
          <div className="panel divide-y divide-line">
            <Field
              label="New cards per day"
              help="How many cards you have never seen before get introduced each day."
              cost="Raising this costs you tomorrow, not today: every new card comes back four or five times in its first fortnight before it starts to space out."
              note={
                <>
                  <AnimatedNumber value={draft.new_cards_per_day} /> a day is
                  about <AnimatedNumber value={draft.new_cards_per_day * 7} /> a
                  week.
                </>
              }
              value={draft.new_cards_per_day}
              min={0}
              max={60}
              step={1}
              onChange={(v) => change({ new_cards_per_day: v })}
            />

            <Field
              label="Daily review cap"
              help="The most cards Recall will put in front of you in one day, new and due together."
              cost="Setting it low does not remove work, it defers it. Anything over the cap waits for tomorrow and arrives on top of tomorrow's own load."
              note={
                capMinutes > 0 ? (
                  <>
                    A full day at this cap is roughly{" "}
                    <AnimatedNumber value={capMinutes} />{" "}
                    {capMinutes === 1 ? "minute" : "minutes"} at eight seconds a
                    card.
                  </>
                ) : undefined
              }
              value={draft.daily_review_cap}
              min={10}
              max={500}
              step={10}
              onChange={(v) => change({ daily_review_cap: v })}
            />

            <Field
              label="Desired retention"
              help="The share of cards you want to still remember at the moment they come back."
              cost="Going from 90% to 95% roughly doubles how often each card is reviewed, for five more cards remembered in every hundred. Below 85% the deck gets cheap but leaky."
              note={
                <>
                  At <AnimatedNumber value={retentionPct} />
                  %, about <AnimatedNumber value={100 - retentionPct} /> reviews
                  in every 100 are meant to be lapses.
                </>
              }
              value={retentionPct}
              min={80}
              max={97}
              step={1}
              suffix="%"
              onChange={(v) => change({ desired_retention: v / 100 })}
            />
          </div>
        </Reveal>
      )}

      <p className="text-[12px] text-fg-3 mt-4 leading-relaxed">
        Scheduling uses FSRS 4.5. Intervals are derived from these three values
        and the review history of each individual card, so a change here shifts
        every future interval rather than rescheduling what is already due.
      </p>
    </main>
  );
}

/** A 200ms path-draw, then it holds. Quiet on purpose. */
function SavedTick() {
  const reduced = useReducedMotion();
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
    >
      <motion.path
        d="M2.5 6.5 5 9l4.5-5.5"
        stroke="var(--g-good)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={reduced ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={reduced ? { duration: 0 } : { duration: 0.2, ease: "easeOut" }}
      />
    </svg>
  );
}

function Field({
  label,
  help,
  cost,
  note,
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  label: string;
  help: string;
  cost: string;
  note?: ReactNode;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onChange: (value: number) => void;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  const reduced = useReducedMotion();

  const wrapRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const [chipX, setChipX] = useState(0);

  const fraction = max > min ? (value - min) / (max - min) : 0;

  // The chip sits over the thumb's centre: fraction of the travel range plus
  // half a thumb, measured against the input's real width.
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    setChipX(fraction * (el.offsetWidth - THUMB_PX) + THUMB_PX / 2);
  }, [fraction, dragging]);

  return (
    <section className="px-3.5 py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <label htmlFor={id} className="text-[14px] font-semibold block">
            {label}
          </label>
          <p className="text-[13px] text-fg-2 mt-1 leading-normal">{help}</p>
        </div>

        <div className="shrink-0 flex items-baseline gap-1">
          <input
            id={id}
            type="number"
            inputMode="numeric"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (Number.isFinite(v)) onChange(clamp(v));
            }}
            className="w-[72px] h-8 px-2 rounded-sm border border-line bg-surface text-right
              text-[14px] font-medium tnum hover:border-line-strong focus:border-line-strong
              transition-colors duration-[90ms]"
          />
          {suffix && (
            <span className="text-[13px] text-fg-3 w-2">{suffix}</span>
          )}
        </div>
      </div>

      <div ref={wrapRef} className="relative mt-3.5">
        <motion.div
          className="absolute -top-[26px] left-0 z-10 pointer-events-none"
          aria-hidden="true"
          initial={false}
          animate={{
            x: chipX,
            opacity: dragging ? 1 : 0,
            scale: dragging ? 1 : 0.92,
          }}
          transition={reduced ? { duration: 0 } : CHIP_SPRING}
        >
          <span
            className="block -translate-x-1/2 elev-3 rounded-sm px-1.5 py-[3px]
              text-[11px] font-medium leading-none tnum whitespace-nowrap"
          >
            {value}
            {suffix ?? ""}
          </span>
        </motion.div>

        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          aria-label={`${label} slider`}
          onChange={(e) => onChange(Number(e.target.value))}
          onPointerDown={() => setDragging(true)}
          onPointerUp={() => setDragging(false)}
          onPointerCancel={() => setDragging(false)}
          onBlur={() => setDragging(false)}
          className="range-slider"
          style={{ "--fill": `${fraction * 100}%` } as CSSProperties}
        />
      </div>

      <p className="text-[12.5px] text-fg-2 mt-3 leading-normal">{cost}</p>
      {note && <p className="text-[12px] text-fg-3 mt-1.5 tnum">{note}</p>}
    </section>
  );
}
