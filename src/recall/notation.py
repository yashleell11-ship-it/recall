"""How mathematics is written, stated once and enforced in Python.

The rule is the owner's, in his words: *"let it be in human laguage not like
that <= stuff it should be like human understablable signs"*. A student
revising for an LPU paper reads ≤, not <=; ∫, not \\int; λ, not "lambda".

Two halves that must not drift apart:

`NOTATION_LAW` is the paragraph spliced into every prompt that produces prose
a student reads. It had grown to three near-identical copies — two in
teach/prompts.py, one in generate/prompts.py — which is how the rule quietly
becomes three different rules.

`check_notation` is the same rule as a check. Asking a model for something is
not the same as getting it, and the one lever that reliably works here is the
one that does not involve asking: generate, check in Python, and send it back
to be repaired. The check is deliberately narrow — it looks only for the
programming operators, LaTeX and spelled-out Greek that the law forbids
outright, so it can be trusted to be right rather than merely opinionated.

**Code is exempt, and that exemption is load-bearing.** `x <= 10` is correct
Python and wrong mathematics, and INT108 and CSE326 are programming courses.
Anything inside backticks is skipped.
"""

import re

NOTATION_LAW = """Write mathematics the way it is written on paper, not the way it is
typed into a machine. Use the real symbols — λ θ π ∫ ∑ √ ∞ ∂ Δ ± ≤ ≥ ≠ ≈ → °
— and real superscripts and subscripts where they exist: x², x³, xⁿ, A⁻¹, a₀,
aₙ. Write fractions as a/b, and set a long one on its own line if it needs the
room.

Never write LaTeX (\\frac{a}{b}, A^{-1}, \\lambda, \\int, $...$), never spell a
Greek letter out as "lambda" or "theta", and never use programming operators
for mathematics: no <=, >=, !=, ->, ==, and no * for multiply.

Code is the one exception, and it is quoted exactly as it would be typed —
`x <= 10` is correct Python and must not be prettified. Put code in backticks
so it is unmistakable."""

#: (pattern, what to write instead, the exact text to write when Python can make
#: the edit itself). Only the unambiguous ones: a check that cries wolf gets
#: switched off, and then the rule has no teeth at all.
#:
#: The third field is the difference between complaining and repairing. Where it
#: is set, `fix_notation` performs the substitution and there is nothing left to
#: complain about. Where it is None the edit needs judgement Python does not have,
#: so it stays a complaint and the writer is asked again.
#:
#: **Every programming operator here is None on purpose, and that is the whole
#: reason this field exists rather than a blanket repair.** The exemption below
#: covers code in backticks; it cannot cover code the writer FORGOT to fence, and
#: INT108 is Python and CSE326 is JavaScript. Repairing `if x == 10` to `if x =
#: 10` turns a comparison into an assignment, and `ptr->field` and `x <= 10` are
#: correct as typed. A rejected lesson costs a cent; a lesson that teaches a
#: first-year student broken Python with a verified lesson's authority is worse
#: than no lesson, which is the trade this whole codebase is built on. So an
#: unfenced operator stays a complaint — the writer is told to fence its code, and
#: in a mathematics unit to write the real symbol.
#:
#: Nothing here was ever observed causing a rejection either. The two MTH165 unit
#: 5 rejections were `^{n}`, `^{1}` and `^{4}`, every one of them a table lookup.
_BANNED: tuple[tuple[str, str, str | None], ...] = (
    (r"<=", "≤", None),
    (r">=", "≥", None),
    (r"!=", "≠", None),
    (r"==", "=", None),
    (r"->", "→", None),
    (r"\\frac\b", "a/b", None),
    (r"\\int\b", "∫", None),
    (r"\\sum\b", "∑", None),
    (r"\\sqrt\b", "√", None),
    (r"\\lambda\b|\\theta\b|\\alpha\b|\\beta\b|\\pi\b",
     "the Greek letter itself", None),
    (r"\$[^$\n]{1,80}\$", "no LaTeX math mode", None),
    # `2 * x`, `a*b` — multiplication typed as code. Not `**` (Python power in
    # a code span is already exempt) and not a lone asterisk used as a bullet.
    (r"(?<![\w*])[\w)\]]\s*\*\s*[\w(\[](?!\*)", "× or juxtaposition", None),
)

#: Every character Unicode actually gives a superscript for. This is the
#: whole set — there is no superscript π, no superscript θ, and no way to
#: stack "2π" or "π/4" at all.
_SUPERSCRIPT = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "−": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ",
    "h": "ʰ", "i": "ⁱ", "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ",
    "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ", "v": "ᵛ",
    "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}

#: The same for subscripts, and a smaller set — Unicode has no subscript b, c,
#: d, f, g, q, w, y or z, and no Greek at all.
_SUBSCRIPT = {
    "0": "\u2080", "1": "\u2081", "2": "\u2082", "3": "\u2083", "4": "\u2084",
    "5": "\u2085", "6": "\u2086", "7": "\u2087", "8": "\u2088", "9": "\u2089",
    "+": "\u208a", "-": "\u208b", "\u2212": "\u208b", "=": "\u208c",
    "(": "\u208d", ")": "\u208e",
    "a": "\u2090", "e": "\u2091", "h": "\u2095", "i": "\u1d62", "j": "\u2c7c",
    "k": "\u2096", "l": "\u2097", "m": "\u2098", "n": "\u2099", "o": "\u2092",
    "p": "\u209a", "r": "\u1d63", "s": "\u209b", "t": "\u209c", "u": "\u1d64",
    "v": "\u1d65", "x": "\u2093",
}

#: `x^{2}`, `A^{-1}`, `∫₀^{2π}` — the LaTeX brace form.
_BRACED_SUPERSCRIPT = re.compile(r"\^\{([^{}]{1,24})\}")

#: `∑_{i=1}`, `a_{n}`, `∫_{y}` — the same, one line lower.
_BRACED_SUBSCRIPT = re.compile(r"_\{([^{}]{1,24})\}")


def _as_superscript(content: str) -> str | None:
    """The real superscript for `content`, or None if Unicode has no way
    to write it.

    This is the difference between a rule with teeth and a rule that
    cannot be obeyed. `x^{2}` really should be `x²` and `A^{-1}` really
    should be `A⁻¹` — those exist. But an integral limit like `2π` or
    `π/4` has no superscript form at all, and banning `^{...}` outright
    demanded something impossible: MTH165 unit 5 (multiple integrals) was
    rejected twice in a row, entirely on limits like ∫₀^{2π}, with every
    complaint unfixable by construction. A gate nobody can satisfy is a
    gate that gets switched off, taking the useful part with it.
    """
    if not content:
        return None
    out = []
    for ch in content:
        mapped = _SUPERSCRIPT.get(ch.lower() if ch.isalpha() else ch)
        if mapped is None:
            return None
        out.append(mapped)
    return "".join(out)


def _as_subscript(content: str) -> str | None:
    """The real subscript for `content`, or None if Unicode has no way to write
    it. The sibling of `_as_superscript`, and a stricter one — `∫_{y}` has no
    form at all, because there is no subscript y."""
    if not content:
        return None
    out = []
    for ch in content:
        mapped = _SUBSCRIPT.get(ch.lower() if ch.isalpha() else ch)
        if mapped is None:
            return None
        out.append(mapped)
    return "".join(out)


def _edits(prose: str) -> list[tuple[int, int, str]]:
    """Every (start, end, replacement) the law makes mechanical.

    Offsets are into `prose`, which is the code-blanked copy — `strip_code`
    replaces a code span with spaces of the same length, so an offset found
    there addresses the same character in the original.
    """
    out: list[tuple[int, int, str]] = []
    for pattern, real, marker in ((_BRACED_SUPERSCRIPT, _as_superscript, "^"),
                                  (_BRACED_SUBSCRIPT, _as_subscript, "_")):
        for m in pattern.finditer(prose):
            content = m.group(1)
            written = real(content)
            if written is not None:
                out.append((m.start(), m.end(), written))
            elif len(content) == 1:
                # No real character for it — `∫_{y}` has none, there is no
                # subscript y — but the braces around a SINGLE character say
                # nothing that the marker alone does not, and `∫_y¹` is how it
                # is written by hand. Multi-character groups keep their braces,
                # because `∫_x²⁴` and `∫_{x²}⁴` are not the same claim.
                out.append((m.start(), m.end(), marker + content))
    for pattern, _instead, repair in _BANNED:
        if repair is None:
            continue
        for m in re.finditer(pattern, prose):
            out.append((m.start(), m.end(), repair))
    return out


def fix_notation(text: str) -> str:
    """Make every edit the law makes mechanical, and no others.

    This exists because asking cost money and did not work. MTH165 unit 5 is
    multiple integrals, so nearly every line of it carries an integral or a sum
    with limits, and the writer kept producing `∑_{i=1}^{n}` and `∫_{y}^{1}`.
    Those complaints are correct — ⁿ and ¹ are real characters — but notation
    faults are fatal after two attempts, so the unit was rejected and about a
    cent was spent to store nothing, twice.

    There is no judgement in `^{n}` → `ⁿ`. It is a table lookup, and Python does
    table lookups perfectly, so the gate should only ever reject what it cannot
    repair itself. What is left over is genuinely ambiguous: `a*b` may be a
    pointer or a glob, and a sentence containing `\frac{a}{b}` usually wants
    rewriting rather than patching.

    Code is untouched, for the same reason it is exempt from the check — `x <= 10`
    is correct Python and INT108 and CSE326 are programming courses.
    """
    if not text:
        return text
    prose = strip_code(text)
    edits = sorted(_edits(prose), key=lambda e: e[0])
    if not edits:
        return text
    # Overlaps are possible in principle (`<==`), and applying both would
    # corrupt the text. First match wins; the leftovers get complained about.
    kept: list[tuple[int, int, str]] = []
    for start, end, written in edits:
        if kept and start < kept[-1][1]:
            continue
        kept.append((start, end, written))
    out = text
    # Right to left, so an earlier edit cannot shift a later one's offsets.
    for start, end, written in reversed(kept):
        out = out[:start] + written + out[end:]
    return out


#: Spelled-out Greek in running prose. Word-boundaried and lower-cased so
#: "Lambda expression" and "Beta release" survive; only the standalone
#: mathematical use is caught.
_SPELLED_GREEK = re.compile(
    r"\b(lambda|theta|alpha|beta|gamma|sigma|omega|epsilon|delta)\b"
    r"(?=\s*(?:=|is|equals|\)|,|\.|\s+of\b))", re.IGNORECASE)

_CODE_SPAN = re.compile(r"`[^`]*`|```.*?```", re.S)


def strip_code(text: str) -> str:
    """Blank out anything in backticks, keeping offsets stable."""
    return _CODE_SPAN.sub(lambda m: " " * len(m.group(0)), text or "")


def check_notation(text: str) -> list[str]:
    """Every notation violation in `text`, as plain sentences. [] when clean.

    Returns the complaints rather than a bool so a repair pass can be told
    exactly what to fix, and so a human reading a rejection knows why.
    """
    prose = strip_code(text)
    found: list[str] = []
    for pattern, instead, _repair in _BANNED:
        for m in re.finditer(pattern, prose):
            snippet = prose[max(0, m.start() - 24):m.end() + 24].strip()
            found.append(f"wrote {m.group(0)!r} where mathematics wants "
                         f"{instead} — near: …{snippet}…")
    for pattern, real in ((_BRACED_SUPERSCRIPT, _as_superscript),
                          (_BRACED_SUBSCRIPT, _as_subscript)):
        for m in pattern.finditer(prose):
            written = real(m.group(1))
            if written is None:
                # Unicode has no form for this content (∫₀^{2π}, ∫₀^{π/4}, and
                # every `_{y}`). Allowed — see _as_superscript.
                continue
            snippet = prose[max(0, m.start() - 24):m.end() + 24].strip()
            found.append(f"wrote {m.group(0)!r} where mathematics wants "
                         f"{written} — near: …{snippet}…")
    for m in _SPELLED_GREEK.finditer(prose):
        snippet = prose[max(0, m.start() - 24):m.end() + 24].strip()
        found.append(f"spelled out {m.group(1)!r} instead of using the letter "
                     f"— near: …{snippet}…")
    return found


__all__ = ["NOTATION_LAW", "check_notation", "fix_notation", "strip_code"]
