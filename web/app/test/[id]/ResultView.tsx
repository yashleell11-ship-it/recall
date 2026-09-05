"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Kbd, KindTag } from "@/components/ui";
import { errorMessage, postExplain } from "@/lib/api";
import { formatDuration, plural } from "@/lib/format";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import { PAPER_LABEL } from "@/lib/marks";
import type { Explanation, TestKind, TestQuestion, TestResult } from "@/lib/types";

interface ExplainState {
  loading: boolean;
  data: Explanation | null;
  error: string | null;
}

/** Marks print as 7 and 7.5, never 7.0 — half marks come from partial credit. */
function marks(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/**
 * The explanation rail opens with the AI's first sentence set apart in the
 * scholar's italic. The split is presentational only: a text with no clean
 * sentence break simply renders whole.
 */
function splitLead(text: string): { lead: string; rest: string } {
  const m = /^[\s\S]*?[.!?]["')\]]*(?=\s|$)/.exec(text);
  if (!m) return { lead: text, rest: "" };
  return { lead: m[0], rest: text.slice(m[0].length).trim() };
}

export function ResultView({
  result,
  kind,
  expired,
}: {
  result: TestResult;
  kind: TestKind;
  expired: boolean;
}) {
  // Wrong before partial: a question you missed entirely is the one to read first.
  const missed = useMemo<{ q: TestQuestion; partial: boolean }[]>(
    () => [
      ...result.wrong.map((q) => ({ q, partial: false })),
      ...result.partial.map((q) => ({ q, partial: true })),
    ],
    [result.wrong, result.partial],
  );

  const [explain, setExplain] = useState<Record<number, ExplainState>>({});
  const [cursor, setCursor] = useState(0);
  const rowRefs = useRef<(HTMLLIElement | null)[]>([]);

  const pct =
    result.total_marks > 0
      ? (result.obtained_marks / result.total_marks) * 100
      : 0;

  // The de-duplication guard has to sit out here rather than inside the state
  // updater: returning `prev` from an updater does not stop the request below,
  // so holding `e` down on a row would have fired a paid call per keypress.
  const asked = useRef<Set<number>>(new Set());

  const ask = useCallback((cardId: number) => {
    if (asked.current.has(cardId)) return;
    asked.current.add(cardId);
    setExplain((prev) => ({
      ...prev,
      [cardId]: { loading: true, data: null, error: null },
    }));
    postExplain(cardId)
      .then((data) =>
        setExplain((prev) => ({
          ...prev,
          [cardId]: { loading: false, data, error: null },
        })),
      )
      .catch((err: unknown) => {
        // Released, so "Try again" can genuinely try again.
        asked.current.delete(cardId);
        setExplain((prev) => ({
          ...prev,
          [cardId]: { loading: false, data: null, error: errorMessage(err) },
        }));
      });
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e) || hasModifier(e) || missed.length === 0) return;
      switch (e.key) {
        case "j":
        case "ArrowDown":
          e.preventDefault();
          setCursor((c) => Math.min(c + 1, missed.length - 1));
          break;
        case "k":
        case "ArrowUp":
          e.preventDefault();
          setCursor((c) => Math.max(c - 1, 0));
          break;
        case "e":
        case "Enter":
          e.preventDefault();
          if (missed[cursor]) ask(missed[cursor].q.card_id);
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ask, cursor, missed]);

  useEffect(() => {
    rowRefs.current[cursor]?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  return (
    <main className="mx-auto max-w-[46rem] px-4 sm:px-6 py-6 pb-16">
      <p className="label">{PAPER_LABEL[kind] ?? kind} · result</p>

      {/* The session score is a display numeral — the one place a number
          gets the scholar's face at full size. */}
      <h1 className="k-display tnum mt-2">
        {marks(result.obtained_marks)}
        <span className="text-fg-3 font-normal"> / {result.total_marks}</span>
        <span className="text-[15px] font-medium text-fg-2 ml-3">
          {pct.toFixed(0)}%
        </span>
      </h1>

      <p className="telemetry text-[12.5px] text-fg-2 mt-2">
        {formatDuration(result.duration_s * 1000)}
        {expired ? " — time expired" : ""}
        <span className="mx-1.5 text-fg-3">·</span>
        {missed.length === 0
          ? "Nothing missed."
          : `${result.wrong.length} wrong, ${result.partial.length} partly right.`}
      </p>

      {/* --- by topic ------------------------------------------------------- */}

      {result.by_topic.length > 0 && (
        <div className="panel mt-5 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-line bg-sunken">
                <th className="label text-left font-semibold px-3 py-1.5">
                  Topic
                </th>
                <th className="label text-right font-semibold px-3 py-1.5 w-24">
                  Marks
                </th>
                <th className="label text-right font-semibold px-3 py-1.5 w-16">
                  Held
                </th>
                <th className="w-[38%] px-3" />
              </tr>
            </thead>
            <tbody>
              {[...result.by_topic]
                .sort(
                  (a, b) =>
                    a.obtained / Math.max(1, a.total) -
                    b.obtained / Math.max(1, b.total),
                )
                .map((t) => {
                  const share = t.total > 0 ? t.obtained / t.total : 0;
                  return (
                    <tr
                      key={t.topic_code}
                      className="border-b border-line last:border-b-0"
                    >
                      <td className="px-3 py-[7px]">
                        <span className="text-[11px] font-semibold tracking-[0.06em]">
                          {t.topic_code}
                        </span>
                      </td>
                      <td className="telemetry px-3 py-[7px] text-right text-fg-2">
                        {marks(t.obtained)}/{t.total}
                      </td>
                      <td className="telemetry px-3 py-[7px] text-right font-medium">
                        {Math.round(share * 100)}%
                      </td>
                      <td className="px-3 py-[7px]">
                        {/* A bar, because a column of percentages does not show
                            which topic is the outlier. */}
                        <span className="block h-1.5 bg-line rounded-xs overflow-hidden">
                          <span
                            className="block h-full bg-fg-2"
                            style={{ width: `${Math.round(share * 100)}%` }}
                          />
                        </span>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      )}

      {/* --- the teaching loop ---------------------------------------------- */}

      {missed.length === 0 ? (
        <div className="panel mt-6 px-3.5 py-5 max-w-prose">
          <p className="text-[14px]">
            Nothing to fix. Every question you attempted was right.
          </p>
          <p className="text-[13px] text-fg-2 mt-1.5">
            Those answers are recorded as reviews, so the scheduler has already
            pushed them further out.
          </p>
        </div>
      ) : (
        <section className="mt-7">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pl-3 border-l-2 border-l-accent">
            <h2 className="text-[16px] font-semibold">What to fix</h2>
            <p className="text-[12px] text-fg-3 flex items-center gap-1.5">
              <Kbd>j</Kbd>
              <Kbd>k</Kbd> move
              <Kbd>e</Kbd> explain
            </p>
          </div>
          <p className="text-[13px] text-fg-2 mt-2 pl-3 max-w-prose">
            Each explanation is written from the same page the card came from,
            and has to quote it. Read{" "}
            {missed.length === 1 ? "it" : `all ${missed.length}`} before the next
            session — {plural(missed.length, "this is", "these are")} already
            scheduled to come back soon.
          </p>

          <ul className="panel mt-3.5 overflow-hidden">
            {missed.map((m, i) => {
              const state = explain[m.q.card_id];
              const focused = i === cursor;
              return (
                <li
                  key={`${m.q.ordinal}-${m.q.card_id}`}
                  ref={(el) => {
                    rowRefs.current[i] = el;
                  }}
                  onClick={() => setCursor(i)}
                  className={`px-3.5 py-3 border-b border-line last:border-b-0 border-l-2
                    transition-colors duration-[90ms] ${
                      focused ? "bg-surface-hover" : ""
                    }`}
                  style={{
                    borderLeftColor: m.partial
                      ? "var(--g-hard)"
                      : "var(--g-again)",
                  }}
                >
                  <div className="telemetry flex items-center gap-2 text-[11px] text-fg-3 mb-1.5">
                    <span className="tnum text-fg-2 font-medium">
                      Q{m.q.ordinal}
                    </span>
                    <span className="font-semibold tracking-[0.05em] text-fg-2">
                      {m.q.topic_code}
                    </span>
                    <span>{m.q.page_ref}</span>
                    <KindTag kind={m.q.kind} />
                    <span className="tnum ml-auto shrink-0">
                      {m.partial
                        ? `${marks(m.q.marks / 2)} of ${m.q.marks}`
                        : `0 of ${m.q.marks}`}
                    </span>
                  </div>

                  {/* Question and answer are knowledge — they wear --k-face. */}
                  <p className="k-text text-[15px] font-medium leading-snug">
                    {m.q.question}
                  </p>
                  <p className="k-text text-[14px] text-fg-2 leading-normal mt-1.5">
                    {m.q.answer}
                  </p>

                  {/* --- explanation ------------------------------------- */}

                  {!state && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setCursor(i);
                        ask(m.q.card_id);
                      }}
                      className={`mt-2.5 inline-flex items-center gap-2 h-8 px-3 rounded-sm
                        text-[13px] font-semibold border transition-colors duration-[90ms]
                        ${
                          focused
                            ? "bg-accent text-accent-fg border-accent hover:bg-accent-hover hover:border-accent-hover"
                            : "bg-surface text-fg border-line hover:border-line-strong hover:bg-surface-hover"
                        }`}
                    >
                      Explain this
                      {focused && <Kbd>e</Kbd>}
                    </button>
                  )}

                  {state?.loading && (
                    <p className="k-ai mt-2.5 text-[13px] text-fg-3">
                      Reading {m.q.page_ref} of {m.q.topic_code}&hellip;
                    </p>
                  )}

                  {state?.error && (
                    <div
                      className="mt-2.5 pl-2.5 border-l-2 text-[12.5px]"
                      style={{ borderColor: "var(--g-again)" }}
                      role="alert"
                    >
                      <p className="text-fg-2">{state.error}</p>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setExplain((prev) => {
                            const next = { ...prev };
                            delete next[m.q.card_id];
                            return next;
                          });
                        }}
                        className="link text-fg-2 mt-1"
                      >
                        Try again
                      </button>
                    </div>
                  )}

                  {state?.data && <SynapseRail data={state.data} />}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-4 mt-7 text-[13px]">
        <Link
          href="/"
          className="inline-flex items-center h-9 px-4 rounded-sm font-medium
            border border-line bg-surface hover:border-line-strong hover:bg-surface-hover
            transition-colors duration-[90ms]"
        >
          Back to today
        </Link>
        <Link href="/review" className="link text-fg-2">
          Review now
        </Link>
        <Link href="/test" className="link text-fg-2">
          Sit another paper
        </Link>
      </div>
    </main>
  );
}

/**
 * The synapse rail (Phosphor §6.4): a 2px violet edge and quiet violet fill
 * mark the explanation as the AI's — the marker is coloured, the words stay
 * ink. It opens with the AI's first sentence in the scholar's italic, and
 * closes with the source quote inset, its page reference in mono.
 */
function SynapseRail({ data }: { data: Explanation }) {
  const paras = data.explanation.split(/\n{2,}/);
  const { lead, rest } = splitLead(paras[0] ?? "");
  return (
    <div
      className="mt-3 anim-reveal rounded-r-sm border-l-2 border-l-ai px-3.5 py-3"
      style={{ background: "var(--ai-quiet)" }}
    >
      <p className="text-[13.5px] leading-[1.6] text-fg">
        <span className="k-ai text-[1.1em]">{lead}</span>
        {rest ? <> {rest}</> : null}
      </p>
      {paras.slice(1).map((para, k) => (
        <p key={k} className="text-[13.5px] leading-[1.6] text-fg mt-2.5">
          {para}
        </p>
      ))}

      <figure className="mt-3 pl-3 border-l-2 border-l-line-strong">
        <blockquote className="k-text text-[13.5px] text-fg-2 leading-relaxed">
          &ldquo;{data.source_quote}&rdquo;
        </blockquote>
        <figcaption className="telemetry text-[11px] text-fg-3 mt-1.5">
          <span className="font-semibold tracking-[0.05em]">
            {data.topic_code}
          </span>
          <span className="mx-1.5">·</span>
          {data.page_ref}
          {data.cached && (
            <>
              <span className="mx-1.5">·</span>
              cached, no new cost
            </>
          )}
        </figcaption>
      </figure>
    </div>
  );
}
