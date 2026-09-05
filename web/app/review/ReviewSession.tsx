"use client";

import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ClozePrompt, clozeShowsAnswer } from "@/components/CardText";
import {
  AnimatedNumber,
  ProgressRing,
  Reveal,
  Skeleton,
  useToast,
} from "@/components/rich";
import { Kbd } from "@/components/ui";
import { errorMessage, getQueue, getSettings, postReview } from "@/lib/api";
import { parseCloze } from "@/lib/cloze";
import { formatDuration, plural } from "@/lib/format";
import { formatInterval, previewIntervals, type MemoryState } from "@/lib/fsrs";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import type { Grade, QueueCard } from "@/lib/types";
import styles from "./review.module.css";

const GRADES: {
  grade: Grade;
  label: string;
  tone: "again" | "hard" | "good" | "easy";
}[] = [
  { grade: 1, label: "Again", tone: "again" },
  { grade: 2, label: "Hard", tone: "hard" },
  { grade: 3, label: "Good", tone: "good" },
  { grade: 4, label: "Easy", tone: "easy" },
];

/** How long the graded card takes to fade and lift out before the next enters. */
const ADVANCE_MS = 240;

/**
 * The Flow Stack (Phosphor spec §6.1): №2 starts promoting this long before
 * the graded card finishes leaving, so the two motions overlap and the flow
 * never breaks.
 */
const PROMOTE_OVERLAP_MS = 40;

/**
 * Stack geometry: the current card at full presence, the next two physically
 * beneath it — present, never demanding attention.
 */
const STACK_POS = [
  { y: 0, scale: 1, opacity: 1 },
  { y: 16, scale: 0.955, opacity: 0.55 },
  { y: 30, scale: 0.915, opacity: 0.28 },
] as const;

/** Where a graded card goes: out the top, fading, over ADVANCE_MS. */
const STACK_LEAVE = { y: -26, scale: 1, opacity: 0 } as const;

/** The card's entrance: fade + 12px lift on a quick spring. */
const ENTER_SPRING = {
  type: "spring",
  stiffness: 380,
  damping: 32,
  mass: 0.9,
} as const;

/** The answer region's unmask: snappier, settles in about 200ms. */
const REVEAL_SPRING = {
  type: "spring",
  stiffness: 560,
  damping: 38,
  mass: 0.8,
} as const;

const TAP = { scale: 0.98 };

interface LogEntry {
  card: QueueCard;
  grade: Grade;
}

/**
 * OPTIONAL / ADDITIVE, matching the convention in lib/types.ts: the contract
 * does not promise leech fields, but when the server sends them the card wears
 * a quiet amber tag. Absent fields simply mean no tag.
 */
interface LeechSignals {
  is_leech?: boolean | null;
  lapses?: number | null;
}

function formatPct(n: number): string {
  return `${Math.round(n)}%`;
}

export function ReviewSession() {
  const router = useRouter();
  const params = useSearchParams();
  const topic = params.get("topic") ?? undefined;
  const toast = useToast();
  const reduced = useReducedMotion();

  const [queue, setQueue] = useState<QueueCard[]>([]);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [retention, setRetention] = useState(0.9);
  const [remaining, setRemaining] = useState(0);
  const [capReached, setCapReached] = useState(false);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [endedAt, setEndedAt] = useState(0);
  const [reloadNonce, setReloadNonce] = useState(0);

  // The graded card is fading out; inputs wait for the next one to arrive.
  const [leaving, setLeaving] = useState(false);
  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Verdict feedback: one bio pulse-ring for a held card, a headshake for
  // "Again". The nonce lets an immediate repeat replay the animation.
  const [fx, setFx] = useState<{ kind: "pulse" | "shake"; n: number } | null>(
    null,
  );

  // Memory state learned from the server as the session goes, so a card that
  // comes back after "Again" is priced exactly rather than estimated.
  const [learned, setLearned] = useState<Record<number, MemoryState>>({});
  const [unsaved, setUnsaved] = useState<LogEntry[]>([]);

  useEffect(() => {
    let live = true;
    Promise.all([getQueue(topic, 50), getSettings()])
      .then(([q, settings]) => {
        if (!live) return;
        setRetention(settings.desired_retention);
        setStartedAt(Date.now());
        setEndedAt(Date.now());
        setRemaining(q.due_remaining + q.new_remaining);
        setCapReached(q.cap_reached);
        setQueue(q.cards);
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
  }, [topic, reloadNonce]);

  // The advance timer only choreographs the visual hand-off; the review
  // itself is recorded at press time, so an unmount mid-flight loses nothing.
  useEffect(() => {
    return () => {
      if (advanceTimer.current) clearTimeout(advanceTimer.current);
    };
  }, []);

  const retryLoad = useCallback(() => {
    setLoading(true);
    setReloadNonce((n) => n + 1);
  }, []);

  /** Pull the next batch without ending the session. */
  const loadMore = useCallback(() => {
    setLoadingMore(true);
    getQueue(topic, 50)
      .then((q) => {
        setRemaining(q.due_remaining + q.new_remaining);
        setCapReached(q.cap_reached);
        setQueue((prev) => [...prev, ...q.cards]);
        setLoadError(null);
      })
      .catch((err: unknown) => setLoadError(errorMessage(err)))
      .finally(() => setLoadingMore(false));
  }, [topic]);

  const card = queue[index] ?? null;
  const done = !loading && !loadError && index >= queue.length;

  const memory = useMemo<MemoryState | null>(() => {
    if (!card) return null;
    const cached = learned[card.id];
    if (cached) return cached;
    if (card.stability != null && card.difficulty != null) {
      return { stability: card.stability, difficulty: card.difficulty };
    }
    return null;
  }, [card, learned]);

  const previews = useMemo(() => {
    if (!card) return [];
    return previewIntervals(
      memory,
      card.is_new,
      card.elapsed_days ?? 0,
      retention,
    );
  }, [card, memory, retention]);

  const grade = useCallback(
    (g: Grade) => {
      if (leaving) return;
      const current = queue[index];
      if (!current) return;

      // Record and save immediately — the exit animation is presentation,
      // never a window in which a grade can be lost.
      setLog((l) => [...l, { card: current, grade: g }]);
      // "Again" puts the card back at the end of this session, the way a
      // relearning step does.
      if (g === 1) setQueue((q) => [...q, current]);
      setEndedAt(Date.now());

      void postReview(current.id, g)
        .then((r) => {
          setLearned((prev) => ({
            ...prev,
            [current.id]: { stability: r.stability, difficulty: r.difficulty },
          }));
        })
        .catch((err: unknown) => {
          setUnsaved((prev) => [...prev, { card: current, grade: g }]);
          toast(errorMessage(err), { variant: "error" });
        });

      const advance = () => {
        setIndex((i) => i + 1);
        setRevealed(false);
        setLeaving(false);
      };

      if (reduced) {
        advance();
        return;
      }
      // Feedback paints at press time, before anything else: bio exhale for a
      // held card, a 4px headshake for a lapse. Presentation only.
      setFx({ kind: g === 1 ? "shake" : "pulse", n: Date.now() });
      setLeaving(true);
      advanceTimer.current = setTimeout(() => {
        advanceTimer.current = null;
        advance();
      }, ADVANCE_MS);
    },
    [index, queue, leaving, reduced, toast],
  );

  const retrySaves = useCallback(() => {
    const batch = unsaved;
    if (batch.length === 0) return;
    setUnsaved([]);
    Promise.all(batch.map((e) => postReview(e.card.id, e.grade)))
      .then(() => {
        toast(`Saved ${batch.length} ${plural(batch.length, "review")}.`);
      })
      .catch((err: unknown) => {
        setUnsaved(batch);
        toast(errorMessage(err), { variant: "error" });
      });
  }, [unsaved, toast]);

  /* --- keyboard ---------------------------------------------------------- */

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e) || hasModifier(e)) return;

      if (e.key === "Escape") {
        e.preventDefault();
        router.push("/");
        return;
      }

      if (done) {
        if (e.key === "Enter") {
          e.preventDefault();
          router.push("/");
        }
        return;
      }

      if (!card) return;

      if (!revealed) {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          setRevealed(true);
        }
        return;
      }

      if (e.key === " ") {
        e.preventDefault();
        grade(3);
        return;
      }
      if (e.key >= "1" && e.key <= "4") {
        e.preventDefault();
        grade(Number(e.key) as Grade);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, revealed, grade, router, done]);

  /* --- states ------------------------------------------------------------ */

  if (loading) {
    return <ReviewSkeleton />;
  }

  if (loadError) {
    return (
      <Centered>
        <Reveal>
          <p
            className="text-[14px] pl-3 border-l-2"
            style={{ borderColor: "var(--g-again)" }}
          >
            {loadError}
          </p>
          <div className="flex gap-4 mt-5 text-[13px]">
            <button onClick={retryLoad} className="link">
              Try again
            </button>
            <Link href="/" className="link text-fg-2">
              Back to today
            </Link>
          </div>
        </Reveal>
      </Centered>
    );
  }

  if (queue.length === 0) {
    return (
      <Centered>
        <Reveal>
          <p className="text-[15px] text-fg">
            {topic
              ? `Nothing is due in ${topic} right now.`
              : "Nothing is due right now."}
          </p>
          <p className="text-[13px] text-fg-2 mt-2 max-w-sm">
            Cards come back when the scheduler decides you are about to forget
            them. To bring work forward, approve some pending cards or ingest a
            new source.
          </p>
          <div className="flex gap-4 mt-5 text-[13px]">
            <Link href="/" className="link">
              Back to today
            </Link>
            <Link href="/approve" className="link text-fg-2">
              Approve queue
            </Link>
          </div>
        </Reveal>
      </Centered>
    );
  }

  if (done) {
    return (
      <Summary
        log={log}
        startedAt={startedAt}
        endedAt={endedAt}
        remaining={remaining}
        capReached={capReached}
        loadingMore={loadingMore}
        onMore={loadMore}
      />
    );
  }

  if (!card) return null;

  const position = index + 1;
  const progress = index / queue.length;
  const solved = card.cloze_text ? parseCloze(card.cloze_text) : null;
  const clozeAnswerIsRedundant =
    !!solved && clozeShowsAnswer(solved, card.answer);

  // The Flow Stack window: the current card plus the next one or two,
  // rendered physically beneath it. Keys are queue positions, so a promoted
  // card keeps its DOM node and its spring simply continues to the next slot.
  const stack = queue.slice(index, index + 3);

  return (
    <div className="min-h-dvh flex flex-col">
      {/* progress: two pixels, monochrome — the fill springs, scaleX only */}
      <div
        className="h-[2px] w-full bg-line shrink-0"
        role="progressbar"
        aria-valuenow={index}
        aria-valuemin={0}
        aria-valuemax={queue.length}
      >
        <motion.div
          className="h-full bg-fg origin-left"
          initial={false}
          animate={{ scaleX: progress }}
          transition={
            reduced
              ? { duration: 0 }
              : { type: "spring", stiffness: 210, damping: 30 }
          }
        />
      </div>

      <div className="shrink-0 px-4 sm:px-6 h-9 flex items-center justify-between text-[11px] text-fg-3">
        <span className={`tnum ${styles.telem}`}>
          {position} / {queue.length}
        </span>
        {unsaved.length > 0 && (
          <button
            onClick={retrySaves}
            className="hover:opacity-80 transition-opacity duration-[90ms]"
            style={{ color: "var(--g-again)" }}
          >
            {unsaved.length} {plural(unsaved.length, "review")} unsaved —
            retry
          </button>
        )}
        <Link
          href="/"
          className="flex items-center gap-1.5 hover:text-fg-2 transition-colors duration-[90ms]"
        >
          <Kbd>Esc</Kbd>
          <span className="hidden sm:inline">exit</span>
        </Link>
      </div>

      <main className="flex-1 flex flex-col justify-center px-5 sm:px-6 py-6">
        <div
          className={`relative w-full max-w-[36rem] mx-auto ${
            fx?.kind === "shake" ? styles.shake : ""
          }`}
          onAnimationEnd={(e) => {
            // The headshake runs on this element itself; animation ends that
            // bubble up from children (cloze flash, pulse ring) are not ours.
            if (e.target === e.currentTarget) setFx(null);
          }}
        >
          {stack.map((c, i) => {
            const top = i === 0;
            const meta = c as QueueCard & LeechSignals;
            const clozeSegs = c.cloze_text ? parseCloze(c.cloze_text) : null;
            const target = leaving
              ? top
                ? STACK_LEAVE
                : STACK_POS[i - 1]
              : STACK_POS[i];
            const transition = reduced
              ? { duration: 0 }
              : leaving
                ? top
                  ? {
                      duration: ADVANCE_MS / 1000 - 0.02,
                      ease: "easeIn" as const,
                    }
                  : {
                      ...ENTER_SPRING,
                      delay: (ADVANCE_MS - PROMOTE_OVERLAP_MS) / 1000,
                    }
                : ENTER_SPRING;
            return (
              <motion.article
                key={`${c.id}-${index + i}`}
                aria-hidden={top ? undefined : true}
                className={`${styles.card} ${top ? "relative" : styles.ghost}`}
                style={{ zIndex: 3 - i }}
                initial={
                  reduced
                    ? false
                    : top
                      ? { ...STACK_POS[0], opacity: 0, y: 12 }
                      : { ...STACK_POS[i], opacity: 0 }
                }
                animate={target}
                transition={transition}
              >
                <p className="flex flex-wrap items-center gap-1.5 mb-4">
                  <span className="prov">
                    {c.topic_code} · {c.page_ref}
                    {c.is_new && <> · new</>}
                  </span>
                  <span className="prov prov--ai">AI</span>
                  {meta.is_leech && (
                    <span
                      className="prov"
                      style={{
                        color: "var(--g-hard)",
                        background: "var(--g-hard-bg)",
                        borderColor: "transparent",
                      }}
                    >
                      {typeof meta.lapses === "number"
                        ? `${meta.lapses} ${plural(meta.lapses, "lapse")}`
                        : "leech"}
                    </span>
                  )}
                </p>

                {clozeSegs ? (
                  <ClozePrompt
                    segments={clozeSegs}
                    revealed={top && revealed}
                    className={`k-question ${top ? styles.clozeFlash : ""}`}
                  />
                ) : top ? (
                  <h1 className="k-question">{c.question}</h1>
                ) : (
                  <p className="k-question">{c.question}</p>
                )}

                {top && revealed && (!solved || !clozeAnswerIsRedundant) && (
                  <motion.div
                    className="mt-7 pt-6 border-t border-line"
                    initial={reduced ? false : { opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={reduced ? { duration: 0 } : REVEAL_SPRING}
                  >
                    <p className="label mb-2">{solved ? "Note" : "Answer"}</p>
                    <p className="k-answer text-fg">{card.answer}</p>
                  </motion.div>
                )}

                {top && revealed && solved && clozeAnswerIsRedundant && (
                  <div
                    className="mt-7 pt-6 border-t border-line"
                    aria-hidden="true"
                  />
                )}
              </motion.article>
            );
          })}

          {fx?.kind === "pulse" && (
            <div
              key={fx.n}
              className={styles.pulseRing}
              aria-hidden="true"
              onAnimationEnd={(e) => {
                e.stopPropagation();
                setFx(null);
              }}
            />
          )}
        </div>
      </main>

      <footer className="shrink-0 px-4 sm:px-6 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="max-w-[36rem] mx-auto">
          {!revealed ? (
            <motion.button
              onClick={() => setRevealed(true)}
              whileTap={reduced ? undefined : TAP}
              className="glow-behind w-full min-h-[64px] sm:min-h-[60px] rounded-sm border border-line bg-surface
                shadow-elev-1 hover:border-line-strong hover:bg-surface-hover transition-colors duration-[90ms]
                flex items-center justify-center gap-2.5 text-[14px] font-medium"
            >
              Show answer
              <Kbd>Space</Kbd>
            </motion.button>
          ) : (
            <motion.div
              className="grid grid-cols-4 gap-1.5"
              initial={reduced ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={reduced ? { duration: 0 } : REVEAL_SPRING}
            >
              {GRADES.map((g, i) => {
                const preview = previews[i];
                return (
                  <motion.button
                    key={g.grade}
                    onClick={() => grade(g.grade)}
                    whileTap={reduced ? undefined : TAP}
                    title={
                      preview?.estimated
                        ? "Estimated: the server did not send this card's memory state"
                        : undefined
                    }
                    className="min-h-[64px] sm:min-h-[60px] rounded-sm border border-line bg-surface shadow-elev-1
                      hover:bg-surface-hover active:bg-surface-hover transition-colors duration-[90ms]
                      flex flex-col items-center justify-center gap-1 px-1"
                    style={{
                      borderTopWidth: 2,
                      borderTopColor: `var(--g-${g.tone})`,
                    }}
                  >
                    <Kbd tone={g.tone}>{g.grade}</Kbd>
                    <span className="text-[12.5px] font-medium leading-none">
                      {g.label}
                    </span>
                    <span
                      className={`text-[11px] text-fg-3 tnum leading-none ${styles.telem}`}
                    >
                      {preview
                        ? `${preview.estimated ? "≈" : ""}${formatInterval(preview.days)}`
                        : "—"}
                    </span>
                  </motion.button>
                );
              })}
            </motion.div>
          )}
        </div>
      </footer>
    </div>
  );
}

/* --- pieces -------------------------------------------------------------- */

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh flex flex-col items-center justify-center px-6">
      <div className="w-full max-w-[36rem]">{children}</div>
    </div>
  );
}

/**
 * The queue-building state, shaped exactly like the card screen it becomes:
 * hairline, counter row, prompt lines, one big button. Nothing moves when the
 * real thing arrives.
 */
export function ReviewSkeleton() {
  return (
    <div
      className="min-h-dvh flex flex-col"
      aria-busy="true"
      aria-label="Building the queue"
    >
      <div className="h-[2px] w-full bg-line shrink-0" />
      <div className="shrink-0 px-4 sm:px-6 h-9 flex items-center justify-between">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-3 w-16" />
      </div>
      <main className="flex-1 flex flex-col justify-center px-5 sm:px-6 py-6">
        <div className="w-full max-w-[36rem] mx-auto">
          <div className={styles.card}>
            <Skeleton className="h-[18px] w-40 mb-4 rounded-full" />
            <Skeleton className="h-6 w-full mb-3" />
            <Skeleton className="h-6 w-4/5" />
          </div>
        </div>
      </main>
      <footer className="shrink-0 px-4 sm:px-6 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="max-w-[36rem] mx-auto">
          <Skeleton className="h-[64px] sm:h-[60px] w-full" />
        </div>
      </footer>
    </div>
  );
}

function Summary({
  log,
  startedAt,
  endedAt,
  remaining,
  capReached,
  loadingMore,
  onMore,
}: {
  log: LogEntry[];
  startedAt: number;
  endedAt: number;
  remaining: number;
  capReached: boolean;
  loadingMore: boolean;
  onMore: () => void;
}) {
  const reduced = useReducedMotion();
  const counts = GRADES.map(
    (g) => log.filter((e) => e.grade === g.grade).length,
  );
  const total = log.length;
  const distinct = new Set(log.map((e) => e.card.id)).size;
  const held = total > 0 ? 1 - counts[0] / total : 0;
  // Measured from the first card loading to the last grade, both captured in
  // event handlers so this render stays pure.
  const durationMs = Math.max(0, endedAt - startedAt);
  const elapsed = formatDuration(durationMs);
  const perMin = total > 0 ? total / Math.max(1 / 60, durationMs / 60000) : 0;

  const byTopic = new Map<string, number>();
  for (const e of log) {
    byTopic.set(e.card.topic_code, (byTopic.get(e.card.topic_code) ?? 0) + 1);
  }

  return (
    <div className="min-h-dvh flex items-center justify-center px-5 py-10">
      <div className="w-full max-w-[36rem]">
        <Reveal>
          <h1 className="text-[18px] font-semibold">Session complete</h1>
          <p className="text-[13px] text-fg-2 mt-1.5">
            {total} {plural(total, "review")} across {distinct}{" "}
            {plural(distinct, "card")} in {elapsed}
            {total > 1 ? `, ${perMin.toFixed(1)} a minute` : ""}.
          </p>
        </Reveal>

        <Reveal index={1}>
          <div className="elev-2 rounded-md mt-5 overflow-hidden">
            <div className="flex items-center gap-5 px-4 py-4">
              <ProgressRing
                value={held}
                size={76}
                thickness={5}
                label={`Held ${Math.round(held * 100)}% of what you saw`}
              >
                <AnimatedNumber
                  value={held * 100}
                  format={formatPct}
                  delay={0.15}
                  className="tnum-display k-text text-[17px] font-semibold"
                />
              </ProgressRing>
              <div className="min-w-0">
                <p className="text-[13px] font-medium">
                  You held{" "}
                  <span className="tnum">{Math.round(held * 100)}%</span> of
                  what you saw.
                </p>
                <p className="text-[12.5px] text-fg-2 mt-1">
                  {counts[0] > 0
                    ? `${counts[0]} ${plural(counts[0], "card")} came back and will be due again soon.`
                    : "Nothing lapsed."}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-4 -ml-px border-t border-line">
              {GRADES.map((g, i) => (
                <div key={g.grade} className="border-l border-line px-3 py-2.5">
                  <div
                    className="text-[22px] font-medium leading-none"
                    style={{
                      color: counts[i] > 0 ? `var(--g-${g.tone})` : undefined,
                    }}
                  >
                    <AnimatedNumber
                      value={counts[i]}
                      delay={0.1 + i * 0.04}
                      className="tnum-display k-text"
                    />
                  </div>
                  <div className="label mt-1.5">{g.label}</div>
                </div>
              ))}
            </div>

            {byTopic.size > 0 && (
              <div className="border-t border-line px-3 py-2.5 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
                {[...byTopic.entries()].map(([code, n], i) => (
                  <Reveal key={code} delay={0.2 + Math.min(i, 6) * 0.04}>
                    <span className="text-fg-2">
                      <span className="font-semibold text-fg tracking-[0.05em]">
                        {code}
                      </span>{" "}
                      <span className="tnum">{n}</span>
                    </span>
                  </Reveal>
                ))}
              </div>
            )}
          </div>
        </Reveal>

        <Reveal index={2}>
          <p className="text-[12.5px] text-fg-2 mt-4">
            {remaining > 0
              ? capReached
                ? `${remaining} more ${plural(remaining, "card")} fit under today's cap.`
                : `${remaining} more ${plural(remaining, "card")} are waiting.`
              : "That is everything scheduled for today."}
          </p>

          <div className="flex flex-wrap items-center gap-2 mt-4">
            <motion.div
              className="glow-behind inline-flex"
              whileTap={reduced ? undefined : TAP}
            >
              <Link
                href="/"
                className="inline-flex items-center gap-2.5 h-9 px-4 rounded-sm text-[13px] font-semibold
                  accent-grad glow-accent-hover border border-transparent"
              >
                Back to today
                <span className="opacity-55 text-[12px] leading-none">
                  &crarr;
                </span>
              </Link>
            </motion.div>
            {remaining > 0 && (
              <motion.button
                onClick={onMore}
                disabled={loadingMore}
                whileTap={reduced ? undefined : TAP}
                className="inline-flex items-center h-9 px-3 rounded-sm text-[13px] font-medium
                  border border-line bg-surface hover:border-line-strong hover:bg-surface-hover
                  transition-colors duration-[90ms] disabled:opacity-45"
              >
                {loadingMore ? "Loading…" : "Keep going"}
              </motion.button>
            )}
          </div>
        </Reveal>
      </div>
    </div>
  );
}
