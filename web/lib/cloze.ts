/**
 * Cloze parsing.
 *
 * Handles `{{c1::answer}}` and `{{c1::answer::hint}}`. Before the reveal a
 * deletion is a visible blank (the hint if there is one); after it, the text
 * is shown in place and marked, so the eye lands on what was being tested.
 */

export type ClozeSegment =
  | { kind: "text"; text: string }
  | { kind: "blank"; index: number; text: string; hint: string | null };

const CLOZE_RE = /\{\{c(\d+)::([\s\S]*?)(?:::([\s\S]*?))?\}\}/g;

export function parseCloze(source: string): ClozeSegment[] {
  const out: ClozeSegment[] = [];
  let last = 0;

  CLOZE_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = CLOZE_RE.exec(source)) !== null) {
    if (m.index > last) {
      out.push({ kind: "text", text: source.slice(last, m.index) });
    }
    out.push({
      kind: "blank",
      index: Number(m[1]),
      text: m[2],
      hint: m[3] ?? null,
    });
    last = m.index + m[0].length;
  }

  if (last < source.length) {
    out.push({ kind: "text", text: source.slice(last) });
  }
  return out.length ? out : [{ kind: "text", text: source }];
}
