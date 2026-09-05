"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorState, Kbd, KindTag, Panel, TopicCode } from "@/components/ui";
import {
  ACCEPTED_EXTENSIONS,
  errorMessage,
  generateCards,
  getSources,
  getTopics,
  MAX_UPLOAD_BYTES,
  uploadSource,
} from "@/lib/api";
import { fileSize, plural, usd } from "@/lib/format";
import { hasModifier, isTypingTarget } from "@/lib/keys";
import type { GenerateResponse, Source, Topic, UploadResponse } from "@/lib/types";
import { useResource } from "@/lib/useResource";

const MAX_MB = Math.round(MAX_UPLOAD_BYTES / (1024 * 1024));

type GenState =
  | { stage: "idle" }
  | { stage: "confirm" }
  | { stage: "running" }
  | { stage: "done"; data: GenerateResponse }
  | { stage: "error"; message: string };

interface Item {
  key: string;
  file: File;
  topic: string;
  stage: "queued" | "uploading" | "done" | "error";
  progress: number;
  result: UploadResponse | null;
  error: string | null;
  abort: AbortController | null;
  gen: GenState;
}

/** Rejected here rather than at the server: a phone should not spend the bytes. */
function refuse(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return `Not a file type this reads. Accepted: ${ACCEPTED_EXTENSIONS.join(", ")}.`;
  }
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) {
    return `${fileSize(file.size)} is over the ${MAX_MB} MB limit.`;
  }
  return null;
}

async function fetchContext(): Promise<{ topics: Topic[]; sources: Source[] }> {
  const [topics, sources] = await Promise.all([getTopics(), getSources()]);
  return { topics, sources };
}

export default function UploadPage() {
  const res = useResource("upload-context", fetchContext);

  const [topic, setTopic] = useState("");
  const [newTopic, setNewTopic] = useState("");
  const [creating, setCreating] = useState(false);
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string | null>(null);

  const fileInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);
  const counter = useRef(0);
  const waiting = useRef<{ key: string; file: File; topic: string }[]>([]);
  const busy = useRef(false);

  const code = (creating ? newTopic : topic).trim().toUpperCase();
  const ready = code.length > 0;

  const patch = useCallback((key: string, next: Partial<Item>) => {
    setItems((prev) =>
      prev.map((i) => (i.key === key ? { ...i, ...next } : i)),
    );
  }, []);

  /**
   * One upload at a time, each starting the next as it settles. A phone on a
   * tunnelled connection gets one bar that actually moves instead of four that
   * crawl, and the server sees a queue rather than a burst.
   */
  const pump = useCallback(
    function run() {
      if (busy.current) return;
      const next = waiting.current.shift();
      if (!next) return;

      busy.current = true;
      const abort = new AbortController();
      patch(next.key, { stage: "uploading", progress: 0, abort });

      uploadSource(
        next.file,
        next.topic,
        (fraction) => patch(next.key, { progress: fraction }),
        abort.signal,
      )
        .then((result) =>
          patch(next.key, {
            stage: "done",
            progress: 1,
            result,
            abort: null,
            error: null,
          }),
        )
        .catch((err: unknown) =>
          patch(next.key, {
            stage: "error",
            abort: null,
            error: errorMessage(err),
          }),
        )
        .finally(() => {
          busy.current = false;
          run();
        });
    },
    [patch],
  );

  const add = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      if (!ready) {
        setRejected("Pick a topic first — every source is filed under one.");
        return;
      }
      setRejected(null);
      const batch: Item[] = [];
      for (const file of Array.from(files)) {
        const problem = refuse(file);
        const key = `${++counter.current}-${file.name}`;
        batch.push({
          key,
          file,
          topic: code,
          stage: problem ? "error" : "queued",
          progress: 0,
          result: null,
          error: problem,
          abort: null,
          gen: { stage: "idle" },
        });
        if (!problem) waiting.current.push({ key, file, topic: code });
      }
      setItems((prev) => [...prev, ...batch]);
      pump();
    },
    [ready, code, pump],
  );

  const retry = useCallback(
    (key: string) => {
      const item = items.find((i) => i.key === key);
      // A file rejected before it was ever sent stays rejected.
      if (!item || refuse(item.file)) return;
      patch(key, { stage: "queued", error: null, progress: 0 });
      waiting.current.push({ key, file: item.file, topic: item.topic });
      pump();
    },
    [items, patch, pump],
  );

  const generate = useCallback(
    (key: string, sourceId: number) => {
      patch(key, { gen: { stage: "running" } });
      generateCards(sourceId)
        .then((data) => patch(key, { gen: { stage: "done", data } }))
        .catch((err: unknown) =>
          patch(key, { gen: { stage: "error", message: errorMessage(err) } }),
        );
    },
    [patch],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e) || hasModifier(e)) return;
      if (e.key === "f") {
        e.preventDefault();
        fileInput.current?.click();
      } else if (e.key === "c") {
        e.preventDefault();
        cameraInput.current?.click();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const uploaded = items.filter((i) => i.stage === "done");
  const spent = (res.data?.sources ?? []).reduce(
    (n, s) => n + s.cost_estimate,
    0,
  );
  const priorSources = res.data?.sources.length ?? 0;

  return (
    <main className="mx-auto max-w-[1120px] px-4 py-5 pb-16">
      <div className="mb-4">
        <h1 className="text-[18px] font-semibold leading-none">Upload</h1>
        <p className="text-[13px] text-fg-2 mt-1.5 max-w-prose">
          Add a PDF, a text file, or a photo of a page. Uploading only pulls the
          text out — it is free and costs no API calls. Making cards from it is
          a separate step you press yourself.
        </p>
      </div>

      {res.error && !res.data ? (
        <ErrorState message={res.error} onRetry={res.reload} />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_320px] items-start">
        <div>
          {/* --- topic ---------------------------------------------------- */}

          <div className="panel px-3.5 py-3">
            <label
              htmlFor="topic"
              className="label block mb-1.5"
            >
              File it under
            </label>

            {creating ? (
              <div className="flex flex-wrap items-center gap-2">
                <input
                  id="topic"
                  value={newTopic}
                  onChange={(e) => setNewTopic(e.target.value)}
                  placeholder="CSE111"
                  autoFocus
                  spellCheck={false}
                  autoCapitalize="characters"
                  className="h-11 px-3 rounded-sm border border-line bg-surface text-[15px]
                    w-full sm:w-48 uppercase tracking-[0.05em]
                    hover:border-line-strong transition-colors duration-[90ms]"
                />
                <button
                  onClick={() => {
                    setCreating(false);
                    setNewTopic("");
                  }}
                  className="h-11 px-3 rounded-sm border border-line bg-surface text-[13px]
                    hover:border-line-strong hover:bg-surface-hover transition-colors duration-[90ms]"
                >
                  Use an existing topic
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <select
                  id="topic"
                  value={topic}
                  onChange={(e) => {
                    if (e.target.value === "__new") {
                      setCreating(true);
                      return;
                    }
                    setTopic(e.target.value);
                  }}
                  className="h-11 px-3 rounded-sm border border-line bg-surface text-[15px]
                    w-full sm:w-64 hover:border-line-strong transition-colors duration-[90ms]"
                >
                  <option value="">Choose a topic&hellip;</option>
                  {(res.data?.topics ?? []).map((t) => (
                    <option key={t.id} value={t.code}>
                      {t.code} — {t.label}
                    </option>
                  ))}
                  <option value="__new">New topic&hellip;</option>
                </select>
              </div>
            )}

            <p className="text-[12px] text-fg-3 mt-2">
              {ready ? (
                <>
                  Everything added next is filed under{" "}
                  <span className="font-semibold tracking-[0.05em] text-fg-2">
                    {code}
                  </span>
                  . Change it and add more to file a second batch elsewhere.
                </>
              ) : (
                "A source belongs to exactly one topic, so its cards land in the right paper."
              )}
            </p>
          </div>

          {/* --- pick files ----------------------------------------------- */}

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              add(e.dataTransfer.files);
            }}
            className="panel mt-3 px-3.5 py-3.5 transition-colors duration-[90ms]"
            style={
              dragging
                ? {
                    borderColor: "var(--accent)",
                    background: "var(--accent-quiet)",
                  }
                : undefined
            }
          >
            <input
              ref={fileInput}
              type="file"
              multiple
              accept={ACCEPTED_EXTENSIONS.join(",")}
              className="sr-only"
              onChange={(e) => {
                add(e.target.files);
                e.target.value = "";
              }}
            />
            {/* capture="environment" opens the back camera on a phone straight
                away; on a desktop the attribute is ignored and it is a picker. */}
            <input
              ref={cameraInput}
              type="file"
              multiple
              accept="image/*"
              capture="environment"
              className="sr-only"
              onChange={(e) => {
                add(e.target.files);
                e.target.value = "";
              }}
            />

            <div className="grid gap-2 sm:grid-cols-2">
              <button
                onClick={() => fileInput.current?.click()}
                disabled={!ready}
                className="min-h-[56px] px-4 rounded-sm text-[15px] font-semibold
                  bg-accent text-accent-fg border border-accent hover:bg-accent-hover
                  hover:border-accent-hover transition-colors duration-[90ms]
                  disabled:opacity-40 disabled:pointer-events-none
                  flex items-center justify-center gap-2.5"
              >
                Choose files
                <Kbd>f</Kbd>
              </button>
              <button
                onClick={() => cameraInput.current?.click()}
                disabled={!ready}
                className="min-h-[56px] px-4 rounded-sm text-[15px] font-medium
                  border border-line bg-surface hover:border-line-strong hover:bg-surface-hover
                  transition-colors duration-[90ms]
                  disabled:opacity-40 disabled:pointer-events-none
                  flex items-center justify-center gap-2.5"
              >
                Take a photo
                <Kbd>c</Kbd>
              </button>
            </div>

            <p className="text-[12px] text-fg-3 mt-2.5">
              {ACCEPTED_EXTENSIONS.join("  ")}
              <span className="mx-1.5">·</span>
              up to {MAX_MB} MB each
              <span className="hidden sm:inline">
                <span className="mx-1.5">·</span>
                or drop them here
              </span>
            </p>
          </div>

          {rejected && (
            <p
              className="mt-3 px-3 py-2 border-l-2 bg-surface text-[13px]"
              style={{ borderLeftColor: "var(--g-again)" }}
              role="alert"
            >
              {rejected}
            </p>
          )}

          {/* --- the queue ------------------------------------------------ */}

          {items.length > 0 && (
            <ul className="mt-3 grid gap-2">
              {items.map((item) => (
                <FileRow
                  key={item.key}
                  item={item}
                  priorSources={priorSources}
                  priorSpend={spent}
                  onCancel={() => item.abort?.abort()}
                  onRetry={() => retry(item.key)}
                  onRemove={() =>
                    setItems((prev) => prev.filter((i) => i.key !== item.key))
                  }
                  onConfirmGenerate={() =>
                    patch(item.key, { gen: { stage: "confirm" } })
                  }
                  onCancelGenerate={() =>
                    patch(item.key, { gen: { stage: "idle" } })
                  }
                  onGenerate={() =>
                    item.result && generate(item.key, item.result.source_id)
                  }
                />
              ))}
            </ul>
          )}

          {uploaded.length > 0 && (
            <p className="text-[12.5px] text-fg-2 mt-3.5">
              {uploaded.length} {plural(uploaded.length, "file")} read.{" "}
              <Link href="/approve" className="link">
                Approve queue
              </Link>{" "}
              <span className="text-fg-3">·</span>{" "}
              <Link href="/sources" className="link text-fg-2">
                All sources
              </Link>
            </p>
          )}
        </div>

        {/* --- the honest bit --------------------------------------------- */}

        <div className="grid gap-4">
          <Panel title="What happens" bodyClassName="px-3.5 py-3">
            <ol className="text-[12.5px] text-fg-2 grid gap-2.5">
              <li>
                <span className="font-semibold text-fg">Upload</span> pulls the
                text out and splits it into chunks. No API call, no cost, and it
                works before any key is configured.
              </li>
              <li>
                <span className="font-semibold text-fg">Generate cards</span>{" "}
                sends each chunk to the model. This is the step that spends
                money, which is why it is a separate press.
              </li>
              <li>
                <span className="font-semibold text-fg">Approve</span> keeps the
                cards worth keeping. Nothing enters your rotation until you say
                so.
              </li>
            </ol>
            {priorSources > 0 && (
              <p className="text-[12px] text-fg-3 mt-3 pt-2.5 border-t border-line tnum">
                {priorSources} {plural(priorSources, "source")} so far have cost{" "}
                {usd(spent)} in all, {usd(spent / priorSources)} each.
              </p>
            )}
          </Panel>

          <Panel title="Photos and OCR" bodyClassName="px-3.5 py-3">
            <p className="text-[12.5px] text-fg-2">
              Images go through Tesseract on the CPU.{" "}
              <span className="text-fg font-medium">
                Printed slides, textbook pages and screenshots read well.
              </span>{" "}
              Handwriting reads badly — that is what CPU OCR does, not a bug.
            </p>
            <p className="text-[12px] text-fg-3 mt-2">
              Shoot straight-on, fill the frame with the page, and keep the
              light even. If the text that comes out looks too short for the
              page, you will be told before you spend anything on it.
            </p>
          </Panel>
        </div>
      </div>
    </main>
  );
}

/* --- one file ------------------------------------------------------------ */

function FileRow({
  item,
  priorSources,
  priorSpend,
  onCancel,
  onRetry,
  onRemove,
  onConfirmGenerate,
  onCancelGenerate,
  onGenerate,
}: {
  item: Item;
  priorSources: number;
  priorSpend: number;
  onCancel: () => void;
  onRetry: () => void;
  onRemove: () => void;
  onConfirmGenerate: () => void;
  onCancelGenerate: () => void;
  onGenerate: () => void;
}) {
  const pct = Math.round(item.progress * 100);
  const result = item.result;

  return (
    <li
      className="panel px-3.5 py-3 border-l-2"
      style={{
        borderLeftColor:
          item.stage === "error"
            ? "var(--g-again)"
            : item.stage === "done"
              ? "var(--g-good)"
              : "var(--line-strong)",
      }}
    >
      <div className="flex items-baseline gap-3">
        <span className="text-[13.5px] font-medium truncate min-w-0">
          {item.file.name}
        </span>
        <span className="text-[11px] text-fg-3 tnum ml-auto shrink-0">
          {fileSize(item.file.size)}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-fg-3 mt-1">
        <TopicCode code={item.topic} />
        {result && <KindTag kind={result.kind} />}
        {item.stage === "queued" && <span>waiting</span>}
        {item.stage === "uploading" && <span className="tnum">{pct}%</span>}
        {result && (
          <span className="tnum">
            {result.chunks} {plural(result.chunks, "chunk")} ·{" "}
            {result.text_chars.toLocaleString()} characters
          </span>
        )}
        <span className="ml-auto flex items-center gap-3">
          {item.stage === "uploading" && (
            <button onClick={onCancel} className="link text-fg-3">
              Cancel
            </button>
          )}
          {(item.stage === "done" || item.stage === "error") && (
            <button onClick={onRemove} className="link text-fg-3">
              Clear
            </button>
          )}
        </span>
      </div>

      {(item.stage === "uploading" || item.stage === "queued") && (
        <div
          className="h-[3px] w-full bg-line rounded-xs overflow-hidden mt-2"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Uploading ${item.file.name}`}
        >
          <div
            className="h-full bg-fg transition-[width] duration-[90ms] ease-out"
            style={{ width: `${item.stage === "queued" ? 0 : pct}%` }}
          />
        </div>
      )}

      {item.stage === "uploading" && pct === 100 && (
        <p className="text-[12px] text-fg-3 mt-1.5">
          Sent. Reading the text out of it&hellip;
        </p>
      )}

      {item.error && (
        <div className="mt-2 text-[12.5px]">
          <p className="text-fg-2">{item.error}</p>
          {item.stage === "error" && !refuse(item.file) && (
            <button onClick={onRetry} className="link text-fg-2 mt-1">
              Try again
            </button>
          )}
        </div>
      )}

      {/* --- OCR honesty ------------------------------------------------- */}

      {result?.warning && (
        <div
          className="mt-2.5 pl-2.5 py-1 border-l-2"
          style={{ borderColor: "var(--g-hard)" }}
        >
          <p
            className="label"
            style={{ color: "var(--g-hard)" }}
          >
            Little text came out
          </p>
          <p className="text-[12.5px] text-fg-2 mt-1 leading-snug">
            {result.warning}
          </p>
        </div>
      )}

      {/* --- the step that spends money ----------------------------------- */}

      {result && (
        <div className="mt-3 pt-2.5 border-t border-line">
          {item.gen.stage === "idle" && (
            <>
              <button
                onClick={onConfirmGenerate}
                className="inline-flex items-center h-9 px-3.5 rounded-sm text-[13px] font-semibold
                  bg-accent text-accent-fg border border-accent hover:bg-accent-hover
                  hover:border-accent-hover transition-colors duration-[90ms]"
              >
                Generate cards
              </button>
              <p className="text-[12px] text-fg-3 mt-1.5">
                {result.chunks} {plural(result.chunks, "chunk")}, one paid call
                each.
                {priorSources > 0
                  ? ` Your ${priorSources} earlier ${plural(
                      priorSources,
                      "source",
                    )} averaged ${usd(priorSpend / priorSources)}.`
                  : " Nothing has been spent on this file yet."}
              </p>
            </>
          )}

          {item.gen.stage === "confirm" && (
            <div>
              <p className="text-[13px]">
                This calls the paid API {result.chunks}{" "}
                {plural(result.chunks, "time")} and takes a minute or two.
              </p>
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <button
                  onClick={onGenerate}
                  className="inline-flex items-center h-9 px-3.5 rounded-sm text-[13px] font-semibold
                    bg-accent text-accent-fg border border-accent hover:bg-accent-hover
                    hover:border-accent-hover transition-colors duration-[90ms]"
                >
                  Spend it
                </button>
                <button
                  onClick={onCancelGenerate}
                  className="inline-flex items-center h-9 px-3 rounded-sm text-[13px] font-medium
                    border border-line bg-surface hover:border-line-strong hover:bg-surface-hover
                    transition-colors duration-[90ms]"
                >
                  Not now
                </button>
              </div>
            </div>
          )}

          {item.gen.stage === "running" && (
            <p className="text-[12.5px] text-fg-3">
              Reading {result.chunks} {plural(result.chunks, "chunk")} and
              writing cards&hellip; you can leave this page, it runs on the
              server.
            </p>
          )}

          {item.gen.stage === "error" && (
            <div className="text-[12.5px]">
              <p
                className="pl-2 border-l-2 text-fg-2"
                style={{ borderColor: "var(--g-again)" }}
              >
                {item.gen.message}
              </p>
              <button onClick={onConfirmGenerate} className="link text-fg-2 mt-1.5">
                Try again
              </button>
            </div>
          )}

          {item.gen.stage === "done" && (
            <div className="text-[12.5px] anim-reveal">
              <p className="text-fg">
                <span className="tnum font-semibold">
                  {item.gen.data.accepted}
                </span>{" "}
                {plural(item.gen.data.accepted, "card")} kept,{" "}
                <span className="tnum">{item.gen.data.rejected}</span> thrown out
                by the groundedness check, for{" "}
                <span className="tnum">{usd(item.gen.data.cost_usd)}</span>.
              </p>
              {item.gen.data.stopped_early && (
                <p className="text-fg-2 mt-1">
                  Generation stopped before the end of the file, so some chunks
                  produced nothing.
                </p>
              )}
              {item.gen.data.accepted > 0 && (
                <Link href="/approve" className="link inline-block mt-1.5">
                  Triage them
                </Link>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
}
