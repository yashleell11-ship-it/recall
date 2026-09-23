"""Build Yash Made Test bank files from bank-workflow output, and check them.

A bank workflow returns {"banks": {"MTH165.u1": {subject, unit, questions,
before, checked, patched, dropped, reasons}, ...}}. This writes one
src/recall/mcq/bank/<code>_unit<n>.json per (subject, unit), with stable keys.

It also re-checks every "what does this print" question by RUNNING it —
Python with python3, JavaScript with node — independently of the verifier
agents. A verifier is a model, and a model can agree with a wrong key; an
interpreter cannot. Snippets that touch the DOM are skipped (node has none)
and reported as such rather than counted as passes.

The mismatch list is a lead, not a verdict: questions about a variable's
VALUE (never printed), input() prompts, and file preconditions all show up as
mismatches and have to be judged by hand. Every one found so far has been the
checker's limitation, not the question's — which is exactly why it only
reports, and never drops, on its own.

usage: python scripts/assemble_mcq_bank.py OUT_DIR WORKFLOW_OUTPUT [...]
"""
import json, os, re, subprocess, sys, tempfile
from collections import Counter, defaultdict
from difflib import SequenceMatcher

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from recall.lpu import SUBJECTS  # noqa: E402
from recall.mcq.bank import _as_read  # noqa: E402  (the seeder's own rule)

TIERS = ["easy", "medium", "hard", "max"]
# A bare "$" is not LaTeX: CSS [attr$=x], ^= selectors and regex anchors use
# it. Flag only LaTeX shapes — $...$ math, backslash commands, ^{} and _{}.
LATEX = re.compile(r"\$[^=\s)/'\"]|\\(frac|sqrt|cdot|times|left|right|begin|alpha|beta|theta|lambda|pi|int|sum|infty|le|ge|ne)\b|\^\{|_\{")
OUTPUT_Q = re.compile(r"\b(print|output|display|shows?|value of|result)\b", re.I)
DOM = re.compile(r"\b(document|window|alert|prompt|localStorage|addEventListener|querySelector)\b")


def _run(argv, code, suffix):
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
        f.write(code)
        path = f.name
    try:
        r = subprocess.run(argv + [path], capture_output=True, text=True, timeout=6,
                           stdin=subprocess.DEVNULL, cwd=tempfile.gettempdir())
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT", -1
    finally:
        os.unlink(path)


def run_py(code):
    return _run([sys.executable], code, ".py")


def run_js(code):
    if DOM.search(code) or code.lstrip().startswith("<"):
        return None, "DOM", -2
    return _run(["node"], code, ".js")


def canon(s):
    return "\n".join(line.rstrip() for line in s.strip().splitlines())


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def main(out_dir, sources):
    banks = {}
    for src in sources:
        data = json.load(open(src))
        banks.update(data.get("result", data)["banks"])
    by_subject = defaultdict(dict)
    for b in banks.values():
        by_subject[b["subject"]][b["unit"]] = b

    ex = {"checked": 0, "match": 0, "mismatch": [], "error": 0, "timeout": 0, "dom": 0}
    grand = 0
    for code in sorted(by_subject):
        units = SUBJECTS[code]["units"]
        print(f"\n######## {code} — {SUBJECTS[code]['full_name']}")
        for unit in sorted(by_subject[code]):
            b = by_subject[code][unit]
            kept, flags, seen = [], [], []
            for q in (dict(x) for x in b["questions"]):
                q.setdefault("code", "")
                q.setdefault("options_mono", False)
                hard_fail = (len(q["options"]) != 4 or not 0 <= q["correct"] <= 3
                             or len(q["why_wrong"]) != 4 or q["why_wrong"][q["correct"]].strip()
                             or q["difficulty"] not in TIERS
                             or len({_as_read(o, q["options_mono"]) for o in q["options"]}) != 4)
                if hard_fail:
                    flags.append(("DROPPED-invalid", q["q"][:60]))
                    continue
                if q["difficulty"] == "easy" and q["kind"] != "recall":
                    flags.append(("easy-scenario", q["q"][:60]))
                if any(LATEX.search(t) for t in [q["q"], q["explain"], *q["options"]]):
                    flags.append(("latex", q["q"][:60]))
                t = norm(q["q"] + " " + q["code"])
                if any(SequenceMatcher(None, t, s).ratio() > 0.9 for s in seen):
                    flags.append(("near-dup", q["q"][:60]))
                seen.append(t)
                runner = run_py if code == "INT108" else run_js if (code == "CSE326" and "console.log" in q["code"]) else None
                if runner and q["code"].strip() and q["options_mono"] and OUTPUT_Q.search(q["q"]):
                    ex["checked"] += 1
                    out, err, rc = runner(q["code"])
                    if out is None:
                        ex["dom" if err == "DOM" else "timeout"] += 1
                    elif rc != 0:
                        ex["error"] += 1
                    elif canon(out) == canon(q["options"][q["correct"]]):
                        ex["match"] += 1
                    else:
                        ex["mismatch"].append((f"{code} u{unit}", q["q"][:70], canon(q["options"][q["correct"]])[:40], canon(out)[:40]))
                kept.append(q)
            for i, q in enumerate(kept, 1):
                q["key"] = f"{code}-U{unit}-{i:03d}"
            tiers = Counter(q["difficulty"] for q in kept)
            print(f"  unit {unit}: {len(kept):>3} kept  (verifier patched {b.get('patched', 0)}, dropped {b.get('dropped', 0)})"
                  f"  | {' '.join(f'{t[0].upper()}{tiers.get(t, 0)}' for t in TIERS)}  | code {sum(1 for q in kept if q['code'])}")
            for kind, text in flags:
                print(f"      flag {kind}: {text}")
            grand += len(kept)
            path = os.path.join(out_dir, f"{code.lower()}_unit{unit}.json")
            json.dump({"subject_code": code, "unit": unit, "unit_label": units[unit - 1], "questions": kept},
                      open(path, "w"), ensure_ascii=False, indent=1)
    print(f"\nTOTAL: {grand}")
    print(f"EXECUTION: {ex['checked']} run | {ex['match']} match | {len(ex['mismatch'])} to judge by hand | "
          f"{ex['error']} raised (error-claim questions) | {ex['timeout']} timeout | {ex['dom']} DOM-only")
    for m in ex["mismatch"]:
        print(f"  ? {m[0]} {m[1]!r}\n      keyed={m[2]!r} ran={m[3]!r}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
