"use client";

import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Reveal, Skeleton } from "@/components/rich";
import { ErrorState, TopicCode } from "@/components/ui";
import { getSources } from "@/lib/api";
import { daysAgo, mediumDate, percent, plural, usd } from "@/lib/format";
import type { Source } from "@/lib/types";
import { useResource } from "@/lib/useResource";

type Key = "filename" | "topic_code" | "added_at" | "accepted" | "rejected" | "rate" | "cost_estimate";

const COLUMNS: {
  key: Key;
  label: string;
  numeric?: boolean;
  hideSm?: boolean;
  width?: string;
}[] = [
  { key: "filename", label: "File" },
  { key: "topic_code", label: "Topic", width: "w-[86px]" },
  { key: "added_at", label: "Added", hideSm: true, width: "w-[112px]" },
  { key: "accepted", label: "Accepted", numeric: true, width: "w-[92px]" },
  { key: "rejected", label: "Rejected", numeric: true, width: "w-[92px]" },
  { key: "rate", label: "Kept", numeric: true, hideSm: true, width: "w-[104px]" },
  { key: "cost_estimate", label: "Cost", numeric: true, width: "w-[88px]" },
];

const rate = (s: Source) =>
  s.accepted + s.rejected === 0 ? 0 : s.accepted / (s.accepted + s.rejected);

/** Entrance for rows on first load; re-sorts ride the layout spring instead. */
const ROW_SPRING = {
  type: "spring",
  stiffness: 420,
  damping: 34,
  mass: 0.9,
} as const;

/** Rows changing places when a column header is clicked. Transform only. */
const SORT_SPRING = {
  type: "spring",
  stiffness: 420,
  damping: 40,
  mass: 0.9,
} as const;

/** Deterministic ragged filename widths for the loading table. */
const SKELETON_WIDTHS = ["62%", "48%", "55%", "67%", "44%"];

export default function SourcesPage() {
  const res = useResource("sources", getSources);
  const reduced = useReducedMotion();
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({
    key: "added_at",
    dir: -1,
  });

  const rows = useMemo(() => {
    const list = [...(res.data ?? [])];
    const { key, dir } = sort;
    list.sort((a, b) => {
      let av: string | number;
      let bv: string | number;
      if (key === "rate") {
        av = rate(a);
        bv = rate(b);
      } else {
        av = a[key];
        bv = b[key];
      }
      if (typeof av === "string" && typeof bv === "string") {
        return av.localeCompare(bv) * dir;
      }
      return ((av as number) - (bv as number)) * dir;
    });
    return list;
  }, [res.data, sort]);

  const totals = useMemo(() => {
    const list = res.data ?? [];
    return {
      accepted: list.reduce((n, s) => n + s.accepted, 0),
      rejected: list.reduce((n, s) => n + s.rejected, 0),
      cost: list.reduce((n, s) => n + s.cost_estimate, 0),
    };
  }, [res.data]);

  function toggle(key: Key) {
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === 1 ? -1 : 1 }
        : { key, dir: key === "filename" || key === "topic_code" ? 1 : -1 },
    );
  }

  return (
    <main className="mx-auto max-w-[1120px] px-4 py-5">
      <div className="mb-4">
        <h1 className="text-[18px] font-semibold leading-none">Sources</h1>
        <p className="text-[13px] text-fg-2 mt-1.5">
          {res.data
            ? res.data.length === 0
              ? "Nothing ingested yet."
              : `${res.data.length} ${plural(res.data.length, "file")} · ${(
                  totals.accepted + totals.rejected
                ).toLocaleString()} cards generated · ${usd(totals.cost)} spent on generation.`
            : " "}
        </p>
      </div>

      {res.error && !res.data ? (
        <ErrorState message={res.error} onRetry={res.reload} />
      ) : null}

      {res.loading && !res.data ? (
        /* The table's own shape in shimmer: header, five rows, totals. */
        <div
          className="panel overflow-hidden"
          aria-busy="true"
          aria-label="Loading sources"
        >
          <div className="flex items-center gap-6 border-b border-line px-3 h-[28px]">
            <Skeleton className="h-2.5 w-12 flex-1 max-w-[120px]" />
            <Skeleton className="h-2.5 w-10 hidden md:block" />
            <Skeleton className="h-2.5 w-14" />
            <Skeleton className="h-2.5 w-14" />
            <Skeleton className="h-2.5 w-10 hidden md:block" />
            <Skeleton className="h-2.5 w-10" />
          </div>
          {SKELETON_WIDTHS.map((w, i) => (
            <div
              key={i}
              className="flex items-center gap-6 border-b border-line px-3 h-[34px]"
            >
              <Skeleton className="h-3 flex-1" style={{ maxWidth: w }} />
              <Skeleton className="h-3 w-12 hidden md:block" />
              <Skeleton className="h-3 w-10" />
              <Skeleton className="h-3 w-10" />
              <Skeleton className="h-3 w-16 hidden md:block" />
              <Skeleton className="h-3 w-12" />
            </div>
          ))}
          <div className="flex items-center gap-6 bg-sunken px-3 h-[34px]">
            <Skeleton className="h-2.5 w-12 flex-1 max-w-[64px]" />
            <Skeleton className="h-3 w-10" />
            <Skeleton className="h-3 w-10" />
            <Skeleton className="h-3 w-12" />
          </div>
        </div>
      ) : null}

      {res.data &&
        (res.data.length === 0 ? (
          <div className="panel px-3 py-8 max-w-prose">
            <p className="text-[13px] text-fg-2">
              Nothing has been ingested yet. Add a PDF or a set of notes and it
              shows up here with the cards it produced and what the generation
              cost.
            </p>
            <div className="mt-3 text-[13px]">
              <Link href="/" className="link">
                Back to today
              </Link>
            </div>
          </div>
        ) : (
          <Reveal>
            <div className="panel overflow-x-auto shadow-elev-1">
              <table className="w-full table-fixed text-[13px] min-w-[580px]">
                <thead>
                  <tr className="border-b border-line">
                    {COLUMNS.map((c) => (
                      <th
                        key={c.key}
                        aria-sort={
                          sort.key === c.key
                            ? sort.dir === 1
                              ? "ascending"
                              : "descending"
                            : "none"
                        }
                        className={`px-3 py-1.5 font-semibold ${
                          c.numeric ? "text-right" : "text-left"
                        } ${c.hideSm ? "hidden md:table-cell" : ""} ${
                          c.width ?? ""
                        }`}
                      >
                        <button
                          onClick={() => toggle(c.key)}
                          className="label hover:text-fg-2 transition-colors duration-[90ms]"
                        >
                          {c.label}
                          <span className="ml-1 inline-block w-1.5">
                            {sort.key === c.key ? (sort.dir === 1 ? "↑" : "↓") : ""}
                          </span>
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s, i) => {
                    const days = daysAgo(s.added_at);
                    const kept = rate(s);
                    return (
                      <motion.tr
                        key={s.id}
                        layout="position"
                        initial={reduced ? false : { opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{
                          layout: reduced ? { duration: 0 } : SORT_SPRING,
                          opacity: {
                            ...ROW_SPRING,
                            delay: 0.06 + Math.min(i, 6) * 0.04,
                          },
                          y: {
                            ...ROW_SPRING,
                            delay: 0.06 + Math.min(i, 6) * 0.04,
                          },
                        }}
                        className="border-b border-line last:border-b-0 hover:bg-surface-hover transition-colors duration-[90ms]"
                      >
                        <td className="px-3 py-[7px] truncate">
                          <span title={s.filename}>{s.filename}</span>
                          <span className="md:hidden text-fg-3 ml-2 text-[11px] tnum">
                            {days}d
                          </span>
                        </td>
                        <td className="px-3 py-[7px]">
                          <TopicCode code={s.topic_code} />
                        </td>
                        <td className="px-3 py-[7px] text-fg-2 hidden md:table-cell whitespace-nowrap">
                          <span title={`${days} ${plural(days, "day")} ago`}>
                            {mediumDate(s.added_at)}
                          </span>
                        </td>
                        <td className="px-3 py-[7px] text-right tnum">
                          {s.accepted.toLocaleString()}
                        </td>
                        <td className="px-3 py-[7px] text-right tnum text-fg-2">
                          {s.rejected.toLocaleString()}
                        </td>
                        <td className="px-3 py-[7px] hidden md:table-cell">
                          <span className="flex items-center justify-end gap-1.5">
                            <span
                              className="block h-[3px] w-10 rounded-full bg-sunken overflow-hidden"
                              aria-hidden="true"
                            >
                              <motion.span
                                className="block h-full w-full origin-left rounded-full"
                                style={{ background: "var(--accent)" }}
                                initial={reduced ? false : { scaleX: 0 }}
                                animate={{ scaleX: kept }}
                                transition={
                                  reduced
                                    ? { duration: 0 }
                                    : {
                                        type: "spring",
                                        duration: 0.9,
                                        bounce: 0,
                                        delay: 0.2 + Math.min(i, 6) * 0.04,
                                      }
                                }
                              />
                            </span>
                            <span
                              className={`tnum min-w-[34px] text-right ${
                                kept < 0.6 ? "text-fg" : "text-fg-2"
                              }`}
                            >
                              {percent(kept)}
                            </span>
                          </span>
                        </td>
                        <td className="px-3 py-[7px] text-right tnum text-fg-2">
                          {usd(s.cost_estimate)}
                        </td>
                      </motion.tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t border-line-strong bg-sunken">
                    <td className="px-3 py-[7px] label">
                      {res.data.length} {plural(res.data.length, "file")}
                    </td>
                    <td />
                    <td className="hidden md:table-cell" />
                    <td className="px-3 py-[7px] text-right tnum font-semibold">
                      {totals.accepted.toLocaleString()}
                    </td>
                    <td className="px-3 py-[7px] text-right tnum font-semibold">
                      {totals.rejected.toLocaleString()}
                    </td>
                    <td className="px-3 py-[7px] text-right tnum font-semibold hidden md:table-cell">
                      {percent(
                        totals.accepted + totals.rejected === 0
                          ? 0
                          : totals.accepted / (totals.accepted + totals.rejected),
                      )}
                    </td>
                    <td className="px-3 py-[7px] text-right tnum font-semibold">
                      {usd(totals.cost)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Reveal>
        ))}

      {res.data && res.data.length > 0 && (
        <p className="text-[12px] text-fg-3 mt-3 leading-relaxed max-w-prose">
          Cost is an estimate from the recorded token counts and the configured
          price per million tokens. A low keep rate usually means the source was
          prose rather than notes, not that generation failed.
        </p>
      )}
    </main>
  );
}
