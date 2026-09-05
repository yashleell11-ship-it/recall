"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ClozePrompt, clozeShowsAnswer } from "@/components/CardText";
import { Kbd } from "@/components/ui";
import { errorMessage, getQueue, getSettings, postReview } from "@/lib/api";
import { parseCloze } from "@/lib/cloze";
import { formatDuration, plural } from "@/lib/format";
import { formatInterval, previewIntervals, type MemoryState } from "@/lib/fsrs";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import type { Grade, QueueCard } from "@/lib/types";

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

interface LogEntry {
  card: QueueCard;
  grade: Grade;
}

export function ReviewSession() {
  const router = useRouter();
  const params = useSearchParams();
  const topic = params.get("topic") ?? undefined;

  const [queue, setQueue] = useState<QueueCard[]>([]);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [retention, setRetention] = useState(0.9);
  const [remaining, setRemaining] = useState(0);
  const [capReached, setCapReached] = useState(false);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [endedAt, setEndedAt] = useState(0);
  const [reloadNonce, setReloadNonce] = useState(0);

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
      const current = queue[index];
      if (!current) return;

      setLog((l) => [...l, { card: current, grade: g }]);
      // "Again" puts the card back at the end of this session, the way a
      // relearning step does.
      if (g === 1) setQueue((q) => [...q, current]);
      setIndex((i) => i + 1);
      setRevealed(false);
      setEndedAt(Date.now());

      void postReview(current.id, g)
        .then((r) => {
          setLearned((prev) => ({
            ...prev,
            [current.id]: { stability: r.stability, difficulty: r.difficulty },
          }));
        })
        .catch((err) => {
          setUnsaved((prev) => [...prev, { card: current, grade: g }]);
          setSaveError(errorMessage(err));
        });
    },
    [index, queue],
  );

  const retrySaves = useCallback(() => {
    const batch = unsaved;
    setUnsaved([]);
    setSaveError(null);
    Promise.all(batch.map((e) => postReview(e.card.id, e.grade))).catch(
      (err) => {
        setUnsaved(batch);
        setSaveError(errorMessage(err));
      },
    );
  }, [unsaved]);

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
    return (
      <Centered>
        <p className="text-[13px] text-fg-3">Building the queue&hellip;</p>
      </Centered>
    );
  }

  if (loadError) {
    return (
      <Centered>
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
      </Centered>
    );
  }

  if (queue.length === 0) {
    return (
      <Centered>
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
  const progress = (index / queue.length) * 100;
  const solved = card.cloze_text ? parseCloze(card.cloze_text) : null;
  const clozeAnswerIsRedundant = !!solved && clozeShowsAnswer(solved, card.answer);

  return (
    <div className="min-h-dvh flex flex-col">
      {/* progress: two pixels, monochrome, no percentage label */}
      <div
        className="h-[2px] w-full bg-line shrink-0"
        role="progressbar"
        aria-valuenow={index}
        aria-valuemin={0}
        aria-valuemax={queue.length}
      >
        <div
          className="h-full bg-fg transition-[width] duration-[90ms] ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="shrink-0 px-4 sm:px-6 h-9 flex items-center justify-between text-[11px] text-fg-3">
        <span className="tnum">
          {position} / {queue.length}
        </span>
        <Link
          href="/"
          className="flex items-center gap-1.5 hover:text-fg-2 transition-colors duration-[90ms]"
        >
          <Kbd>Esc</Kbd>
          <span className="hidden sm:inline">exit</span>
        </Link>
      </div>

      <main className="flex-1 flex flex-col justify-center px-5 sm:px-6 py-6">
        <article key={`${card.id}-${index}`} className="w-full max-w-[36rem] mx-auto anim-advance">
          <p className="text-[11px] text-fg-3 tracking-[0.05em] mb-4">
            <span className="font-semibold text-fg-2">{card.topic_code}</span>
            <span className="mx-1.5">·</span>
            {card.page_ref}
            {card.is_new && (
              <>
                <span className="mx-1.5">·</span>
                new
              </>
            )}
          </p>

          {solved ? (
            <ClozePrompt
              segments={solved}
              revealed={revealed}
              className="text-[clamp(1.15rem,1rem+1.1vw,1.6rem)] leading-[1.55] font-normal"
            />
          ) : (
            <h1 className="text-[clamp(1.15rem,1rem+1.1vw,1.6rem)] leading-[1.5] font-normal">
              {card.question}
            </h1>
          )}

          {revealed && (!solved || !clozeAnswerIsRedundant) && (
            <div className="mt-7 pt-6 border-t border-line anim-reveal">
              <p className="label mb-2">{solved ? "Note" : "Answer"}</p>
              <p className="text-[clamp(1rem,0.95rem+0.5vw,1.2rem)] leading-[1.6] text-fg">
                {card.answer}
              </p>
            </div>
          )}

          {revealed && solved && clozeAnswerIsRedundant && (
            <div className="mt-7 pt-6 border-t border-line" aria-hidden="true" />
          )}
        </article>
      </main>

      {saveError && (
        <div className="shrink-0 px-4 sm:px-6 pb-2">
          <div className="max-w-[36rem] mx-auto flex items-baseline gap-3 text-[12px]">
            <span
              className="pl-2 border-l-2 text-fg-2"
              style={{ borderColor: "var(--g-again)" }}
            >
              {unsaved.length} {plural(unsaved.length, "review")} not saved —{" "}
              {saveError}
            </span>
            <button onClick={retrySaves} className="link text-fg-2 shrink-0">
              Retry
            </button>
          </div>
        </div>
      )}

      <footer className="shrink-0 px-4 sm:px-6 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="max-w-[36rem] mx-auto">
          {!revealed ? (
            <button
              onClick={() => setRevealed(true)}
              className="w-full min-h-[64px] sm:min-h-[60px] rounded-sm border border-line bg-surface
                hover:border-line-strong hover:bg-surface-hover transition-colors duration-[90ms]
                flex items-center justify-center gap-2.5 text-[14px] font-medium"
            >
              Show answer
              <Kbd>Space</Kbd>
            </button>
          ) : (
            <div className="grid grid-cols-4 gap-1.5">
              {GRADES.map((g, i) => {
                const preview = previews[i];
                return (
                  <button
                    key={g.grade}
                    onClick={() => grade(g.grade)}
                    title={
                      preview?.estimated
                        ? "Estimated: the server did not send this card's memory state"
                        : undefined
                    }
                    className="min-h-[64px] sm:min-h-[60px] rounded-sm border border-line bg-surface
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
                    <span className="text-[11px] text-fg-3 tnum leading-none">
                      {preview
                        ? `${preview.estimated ? "≈" : ""}${formatInterval(preview.days)}`
                        : "—"}
                    </span>
                  </button>
                );
              })}
            </div>
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
        <h1 className="text-[18px] font-semibold">Session complete</h1>
        <p className="text-[13px] text-fg-2 mt-1.5">
          {total} {plural(total, "review")} across {distinct}{" "}
          {plural(distinct, "card")} in {elapsed}
          {total > 1 ? `, ${perMin.toFixed(1)} a minute` : ""}.
        </p>

        <div className="panel mt-5 overflow-hidden">
          <div className="grid grid-cols-4 -ml-px">
            {GRADES.map((g, i) => (
              <div key={g.grade} className="border-l border-line px-3 py-2.5">
                <div
                  className="text-[22px] font-medium tnum leading-none"
                  style={{ color: counts[i] > 0 ? `var(--g-${g.tone})` : undefined }}
                >
                  {counts[i]}
                </div>
                <div className="label mt-1.5">{g.label}</div>
              </div>
            ))}
          </div>

          <div className="border-t border-line px-3 py-2.5 text-[12.5px] text-fg-2">
            You held {Math.round(held * 100)}% of what you saw.{" "}
            {counts[0] > 0
              ? `${counts[0]} ${plural(counts[0], "card")} came back and will be due again soon.`
              : "Nothing lapsed."}
          </div>

          {byTopic.size > 0 && (
            <div className="border-t border-line px-3 py-2.5 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
              {[...byTopic.entries()].map(([code, n]) => (
                <span key={code} className="text-fg-2">
                  <span className="font-semibold text-fg tracking-[0.05em]">
                    {code}
                  </span>{" "}
                  <span className="tnum">{n}</span>
                </span>
              ))}
            </div>
          )}
        </div>

        <p className="text-[12.5px] text-fg-2 mt-4">
          {remaining > 0
            ? capReached
              ? `${remaining} more ${plural(remaining, "card")} fit under today's cap.`
              : `${remaining} more ${plural(remaining, "card")} are waiting.`
            : "That is everything scheduled for today."}
        </p>

        <div className="flex flex-wrap items-center gap-2 mt-4">
          <Link
            href="/"
            className="inline-flex items-center gap-2.5 h-9 px-4 rounded-sm text-[13px] font-semibold
              bg-accent text-accent-fg border border-accent hover:bg-accent-hover
              hover:border-accent-hover transition-colors duration-[90ms]"
          >
            Back to today
            <span className="opacity-55 text-[12px] leading-none">&crarr;</span>
          </Link>
          {remaining > 0 && (
            <button
              onClick={onMore}
              disabled={loadingMore}
              className="inline-flex items-center h-9 px-3 rounded-sm text-[13px] font-medium
                border border-line bg-surface hover:border-line-strong hover:bg-surface-hover
                transition-colors duration-[90ms] disabled:opacity-45"
            >
              {loadingMore ? "Loading…" : "Keep going"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
