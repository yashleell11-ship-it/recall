"""Per-unit generation guidance.

The content is prose and cannot be unit-tested for being *good*. What can be
tested is everything around it: that it lines up with the subject registry,
that an unresearched unit degrades to silence rather than a dangling header,
that it reaches the prompt, and that the traps reach the fact checker and NOT
the writer.
"""

import pytest

from recall.generate.prompts import KNOWLEDGE_GENERATE_SYSTEM, KNOWLEDGE_GENERATE_USER
from recall.generate.unit_guidance import (
    _UNITS,
    guidance_for,
    guidance_text,
    traps_text,
)
from recall.lpu import SUBJECTS


def test_every_guided_subject_is_a_real_subject():
    assert set(_UNITS) <= set(SUBJECTS)


def test_guidance_never_outruns_the_unit_list():
    """Guidance is indexed by unit number, so a seventh entry for a six-unit
    subject would be silently unreachable — and would mean the two lists have
    drifted apart."""
    for code, units in _UNITS.items():
        assert len(units) <= len(SUBJECTS[code]["units"]), code


def test_mth165_is_covered_end_to_end():
    for n in range(1, len(SUBJECTS["MTH165"]["units"]) + 1):
        g = guidance_for("MTH165", n)
        assert g is not None, n
        assert len(g.guidance.split()) >= 60, n
        assert g.traps, n


@pytest.mark.parametrize("code,unit", [
    ("MTH165", 0),      # 1-based: there is no unit zero
    ("MTH165", 7),      # past the end
    ("NOPE", 1),        # not a subject at all
    ("", 1),
])
def test_unresearched_lookups_are_none_not_errors(code, unit):
    assert guidance_for(code, unit) is None


def test_a_subject_with_no_guidance_yet_is_none_all_the_way_down():
    """Coverage is allowed to be partial, and it is going to be: a subject
    gets researched or it does not, and the generator has to work either
    way."""
    for code in set(SUBJECTS) - set(_UNITS):
        for n in range(1, len(SUBJECTS[code]["units"]) + 1):
            assert guidance_for(code, n) is None, (code, n)
            assert guidance_text(code, n) == ""
            assert traps_text(code, n) == ""


def test_the_code_is_matched_case_insensitively():
    assert guidance_for("mth165", 1) is not None


def test_an_unresearched_unit_leaves_no_gap_in_the_prompt():
    assert guidance_text("NOPE", 1) == ""
    assert traps_text("NOPE", 1) == ""


def test_a_researched_unit_is_its_own_paragraph():
    text = guidance_text("MTH165", 1)
    assert text.startswith("\n") and text.endswith("\n")
    assert "Cayley" in text


def test_the_prompt_actually_carries_the_guidance():
    prompt = KNOWLEDGE_GENERATE_USER.format(
        full_name="Mathematics for Engineers", topic_code="MTH165",
        unit_number=6, unit_name="Fourier Series",
        format_guidance="(paper shape)",
        unit_guidance=guidance_text("MTH165", 6), n=10,
    )
    assert "Dirichlet" in prompt
    assert "(paper shape)" in prompt


def test_the_traps_do_not_reach_the_writer():
    """A trap list is a checklist for the checker. Telling a model "never write
    a0 as the constant term" is a reliable way to get a0 as the constant
    term, so the writer is never shown one."""
    for unit in _UNITS["MTH165"]:
        for trap in unit.traps:
            assert trap not in KNOWLEDGE_GENERATE_SYSTEM
            assert trap not in guidance_text("MTH165", 1)


def test_traps_are_a_checklist_the_checker_can_read():
    text = traps_text("MTH165", 4)
    assert "Euler" in text
    assert text.count("\n- ") == len(guidance_for("MTH165", 4).traps)


# The maths-notation rule applies to subjects made of mathematics. It does not
# apply to the programming subjects, where `lambda`, `->` and `<=` are not bad
# notation for a symbol — they are the vocabulary being examined, and a card
# for INT108 that wrote a lambda as λ would be wrong rather than tidy.
_MATHS_SUBJECTS = ("MTH165", "MEC103")


def test_maths_guidance_is_written_in_human_notation():
    """The owner asked for maths that looks like maths. LaTeX and programming
    operators here would be copied straight onto the cards."""
    banned = ["\\frac", "\\int", "\\lambda", "lambda", "<=", ">=", "->", "sqrt("]
    for code in _MATHS_SUBJECTS:
        for i, unit in enumerate(_UNITS.get(code, ()), 1):
            blob = unit.guidance + " " + " ".join(unit.traps)
            for token in banned:
                assert token not in blob, f"{code} unit {i}: {token!r}"


def test_no_subject_smuggles_in_latex():
    """LaTeX is wrong everywhere, including in a programming subject."""
    for code, units in _UNITS.items():
        for i, unit in enumerate(units, 1):
            blob = unit.guidance + " " + " ".join(unit.traps)
            for token in ("\\frac", "\\int", "\\sum", "\\alpha", "$$"):
                assert token not in blob, f"{code} unit {i}: {token!r}"
