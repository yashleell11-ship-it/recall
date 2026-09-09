"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo } from "react";
import { Skeleton } from "@/components/rich";
import { EmptyState, ErrorState } from "@/components/ui";
import { CheckYourself } from "@/app/learn/CheckYourself";
import { CommandBlock } from "@/app/learn/CommandBlock";
import { Worked } from "@/app/learn/Worked";
import { otherNotes, StatusChip, Warranty, workedNote } from "@/app/learn/Warranty";
import { getLesson } from "@/lib/api";
import { mediumDate } from "@/lib/format";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import type { LessonSection } from "@/lib/types";
import { useResource } from "@/lib/useResource";

/**
 * One lesson, read top to bottom.
 *
 * This is reading, not a timed session, so the shell stays: `useFocusMode` is
 * deliberately not called. One measured column, no tabs and no accordions over
 * the teaching — the only thing hidden on the page is the answers under
 * "Check yourself", where hiding is the point.
 */

/* --- the sections ---------------------------------------------------------
   Two signals per section, and both are structural rather than decorative: a
   chip in the heading row, and — for a cited one — a quote block under the
   paragraph it supports. A section written from the model's own knowledge
   simply has no such block, which is a large, unmissable difference. */

function Section({ section, index }: { section: LessonSection; index: number }) {
  const quote = (section.quote ?? "").trim();

  return (
    <section className="mb-8">
      <div className="flex items-baseline gap-2.5">
        <span className="telemetry text-[10px] text-fg-3 w-4 shrink-0">
          {String(index).padStart(2, "0")}
        </span>
        <h2 className="k-text text-[17px] font-medium text-fg flex-1">
          {section.heading}
        </h2>
        {quote ? (
          <span
            className="prov shrink-0"
            title="A sentence from your own uploaded material appears below, word for word."
          >
            cited
          </span>
        ) : (
          <span
            className="prov prov--ai shrink-0"
            title="Written from the model's own knowledge, with nothing in your course material to check it against."
          >
            model only
          </span>
        )}
      </div>

      {/* whitespace-pre-line for the same reason a card's detail has it:
          derivation lines must not collapse into one paragraph. */}
      <p className="k-text text-[16px] leading-[1.7] text-fg max-w-[64ch] whitespace-pre-line mt-2.5 pl-[1.6rem]">
        {section.body}
      </p>

      {quote ? (
        /* The rail is ink, never --ai: this text is the student's own
           material, the one thing on the page the model did not write. The
           quote and its attribution are one figure and cannot be rendered
           apart. */
        <figure className="mt-3 ml-[1.6rem] border-l-2 border-line-strong pl-3.5 max-w-[62ch]">
          <blockquote className="k-text text-[14.5px] leading-relaxed text-fg-2">
            &ldquo;{quote}&rdquo;
          </blockquote>
          <figcaption className="telemetry text-[10.5px] text-fg-3 mt-1.5">
            {section.source ?? "your course material"}
          </figcaption>
        </figure>
      ) : null}
    </section>
  );
}

/* --- loading --------------------------------------------------------------
   The document's own skeleton, at the document's own width, so nothing
   reflows when the text lands. */

function ReaderSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading lesson">
      <Skeleton className="h-7 w-2/3" />
      <Skeleton className="h-[5px] w-[18rem] max-w-full mt-3" />
      <Skeleton className="h-4 w-1/2 mt-3" />
      {[0, 1, 2].map((p) => (
        <div key={p} className="mt-7 space-y-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-4" style={{ width: "100%" }} />
          <Skeleton className="h-4" style={{ width: "96%" }} />
          <Skeleton className="h-4" style={{ width: "88%" }} />
          <Skeleton className="h-4" style={{ width: "60%" }} />
        </div>
      ))}
      {[0, 1].map((p) => (
        <Skeleton key={p} className="h-[150px] mt-4" />
      ))}
    </div>
  );
}

export function LessonReader({ topic, unit }: { topic: string; unit: number }) {
  const router = useRouter();
  const fetcher = useCallback(() => getLesson(topic, unit), [topic, unit]);
  const res = useResource(`lesson:${topic}:${unit}`, fetcher);

  const page = res.data;
  const code = page?.topic_code ?? topic;
  const reviewHref = `/review?topic=${encodeURIComponent(code)}`;

  // Esc leaves, r reviews the same subject. Both plain keys, both yielding to
  // text fields and modifier chords. The shell's own listener runs first, in
  // the capture phase, and stops propagation on its `g` chords — so `g r`
  // still means "go to review", not "review this subject".
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e) || hasModifier(e)) return;
      if (e.key === "Escape") {
        e.preventDefault();
        router.push("/learn");
        return;
      }
      if (e.key === "r") {
        e.preventDefault();
        router.push(reviewHref);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, reviewHref]);

  const lesson = page?.lesson ?? null;
  const sections = useMemo(
    () => lesson?.body.sections ?? [],
    [lesson],
  );
  const notes = lesson?.notes ?? [];

  return (
    <main className="mx-auto max-w-[46rem] px-4 sm:px-6 py-6 pb-24">
      <div className="mb-5 flex items-center justify-between gap-3">
        <Link
          href="/learn"
          className="text-[12px] text-fg-3 hover:text-fg-2 transition-colors duration-[90ms]"
        >
          ← Learn
        </Link>
        <Link
          href={reviewHref}
          className="text-[13px] link text-fg-2 hover:text-fg"
        >
          Review {code}
        </Link>
      </div>

      {res.error && !page ? (
        <ErrorState message={res.error} onRetry={res.reload} />
      ) : null}

      {res.loading && !page ? <ReaderSkeleton /> : null}

      {page ? (
        <>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="prov">
              {page.topic_code} · Unit {page.unit_number}
            </span>
            {/* The AI mark means "content the model produced". On a unit
                with nothing written there is none, so it is not claimed. */}
            {lesson ? (
              <>
                <span className="prov prov--ai">AI</span>
                <StatusChip status={lesson.status} />
              </>
            ) : null}
          </div>

          <h1 className="k-text text-[26px] font-medium leading-snug mt-2.5">
            {page.unit_name}
          </h1>

          {lesson ? (
            <>
              <Warranty
                status={lesson.status}
                sections={sections}
                cited={lesson.cited_sections}
                total={lesson.section_count}
                notes={otherNotes(notes)}
              />

              <p className="telemetry text-[10.5px] text-fg-3 mt-2">
                written {mediumDate(lesson.created_at)}
              </p>

              <hr className="border-line my-6" />

              {/* The lede: what this unit lets you do and how it is examined.
                  The only paragraph on the page set at answer weight, and it
                  carries no label — it reads as the opening of the document,
                  which is what it is. */}
              <p className="k-answer text-fg max-w-[64ch]">
                {lesson.body.why}
              </p>

              <hr className="border-line my-6" />

              {sections.map((s, i) => (
                <Section key={`${i}-${s.heading}`} section={s} index={i + 1} />
              ))}

              {(lesson.body.worked ?? []).length > 0 ? (
                <div className="mt-8 space-y-4">
                  {(lesson.body.worked ?? []).map((w, i) => (
                    <Worked
                      key={i}
                      index={i + 1}
                      item={w}
                      note={workedNote(notes, i + 1)}
                    />
                  ))}
                </div>
              ) : null}

              {(lesson.body.check ?? []).length > 0 ? (
                <CheckYourself items={lesson.body.check ?? []} />
              ) : null}

              <div className="mt-10 pt-5 border-t border-line flex flex-wrap items-center gap-x-5 gap-y-2">
                <Link href={reviewHref} className="link text-[13px]">
                  Review {code}
                </Link>
                <Link href="/test" className="link text-[13px] text-fg-2">
                  Sit a paper
                </Link>
                <Link
                  href="/learn"
                  className="text-[13px] text-fg-3 hover:text-fg-2 transition-colors duration-[90ms]"
                >
                  All lessons
                </Link>
                <span className="telemetry text-[10.5px] text-fg-3 ml-auto">
                  lesson #{lesson.id} · {lesson.status}
                </span>
              </div>
            </>
          ) : (
            /* Reached by a typed URL or a stale link. The header above still
               names the unit, so the page is about something. */
            <div className="mt-4">
              <EmptyState
                action={
                  <Link href="/learn" className="link text-[13px]">
                    Back to lessons
                  </Link>
                }
              >
                No lesson has been written for this unit yet. Lessons are
                written offline, on the server, because each one takes a minute
                or two and costs money — so nothing here can start one for you.
              </EmptyState>
              <div className="px-3">
                <CommandBlock
                  command={`recall lessons ${page.topic_code} --unit ${page.unit_number}`}
                />
              </div>
            </div>
          )}
        </>
      ) : null}
    </main>
  );
}
