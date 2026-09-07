"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { errorMessage, generateFromKnowledge } from "@/lib/api";
import { Reveal } from "@/components/rich";
import type { SubjectScheme, TestKind, Topic, TopicMeta } from "@/lib/types";

/** A topic the server sent LPU facts for. The rail renders nothing else. */
export interface SubjectTopic extends Topic {
  meta: TopicMeta;
}

/* --- the weight split ------------------------------------------------------
   A slim segmented bar. Monochrome on purpose: in this product colour is
   reserved for grades and the one primary action, so the split reads through
   an ink ramp — attendance faintest, ETE full ink — with a mono legend
   underneath doing the exact numbers. Weights sum to 100, so each weight is
   its own percentage width. */

const SEGMENTS: { key: keyof SubjectScheme; label: string; tone: string }[] = [
  { key: "attendance", label: "ATT", tone: "var(--line-strong)" },
  { key: "ca", label: "CA", tone: "var(--fg-3)" },
  { key: "mte", label: "MTE", tone: "var(--fg-2)" },
  { key: "ete", label: "ETE", tone: "var(--fg)" },
];

function SchemeBar({ scheme }: { scheme: SubjectScheme }) {
  const parts = SEGMENTS.map((s) => ({ ...s, value: scheme[s.key] })).filter(
    (p) => p.value > 0,
  );
  const legend = parts.map((p) => `${p.label} ${p.value}`).join(" · ");
  return (
    <div>
      <div
        className="flex h-[5px] gap-px rounded-[2px] overflow-hidden"
        role="img"
        aria-label={`Weight split: ${legend}`}
      >
        {parts.map((p) => (
          <div
            key={p.key}
            style={{ width: `${p.value}%`, background: p.tone }}
            title={`${p.label} ${p.value}`}
          />
        ))}
      </div>
      <p className="telemetry text-[10.5px] text-fg-3 mt-1" aria-hidden="true">
        {legend}
      </p>
    </div>
  );
}

/* --- the paper chips ------------------------------------------------------- */

interface Chip {
  kind: TestKind;
  label: string;
  detail: string;
}

function chipsFor(meta: TopicMeta): Chip[] {
  const chips: Chip[] = [
    { kind: "class30", label: "CA", detail: "30 marks · 45 min" },
  ];
  if (meta.mte_exists) {
    chips.push({
      kind: "mte40",
      label: "MTE",
      detail: "40 marks · 90 min · units 1–3",
    });
  }
  // A course whose scheme carries no ETE weight (CSE111 is fully CA-driven)
  // must not offer an ETE paper — the university will never set one.
  if ((meta.scheme?.ete ?? 0) > 0) {
    chips.push({
      kind: "endterm100",
      label: "ETE",
      detail: "100 marks · 3 h · all units",
    });
  }
  return chips;
}

/* --- generating a unit with nothing uploaded --------------------------------

   The other way into a deck. Upload is better — those cards are checked
   against your own notes — so this is deliberately the quieter control: a
   text button at the end of a unit row, not a call to action competing with
   the paper chips. It spends money on a press, exactly like Generate on the
   upload screen, so it says what it did and what it cost. */

type GenState =
  | { stage: "idle" }
  | { stage: "busy" }
  | { stage: "done"; accepted: number }
  | { stage: "error"; message: string };

function UnitGenerate({ topicCode, unit }: { topicCode: string; unit: number }) {
  const [state, setState] = useState<GenState>({ stage: "idle" });

  async function run() {
    setState({ stage: "busy" });
    try {
      const res = await generateFromKnowledge(topicCode, unit);
      setState({ stage: "done", accepted: res.accepted });
    } catch (err) {
      setState({ stage: "error", message: errorMessage(err) });
    }
  }

  if (state.stage === "busy") {
    return (
      <span className="telemetry text-[10px] text-fg-3 shrink-0 pt-px">
        writing…
      </span>
    );
  }
  if (state.stage === "done") {
    return (
      <Link
        href={`/review?topic=${encodeURIComponent(topicCode)}`}
        className="telemetry text-[10px] text-fg-2 shrink-0 pt-px underline
          underline-offset-2 hover:text-fg"
      >
        +{state.accepted} to study
      </Link>
    );
  }
  if (state.stage === "error") {
    return (
      <span
        className="telemetry text-[10px] shrink-0 pt-px"
        style={{ color: "var(--g-again)" }}
        title={state.message}
      >
        failed
      </span>
    );
  }
  return (
    <button
      onClick={run}
      title={`Write practice cards for unit ${unit} from the model's own knowledge. Spends a little of your daily budget. What survives the checks goes straight into your rotation, marked "no source".`}
      className="telemetry text-[10px] text-fg-3 shrink-0 pt-px
        hover:text-fg-2 underline underline-offset-2
        transition-colors duration-[120ms]"
    >
      generate
    </button>
  );
}

/* --- one subject ------------------------------------------------------------ */

function SubjectCard({
  topic,
  index,
  startingKey,
  anyStarting,
  errorMessage,
  onStart,
}: {
  topic: SubjectTopic;
  index: number;
  /** `${code}:${kind}` of the chip currently assembling, or null. */
  startingKey: string | null;
  anyStarting: boolean;
  errorMessage: string | null;
  onStart: (kind: TestKind, code: string) => void;
}) {
  const reduced = useReducedMotion();
  const meta = topic.meta;

  return (
    <Reveal index={index} className="h-full">
      <article className="panel h-full flex flex-col px-3.5 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <span className="telemetry text-[11px] font-semibold tracking-[0.06em] text-fg">
            {topic.code}
          </span>
          <span className="telemetry text-[10.5px] text-fg-3 shrink-0">
            {meta.credits} cr · {meta.exam_format}
          </span>
        </div>

        <h3 className="k-text text-[17px] font-medium leading-snug mt-1">
          {meta.full_name}
        </h3>

        <div className="mt-2.5">
          <SchemeBar scheme={meta.scheme} />
          {meta.scheme_confirmed === false && (
            <p
              className="telemetry text-[10px] mt-1 leading-relaxed"
              style={{ color: "var(--g-hard)" }}
            >
              weights not confirmed for this course — check UMS before trusting
              them
            </p>
          )}
        </div>

        <p className="telemetry text-[10.5px] text-fg-3 mt-2 leading-relaxed">
          {meta.ca_policy}
        </p>

        <details className="group mt-2">
          <summary
            className="label cursor-pointer select-none list-none inline-flex items-center gap-1
              [&::-webkit-details-marker]:hidden hover:text-fg-2 transition-colors duration-[90ms]"
          >
            <span
              aria-hidden="true"
              className="inline-block transition-transform duration-[90ms] group-open:rotate-90"
            >
              ›
            </span>
            units
          </summary>
          <ol className="mt-1.5 border-t border-line">
            {meta.units.map((u, i) => (
              <li
                key={u}
                className="flex gap-2 py-[4px] border-b border-line last:border-b-0"
              >
                <span className="telemetry text-[10px] text-fg-3 w-4 shrink-0 pt-px">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-[12px] text-fg-2 leading-snug flex-1">{u}</span>
                <UnitGenerate topicCode={topic.code} unit={i + 1} />
              </li>
            ))}
          </ol>
        </details>

        <div className="mt-auto pt-3 flex flex-wrap items-center gap-1.5">
          {chipsFor(meta).map((chip) => {
            const key = `${topic.code}:${chip.kind}`;
            const busy = startingKey === key;
            return (
              <motion.button
                key={chip.kind}
                onClick={() => onStart(chip.kind, topic.code)}
                disabled={anyStarting}
                whileTap={reduced ? undefined : { scale: 0.97 }}
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
                aria-label={`Start ${chip.label} paper for ${topic.code} — ${chip.detail}`}
                className="telemetry text-[11px] leading-none px-2 py-[7px] rounded-sm border border-line
                  bg-surface hover:border-line-strong hover:bg-surface-hover
                  transition-colors duration-[90ms]
                  disabled:opacity-40 disabled:pointer-events-none"
              >
                {busy ? (
                  <span className="text-fg-2">assembling…</span>
                ) : (
                  <>
                    <span className="font-semibold text-fg">{chip.label}</span>
                    <span className="text-fg-3"> · {chip.detail}</span>
                  </>
                )}
              </motion.button>
            );
          })}
        </div>

        {!meta.mte_exists && (
          <p className="telemetry text-[10.5px] text-fg-3 mt-1.5">
            {meta.scheme.ete > 0
              ? "no MTE at LPU — CA + ETE only"
              : "no MTE or ETE at LPU — fully CA-driven"}
          </p>
        )}

        {errorMessage && (
          <p
            role="alert"
            className="mt-2 px-2 py-1.5 border-l-2 bg-surface text-[12px] text-fg"
            style={{ borderLeftColor: "var(--g-again)" }}
          >
            {errorMessage}
          </p>
        )}
      </article>
    </Reveal>
  );
}

/* --- the rail ---------------------------------------------------------------- */

export function SubjectRail({
  topics,
  startingKey,
  error,
  onStart,
}: {
  topics: SubjectTopic[];
  startingKey: string | null;
  error: { code: string; message: string } | null;
  onStart: (kind: TestKind, code: string) => void;
}) {
  return (
    <section aria-label="Subjects">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {topics.map((t, i) => (
          <SubjectCard
            key={t.id}
            topic={t}
            index={i}
            startingKey={startingKey}
            anyStarting={startingKey !== null}
            errorMessage={error && error.code === t.code ? error.message : null}
            onStart={onStart}
          />
        ))}
      </div>
      <p className="telemetry text-[10.5px] text-fg-3 mt-3 leading-relaxed max-w-[78ch]">
        CA = best 2 of 3, 30-mark tests · MTE covers units 1–3, marked out of
        40 then scaled to the course&rsquo;s MTE weight · ETE covers all six
        units — on MCQ courses roughly two thirds of the paper is units 4–6
      </p>
    </section>
  );
}
