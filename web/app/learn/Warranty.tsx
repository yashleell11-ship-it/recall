"use client";

import type { LessonSection, LessonStatus } from "@/lib/types";

/**
 * The honesty layer of a lesson, in three pieces: the status chip, the
 * coverage meter, and the one sentence that says in words what the meter says
 * in ink.
 *
 * The rule the whole screen enforces: ink means your course material, violet
 * means the model's own knowledge, and weight means how much of the lesson is
 * which. Nothing here is red or green — `--g-good` and `--g-again` mean "you
 * graded this card", and borrowing them would tell a student a lesson is
 * CORRECT when what Python actually checked is that a quote exists.
 */

const GROUNDED_TITLE =
  "Every claim marked “cited” was checked, in Python, against your uploaded course material.";
const UNVERIFIED_TITLE =
  "Written and structurally checked, but not anchored to your course material — most of it is the model's own knowledge.";

/**
 * The same pill on the index and in the reader, differing only in ink weight.
 * A grounded lesson reads dark and settled; an unverified one reads grey and
 * provisional, and a column of them shows the split as a gradient without a
 * word being read. `draft` is legacy and gets the unverified treatment,
 * because that is what a draft is.
 */
export function StatusChip({ status }: { status: LessonStatus }) {
  if (status === "grounded") {
    return (
      <span
        className="prov shrink-0"
        style={{
          color: "var(--fg)",
          borderColor: "var(--line-strong)",
          fontWeight: 600,
        }}
        title={GROUNDED_TITLE}
      >
        grounded
      </span>
    );
  }
  return (
    <span className="prov shrink-0" title={UNVERIFIED_TITLE}>
      unverified
    </span>
  );
}

/** Notes about one worked example, e.g. "worked example 2: …". */
const WORKED_NOTE = /^worked example (\d+)\b/i;

/**
 * The note the re-derivation recorded about worked example `n`, if any.
 *
 * These lines are CAVEATS by contract — the re-derivation records a line only
 * when it could not confirm an answer — which is why the reader renders one as
 * a flat "not confirmed" chip without reading the sentence. A note that
 * asserted the opposite would be shown as its own contradiction, so if the
 * pipeline ever starts recording confirmations they need their own prefix,
 * not this one.
 */
export function workedNote(notes: string[], n: number): string | undefined {
  return notes.find((line) => {
    const m = WORKED_NOTE.exec(line.trim());
    return m ? Number(m[1]) === n : false;
  });
}

/** Everything that is not about a specific worked example. Those are shown on
 *  the derivation they doubt, not in a list at the top of the page. */
export function otherNotes(notes: string[]): string[] {
  return notes.filter((line) => !WORKED_NOTE.test(line.trim()));
}

/**
 * One segment per section, ink for cited and hairline-grey for not — the same
 * 5px segmented bar the subject rail already uses for the CA/MTE/ETE split,
 * so this is existing vocabulary rather than a new chart.
 *
 * `--ai` is deliberately NOT the grey: this bar sits a few pixels from a
 * `.prov--ai` chip, and two violets meaning different things is how a
 * one-meaning colour stops meaning one thing.
 */
function CoverageMeter({
  sections,
  cited,
  total,
}: {
  sections: LessonSection[];
  cited: number;
  total: number;
}) {
  return (
    <div
      className="flex h-[5px] gap-px rounded-[2px] overflow-hidden mt-3 max-w-[18rem]"
      role="img"
      aria-label={`${cited} of ${total} sections quote your course material`}
    >
      {sections.map((s, i) => (
        <div
          key={`${i}-${s.heading}`}
          className="flex-1"
          style={{
            background: (s.quote ?? "").trim()
              ? "var(--fg)"
              : "var(--line-strong)",
          }}
        />
      ))}
    </div>
  );
}

/**
 * Composed from the two counts and the status — never by reading `notes`
 * prose. The numbers are the same ones the meter is drawn from, so the
 * sentence and the picture cannot disagree.
 */
function warrantySentence(
  status: LessonStatus,
  cited: number,
  total: number,
): string {
  if (total === 0 || cited === 0) {
    return "No section here quotes your course material. All of it is the model's own knowledge.";
  }
  if (cited === total) {
    return `All ${total} sections quote your course material, word for word. The explanation around the quotes is still the model's.`;
  }
  if (status === "grounded") {
    return `${cited} of ${total} sections quote your course material, word for word. The rest is the model's own explanation.`;
  }
  return `Only ${cited} of ${total} sections ${
    cited === 1 ? "is" : "are"
  } anchored in your course material. The rest is the model's own knowledge — check it before you trust it.`;
}

export function Warranty({
  status,
  sections,
  cited,
  total,
  notes,
}: {
  status: LessonStatus;
  sections: LessonSection[];
  cited: number;
  total: number;
  /** Already stripped of the worked-example lines. */
  notes: string[];
}) {
  return (
    <div className="mt-3">
      {sections.length > 0 ? (
        <CoverageMeter sections={sections} cited={cited} total={total} />
      ) : null}

      <p className="k-text text-[13px] leading-relaxed text-fg-2 max-w-[64ch] mt-2">
        {warrantySentence(status, cited, total)}
      </p>

      {notes.length > 0 ? (
        /* Nothing is hidden — everything the pipeline recorded is one click
           away, verbatim, in the pipeline's own words — but the resting page
           is a lesson, not a build log. */
        <details className="mt-2.5 group">
          <summary
            className="label cursor-pointer select-none list-none inline-flex items-center gap-1
              [&::-webkit-details-marker]:hidden hover:text-fg-2 transition-colors duration-[90ms]"
          >
            <span
              aria-hidden="true"
              className="inline-block transition-transform duration-[90ms] group-open:rotate-90"
            >
              ›
            </span>
            what the checks recorded ({notes.length})
          </summary>
          <ul className="anim-reveal mt-2 space-y-1.5 max-w-[64ch] border-l border-line pl-3">
            {notes.map((n, i) => (
              <li
                key={i}
                className="k-text text-[12.5px] leading-relaxed text-fg-2"
              >
                {n}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
