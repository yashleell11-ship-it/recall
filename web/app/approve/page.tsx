"use client";

import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatedNumber, Skeleton, useToast } from "@/components/rich";
import { Kbd, KindTag } from "@/components/ui";
import { errorMessage, getPending, getTopics, postDecide } from "@/lib/api";
import { parseCloze } from "@/lib/cloze";
import { plural } from "@/lib/format";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import type { PendingCard, Topic } from "@/lib/types";

type Mark = "approve" | "reject";
const PAGE = 50;

/** Mount reveal: the dashboard's spring, staggered at most 40ms per row and
 *  capped so a 200-row page settles in a third of a second, not eight. */
const ROW_SPRING = {
  type: "spring",
  stiffness: 420,
  damping: 34,
  mass: 0.9,
} as const;
const REVEAL_CAP = 8;

/** Committed rows fade + collapse out with a short stagger before removal. */
const EXIT_MS = 180;
const EXIT_STAGGER_S = 0.03;
const EXIT_STAGGER_CAP = 8;

/** Ragged question-line widths for the skeleton, deterministic for SSR. */
const SKELETON_WIDTHS = ["82%", "68%", "75%", "88%", "64%", "79%"];

/** Entrance delays for one arriving batch, keyed by card id. */
function staggerFor(batch: PendingCard[]): Record<number, number> {
  const delays: Record<number, number> = {};
  batch.forEach((c, i) => {
    delays[c.id] = Math.min(i, REVEAL_CAP) * 0.04;
  });
  return delays;
}

function edgeColor(mark: Mark | undefined): string {
  if (mark === "approve") return "var(--g-good)";
  if (mark === "reject") return "var(--g-again)";
  return "transparent";
}

function rowTint(mark: Mark | undefined, isCursor: boolean): string | undefined {
  if (mark === "approve") return "var(--g-good-bg)";
  if (mark === "reject") return "var(--g-again-bg)";
  if (isCursor) return "var(--surface-hover)";
  return undefined;
}

export default function ApprovePage() {
  const toast = useToast();
  const reduced = useReducedMotion();

  const [cards, setCards] = useState<PendingCard[]>([]);
  const [total, setTotal] = useState(0);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topic, setTopic] = useState("");

  const [marks, setMarks] = useState<Record<number, Mark>>({});
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [cursor, setCursor] = useState(0);

  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  // Rows collapsing out after a commit. They stay in `cards` until the exit
  // animation lands, so a failed request can bring them back exactly.
  const [exiting, setExiting] = useState<Set<number>>(() => new Set());
  const [exitDelays, setExitDelays] = useState<Map<number, number>>(
    () => new Map(),
  );
  const removeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const rowRefs = useRef<(HTMLLIElement | null)[]>([]);

  // Entrance delay per card id, assigned once when its batch arrives — the
  // first page and each "load more" stagger; nothing else ever replays it.
  const [mountDelays, setMountDelays] = useState<Record<number, number>>({});

  /* --- data -------------------------------------------------------------- */

  useEffect(() => {
    let live = true;
    getPending(PAGE, 0, topic || undefined)
      .then((res) => {
        if (!live) return;
        setMountDelays(staggerFor(res.cards));
        setCards(res.cards);
        setTotal(res.total);
        setCursor(0);
        setMarks({});
        setSelected(new Set());
        setExiting(new Set());
        setError(null);
      })
      .catch((err: unknown) => {
        if (live) setError(errorMessage(err));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [topic, reloadNonce]);

  useEffect(() => {
    getTopics()
      .then(setTopics)
      .catch(() => setTopics([]));
  }, []);

  useEffect(
    () => () => {
      if (removeTimer.current) clearTimeout(removeTimer.current);
    },
    [],
  );

  const reload = useCallback(() => {
    setLoading(true);
    setReloadNonce((n) => n + 1);
  }, []);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      const res = await getPending(PAGE, cards.length, topic || undefined);
      setMountDelays((prev) => ({ ...prev, ...staggerFor(res.cards) }));
      setCards((c) => [...c, ...res.cards]);
      setTotal(res.total);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingMore(false);
    }
  }, [cards.length, topic]);

  /* --- marking ----------------------------------------------------------- */

  const applyMark = useCallback(
    (mark: Mark | null, ids?: number[]) => {
      setMarks((prev) => {
        const next = { ...prev };
        const here = cards[cursor];
        const targets = ids ?? (here ? [here.id] : []);
        for (const id of targets) {
          if (mark === null) delete next[id];
          else next[id] = mark;
        }
        return next;
      });
    },
    [cards, cursor],
  );

  const markHere = useCallback(
    (mark: Mark) => {
      if (selected.size > 0) {
        applyMark(mark, [...selected]);
        setSelected(new Set());
        return;
      }
      const card = cards[cursor];
      if (!card) return;
      applyMark(mark, [card.id]);
      setCursor((c) => Math.min(c + 1, cards.length - 1));
    },
    [applyMark, cards, cursor, selected],
  );

  const toggleSelect = useCallback(() => {
    const card = cards[cursor];
    if (!card) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(card.id)) next.delete(card.id);
      else next.add(card.id);
      return next;
    });
    setCursor((c) => Math.min(c + 1, cards.length - 1));
  }, [cards, cursor]);

  const approveIds = cards.filter((c) => marks[c.id] === "approve").map((c) => c.id);
  const rejectIds = cards.filter((c) => marks[c.id] === "reject").map((c) => c.id);
  const markedCount = approveIds.length + rejectIds.length;

  /* --- commit ------------------------------------------------------------ */

  const commit = useCallback(async () => {
    if (markedCount === 0 || committing) return;

    const before = { cards, marks, total, cursor };
    const decided = new Set([...approveIds, ...rejectIds]);

    // Optimistic: the rows leave immediately, which is the whole point of a
    // triage screen. If the request fails the exact prior state comes back.
    const delays = new Map<number, number>();
    let k = 0;
    for (const c of cards) {
      if (decided.has(c.id)) {
        delays.set(c.id, Math.min(k++, EXIT_STAGGER_CAP) * EXIT_STAGGER_S);
      }
    }
    setExitDelays(delays);

    const finishRemoval = () => {
      setCards((c) => c.filter((x) => !decided.has(x.id)));
      setExiting(new Set());
      setCursor((c) =>
        Math.min(c, Math.max(0, before.cards.length - decided.size - 1)),
      );
    };

    setMarks({});
    setSelected(new Set());
    setTotal((t) => Math.max(0, t - decided.size));
    setCommitting(true);
    setError(null);

    if (reduced) {
      finishRemoval();
    } else {
      setExiting(decided);
      const lastDelay =
        Math.min(Math.max(decided.size - 1, 0), EXIT_STAGGER_CAP) *
        EXIT_STAGGER_S *
        1000;
      removeTimer.current = setTimeout(() => {
        removeTimer.current = null;
        finishRemoval();
      }, lastDelay + EXIT_MS + 40);
    }

    try {
      // One request per action — the contract's decide endpoint carries a
      // single action, so this is the fewest possible round trips.
      const requests: Promise<unknown>[] = [];
      if (approveIds.length) requests.push(postDecide(approveIds, "approve"));
      if (rejectIds.length) requests.push(postDecide(rejectIds, "reject"));
      await Promise.all(requests);
      toast(
        [
          approveIds.length ? `${approveIds.length} approved` : null,
          rejectIds.length ? `${rejectIds.length} rejected` : null,
        ]
          .filter(Boolean)
          .join(", "),
      );
    } catch (err) {
      // Exact rollback of the optimistic removal.
      if (removeTimer.current) {
        clearTimeout(removeTimer.current);
        removeTimer.current = null;
      }
      setExiting(new Set());
      setCards(before.cards);
      setMarks(before.marks);
      setTotal(before.total);
      setCursor(before.cursor);
      toast(`${errorMessage(err)} Nothing was changed.`, { variant: "error" });
    } finally {
      setCommitting(false);
    }
  }, [
    approveIds,
    rejectIds,
    markedCount,
    committing,
    cards,
    marks,
    total,
    cursor,
    reduced,
    toast,
  ]);

  /* --- keyboard ---------------------------------------------------------- */

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e) || hasModifier(e)) return;

      switch (e.key) {
        case "j":
        case "ArrowDown":
          e.preventDefault();
          setCursor((c) => Math.min(c + 1, cards.length - 1));
          break;
        case "k":
        case "ArrowUp":
          e.preventDefault();
          setCursor((c) => Math.max(c - 1, 0));
          break;
        case "Home":
          e.preventDefault();
          setCursor(0);
          break;
        case "End":
          e.preventDefault();
          setCursor(Math.max(0, cards.length - 1));
          break;
        case "a":
          e.preventDefault();
          markHere("approve");
          break;
        case "r":
          e.preventDefault();
          markHere("reject");
          break;
        case "A":
          e.preventDefault();
          if (selected.size) {
            applyMark("approve", [...selected]);
            setSelected(new Set());
          }
          break;
        case "R":
          e.preventDefault();
          if (selected.size) {
            applyMark("reject", [...selected]);
            setSelected(new Set());
          }
          break;
        case "u":
          e.preventDefault();
          applyMark(null, selected.size ? [...selected] : undefined);
          break;
        case "x":
          e.preventDefault();
          toggleSelect();
          break;
        case "Enter":
          e.preventDefault();
          void commit();
          break;
        case "Escape":
          e.preventDefault();
          setMarks({});
          setSelected(new Set());
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cards.length, markHere, applyMark, toggleSelect, commit, selected]);

  useEffect(() => {
    rowRefs.current[cursor]?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  /* --- render ------------------------------------------------------------ */

  return (
    <main className="mx-auto max-w-[1120px] px-4 py-5 pb-24">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-1">
        <div>
          <h1 className="text-[18px] font-semibold leading-none">Approve</h1>
          <p className="text-[13px] text-fg-2 mt-1.5">
            {loading ? (
              "Loading the triage queue…"
            ) : total === 0 ? (
              "Nothing waiting."
            ) : (
              <>
                <AnimatedNumber value={total} /> generated{" "}
                {plural(total, "card")} waiting. Read, mark, commit.
              </>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={topic}
            onChange={(e) => {
              setLoading(true);
              setTopic(e.target.value);
            }}
            aria-label="Filter by topic"
            className="h-8 px-2 rounded-sm border border-line bg-surface text-[13px] text-fg-2
              hover:border-line-strong transition-colors duration-[90ms]"
          >
            <option value="">All topics</option>
            {topics.map((t) => (
              <option key={t.id} value={t.code}>
                {t.code}
              </option>
            ))}
          </select>
        </div>
      </div>

      <p className="text-[12px] text-fg-3 mb-3.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="flex items-center gap-1.5">
          <Kbd>j</Kbd>
          <Kbd>k</Kbd> move
        </span>
        <span className="flex items-center gap-1.5">
          <Kbd>a</Kbd> approve
        </span>
        <span className="flex items-center gap-1.5">
          <Kbd>r</Kbd> reject
        </span>
        <span className="flex items-center gap-1.5">
          <Kbd>x</Kbd> select
        </span>
        <span className="flex items-center gap-1.5">
          <Kbd>u</Kbd> undo mark
        </span>
        <span className="flex items-center gap-1.5">
          <Kbd>Enter</Kbd> commit
        </span>
      </p>

      {error && (
        <div
          className="mb-3 px-3 py-2 border-l-2 bg-surface text-[13px]"
          style={{ borderLeftColor: "var(--g-again)" }}
          role="alert"
        >
          {error}{" "}
          <button onClick={reload} className="link ml-1">
            Reload
          </button>
        </div>
      )}

      {loading ? (
        /* Shaped exactly like the rows it becomes: gutter, meta line,
           question, answer. Nothing moves when the real queue arrives. */
        <div
          className="panel overflow-hidden"
          aria-busy="true"
          aria-label="Loading the triage queue"
        >
          <ul>
            {SKELETON_WIDTHS.map((w, i) => (
              <li
                key={i}
                className="flex gap-2.5 px-2.5 py-2.5 border-b border-line last:border-b-0 border-l-2 border-l-transparent"
              >
                <div className="w-6 shrink-0 flex flex-col items-center gap-1.5 pt-px">
                  <span
                    className="text-[10px] leading-none text-transparent"
                    aria-hidden="true"
                  >
                    &#9656;
                  </span>
                  <Skeleton className="w-3 h-3 rounded-xs" />
                </div>
                <div className="min-w-0 flex-1">
                  <Skeleton className="h-[14px] w-44 mb-2" />
                  <Skeleton className="h-4" style={{ width: w }} />
                  <Skeleton className="h-[14px] w-3/5 mt-2" />
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : cards.length === 0 ? (
        <div className="panel px-3 py-8 max-w-prose">
          <p className="text-[13px] text-fg-2">
            {topic
              ? `No cards from ${topic} are waiting. Clear the filter to see the rest.`
              : "Nothing is waiting for triage. Ingest a source and its generated cards will land here for you to approve."}
          </p>
          <div className="mt-3 flex gap-4 text-[13px]">
            <Link href="/" className="link">
              Back to today
            </Link>
            <Link href="/sources" className="link text-fg-2">
              Sources
            </Link>
          </div>
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <ul>
            {cards.map((card, i) => {
              const mark = marks[card.id];
              const isCursor = i === cursor;
              const isSelected = selected.has(card.id);
              const isExiting = exiting.has(card.id);
              return (
                <motion.li
                  key={card.id}
                  ref={(el) => {
                    rowRefs.current[i] = el;
                  }}
                  onClick={() => setCursor(i)}
                  initial={reduced ? false : { opacity: 0, y: 8 }}
                  animate={
                    isExiting
                      ? { opacity: 0, y: 0, height: 0, paddingTop: 0, paddingBottom: 0 }
                      : { opacity: 1, y: 0, height: "auto", paddingTop: 10, paddingBottom: 10 }
                  }
                  transition={
                    reduced
                      ? { duration: 0 }
                      : isExiting
                        ? {
                            duration: EXIT_MS / 1000,
                            ease: "easeIn",
                            delay: exitDelays.get(card.id) ?? 0,
                          }
                        : { ...ROW_SPRING, delay: mountDelays[card.id] ?? 0 }
                  }
                  className={`flex gap-2.5 px-2.5 py-2.5 border-b border-line last:border-b-0 border-l-2
                    cursor-default transition-[background-color,border-color] duration-150 ease-out
                    ${!mark && !isCursor && !isExiting ? "hover:bg-surface-hover" : ""}`}
                  style={{
                    borderLeftColor: edgeColor(mark),
                    backgroundColor: rowTint(mark, isCursor),
                    overflow: isExiting ? "hidden" : undefined,
                    borderBottomWidth: isExiting ? 0 : undefined,
                    pointerEvents: isExiting ? "none" : undefined,
                  }}
                >
                  {/* gutter: cursor caret + selection box */}
                  <div className="w-6 shrink-0 flex flex-col items-center gap-1.5 pt-px">
                    <motion.span
                      className="text-[10px] leading-none text-fg"
                      aria-hidden="true"
                      initial={false}
                      animate={{ opacity: isCursor ? 1 : 0, x: isCursor ? 0 : -3 }}
                      transition={
                        reduced
                          ? { duration: 0 }
                          : { type: "spring", stiffness: 520, damping: 32, mass: 0.7 }
                      }
                    >
                      &#9656;
                    </motion.span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelected((prev) => {
                          const next = new Set(prev);
                          if (next.has(card.id)) next.delete(card.id);
                          else next.add(card.id);
                          return next;
                        });
                      }}
                      aria-label={isSelected ? "Deselect card" : "Select card"}
                      aria-pressed={isSelected}
                      className={`w-3 h-3 rounded-xs border ${
                        isSelected
                          ? "bg-fg border-fg"
                          : "border-line-strong hover:border-fg-2"
                      }`}
                    />
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 text-[11px] text-fg-3">
                      <span className="font-semibold tracking-[0.05em] text-fg-2">
                        {card.topic_code}
                      </span>
                      <span>{card.page_ref}</span>
                      {/* Provenance: every row here is model-generated, and
                          the one legal violet is the marker saying so. */}
                      <span
                        className="text-ai text-[10px] font-medium tracking-[0.08em] leading-none"
                        style={{ fontFamily: "var(--font-mono)" }}
                        title="Generated by the model"
                      >
                        AI
                      </span>
                      <KindTag kind={card.kind} />
                      <span className="truncate hidden sm:inline">
                        {card.source_filename}
                      </span>
                    </div>

                    <p
                      className={`k-text text-[13.5px] font-medium leading-snug ${
                        mark === "reject" ? "line-through text-fg-2" : ""
                      }`}
                    >
                      {card.cloze_text
                        ? parseCloze(card.cloze_text).map((seg, k) =>
                            seg.kind === "text" ? (
                              <span key={k}>{seg.text}</span>
                            ) : (
                              <span key={k} className="border-b border-fg-3">
                                {seg.text}
                              </span>
                            ),
                          )
                        : card.question}
                    </p>

                    {(!card.cloze_text || card.answer) && (
                      <p className="k-text text-[12.5px] text-fg-2 leading-snug mt-1">
                        {card.answer}
                      </p>
                    )}
                  </div>

                  <div className="w-[58px] shrink-0 text-right">
                    {mark && (
                      <span
                        className="label"
                        style={{
                          color:
                            mark === "approve"
                              ? "var(--g-good)"
                              : "var(--g-again)",
                        }}
                      >
                        {mark === "approve" ? "keep" : "drop"}
                      </span>
                    )}
                  </div>
                </motion.li>
              );
            })}
          </ul>

          {cards.length < total && (
            <div className="border-t border-line px-3 py-2">
              <button
                onClick={() => void loadMore()}
                disabled={loadingMore}
                className="text-[13px] link text-fg-2 disabled:opacity-45"
              >
                {loadingMore
                  ? "Loading…"
                  : `Load ${Math.min(PAGE, total - cards.length)} more`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* --- commit bar ---------------------------------------------------- */}
      {cards.length > 0 && (
        <div className="fixed bottom-0 inset-x-0 border-t border-line bg-surface z-20">
          <div className="mx-auto max-w-[1120px] px-4 h-14 flex items-center gap-4">
            <div className="text-[12.5px] text-fg-2 min-w-0 tnum">
              {markedCount === 0 ? (
                <span className="text-fg-3">
                  {selected.size > 0
                    ? `${selected.size} selected — press a or r to mark them`
                    : "Nothing marked yet"}
                </span>
              ) : (
                <>
                  <span className="font-semibold text-fg">
                    {approveIds.length}
                  </span>{" "}
                  to keep
                  <span className="mx-2 text-fg-3">·</span>
                  <span className="font-semibold text-fg">
                    {rejectIds.length}
                  </span>{" "}
                  to drop
                </>
              )}
            </div>

            <div className="ml-auto flex items-center gap-2 shrink-0">
              {markedCount > 0 && (
                <button
                  onClick={() => {
                    setMarks({});
                    setSelected(new Set());
                  }}
                  className="h-8 px-3 rounded-sm text-[13px] text-fg-2 hover:text-fg
                    hover:bg-surface-hover transition-colors duration-[90ms]"
                >
                  Clear
                </button>
              )}
              <button
                onClick={() => void commit()}
                disabled={markedCount === 0 || committing}
                className="inline-flex items-center gap-2.5 h-8 px-4 rounded-sm text-[13px] font-semibold
                  bg-accent text-accent-fg border border-accent hover:bg-accent-hover
                  hover:border-accent-hover transition-colors duration-[90ms]
                  disabled:opacity-40 disabled:pointer-events-none"
              >
                {committing ? "Committing…" : `Commit ${markedCount || ""}`.trim()}
                <span className="opacity-55 text-[12px] leading-none">
                  &crarr;
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
