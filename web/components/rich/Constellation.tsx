"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { Stats } from "@/lib/types";

/**
 * Mastery Constellation (Phosphor spec §6.2) — progress as a sky that
 * fills in. Topics are stars, a ring around each star tracks a mastery
 * proxy, and edges tie the topics together. Plain SVG on design tokens, so
 * it is skin-agnostic: ion rings under Phosphor, ember rings under ember.
 *
 * DATA — computed ONLY from what GET /api/stats already returns. The
 * endpoint has no per-topic retention and no per-topic review days, so:
 *
 *   held      = 1 − today.again / today.reviewed
 *               … today's global retention proxy: the share of today's
 *               reviews that did NOT lapse (0 when nothing was reviewed).
 *   share_t   = by_topic[t].reviewed / max_u(by_topic[u].reviewed)
 *               … the topic's share of today's practice, normalised to the
 *               most-practised topic so the busiest star reads at the full
 *               held-rate and the others scale down from it.
 *   mastery_t = totals.active > 0 ? clamp01(held × share_t) : 0
 *
 * It cannot flatter: a lapse-heavy day dims every star, and a topic that
 * got no practice today shows an empty ring until it is practised.
 *
 * EDGES — the stats payload carries no per-topic co-practice days, so
 * (exactly as the spec's fallback allows) stars are linked in display
 * order rather than by shared review days. An edge brightens when both of
 * its endpoints were reviewed today — the one co-practice fact the
 * endpoint does prove.
 *
 * MOTION — rings animate once, on entry, by stroke-dashoffset behind an
 * IntersectionObserver. Reduced motion renders the final state outright.
 */

const H = 190;
const PAD_X = 36;
const SETTLE = "cubic-bezier(0.22, 0.9, 0.3, 1)";

/** Deterministic vertical scatter: a constellation, not a row. */
const ROW_Y = [64, 126];
const Y_JITTER = [0, 14, -10, 12, -16, 8, -6, 10];

/** Legibility ceiling; the spec defers clustering until a deck needs it. */
const MAX_STARS = 8;

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));

/** Measure rather than scale: text in a stretched viewBox goes illegible. */
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

export function Constellation({
  stats,
  className = "",
}: {
  stats: Stats;
  className?: string;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const reduced = useReducedMotion();
  /** Rings draw once, when the sky first scrolls into view. */
  const [lit, setLit] = useState(false);

  useEffect(() => {
    // Reduced motion never needs the observer: `drawn` below falls through
    // to the final state without any animation.
    if (reduced) return;
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      const raf = requestAnimationFrame(() => setLit(true));
      return () => cancelAnimationFrame(raf);
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setLit(true);
          io.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [reduced, ref]);

  /** Final state immediately under reduced motion; once-on-entry otherwise. */
  const drawn = reduced || lit;

  const topics = stats.by_topic.slice(0, MAX_STARS);
  const n = topics.length;
  if (n === 0) return null;

  const reviewedOf = (i: number) => Math.max(0, topics[i].reviewed ?? 0);
  const maxReviewed = topics.reduce((m, _, i) => Math.max(m, reviewedOf(i)), 0);
  const held =
    stats.today.reviewed > 0
      ? clamp01(1 - stats.today.again / stats.today.reviewed)
      : 0;
  const masteryOf = (i: number) =>
    stats.totals.active > 0 && maxReviewed > 0
      ? clamp01(held * (reviewedOf(i) / maxReviewed))
      : 0;

  const span = Math.max(0, width - PAD_X * 2);
  const step = n > 1 ? span / (n - 1) : 0;
  const r = Math.round(Math.min(20, Math.max(12, (n > 1 ? step : span) * 0.24)));
  const C = 2 * Math.PI * r;

  const stars = topics.map((t, i) => ({
    code: t.code,
    mastery: masteryOf(i),
    practised: reviewedOf(i) > 0,
    x: n > 1 ? PAD_X + i * step : width / 2,
    y: ROW_Y[i % 2] + Y_JITTER[i % Y_JITTER.length],
  }));

  const label = `Mastery constellation: ${stars
    .map((s) => `${s.code} ${Math.round(s.mastery * 100)}%`)
    .join(", ")}`;

  return (
    <div ref={ref} className={`w-full ${className}`} style={{ height: H }}>
      {width > 0 && (
        <svg width={width} height={H} role="img" aria-label={label} className="block">
          {/* edges first, so stars sit above them */}
          {stars.slice(0, -1).map((a, i) => {
            const b = stars[i + 1];
            return (
              <line
                key={`${a.code}-${b.code}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="var(--accent)"
                strokeOpacity={a.practised && b.practised ? 0.4 : 0.16}
                strokeWidth={1}
              />
            );
          })}

          {stars.map((s, i) => {
            const pct = Math.round(s.mastery * 100);
            const pctLeft = n > 1 && i === n - 1;
            return (
              <g key={s.code} transform={`translate(${s.x},${s.y})`}>
                {/* ring track */}
                <circle
                  r={r}
                  fill="none"
                  stroke="var(--line-strong)"
                  strokeOpacity={0.55}
                  strokeWidth={3}
                />
                {/* ring fill — stroke-dashoffset only: paint, never layout */}
                <circle
                  r={r}
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth={3}
                  strokeLinecap="round"
                  transform="rotate(-90)"
                  strokeDasharray={C}
                  strokeDashoffset={drawn ? C * (1 - s.mastery) : C}
                  style={
                    reduced
                      ? undefined
                      : {
                          transition: `stroke-dashoffset 1.1s ${SETTLE} ${i * 90}ms`,
                        }
                  }
                />
                {/* the star: brightness tracks mastery, dimmed, never out */}
                <circle
                  r={4.5}
                  fill="var(--accent)"
                  fillOpacity={0.3 + 0.7 * s.mastery}
                />
                <text
                  x={pctLeft ? -(r + 8) : r + 8}
                  y={3.5}
                  textAnchor={pctLeft ? "end" : "start"}
                  fontSize={10.5}
                  fontWeight={600}
                  fill="var(--fg)"
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {pct}%
                </text>
                <text
                  y={r + 15}
                  textAnchor="middle"
                  fontSize={9.5}
                  letterSpacing="0.08em"
                  fill="var(--fg-3)"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {s.code}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
