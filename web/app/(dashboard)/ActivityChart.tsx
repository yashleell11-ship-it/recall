"use client";

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import {
  isWeekend,
  shortDate,
  weekdayInitial,
  weekdayShort,
} from "@/lib/format";
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
 * Fourteen days of review counts. Hand-drawn SVG: bars that spring up from
 * the baseline on mount, a dashed line where the daily cap sits, and a
 * floating label pinned to the top band that follows the pointer with the
 * exact count. Today's bar is the one thing in the chart allowed the ember.
 *
 * Bars animate scaleY from their own bottom edge — transform only, staggered
 * 30ms apart, snapped into place under reduced motion.
 */
export function ActivityChart({
  days,
  cap,
}: {
  days: StatsDay[];
  cap?: number | null;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const reduced = useReducedMotion();
  const [hover, setHover] = useState<number | null>(null);

  const counts = days.map((d) => d.count);
  const peak = Math.max(1, ...counts, cap ?? 0);
  const scaleMax = peak * 1.14;
  const plotH = H - PAD_T - PAD_B;
  const n = days.length || 1;
  const barW = width > 0 ? Math.max(2, (width - GAP * (n - 1)) / n) : 0;
  const capY =
    cap && cap > 0 ? PAD_T + plotH - (cap / scaleMax) * plotH : null;

  const todayIndex = days.length - 1;
  const hovered = hover !== null ? days[hover] : null;

  return (
    <div ref={ref} className="w-full" style={{ height: H }}>
      {width > 0 && (
        <svg
          width={width}
          height={H}
          role="img"
          aria-label={`Reviews completed over the last ${n} days`}
          className="block"
          onMouseLeave={() => setHover(null)}
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
              {hover === null && (
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
              )}
            </>
          )}

          {days.map((d, i) => {
            const x = i * (barW + GAP);
            const isToday = i === todayIndex;
            const h = (d.count / scaleMax) * plotH;
            const y = PAD_T + plotH - h;
            return (
              <g key={d.date}>
                {d.count === 0 ? (
                  <rect
                    x={x}
                    y={PAD_T + plotH - 1}
                    width={barW}
                    height={1}
                    fill="var(--line-strong)"
                  />
                ) : (
                  <motion.rect
                    x={x}
                    y={y}
                    width={barW}
                    height={Math.max(1, h)}
                    rx={1}
                    fill={
                      isToday
                        ? "var(--accent)"
                        : hover === i
                          ? "var(--fg-2)"
                          : "var(--fg-3)"
                    }
                    style={
                      isToday
                        ? {
                            originY: 1,
                            filter:
                              "drop-shadow(0 1px 5px var(--accent-glow))",
                          }
                        : { originY: 1 }
                    }
                    initial={reduced ? false : { scaleY: 0 }}
                    animate={{ scaleY: 1 }}
                    transition={
                      reduced
                        ? { duration: 0 }
                        : {
                            type: "spring",
                            stiffness: 320,
                            damping: 30,
                            mass: 0.8,
                            delay: i * 0.03,
                          }
                    }
                  />
                )}
                {isToday && d.count > 0 && hover !== i && (
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
                {/* Full-height hit area, last so it sits above the bar. */}
                <rect
                  x={x}
                  y={PAD_T}
                  width={barW + (i < n - 1 ? GAP : 0)}
                  height={plotH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                />
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

          {hovered &&
            hover !== null &&
            (() => {
              const label = `${weekdayShort(hovered.date)} ${shortDate(
                hovered.date,
              )} · ${hovered.count}`;
              const w = label.length * 5.4 + 14;
              const cx = hover * (barW + GAP) + barW / 2;
              const px = Math.min(Math.max(cx - w / 2, 1), width - w - 1);
              return (
                <g pointerEvents="none">
                  <rect
                    x={px}
                    y={0.5}
                    width={w}
                    height={15}
                    rx={3}
                    fill="var(--surface-overlay)"
                    stroke="var(--line-strong)"
                    strokeWidth={1}
                  />
                  <text
                    x={px + w / 2}
                    y={11}
                    textAnchor="middle"
                    fontSize={9}
                    fontWeight={600}
                    fill="var(--fg)"
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {label}
                  </text>
                </g>
              );
            })()}
        </svg>
      )}
    </div>
  );
}
