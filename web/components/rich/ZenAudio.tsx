"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Zen mode: a generative ambient drone, made entirely by the Web Audio API —
 * no audio files, zero bytes shipped.
 *
 * The sound is two detuned low oscillators (a sine root and a softened
 * triangle a few cents sharp, so they beat slowly against each other) under
 * a bed of white noise pushed through a lowpass whose cutoff breathes on a
 * very slow LFO. The master gain is held far below speech level (-18 LUFS-ish)
 * and every start/stop is an 800ms fade, so the drone arrives and leaves like
 * room tone, never like playback.
 *
 * Laws, from the Phosphor spec (§6.3):
 * - it NEVER autoplays — the graph is only ever built and resumed inside
 *   `setZen(true)`, which is only called from the user's toggle;
 * - the AudioContext is suspended after the fade-out, so an idle Zen costs
 *   nothing;
 * - the six-bar visualizer is the one continuous animation the design system
 *   permits, and it is hidden when Zen is off and frozen under
 *   prefers-reduced-motion.
 *
 * The store is module-level (same shape as lib/skin.ts) so the drone keeps
 * playing across client-side navigation; it deliberately does NOT persist to
 * localStorage — a page load always starts silent.
 */

const FADE_S = 0.8;
/** Master level. Sines this low at 0.045 sit around -18 LUFS integrated. */
const LEVEL = 0.045;

let zenOn = false;
const listeners = new Set<() => void>();

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let suspendTimer: ReturnType<typeof setTimeout> | null = null;

/** Build the drone once; afterwards start/stop only move gain + suspend. */
function buildGraph(ac: AudioContext): GainNode {
  const out = ac.createGain();
  out.gain.value = 0;
  out.connect(ac.destination);

  // Root: a low D, pure sine.
  const oscA = ac.createOscillator();
  oscA.type = "sine";
  oscA.frequency.value = 73.42; // D2
  const gainA = ac.createGain();
  gainA.gain.value = 0.5;
  oscA.connect(gainA);
  gainA.connect(out);

  // Its shadow: the same note as a triangle, 9 cents sharp — the detune is
  // what makes the drone feel alive, a beat every few seconds. The lowpass
  // files the triangle's edge off so it reads as warmth, not buzz.
  const oscB = ac.createOscillator();
  oscB.type = "triangle";
  oscB.frequency.value = 73.42;
  oscB.detune.value = 9;
  const softenB = ac.createBiquadFilter();
  softenB.type = "lowpass";
  softenB.frequency.value = 320;
  const gainB = ac.createGain();
  gainB.gain.value = 0.3;
  oscB.connect(softenB);
  softenB.connect(gainB);
  gainB.connect(out);

  // The noise bed: two seconds of white noise, looped, through a lowpass
  // whose cutoff swells on a ~20-second LFO. Distant surf, not hiss.
  const len = Math.floor(ac.sampleRate * 2);
  const buf = ac.createBuffer(1, len, ac.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
  const noise = ac.createBufferSource();
  noise.buffer = buf;
  noise.loop = true;
  const noiseFilter = ac.createBiquadFilter();
  noiseFilter.type = "lowpass";
  noiseFilter.frequency.value = 240;
  noiseFilter.Q.value = 0.6;
  const noiseGain = ac.createGain();
  noiseGain.gain.value = 0.12;
  noise.connect(noiseFilter);
  noiseFilter.connect(noiseGain);
  noiseGain.connect(out);

  const lfo = ac.createOscillator();
  lfo.type = "sine";
  lfo.frequency.value = 0.05;
  const lfoDepth = ac.createGain();
  lfoDepth.gain.value = 110;
  lfo.connect(lfoDepth);
  lfoDepth.connect(noiseFilter.frequency);

  oscA.start();
  oscB.start();
  noise.start();
  lfo.start();
  return out;
}

/** Only ever called from `setZen(true)` — i.e. from a user gesture. */
function startAudio(): void {
  if (typeof window === "undefined") return;
  try {
    if (!ctx) {
      ctx = new AudioContext();
      master = buildGraph(ctx);
    }
    if (suspendTimer) {
      clearTimeout(suspendTimer);
      suspendTimer = null;
    }
    void ctx.resume();
    const gain = master?.gain;
    if (!gain) return;
    const now = ctx.currentTime;
    gain.cancelScheduledValues(now);
    gain.setValueAtTime(gain.value, now);
    gain.linearRampToValueAtTime(LEVEL, now + FADE_S);
  } catch {
    // No Web Audio (or it refused) — the toggle still flips, silently.
  }
}

function stopAudio(): void {
  if (!ctx || !master) return;
  try {
    const now = ctx.currentTime;
    master.gain.cancelScheduledValues(now);
    master.gain.setValueAtTime(master.gain.value, now);
    master.gain.linearRampToValueAtTime(0, now + FADE_S);
    if (suspendTimer) clearTimeout(suspendTimer);
    // Suspend once the fade has landed: an off Zen holds no audio thread.
    suspendTimer = setTimeout(() => {
      suspendTimer = null;
      void ctx?.suspend();
    }, FADE_S * 1000 + 100);
  } catch {
    // ignore — worst case the context idles at zero gain
  }
}

export function getZen(): boolean {
  return zenOn;
}

export function setZen(next: boolean): void {
  if (next === zenOn) return;
  zenOn = next;
  if (next) startAudio();
  else stopAudio();
  for (const l of listeners) l();
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

function getServerSnapshot(): boolean {
  return false; // a page never renders with Zen already on
}

export function useZen() {
  const on = useSyncExternalStore(subscribe, getZen, getServerSnapshot);
  const toggle = useCallback(() => {
    setZen(!getZen());
  }, []);
  return { on, toggle, setZen };
}

/* --- visualizer ----------------------------------------------------------- */

const BAR_DELAYS = [0, 0.2, 0.4, 0.6, 0.8, 1.0];

/**
 * Six 3px synapse-tinted bars — the design system's single sanctioned loop.
 * Animates transform only (law №5); hidden entirely while Zen is off;
 * frozen to a designed resting state under prefers-reduced-motion.
 */
const ZENBAR_CSS = `
.zenbar {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 22px;
  padding: 0 2px;
}
.zenbar i {
  width: 3px;
  height: 22px;
  border-radius: 2px;
  background: var(--ai);
  opacity: 0.7;
  transform: scaleY(0.26);
  transform-origin: center;
  animation: zen-swell 1.6s ease-in-out infinite;
}
@keyframes zen-swell {
  0%, 100% { transform: scaleY(0.26); }
  50% { transform: scaleY(0.88); }
}
@media (prefers-reduced-motion: reduce) {
  .zenbar i {
    animation: none;
    transform: scaleY(0.45);
  }
}
`;

export function ZenVisualizer({ className = "" }: { className?: string }) {
  const { on } = useZen();
  if (!on) return null;
  return (
    <span className={`zenbar ${className}`} aria-hidden="true">
      <style>{ZENBAR_CSS}</style>
      {BAR_DELAYS.map((d) => (
        <i key={d} style={{ animationDelay: `${d}s` }} />
      ))}
    </span>
  );
}
