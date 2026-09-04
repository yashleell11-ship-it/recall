"use client";

import { useEffect, useRef, useState } from "react";
import { isWeekend, weekdayInitial, weekdayShort, shortDate } from "@/lib/format";
import type { StatsDay } from "@/lib/types";

const H = 104;
const PAD_T = 16;
const PAD_B = 16;
const GAP = 3;

/** Measure rather than scale: text in a stretched viewBox goes illegible on a phone. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      setWidth(Math.round(w));
    });
    ro.observe(el);
    setWidth(Math.round(el.getBoundingClientRect().width));
    return () => ro.disconnect();
  }, []);
  return { ref, width };
}

/**
 * Fourteen days of review counts. Hand-drawn SVG: bars, a baseline, and a
 * dashed line where the daily cap sits, which is the only comparison that
 * actually matters when you are deciding whether today is going to fit.
 */
export function ReviewChart({
  days,
  cap,
}: {
  days: StatsDay[];
  cap?: number | null;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();

  const counts = days.map((d) => d.count);
  const peak = Math.max(1, ...counts, cap ?? 0);
  const scaleMax = peak * 1.14;
  const plotH = H - PAD_T - PAD_B;
  const n = days.length || 1;
  const barW = width > 0 ? Math.max(2, (width - GAP * (n - 1)) / n) : 0;
  const capY =
    cap && cap > 0 ? PAD_T + plotH - (cap / scaleMax) * plotH : null;

  const todayIndex = days.length - 1;

  return (
    <div ref={ref} className="w-full" style={{ height: H }}>
      {width > 0 && (
        <svg
          width={width}
          height={H}
          role="img"
          aria-label={`Reviews completed over the last ${n} days`}
          className="block"
        >
          {capY !== null && capY > PAD_T - 2 && (
            <>
              <line
                x1={0}
                x2={width}
                y1={capY}
                y2={capY}
                stroke="var(--line-strong)"
                strokeWidth={1}
                strokeDasharray="2 3"
              />
              <text
                x={width}
                y={capY - 4}
                textAnchor="end"
                fontSize={9}
                fill="var(--fg-3)"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                cap {cap}
              </text>
            </>
          )}

          {days.map((d, i) => {
            const x = i * (barW + GAP);
            const isToday = i === todayIndex;
            const h = (d.count / scaleMax) * plotH;
            const y = PAD_T + plotH - h;
            return (
              <g key={d.date} className="group">
                <title>{`${weekdayShort(d.date)} ${shortDate(d.date)} — ${d.count} reviewed`}</title>
                {/* Full-height hit area so the tooltip works on short bars. */}
                <rect
                  x={x}
                  y={PAD_T}
                  width={barW}
                  height={plotH}
                  fill="transparent"
                />
                {d.count === 0 ? (
                  <rect
                    x={x}
                    y={PAD_T + plotH - 1}
                    width={barW}
                    height={1}
                    fill="var(--line-strong)"
                  />
                ) : (
                  <rect
                    x={x}
                    y={y}
                    width={barW}
                    height={Math.max(1, h)}
                    fill={isToday ? "var(--fg)" : "var(--fg-3)"}
                    rx={1}
                  />
                )}
                {isToday && d.count > 0 && (
                  <text
                    x={x + barW / 2}
                    y={y - 4}
                    textAnchor="middle"
                    fontSize={10}
                    fontWeight={600}
                    fill="var(--fg)"
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {d.count}
                  </text>
                )}
                <text
                  x={x + barW / 2}
                  y={H - 4}
                  textAnchor="middle"
                  fontSize={9}
                  fontWeight={isToday ? 700 : 400}
                  fill={
                    isToday
                      ? "var(--fg)"
                      : isWeekend(d.date)
                        ? "var(--line-strong)"
                        : "var(--fg-3)"
                  }
                >
                  {weekdayInitial(d.date)}
                </text>
              </g>
            );
          })}

          <line
            x1={0}
            x2={width}
            y1={PAD_T + plotH + 0.5}
            y2={PAD_T + plotH + 0.5}
            stroke="var(--line-strong)"
            strokeWidth={1}
          />
        </svg>
      )}
    </div>
  );
}
