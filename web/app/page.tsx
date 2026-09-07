"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo } from "react";
import { ActivityChart } from "@/app/(dashboard)/ActivityChart";
import { DashboardSkeleton } from "@/app/(dashboard)/DashboardSkeleton";
import { MetricStrip } from "@/app/(dashboard)/MetricStrip";
import { ProgressRing, Reveal, Skeleton } from "@/components/rich";
import { Constellation } from "@/components/rich/Constellation";
import {
  EmptyState,
  ErrorState,
  KindTag,
  Panel,
  TopicCode,
} from "@/components/ui";
import { longDate, plural } from "@/lib/format";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import { fetchDashboard, prefetchReviewQueue } from "@/lib/resources";
import { useResource } from "@/lib/useResource";

const MotionLink = motion.create(Link);

export default function DashboardPage() {
  const router = useRouter();
  const reduced = useReducedMotion();

  const res = useResource("dashboard", fetchDashboard);

  const totals = useMemo(() => {
    const t = res.data?.topics ?? [];
    return {
      due: t.reduce((n, x) => n + x.due, 0),
      new: t.reduce((n, x) => n + x.new, 0),
      active: t.reduce((n, x) => n + x.active, 0),
    };
  }, [res.data]);

  const statsDate =
    res.data?.stats.last_14_days[res.data.stats.last_14_days.length - 1]?.date ??
    null;
  const load = totals.due + totals.new;
  const reviewed = res.data?.stats.today.reviewed ?? 0;
  const cap = res.data?.settings.daily_review_cap ?? null;
  const slots = cap === null ? null : Math.max(0, cap - reviewed);
  const capped = slots !== null && load > slots;
  const willFit = slots === null ? load : Math.min(load, slots);
  const streak = res.data?.stats.today.streak ?? 0;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e) || hasModifier(e)) return;
      if (e.key === "Enter" && willFit > 0) {
        e.preventDefault();
        // Enter has no hover step to warm the queue with, so start the fetch
        // in the same tick as the navigation it triggers.
        prefetchReviewQueue();
        router.push("/review");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, willFit]);

  return (
    <main className="mx-auto max-w-[1120px] px-4 py-5">
      {/* Wraps rather than squeezing: on a phone the actions drop to their own
          line instead of breaking the date across two. */}
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2 mb-3.5">
        <div>
          <h1 className="text-[18px] font-semibold leading-none">Today</h1>
          <p className="text-[13px] text-fg-2 mt-1.5 min-h-[1.25rem]">
            {statsDate ? longDate(statsDate) : ""}
          </p>
        </div>

        <div className="flex items-center gap-4 shrink-0 ml-auto">
          <Link
            href="/test"
            className="text-[13px] link text-fg-2 hover:text-fg whitespace-nowrap"
          >
            Sit a test
          </Link>

          {!res.data ? (
            res.loading ? (
              <Skeleton className="h-9 w-32 rounded-sm" />
            ) : (
              <span aria-hidden="true" className="h-9" />
            )
          ) : load === 0 ? (
            /* All clear: nothing waiting. The streak, held with the dignity
               of a number and a ring — no flame required. */
            <div className="flex items-center gap-2.5 h-9">
              <ProgressRing
                value={cap !== null && cap > 0 ? Math.min(1, reviewed / cap) : 1}
                size={30}
                thickness={3}
                label={`${reviewed} reviews done today`}
              />
              <div>
                <div className="text-[13px] font-medium leading-tight text-fg">
                  All clear
                </div>
                <div className="text-[11px] text-fg-3 leading-tight">
                  <span className="tnum">{streak}</span>-day streak
                </div>
              </div>
            </div>
          ) : willFit > 0 ? (
            <MotionLink
              href="/review"
              onMouseEnter={() => prefetchReviewQueue()}
              onFocus={() => prefetchReviewQueue()}
              whileTap={reduced ? undefined : { scale: 0.98 }}
              className="glow-behind glow-accent-hover accent-grad inline-flex items-center gap-2.5
                h-9 px-4 rounded-sm text-[13px] font-semibold"
            >
              Start review
              <span className="tnum opacity-70">{willFit}</span>
              <span className="opacity-55 text-[12px] leading-none">&crarr;</span>
            </MotionLink>
          ) : (
            <span className="text-[13px] text-fg-3 h-9 flex items-center">
              Cap reached for today
            </span>
          )}
        </div>
      </div>

      {res.error && !res.data ? (
        <ErrorState message={res.error} onRetry={res.reload} />
      ) : null}

      {res.loading && !res.data ? <DashboardSkeleton /> : null}

      {res.data && (
        <>
          {/* --- the day in one strip ------------------------------------ */}
          <Reveal index={0}>
            <MetricStrip
              due={totals.due}
              newCount={totals.new}
              newLimit={res.data.settings.new_cards_per_day}
              reviewed={reviewed}
              cap={cap}
              again={res.data.stats.today.again}
              streak={streak}
              active={res.data.stats.totals.active}
            />
          </Reveal>

          <Reveal
            index={1}
            className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 mt-2 mb-4 text-[12.5px]"
          >
            <p className={capped ? "text-fg" : "text-fg-2"}>
              {slots === null ? (
                <>
                  {load} {plural(load, "card")} waiting.
                </>
              ) : capped ? (
                <>
                  <span className="font-semibold">Cap reached.</span> {willFit} of{" "}
                  {load} will fit today — {reviewed} of {cap} already done. The
                  remaining {load - willFit} roll into tomorrow.
                </>
              ) : load === 0 ? (
                <>Nothing is due. The next cards come back when they are ready.</>
              ) : (
                <>
                  {load} {plural(load, "card")} to go, {slots} still allowed
                  under today&rsquo;s cap of {cap}.
                </>
              )}
            </p>

          </Reveal>

          {/* --- topics and history -------------------------------------- */}
          <div className="grid gap-4 lg:grid-cols-[1fr_340px] items-start">
            <Reveal index={2}>
              <Panel
                title="By topic"
                aside={`${res.data.topics.length} topics`}
                className="shadow-elev-1"
              >
                {res.data.topics.length === 0 ? (
                  <EmptyState>
                    No topics yet. Ingest a PDF or a set of notes and the topic
                    appears here once its cards are generated.
                  </EmptyState>
                ) : (
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className="border-b border-line">
                        <th className="label text-left font-semibold px-3 py-1.5">
                          Topic
                        </th>
                        <th className="label text-left font-semibold px-3 py-1.5 hidden sm:table-cell">
                          Course
                        </th>
                        <th className="label text-right font-semibold px-3 py-1.5 w-14">
                          Due
                        </th>
                        <th className="label text-right font-semibold px-3 py-1.5 w-14">
                          New
                        </th>
                        <th className="label text-right font-semibold px-3 py-1.5 w-16">
                          Active
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {res.data.topics.map((t, i) => (
                        <motion.tr
                          key={t.id}
                          initial={reduced ? false : { opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{
                            type: "spring",
                            stiffness: 420,
                            damping: 34,
                            mass: 0.9,
                            delay: 0.06 + Math.min(i, 6) * 0.04,
                          }}
                          onMouseEnter={() => prefetchReviewQueue(t.code)}
                          onClick={() => {
                            prefetchReviewQueue(t.code);
                            router.push(`/review?topic=${t.code}`);
                          }}
                          className="border-b border-line last:border-b-0 cursor-pointer hover:bg-surface-hover transition-colors duration-[90ms]"
                        >
                          <td className="px-3 py-[7px]">
                            <Link
                              href={`/review?topic=${t.code}`}
                              onClick={(e) => e.stopPropagation()}
                              onMouseEnter={() => prefetchReviewQueue(t.code)}
                              className="hover:underline underline-offset-2"
                            >
                              <TopicCode code={t.code} />
                            </Link>
                          </td>
                          <td className="px-3 py-[7px] text-fg-2 hidden sm:table-cell truncate max-w-[1px]">
                            {t.label}
                          </td>
                          <td
                            className={`px-3 py-[7px] text-right tnum ${
                              t.due > 0 ? "font-medium" : "text-fg-3"
                            }`}
                          >
                            {t.due || "—"}
                          </td>
                          <td
                            className={`px-3 py-[7px] text-right tnum ${
                              t.new > 0 ? "" : "text-fg-3"
                            }`}
                          >
                            {t.new || "—"}
                          </td>
                          <td className="px-3 py-[7px] text-right tnum text-fg-2">
                            {t.active.toLocaleString()}
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t border-line-strong bg-sunken">
                        <td className="px-3 py-[7px] label">Total</td>
                        <td className="hidden sm:table-cell" />
                        <td className="px-3 py-[7px] text-right tnum font-semibold">
                          {totals.due}
                        </td>
                        <td className="px-3 py-[7px] text-right tnum font-semibold">
                          {totals.new}
                        </td>
                        <td className="px-3 py-[7px] text-right tnum font-semibold">
                          {totals.active.toLocaleString()}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </Panel>
            </Reveal>

            <Reveal index={3} className="grid gap-4">
              <Panel
                title="Last 14 days"
                aside={`${res.data.stats.last_14_days
                  .reduce((n, d) => n + d.count, 0)
                  .toLocaleString()} reviews`}
                bodyClassName="px-3 pt-2 pb-1"
                className="shadow-elev-1"
              >
                <ActivityChart days={res.data.stats.last_14_days} cap={cap} />
              </Panel>

              {/* Progress as a sky that fills in (Phosphor §6.2). Skin-
                  agnostic — tokens do the theming, so ember gets it too. */}
              {res.data.stats.by_topic.length > 0 && (
                <Panel
                  title="Constellation"
                  aside="practice × retention"
                  bodyClassName="px-1.5 py-1.5"
                  className="shadow-elev-1"
                >
                  <Constellation stats={res.data.stats} />
                </Panel>
              )}

              {res.data.stats.by_topic.some((t) => (t.reviewed ?? 0) > 0) && (
                <Panel
                  title="Reviewed today"
                  bodyClassName="px-3 py-2"
                  className="shadow-elev-1"
                >
                  <dl className="text-[12.5px]">
                    {res.data.stats.by_topic
                      .filter((t) => (t.reviewed ?? 0) > 0)
                      .map((t) => (
                        <div
                          key={t.code}
                          className="flex items-baseline justify-between py-[3px]"
                        >
                          <dt>
                            <TopicCode code={t.code} />
                          </dt>
                          <dd className="tnum text-fg-2">{t.reviewed}</dd>
                        </div>
                      ))}
                  </dl>
                </Panel>
              )}

              <Panel
                title="Collection"
                bodyClassName="px-3 py-2"
                className="shadow-elev-1"
              >
                <dl className="text-[12.5px]">
                  {[
                    ["Active cards", res.data.stats.totals.active],
                    ["Sources ingested", res.data.stats.totals.sources],
                  ].map(([label, value]) => (
                    <div
                      key={String(label)}
                      className="flex items-baseline justify-between py-[3px]"
                    >
                      <dt className="text-fg-2">{label}</dt>
                      <dd className="tnum">{Number(value).toLocaleString()}</dd>
                    </div>
                  ))}
                </dl>
                <div className="flex items-center gap-2 pt-2 mt-1.5 border-t border-line">
                  <KindTag kind="fsrs 4.5" />
                  <span className="text-[11px] text-fg-3">
                    retention target{" "}
                    <span className="tnum">
                      {Math.round(res.data.settings.desired_retention * 100)}%
                    </span>
                  </span>
                </div>
              </Panel>
            </Reveal>
          </div>
        </>
      )}
    </main>
  );
}
