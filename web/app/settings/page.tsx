"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorState } from "@/components/ui";
import { errorMessage, getSettings, putSettings } from "@/lib/api";
import type { Settings, SettingsPatch } from "@/lib/types";

type Status = "idle" | "saving" | "saved" | "error";

export default function SettingsPage() {
  const [draft, setDraft] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

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
  const change = useCallback((patch: SettingsPatch) => {
    setDraft((d) => (d ? { ...d, ...patch } : d));
    setStatus("saving");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      putSettings(patch)
        .then((next) => {
          setDraft(next);
          setStatus("saved");
          setSaveError(null);
          if (savedTimer.current) clearTimeout(savedTimer.current);
          savedTimer.current = setTimeout(() => setStatus("idle"), 2400);
        })
        .catch((err) => {
          setStatus("error");
          setSaveError(errorMessage(err));
        });
    }, 450);
  }, []);

  const retentionPct = draft ? Math.round(draft.desired_retention * 100) : 90;
  const capMinutes = draft ? Math.round((draft.daily_review_cap * 8) / 60) : 0;

  return (
    <main className="mx-auto max-w-[680px] px-4 py-5">
      <div className="flex items-end justify-between gap-4 mb-4">
        <div>
          <h1 className="text-[18px] font-semibold leading-none">Settings</h1>
          <p className="text-[13px] text-fg-2 mt-1.5">
            Changes save as you make them.
          </p>
        </div>
        <span
          className="label h-5 flex items-center"
          aria-live="polite"
          style={{ color: status === "error" ? "var(--g-again)" : undefined }}
        >
          {status === "saving"
            ? "saving"
            : status === "saved"
              ? "saved"
              : status === "error"
                ? "not saved"
                : ""}
        </span>
      </div>

      {loadError && !draft ? (
        <ErrorState message={loadError} onRetry={reload} />
      ) : null}

      {loading && !draft ? (
        <div className="panel px-3 py-6 text-[13px] text-fg-3">
          Loading settings&hellip;
        </div>
      ) : null}

      {saveError && (
        <div
          className="mb-3 px-3 py-2 border-l-2 bg-surface text-[13px]"
          style={{ borderLeftColor: "var(--g-again)" }}
          role="alert"
        >
          {saveError} The value on screen is not the value on the server.
        </div>
      )}

      {draft && (
        <div className="panel divide-y divide-line">
          <Field
            label="New cards per day"
            help="How many cards you have never seen before get introduced each day."
            cost="Raising this costs you tomorrow, not today: every new card comes back four or five times in its first fortnight before it starts to space out."
            note={`${draft.new_cards_per_day} a day is about ${(
              draft.new_cards_per_day * 7
            ).toLocaleString()} a week.`}
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
              capMinutes > 0
                ? `A full day at this cap is roughly ${capMinutes} ${
                    capMinutes === 1 ? "minute" : "minutes"
                  } at eight seconds a card.`
                : undefined
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
            note={`At ${retentionPct}%, about ${
              100 - retentionPct
            } reviews in every 100 are meant to be lapses.`}
            value={retentionPct}
            min={80}
            max={97}
            step={1}
            suffix="%"
            onChange={(v) => change({ desired_retention: v / 100 })}
          />
        </div>
      )}

      <p className="text-[12px] text-fg-3 mt-4 leading-relaxed">
        Scheduling uses FSRS 4.5. Intervals are derived from these three values
        and the review history of each individual card, so a change here shifts
        every future interval rather than rescheduling what is already due.
      </p>
    </main>
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
  note?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onChange: (value: number) => void;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
  const clamp = (v: number) => Math.min(max, Math.max(min, v));

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

      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-label={`${label} slider`}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full mt-3.5 h-1 cursor-pointer"
      />

      <p className="text-[12.5px] text-fg-2 mt-3 leading-normal">{cost}</p>
      {note && <p className="text-[12px] text-fg-3 mt-1.5 tnum">{note}</p>}
    </section>
  );
}
