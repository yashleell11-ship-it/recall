"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Kbd, KindTag } from "@/components/ui";
import { errorMessage, getPending, getTopics, postDecide } from "@/lib/api";
import { parseCloze } from "@/lib/cloze";
import { plural } from "@/lib/format";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import type { PendingCard, Topic } from "@/lib/types";

type Mark = "approve" | "reject";
const PAGE = 50;

export default function ApprovePage() {
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
  const [flash, setFlash] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const rowRefs = useRef<(HTMLLIElement | null)[]>([]);

  /* --- data -------------------------------------------------------------- */

  useEffect(() => {
    let live = true;
    getPending(PAGE, 0, topic || undefined)
      .then((res) => {
        if (!live) return;
        setCards(res.cards);
        setTotal(res.total);
        setCursor(0);
        setMarks({});
        setSelected(new Set());
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

  const reload = useCallback(() => {
    setLoading(true);
    setReloadNonce((n) => n + 1);
  }, []);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      const res = await getPending(PAGE, cards.length, topic || undefined);
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
    setCards((c) => c.filter((x) => !decided.has(x.id)));
    setMarks({});
    setSelected(new Set());
    setTotal((t) => Math.max(0, t - decided.size));
    setCursor((c) => Math.min(c, Math.max(0, before.cards.length - decided.size - 1)));
    setCommitting(true);
    setError(null);

    try {
      // One request per action — the contract's decide endpoint carries a
      // single action, so this is the fewest possible round trips.
      const requests: Promise<unknown>[] = [];
      if (approveIds.length) requests.push(postDecide(approveIds, "approve"));
      if (rejectIds.length) requests.push(postDecide(rejectIds, "reject"));
      await Promise.all(requests);
      setFlash(
        [
          approveIds.length ? `${approveIds.length} approved` : null,
          rejectIds.length ? `${rejectIds.length} rejected` : null,
        ]
          .filter(Boolean)
          .join(", "),
      );
    } catch (err) {
      setCards(before.cards);
      setMarks(before.marks);
      setTotal(before.total);
      setCursor(before.cursor);
      setError(`${errorMessage(err)} Nothing was changed.`);
    } finally {
      setCommitting(false);
    }
  }, [approveIds, rejectIds, markedCount, committing, cards, marks, total, cursor]);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 2600);
    return () => clearTimeout(t);
  }, [flash]);

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
            {loading
              ? "Loading the triage queue…"
              : total === 0
                ? "Nothing waiting."
                : `${total} generated ${plural(total, "card")} waiting. Read, mark, commit.`}
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
        <div className="panel px-3 py-6 text-[13px] text-fg-3">
          Loading the triage queue&hellip;
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
              return (
                <li
                  key={card.id}
                  ref={(el) => {
                    rowRefs.current[i] = el;
                  }}
                  onClick={() => setCursor(i)}
                  className={`flex gap-2.5 px-2.5 py-2.5 border-b border-line last:border-b-0 border-l-2
                    cursor-default transition-colors duration-[90ms]
                    ${isCursor ? "bg-surface-hover" : "hover:bg-surface-hover"}
                    ${mark === "reject" ? "opacity-55" : ""}`}
                  style={{
                    borderLeftColor:
                      mark === "approve"
                        ? "var(--fg)"
                        : mark === "reject"
                          ? "var(--line-strong)"
                          : "transparent",
                  }}
                >
                  {/* gutter: cursor caret + selection box */}
                  <div className="w-6 shrink-0 flex flex-col items-center gap-1.5 pt-px">
                    <span
                      className={`text-[10px] leading-none ${
                        isCursor ? "text-fg" : "text-transparent"
                      }`}
                      aria-hidden="true"
                    >
                      &#9656;
                    </span>
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
                      <KindTag kind={card.kind} />
                      <span className="truncate hidden sm:inline">
                        {card.source_filename}
                      </span>
                    </div>

                    <p
                      className={`text-[13.5px] font-medium leading-snug ${
                        mark === "reject" ? "line-through" : ""
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
                      <p className="text-[12.5px] text-fg-2 leading-snug mt-1">
                        {card.answer}
                      </p>
                    )}
                  </div>

                  <div className="w-[58px] shrink-0 text-right">
                    {mark && (
                      <span className="label">
                        {mark === "approve" ? "keep" : "drop"}
                      </span>
                    )}
                  </div>
                </li>
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
              {flash && (
                <span className="ml-3 text-fg-3">{flash}</span>
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
