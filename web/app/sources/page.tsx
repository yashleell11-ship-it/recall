"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
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
  { key: "rate", label: "Kept", numeric: true, hideSm: true, width: "w-[72px]" },
  { key: "cost_estimate", label: "Cost", numeric: true, width: "w-[88px]" },
];

const rate = (s: Source) =>
  s.accepted + s.rejected === 0 ? 0 : s.accepted / (s.accepted + s.rejected);

export default function SourcesPage() {
  const res = useResource("sources", getSources);
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
            : " "}
        </p>
      </div>

      {res.error && !res.data ? (
        <ErrorState message={res.error} onRetry={res.reload} />
      ) : null}

      {res.loading && !res.data ? (
        <div className="panel px-3 py-6 text-[13px] text-fg-3">
          Loading sources&hellip;
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
          <div className="panel overflow-x-auto">
            <table className="w-full table-fixed text-[13px] min-w-[560px]">
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
                {rows.map((s) => {
                  const days = daysAgo(s.added_at);
                  return (
                    <tr
                      key={s.id}
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
                      <td
                        className={`px-3 py-[7px] text-right tnum hidden md:table-cell ${
                          rate(s) < 0.6 ? "text-fg" : "text-fg-2"
                        }`}
                      >
                        {percent(rate(s))}
                      </td>
                      <td className="px-3 py-[7px] text-right tnum text-fg-2">
                        {usd(s.cost_estimate)}
                      </td>
                    </tr>
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
