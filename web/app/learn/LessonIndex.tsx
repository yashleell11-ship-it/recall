"use client";

import Link from "next/link";
import { Reveal, Skeleton } from "@/components/rich";
import { EmptyState, ErrorState, Panel, TopicCode } from "@/components/ui";
import { getLessonIndex } from "@/lib/api";
import { mediumDate } from "@/lib/format";
import type { LessonIndexEntry, LessonIndexUnit } from "@/lib/types";
import { useResource } from "@/lib/useResource";
import { CommandBlock } from "./CommandBlock";
import { StatusChip } from "./Warranty";

/**
 * Which syllabus units have a written lesson, and which do not.
 *
 * The unwritten ones are listed too. "MTH165 unit 4 has nothing" is
 * information a student wants, and hiding it would make a half-written
 * subject look finished.
 */

function UnitRow({ code, unit }: { code: string; unit: LessonIndexUnit }) {
  const n = String(unit.number).padStart(2, "0");

  if (!unit.lesson) {
    // Inert on purpose: there is nothing to open, and nothing here offers to
    // spend money writing one.
    return (
      <li className="border-b border-line last:border-b-0">
        <div className="flex items-center gap-2 px-3 py-2">
          <span className="telemetry text-[10px] text-fg-3 w-4 shrink-0">
            {n}
          </span>
          <span className="text-[13px] leading-snug text-fg-3 flex-1">
            {unit.name}
          </span>
          <span className="telemetry text-[10.5px] text-fg-3 shrink-0">
            not written
          </span>
        </div>
      </li>
    );
  }

  return (
    <li className="border-b border-line last:border-b-0">
      <Link
        href={`/learn/${encodeURIComponent(code)}/${unit.number}`}
        className="flex items-center gap-2 px-3 py-2 hover:bg-surface-hover transition-colors duration-[90ms]"
      >
        <span className="telemetry text-[10px] text-fg-3 w-4 shrink-0">{n}</span>
        <span className="text-[13px] leading-snug text-fg flex-1">
          {unit.name}
        </span>
        <StatusChip status={unit.lesson.status} />
        <span className="telemetry text-[10.5px] text-fg-3 shrink-0 hidden sm:inline">
          {mediumDate(unit.lesson.created_at)}
        </span>
      </Link>
    </li>
  );
}

function SubjectPanel({ entry, index }: { entry: LessonIndexEntry; index: number }) {
  return (
    <Reveal index={index} className="h-full">
      <Panel
        className="h-full"
        title={<TopicCode code={entry.topic_code} />}
        aside={`${entry.written}/${entry.units.length} written`}
      >
        <ol>
          {entry.units.map((u) => (
            <UnitRow key={u.number} code={entry.topic_code} unit={u} />
          ))}
        </ol>
      </Panel>
    </Reveal>
  );
}

/** The grid's own shape in shimmer, so nothing reflows when the data lands. */
function IndexSkeleton() {
  return (
    <div
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
      aria-busy="true"
      aria-label="Loading lessons"
    >
      {[0, 1, 2].map((p) => (
        <div key={p} className="panel overflow-hidden">
          <div className="flex items-center justify-between px-3 h-9 border-b border-line bg-sunken">
            <Skeleton className="h-2.5 w-14" />
            <Skeleton className="h-2.5 w-16" />
          </div>
          {[0, 1, 2, 3, 4, 5].map((r) => (
            <div
              key={r}
              className="flex items-center gap-2 px-3 h-[34px] border-b border-line last:border-b-0"
            >
              <Skeleton className="h-4 w-3 shrink-0" />
              <Skeleton className="h-4 flex-1" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function LessonIndex() {
  const res = useResource("learn", getLessonIndex);
  const entries = res.data;
  const nothingWritten =
    entries !== null && entries.every((e) => e.written === 0);

  return (
    <main className="mx-auto max-w-[1120px] px-4 py-5">
      <div className="mb-4">
        <h1 className="text-[18px] font-semibold leading-none">Learn</h1>
        <p className="text-[13px] text-fg-2 mt-1.5">
          Written lessons for your syllabus units. Reading one costs nothing.
        </p>
      </div>

      {res.error && !entries ? (
        <ErrorState message={res.error} onRetry={res.reload} />
      ) : null}

      {res.loading && !entries ? <IndexSkeleton /> : null}

      {entries && nothingWritten ? (
        <div className="panel max-w-prose">
          <EmptyState>
            No lessons have been written yet. They are written offline, on the
            server, because each one costs money and takes a minute or two.
          </EmptyState>
          <div className="px-3 pb-4 -mt-3">
            <CommandBlock
              command={`recall lessons ${entries[0]?.topic_code ?? "MTH165"} --unit 1`}
            />
          </div>
        </div>
      ) : null}

      {entries && !nothingWritten ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {entries.map((e, i) => (
            <SubjectPanel key={e.topic_code} entry={e} index={i} />
          ))}
        </div>
      ) : null}

      {entries && entries.length > 0 && !nothingWritten ? (
        <p className="text-[12px] text-fg-3 mt-3 leading-relaxed max-w-prose">
          A lesson marked <span className="text-fg-2">grounded</span> quotes
          your uploaded course material word for word, checked in Python. One
          marked <span className="text-fg-2">unverified</span> was written and
          structurally checked but anchored to nothing — it is mostly the
          model&rsquo;s own knowledge. Units with nothing written are listed so
          you can see the gaps.
        </p>
      ) : null}
    </main>
  );
}
