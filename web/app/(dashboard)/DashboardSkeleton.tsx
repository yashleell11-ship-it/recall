"use client";

import { Skeleton } from "@/components/rich";

/**
 * The dashboard, before its data: the same strip, summary line, table and
 * side column, block for block, so nothing moves when the real thing lands.
 * Shimmer instead of a spinner; frozen to plain blocks under reduced motion.
 */
export function DashboardSkeleton() {
  return (
    <div aria-hidden="true">
      {/* Metric strip */}
      <div className="panel shadow-elev-1 overflow-hidden">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 -ml-px -mt-px">
          {Array.from({ length: 5 }, (_, i) => (
            <div
              key={i}
              className="border-l border-t border-line px-3.5 py-2.5"
            >
              <Skeleton className="h-[26px] w-14" />
              <Skeleton className="mt-1.5 h-[15px] w-20" />
              <Skeleton className="mt-0.5 h-4 w-24" />
              {/* The "New" cell carries a budget bar; reserve it. */}
              {i === 1 ? (
                <Skeleton className="mt-1.5 h-[3px] w-[72px] rounded-full" />
              ) : null}
            </div>
          ))}
        </div>
      </div>

      {/* Summary line */}
      <div className="mt-2 mb-4">
        <Skeleton className="h-[19px] w-[420px] max-w-full" />
      </div>

      {/* Topics and history */}
      <div className="grid gap-4 lg:grid-cols-[1fr_340px] items-start">
        <div className="panel shadow-elev-1 overflow-hidden">
          <div className="flex items-center justify-between px-3 h-9 border-b border-line bg-sunken">
            <Skeleton className="h-2.5 w-14" />
            <Skeleton className="h-2.5 w-12" />
          </div>
          <div className="flex items-center justify-between px-3 h-7 border-b border-line">
            <Skeleton className="h-2.5 w-10" />
            <div className="flex gap-6">
              <Skeleton className="h-2.5 w-7" />
              <Skeleton className="h-2.5 w-7" />
              <Skeleton className="h-2.5 w-9" />
            </div>
          </div>
          {Array.from({ length: 5 }, (_, i) => (
            <div
              key={i}
              className="flex items-center justify-between px-3 h-[35px] border-b border-line"
            >
              <Skeleton className="h-3 w-14" />
              <div className="flex gap-6">
                <Skeleton className="h-3 w-6" />
                <Skeleton className="h-3 w-6" />
                <Skeleton className="h-3 w-9" />
              </div>
            </div>
          ))}
          <div className="flex items-center justify-between px-3 h-[35px] bg-sunken">
            <Skeleton className="h-2.5 w-10" />
            <div className="flex gap-6">
              <Skeleton className="h-3 w-6" />
              <Skeleton className="h-3 w-6" />
              <Skeleton className="h-3 w-9" />
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <div className="panel shadow-elev-1 overflow-hidden">
            <div className="flex items-center justify-between px-3 h-9 border-b border-line bg-sunken">
              <Skeleton className="h-2.5 w-20" />
              <Skeleton className="h-2.5 w-16" />
            </div>
            <div className="px-3 pt-2 pb-1">
              <Skeleton className="w-full" style={{ height: 104 }} />
            </div>
          </div>

          <div className="panel shadow-elev-1 overflow-hidden">
            <div className="flex items-center px-3 h-9 border-b border-line bg-sunken">
              <Skeleton className="h-2.5 w-24" />
            </div>
            <div className="px-3 py-2">
              {Array.from({ length: 5 }, (_, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-[3px] h-[25px]"
                >
                  <Skeleton className="h-3 w-14" />
                  <Skeleton className="h-3 w-7" />
                </div>
              ))}
            </div>
          </div>

          <div className="panel shadow-elev-1 overflow-hidden">
            <div className="flex items-center px-3 h-9 border-b border-line bg-sunken">
              <Skeleton className="h-2.5 w-20" />
            </div>
            <div className="px-3 py-2">
              {Array.from({ length: 3 }, (_, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-[3px] h-[25px]"
                >
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-3 w-10" />
                </div>
              ))}
              <div className="flex items-center gap-2 pt-2 mt-1.5 border-t border-line">
                <Skeleton className="h-[17px] w-14" />
                <Skeleton className="h-3 w-28" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
