"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatedNumber, Reveal, Skeleton } from "@/components/rich";
import { ErrorState, Kbd, Panel, TopicCode } from "@/components/ui";
import { createTest, errorMessage, getTests, getTopics } from "@/lib/api";
import { formatDuration, mediumDate, plural } from "@/lib/format";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import { MAX_MARKS, PAPER_LABEL } from "@/lib/marks";
import type { TestKind, TestSummary, Topic } from "@/lib/types";
import { useResource } from "@/lib/useResource";
import { HeightSpring } from "./HeightSpring";

interface Paper {
  kind: TestKind;
  name: string;
  /** null for the full-day paper, which is sized by the deck, not by a target. */
  target: number | null;
  limitMin: number | null;
  character: string;
}

const PAPERS: Paper[] = [
  {
    kind: "class30",
    name: "Class test",
    target: 30,
    limitMin: 45,
    character: "A sessional. Short enough to sit between lectures.",
  },
  {
    kind: "endterm100",
    name: "End term",
    target: 100,
    limitMin: 180,
    character: "A full paper at exam length, so the pacing is the real thing.",
  },
  {
    kind: "fullday",
    name: "Full day",
    target: null,
    limitMin: null,
    character:
      "Every active card, no clock. Close the tab and pick it up tomorrow.",
  },
];

async function fetchPicker(): Promise<{ topics: Topic[]; tests: TestSummary[] }> {
  const [topics, tests] = await Promise.all([getTopics(), getTests()]);
  return { topics, tests };
}

/** A paper with no duration recorded was started and never submitted. */
function isOpen(t: TestSummary): boolean {
  return !t.duration_s;
}

export default function TestPickerPage() {
  const router = useRouter();
  const reduced = useReducedMotion();
  const res = useResource("test-picker", fetchPicker);

  const [kind, setKind] = useState<TestKind>("class30");
  const [topic, setTopic] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const topics = useMemo(() => res.data?.topics ?? [], [res.data]);

  /** The topics this paper will actually draw from. */
  const pool = useMemo(
    () => (topic ? topics.filter((t) => t.code === topic) : topics),
    [topics, topic],
  );
  const activeTotal = pool.reduce((n, t) => n + t.active, 0);
  const paper = PAPERS.find((p) => p.kind === kind)!;

  /**
   * Exact bounds, not a guess: every card is worth 1 to 5 marks, so a paper of
   * T marks holds between ceil(T/5) and T questions — and never more questions
   * than the deck has cards.
   */
  const bounds = useMemo(() => {
    if (paper.target === null) {
      return {
        minQ: activeTotal,
        maxQ: activeTotal,
        short: false,
        ceiling: activeTotal * MAX_MARKS,
      };
    }
    const ceiling = activeTotal * MAX_MARKS;
    return {
      minQ: Math.ceil(paper.target / MAX_MARKS),
      maxQ: Math.min(paper.target, activeTotal),
      short: ceiling < paper.target,
      ceiling,
    };
  }, [paper.target, activeTotal]);

  const start = useCallback(() => {
    if (starting || activeTotal === 0) return;
    setStarting(true);
    setStartError(null);
    createTest(kind, topic || undefined)
      .then((p) => router.push(`/test/${p.test_id}`))
      .catch((err: unknown) => {
        setStartError(errorMessage(err));
        setStarting(false);
      });
  }, [kind, topic, router, starting, activeTotal]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e) || hasModifier(e)) return;
      if (e.key >= "1" && e.key <= "3") {
        e.preventDefault();
        setKind(PAPERS[Number(e.key) - 1].kind);
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        start();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [start]);

  const open = (res.data?.tests ?? []).filter(isOpen);
  const finished = (res.data?.tests ?? []).filter((t) => !isOpen(t));

  return (
    <main className="mx-auto max-w-[1120px] px-4 py-5 pb-10">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
        <div>
          <h1 className="text-[18px] font-semibold leading-none">Test</h1>
          <p className="text-[13px] text-fg-2 mt-1.5 max-w-prose">
            Sit a paper, grade yourself honestly, and what you miss comes back
            sooner. Everything you answer records a real review.
          </p>
        </div>

        <select
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          aria-label="Restrict the paper to one topic"
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

      {res.error && !res.data ? (
        <ErrorState message={res.error} onRetry={res.reload} />
      ) : null}

      {open.length > 0 && (
        <div className="panel mb-4 px-3 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-2 border-l-2 border-l-accent">
          <p className="text-[13px] text-fg-2">
            <span className="font-semibold text-fg">
              {open.length} unfinished {plural(open.length, "paper")}.
            </span>{" "}
            Nothing was lost — every answer was saved as you gave it.
          </p>
          <div className="flex flex-wrap gap-3 ml-auto">
            {open.map((t) => (
              <Link
                key={t.id}
                href={`/test/${t.id}`}
                className="link text-[13px]"
              >
                Resume {PAPER_LABEL[t.kind] ?? t.kind} from{" "}
                {mediumDate(t.started_at)}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* --- pick a paper --------------------------------------------------- */}

      <div className="grid gap-3 lg:grid-cols-3" role="radiogroup" aria-label="Paper">
        {PAPERS.map((p, i) => {
          const selected = p.kind === kind;
          return (
            <Reveal key={p.kind} index={i}>
              <motion.button
                role="radio"
                aria-checked={selected}
                onClick={() => setKind(p.kind)}
                whileHover={reduced ? undefined : { y: -2 }}
                whileTap={reduced ? undefined : { scale: 0.98 }}
                transition={{ type: "spring", stiffness: 460, damping: 32 }}
                className={`w-full text-left px-3.5 py-3 rounded-md border
                  transition-[border-color,background-color,box-shadow] duration-[140ms]
                  ${
                    selected
                      ? "bg-surface-raised border-accent"
                      : "panel hover:border-line-strong hover:bg-surface-hover"
                  }`}
                style={
                  selected
                    ? {
                        boxShadow:
                          "var(--shadow-2), 0 8px 28px -8px var(--accent-glow)",
                      }
                    : undefined
                }
              >
                <div className="flex items-baseline gap-2">
                  <Kbd>{i + 1}</Kbd>
                  <h2
                    className={`text-[14px] ${
                      selected ? "font-semibold text-fg" : "font-medium text-fg-2"
                    }`}
                  >
                    {p.name}
                  </h2>
                </div>

                <p className="text-[19px] font-medium tnum mt-2.5 leading-none">
                  {p.target === null ? (
                    <>
                      <AnimatedNumber value={activeTotal} />{" "}
                      <span className="text-[13px] text-fg-2 font-normal">
                        cards
                      </span>
                    </>
                  ) : (
                    <>
                      <AnimatedNumber value={p.target} />{" "}
                      <span className="text-[13px] text-fg-2 font-normal">
                        marks
                      </span>
                    </>
                  )}
                </p>

                <p className="text-[12px] text-fg-3 mt-1.5 tnum">
                  {p.limitMin === null
                    ? "no time limit"
                    : `${p.limitMin} minutes`}
                  <span className="mx-1.5">·</span>
                  {p.target === null
                    ? `${activeTotal * 1}–${activeTotal * MAX_MARKS} marks`
                    : bounds.minQ === bounds.maxQ
                      ? `${bounds.maxQ} questions`
                      : `${Math.ceil(p.target / MAX_MARKS)}–${Math.min(
                          p.target,
                          activeTotal,
                        )} questions`}
                </p>

                <p className="text-[12.5px] text-fg-2 mt-2.5 leading-snug">
                  {p.character}
                </p>
              </motion.button>
            </Reveal>
          );
        })}
      </div>

      {/* --- what it will contain ------------------------------------------- */}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px] items-start mt-4">
        <HeightSpring>
          <Panel
            title="What this paper will contain"
            aside={topic ? `${topic} only` : `${pool.length} topics`}
          >
            {res.loading && !res.data ? (
              <div className="px-3 py-3" aria-label="Reading your deck">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-4 py-2">
                    <Skeleton className="h-3 w-14" />
                    <Skeleton className="h-3 flex-1 hidden sm:block" />
                    <Skeleton className="h-3 w-10" />
                    <Skeleton className="h-3 w-8" />
                    <Skeleton className="h-3 w-12" />
                  </div>
                ))}
              </div>
            ) : activeTotal === 0 ? (
              <div className="px-3 py-8 max-w-prose">
                <p className="text-[13px] text-fg-2">
                  {topic
                    ? `${topic} has no active cards yet, so there is nothing to examine. Approve some of its pending cards first.`
                    : "You have no active cards yet. Upload a source, generate cards from it, and approve the ones worth keeping."}
                </p>
                <div className="mt-3 flex gap-4 text-[13px]">
                  <Link href="/upload" className="link">
                    Upload a source
                  </Link>
                  <Link href="/approve" className="link text-fg-2">
                    Approve queue
                  </Link>
                </div>
              </div>
            ) : (
              <div key={`${kind}-${topic}`} className="anim-reveal">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="label text-left font-semibold px-3 py-1.5">
                        Topic
                      </th>
                      <th className="label text-left font-semibold px-3 py-1.5 hidden sm:table-cell">
                        Course
                      </th>
                      <th className="label text-right font-semibold px-3 py-1.5 w-16">
                        Active
                      </th>
                      <th className="label text-right font-semibold px-3 py-1.5 w-16">
                        Share
                      </th>
                      <th className="label text-right font-semibold px-3 py-1.5 w-20">
                        {paper.target === null ? "Questions" : "Marks"}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {pool.map((t) => {
                      const share = t.active / activeTotal;
                      return (
                        <tr
                          key={t.id}
                          className="border-b border-line last:border-b-0"
                        >
                          <td className="px-3 py-[7px]">
                            <TopicCode code={t.code} />
                          </td>
                          <td className="px-3 py-[7px] text-fg-2 hidden sm:table-cell truncate max-w-[1px]">
                            {t.label}
                          </td>
                          <td className="px-3 py-[7px] text-right tnum text-fg-2">
                            {t.active.toLocaleString()}
                          </td>
                          <td className="px-3 py-[7px] text-right tnum text-fg-2">
                            {Math.round(share * 100)}%
                          </td>
                          <td className="px-3 py-[7px] text-right tnum font-medium">
                            {paper.target === null
                              ? t.active.toLocaleString()
                              : `≈ ${Math.round(paper.target * share)}`}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                <div className="border-t border-line px-3 py-2.5 text-[12.5px] text-fg-2 max-w-prose">
                  <p>
                    Questions are drawn in proportion to each topic&rsquo;s active
                    cards, weighted toward the ones you are weakest on — high
                    difficulty, low stability, due or overdue — with some settled
                    cards mixed in so the paper is not purely punishment.
                  </p>
                  {bounds.short && (
                    <p className="mt-2 pl-2 border-l-2 border-l-line-strong">
                      Your deck cannot fill this paper. {activeTotal.toLocaleString()}{" "}
                      active {plural(activeTotal, "card")} is at most{" "}
                      {bounds.ceiling} marks, so a {paper.target}-mark paper will
                      come up short and will say so when you submit it.
                    </p>
                  )}
                </div>
              </div>
            )}
          </Panel>
        </HeightSpring>

        <div className="grid gap-4">
          <Panel title="Scoring" bodyClassName="px-3 py-2.5">
            <dl className="text-[12.5px]">
              {[
                ["Correct", "full marks", "good"],
                ["Partial", "half, on 2+ mark questions", "hard"],
                ["Wrong", "nothing", "again"],
                ["Skipped", "nothing, and no review recorded", null],
              ].map(([label, note, tone]) => (
                <div
                  key={label}
                  className="flex items-baseline justify-between gap-3 py-[3px]"
                >
                  <dt
                    className="font-medium"
                    style={tone ? { color: `var(--g-${tone})` } : undefined}
                  >
                    {label}
                  </dt>
                  <dd className="text-fg-3 text-right">{note}</dd>
                </div>
              ))}
            </dl>
            <p className="text-[12px] text-fg-3 mt-2 pt-2 border-t border-line leading-snug">
              Answering records a real review, so the scheduler moves exactly as
              it does in daily practice. Skipping records nothing — not
              attempting a question is not evidence about memory.
            </p>
          </Panel>

          {finished.length > 0 && (
            <Panel title="Past papers" aside={`${finished.length}`}>
              <ul className="text-[12.5px]">
                {finished.slice(0, 6).map((t) => (
                  <li
                    key={t.id}
                    className="flex items-baseline justify-between gap-3 px-3 py-[6px] border-b border-line last:border-b-0"
                  >
                    <span className="min-w-0">
                      <span className="font-medium">
                        {PAPER_LABEL[t.kind] ?? t.kind}
                      </span>
                      <span className="text-fg-3 ml-2">
                        {mediumDate(t.started_at)}
                      </span>
                    </span>
                    <span className="tnum shrink-0 text-fg-2">
                      {t.obtained_marks}/{t.total_marks}
                      {t.duration_s ? (
                        <span className="text-fg-3 ml-2">
                          {formatDuration(t.duration_s * 1000)}
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>

      {startError && (
        <div
          className="mt-4 px-3 py-2 border-l-2 bg-surface text-[13px]"
          style={{ borderLeftColor: "var(--g-again)" }}
          role="alert"
        >
          {startError}
        </div>
      )}

      {/* --- start ---------------------------------------------------------- */}

      <div className="flex flex-wrap items-center gap-3 mt-5">
        <motion.button
          onClick={start}
          disabled={starting || activeTotal === 0 || res.loading}
          whileTap={reduced ? undefined : { scale: 0.98 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
          className="glow-behind accent-grad glow-accent-hover inline-flex items-center gap-2.5
            h-9 px-4 rounded-sm text-[13px] font-semibold border border-accent
            disabled:opacity-40 disabled:pointer-events-none"
        >
          {starting ? "Assembling…" : `Start ${paper.name.toLowerCase()}`}
          <span className="opacity-55 text-[12px] leading-none">&crarr;</span>
        </motion.button>
        <p className="text-[12px] text-fg-3">
          {paper.limitMin === null
            ? "The clock does not run. Leave and come back."
            : `The clock starts now and runs for ${paper.limitMin} minutes.`}
        </p>
      </div>
    </main>
  );
}
