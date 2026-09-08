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

#: (pattern, what to write instead). Only the unambiguous ones: a check that
#: cries wolf gets switched off, and then the rule has no teeth at all.
_BANNED: tuple[tuple[str, str], ...] = (
    (r"<=", "≤"),
    (r">=", "≥"),
    (r"!=", "≠"),
    (r"==", "="),
    (r"->", "→"),
    (r"\\frac\b", "a/b"),
    (r"\\int\b", "∫"),
    (r"\\sum\b", "∑"),
    (r"\\sqrt\b", "√"),
    (r"\\lambda\b|\\theta\b|\\alpha\b|\\beta\b|\\pi\b", "the Greek letter itself"),
    (r"\^\{", "a real superscript, x²"),
    (r"\$[^$\n]{1,80}\$", "no LaTeX math mode"),
    # `2 * x`, `a*b` — multiplication typed as code. Not `**` (Python power in
    # a code span is already exempt) and not a lone asterisk used as a bullet.
    (r"(?<![\w*])[\w)\]]\s*\*\s*[\w(\[](?!\*)", "× or juxtaposition"),
)

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
    for pattern, instead in _BANNED:
        for m in re.finditer(pattern, prose):
            snippet = prose[max(0, m.start() - 24):m.end() + 24].strip()
            found.append(f"wrote {m.group(0)!r} where mathematics wants "
                         f"{instead} — near: …{snippet}…")
    for m in _SPELLED_GREEK.finditer(prose):
        snippet = prose[max(0, m.start() - 24):m.end() + 24].strip()
        found.append(f"spelled out {m.group(1)!r} instead of using the letter "
                     f"— near: …{snippet}…")
    return found


__all__ = ["NOTATION_LAW", "check_notation", "strip_code"]
