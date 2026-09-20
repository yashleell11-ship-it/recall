"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useCallback, useMemo, useState } from "react";
import { Reveal, Skeleton } from "@/components/rich";
import { EmptyState, ErrorState, Panel, TopicCode } from "@/components/ui";
import {
  abandonMcqAttempt,
  createMcqAttempt,
  errorMessage,
  getMcqAttempts,
  getMcqLeaderboard,
  getMcqSubjects,
} from "@/lib/api";
import { formatDuration, mediumDate, plural } from "@/lib/format";
import type { McqAttemptSummary, McqLength, McqSubject } from "@/lib/types";
import { useResource } from "@/lib/useResource";

const LENGTH_LABEL: Record<string, string> = {
  "30": "30",
  "60": "60",
  full: "Full",
};

function lengthLabel(length: McqLength): string {
  return LENGTH_LABEL[String(length)] ?? String(length);
}

function unitList(units: number[]): string {
  if (units.length === 0) return "no units";
  return `${plural(units.length, "unit")} ${units.join(", ")}`;
}

/* --- chips ---------------------------------------------------------------- */

/**
 * One selectable chip. A chip that cannot be chosen says why on its own line
 * rather than vanishing: a unit with no questions yet is waiting for
 * material, not missing from the course.
 */
function Chip({
  active,
  disabled,
  onClick,
  title,
  note,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  title: string;
  note?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.button
      type="button"
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      whileTap={reduced || disabled ? undefined : { scale: 0.98 }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      className={`text-left px-3 py-2 rounded-sm border text-[13px] min-h-[44px]
        transition-[border-color,background-color] duration-[90ms]
        disabled:opacity-45 disabled:pointer-events-none
        ${
          active
            ? "bg-surface-raised border-accent text-fg"
            : "bg-surface border-line text-fg-2 hover:border-line-strong hover:bg-surface-hover"
        }`}
    >
      <span className={`block ${active ? "font-semibold" : "font-medium"}`}>
        {title}
      </span>
      {note ? (
        <span className="telemetry block text-[11px] text-fg-3 mt-0.5">
          {note}
        </span>
      ) : null}
    </motion.button>
  );
}

/* --- one row of history --------------------------------------------------- */

/**
 * A sitting you already have: resume it, review it, or drop it.
 *
 * A submitted attempt links to its own result screen, which is the review
 * sheet — every question missed, with the teaching note and why the option
 * picked was wrong. Without the link that sheet is reachable exactly once,
 * in the seconds after finishing, and the whole point of the mode is that
 * you go back to it.
 */
function AttemptRow({
  attempt,
  onDropped,
}: {
  attempt: McqAttemptSummary;
  onDropped: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = attempt.submitted_at === null;

  const drop = useCallback(() => {
    setBusy(true);
    setError(null);
    abandonMcqAttempt(attempt.id)
      .then(onDropped)
      .catch((err: unknown) => {
        setError(errorMessage(err));
        setBusy(false);
        setConfirming(false);
      });
  }, [attempt.id, onDropped]);

  return (
    <li
      className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2
        border-b border-line last:border-b-0"
    >
      <TopicCode code={attempt.subject_code} />
      <span className="text-fg-2 tnum">{unitList(attempt.units)}</span>
      <span className="text-fg-3">{lengthLabel(attempt.length)}</span>
      <span className="text-fg-3">{mediumDate(attempt.started_at)}</span>

      <span className="ml-auto flex items-baseline gap-3 shrink-0">
        {error && (
          <span className="text-[12px]" style={{ color: "var(--g-again)" }}>
            {error}
          </span>
        )}
        {confirming ? (
          <>
            <span className="text-fg-2 text-[12px]">Discard it?</span>
            <button
              onClick={drop}
              disabled={busy}
              className="link text-[12.5px] disabled:opacity-50"
              style={{ color: "var(--g-again)" }}
            >
              {busy ? "dropping…" : "Yes, drop"}
            </button>
            <button
              onClick={() => setConfirming(false)}
              disabled={busy}
              className="link text-fg-3 text-[12.5px] disabled:opacity-50"
            >
              Keep
            </button>
          </>
        ) : open ? (
          <>
            <span className="telemetry text-[11px] text-fg-3">
              {attempt.answered}/{attempt.total} answered
            </span>
            <Link href={`/test/mcq/${attempt.id}`} className="link">
              Resume
            </Link>
            <button
              onClick={() => setConfirming(true)}
              className="link text-fg-3 text-[12.5px]"
            >
              Drop
            </button>
          </>
        ) : (
          <>
            <span className="telemetry text-[11.5px] text-fg-2">
              {attempt.score ?? 0}/{attempt.total}
              <span className="text-fg-3 ml-2">
                {attempt.total > 0
                  ? Math.round((100 * (attempt.score ?? 0)) / attempt.total)
                  : 0}
                %
              </span>
            </span>
            <Link href={`/test/mcq/${attempt.id}`} className="link">
              Review
            </Link>
          </>
        )}
      </span>
    </li>
  );
}

/* --- the picker ----------------------------------------------------------- */

export function YashMadeTest() {
  const router = useRouter();
  const reduced = useReducedMotion();
  const subjectsRes = useResource<McqSubject[]>("mcq-subjects", getMcqSubjects);
  const attemptsRes = useResource("mcq-attempts", getMcqAttempts);

  /** Null until something is actually picked; the default is derived, not
   *  written into state by an effect. */
  const [picked, setPicked] = useState<{
    subject: string;
    units: number[];
  } | null>(null);
  const [length, setLength] = useState<McqLength>(30);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const subjects = useMemo(() => subjectsRes.data ?? [], [subjectsRes.data]);

  /** The first subject that actually has material, so the picker opens on
   *  something startable rather than on an empty one. */
  const subject = useMemo(() => {
    if (subjects.length === 0) return null;
    if (picked) {
      const named = subjects.find((s) => s.subject_code === picked.subject);
      if (named) return named;
    }
    return subjects.find((s) => s.units.some((u) => u.count > 0)) ?? subjects[0];
  }, [subjects, picked]);

  /** Every unit that has questions — the "All units" selection, and the
   *  default one. */
  const allUnits = useMemo(
    () =>
      (subject?.units ?? []).filter((u) => u.count > 0).map((u) => u.unit),
    [subject],
  );

  const units = useMemo(() => {
    if (picked && subject && picked.subject === subject.subject_code) {
      return picked.units;
    }
    return allUnits;
  }, [picked, subject, allUnits]);

  const available = useMemo(
    () =>
      (subject?.units ?? [])
        .filter((u) => units.includes(u.unit))
        .reduce((n, u) => n + u.count, 0),
    [subject, units],
  );

  const lengths: McqLength[] = subject?.lengths?.length
    ? subject.lengths
    : [30, 60, "full"];

  const setUnits = useCallback(
    (next: number[]) => {
      if (!subject) return;
      setPicked({
        subject: subject.subject_code,
        units: [...next].sort((a, b) => a - b),
      });
    },
    [subject],
  );

  const toggleUnit = useCallback(
    (unit: number) => {
      setUnits(
        units.includes(unit) ? units.filter((u) => u !== unit) : [...units, unit],
      );
    },
    [units, setUnits],
  );

  const boardKey = subject
    ? `mcq-board:${subject.subject_code}:${units.join(",")}:${length}`
    : "mcq-board:none";

  const fetchBoard = useCallback(() => {
    if (!subject || units.length === 0) return Promise.resolve([]);
    return getMcqLeaderboard(subject.subject_code, units, length);
    // The key carries the selection, so the fetcher is allowed to close over
    // it: useResource refetches whenever the key changes.
  }, [subject, units, length]);

  const boardRes = useResource(boardKey, fetchBoard);

  const start = useCallback(() => {
    if (!subject || starting || available === 0) return;
    setStarting(true);
    setStartError(null);
    createMcqAttempt(subject.subject_code, units, length)
      .then((a) => router.push(`/test/mcq/${a.attempt_id}`))
      .catch((err: unknown) => {
        setStartError(errorMessage(err));
        setStarting(false);
      });
  }, [subject, units, length, available, starting, router]);

  const attempts = attemptsRes.data ?? [];
  const drawn = length === "full" ? available : Math.min(length, available);

  if (subjectsRes.loading && !subjectsRes.data) {
    return (
      <div aria-label="Reading the question bank">
        <Skeleton className="h-4 w-52" />
        <div className="flex gap-2 mt-4">
          <Skeleton className="h-11 w-44" />
          <Skeleton className="h-11 w-44" />
          <Skeleton className="h-11 w-28" />
        </div>
        <Skeleton className="h-9 w-40 mt-5" />
      </div>
    );
  }

  if (subjectsRes.error && !subjectsRes.data) {
    return (
      <ErrorState message={subjectsRes.error} onRetry={subjectsRes.reload} />
    );
  }

  if (!subject) {
    return (
      <Panel title="Yash Made Test">
        <EmptyState>
          The bank is empty — no subject has questions written for it yet.
        </EmptyState>
      </Panel>
    );
  }

  return (
    <div>
      {/* --- subject ------------------------------------------------------ */}

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {subjects.length > 1 ? (
          <select
            value={subject.subject_code}
            onChange={(e) => {
              const next = subjects.find(
                (s) => s.subject_code === e.target.value,
              );
              if (!next) return;
              setPicked({
                subject: next.subject_code,
                units: next.units.filter((u) => u.count > 0).map((u) => u.unit),
              });
            }}
            aria-label="Subject"
            className="h-8 px-2 rounded-sm border border-line bg-surface text-[13px] text-fg
              hover:border-line-strong transition-colors duration-[90ms]"
          >
            {subjects.map((s) => (
              <option key={s.subject_code} value={s.subject_code}>
                {s.subject_code} — {s.label}
              </option>
            ))}
          </select>
        ) : (
          <span className="flex items-baseline gap-2">
            <TopicCode code={subject.subject_code} />
            <span className="text-[13px] text-fg-2">{subject.label}</span>
          </span>
        )}
        <span className="telemetry text-[11px] text-fg-3">
          {available} {plural(available, "question")} in this selection
        </span>
      </div>

      {/* --- units -------------------------------------------------------- */}

      <h2 className="label mt-4 mb-2">Units</h2>
      <div className="flex flex-wrap gap-2">
        {subject.units.map((u) => (
          <Chip
            key={u.unit}
            active={units.includes(u.unit)}
            disabled={u.count === 0}
            onClick={() => toggleUnit(u.unit)}
            title={`Unit ${u.unit} — ${u.label}`}
            note={
              u.count === 0
                ? "waiting for material"
                : `${u.count} ${plural(u.count, "question")}`
            }
          />
        ))}
        {allUnits.length > 1 && (
          <Chip
            active={
              units.length === allUnits.length &&
              allUnits.every((u) => units.includes(u))
            }
            onClick={() => setUnits(allUnits)}
            title="All units"
            note={`${allUnits.length} with material`}
          />
        )}
      </div>

      {/* --- length ------------------------------------------------------- */}

      <h2 className="label mt-4 mb-2">Length</h2>
      <div className="flex flex-wrap gap-2">
        {lengths.map((l) => (
          <Chip
            key={String(l)}
            active={l === length}
            onClick={() => setLength(l)}
            title={lengthLabel(l)}
            note={
              l === "full" || available < Number(l)
                ? `${available} available`
                : "questions"
            }
          />
        ))}
      </div>

      {startError && (
        <div
          className="mt-4 px-3 py-2 border-l-2 bg-surface text-[13px]"
          style={{ borderLeftColor: "var(--g-again)" }}
          role="alert"
        >
          {startError}
        </div>
      )}

      {/* --- start -------------------------------------------------------- */}

      <div className="flex flex-wrap items-center gap-3 mt-5">
        <motion.button
          onClick={start}
          disabled={starting || available === 0}
          whileTap={reduced ? undefined : { scale: 0.98 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
          className="glow-behind accent-grad glow-accent-hover inline-flex items-center gap-2.5
            h-9 px-4 rounded-sm text-[13px] font-semibold border border-accent
            disabled:opacity-40 disabled:pointer-events-none"
        >
          {starting ? "Shuffling…" : "Start"}
        </motion.button>
        <p className="text-[12px] text-fg-3">
          {available === 0
            ? "Pick a unit that has questions."
            : `${drawn} ${plural(drawn, "question")}, shuffled — and so are the
               options, so two sittings never look the same.`}
        </p>
      </div>

      {/* --- history and the board ---------------------------------------- */}

      <div className="grid gap-4 lg:grid-cols-2 items-start mt-6">
        <Reveal>
          <Panel
            title="Your attempts"
            aside={attempts.length ? `${attempts.length}` : undefined}
          >
            {attemptsRes.error && !attemptsRes.data ? (
              <ErrorState
                message={attemptsRes.error}
                onRetry={attemptsRes.reload}
              />
            ) : attemptsRes.loading && !attemptsRes.data ? (
              <div className="px-3 py-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-3 w-full my-2" />
                ))}
              </div>
            ) : attempts.length === 0 ? (
              <EmptyState>
                You have not sat this test yet. Pick a unit and press Start —
                nothing here touches your review schedule.
              </EmptyState>
            ) : (
              <ul className="text-[12.5px]">
                {attempts.slice(0, 8).map((a) => (
                  <AttemptRow
                    key={a.id}
                    attempt={a}
                    onDropped={attemptsRes.reload}
                  />
                ))}
              </ul>
            )}
          </Panel>
        </Reveal>

        <Reveal index={1}>
          <Panel
            title="Leaderboard"
            aside={`${subject.subject_code} · ${unitList(units)} · ${lengthLabel(length)}`}
          >
            {boardRes.error && !boardRes.data ? (
              <ErrorState message={boardRes.error} onRetry={boardRes.reload} />
            ) : boardRes.loading && !boardRes.data ? (
              <div className="px-3 py-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-3 w-full my-2" />
                ))}
              </div>
            ) : (boardRes.data ?? []).length === 0 ? (
              <EmptyState>Nobody has sat this yet — be first.</EmptyState>
            ) : (
              <ul className="text-[12.5px]">
                {(boardRes.data ?? []).map((row, i) => (
                  <li
                    key={`${row.user_id}-${row.submitted_at}`}
                    className="flex items-baseline gap-3 px-3 py-2 border-b border-line last:border-b-0"
                  >
                    <span className="telemetry text-[11px] text-fg-3 w-6 shrink-0">
                      #{i + 1}
                    </span>
                    <span className="font-medium text-fg truncate">
                      {row.name}
                    </span>
                    <span className="ml-auto telemetry text-[11.5px] text-fg-2 shrink-0">
                      {row.score}/{row.total}
                      <span className="text-fg-3 ml-2">
                        {row.total > 0
                          ? Math.round((100 * row.score) / row.total)
                          : 0}
                        %
                      </span>
                      <span className="text-fg-3 ml-2">
                        {formatDuration(row.duration_s * 1000)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </Reveal>
      </div>
    </div>
  );
}
