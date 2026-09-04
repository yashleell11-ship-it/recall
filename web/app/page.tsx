"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo } from "react";
import { ReviewChart } from "@/components/ReviewChart";
import {
  EmptyState,
  ErrorState,
  KindTag,
  Loading,
  Metric,
  Panel,
  TopicCode,
} from "@/components/ui";
import { getSettings, getStats, getTopics } from "@/lib/api";
import { longDate, plural } from "@/lib/format";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import { useResource } from "@/lib/useResource";

export default function DashboardPage() {
  const router = useRouter();

  const fetchDashboard = useCallback(async () => {
    const [topics, stats, settings] = await Promise.all([
      getTopics(),
      getStats(),
      getSettings(),
    ]);
    return { topics, stats, settings };
  }, []);

  const res = useResource("dashboard", fetchDashboard);

  const totals = useMemo(() => {
    const t = res.data?.topics ?? [];
    return {
      due: t.reduce((n, x) => n + x.due, 0),
      new: t.reduce((n, x) => n + x.new, 0),
      active: t.reduce((n, x) => n + x.active, 0),
      pending: t.reduce((n, x) => n + x.pending, 0),
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

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e) || hasModifier(e)) return;
      if (e.key === "Enter" && willFit > 0) {
        e.preventDefault();
        router.push("/review");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, willFit]);

  return (
    <main className="mx-auto max-w-[1120px] px-4 py-5">
      <div className="flex items-end justify-between gap-4 mb-3.5">
        <div>
          <h1 className="text-[18px] font-semibold leading-none">Today</h1>
          <p className="text-[13px] text-fg-2 mt-1.5 min-h-[1.25rem]">
            {statsDate ? longDate(statsDate) : ""}
          </p>
        </div>

        {willFit > 0 ? (
          <Link
            href="/review"
            className="inline-flex items-center gap-2.5 h-9 px-4 rounded-sm text-[13px] font-semibold
              bg-accent text-accent-fg border border-accent hover:bg-accent-hover
              hover:border-accent-hover transition-colors duration-[90ms]"
          >
            Start review
            <span className="tnum opacity-70">{willFit}</span>
            <span className="opacity-55 text-[12px] leading-none">&crarr;</span>
          </Link>
        ) : (
          <span className="text-[13px] text-fg-3 h-9 flex items-center">
            {res.loading ? "" : "Nothing to review"}
          </span>
        )}
      </div>

      {res.error && !res.data ? (
        <ErrorState message={res.error} onRetry={res.reload} />
      ) : null}

      {res.loading && !res.data ? (
        <div className="panel">
          <Loading label="Reading today's load" />
        </div>
      ) : null}

      {res.data && (
        <>
          {/* --- the day in one strip ------------------------------------ */}
          <div className="panel overflow-hidden">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 -ml-px -mt-px">
              {[
                {
                  value: totals.due,
                  label: "Due",
                  note: "scheduled for today",
                  emphasis: true,
                },
                {
                  value: totals.new,
                  label: "New",
                  note: `limit ${res.data.settings.new_cards_per_day}/day`,
                  emphasis: true,
                },
                {
                  value: reviewed,
                  label: "Reviewed today",
                  note: cap === null ? undefined : `of ${cap} allowed`,
                },
                {
                  value: res.data.stats.today.again,
                  label: "Again today",
                  note:
                    reviewed > 0
                      ? `${Math.round(
                          (1 - res.data.stats.today.again / reviewed) * 100,
                        )}% held`
                      : undefined,
                },
                {
                  value: res.data.stats.today.streak,
                  label: "Day streak",
                  note: `${res.data.stats.totals.active.toLocaleString()} cards in rotation`,
                },
              ].map((m) => (
                <div key={m.label} className="border-l border-t border-line">
                  <Metric
                    value={m.value.toLocaleString()}
                    label={m.label}
                    note={m.note}
                    emphasis={m.emphasis}
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 mt-2 mb-4 text-[12.5px]">
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

            {totals.pending > 0 && (
              <Link href="/approve" className="link text-fg-2 hover:text-fg">
                {totals.pending} generated {plural(totals.pending, "card")}{" "}
                waiting for triage
              </Link>
            )}
          </div>

          {/* --- topics and history -------------------------------------- */}
          <div className="grid gap-4 lg:grid-cols-[1fr_340px] items-start">
            <Panel
              title="By topic"
              aside={`${res.data.topics.length} topics`}
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
                      <th className="label text-right font-semibold px-3 py-1.5 w-16">
                        Pending
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {res.data.topics.map((t) => (
                      <tr
                        key={t.id}
                        onClick={() => router.push(`/review?topic=${t.code}`)}
                        className="border-b border-line last:border-b-0 cursor-pointer hover:bg-surface-hover transition-colors duration-[90ms]"
                      >
                        <td className="px-3 py-[7px]">
                          <Link
                            href={`/review?topic=${t.code}`}
                            onClick={(e) => e.stopPropagation()}
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
                        <td
                          className={`px-3 py-[7px] text-right tnum ${
                            t.pending > 0 ? "text-fg-2" : "text-fg-3"
                          }`}
                        >
                          {t.pending || "—"}
                        </td>
                      </tr>
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
                      <td className="px-3 py-[7px] text-right tnum font-semibold">
                        {totals.pending}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              )}
            </Panel>

            <div className="grid gap-4">
              <Panel
                title="Last 14 days"
                aside={`${res.data.stats.last_14_days
                  .reduce((n, d) => n + d.count, 0)
                  .toLocaleString()} reviews`}
                bodyClassName="px-3 pt-2 pb-1"
              >
                <ReviewChart days={res.data.stats.last_14_days} cap={cap} />
              </Panel>

              {res.data.stats.by_topic.some((t) => (t.reviewed ?? 0) > 0) && (
                <Panel title="Reviewed today" bodyClassName="px-3 py-2">
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

              <Panel title="Collection" bodyClassName="px-3 py-2">
                <dl className="text-[12.5px]">
                  {[
                    ["Active cards", res.data.stats.totals.active],
                    ["Pending triage", res.data.stats.totals.pending],
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
            </div>
          </div>
        </>
      )}
    </main>
  );
}
