"""What a good card looks like for one specific unit of one specific subject.

`format_guidance` in prompts.py knows the shape of the PAPER — objective,
practical, subjective. This knows the shape of the SUBJECT: that unit 1 of
MTH165 is examined by asking you to find a rank, not to define one; that the
mistake students actually make in unit 6 is dropping the a_0/2.

It lives here rather than in `lpu.py` on purpose. `lpu.py` is the registry
that gets serialised into `topics.meta` and shipped to the browser on every
page load; this is several paragraphs per unit that only the generator and the
fact checker ever read. Putting it in the registry would put it in the DB and
then in the wire.

Everything here was researched per-unit and then checked by a second pass for
mathematical correctness before being written down, because a wrong condition
in guidance becomes a wrong condition on a card and then a wrong condition in
a student's memory. Where research found nothing solid, there is no entry —
`guidance_for` returning None is a supported answer, and the prompt simply
falls back to the paper-shape guidance alone.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitGuidance:
    """One unit's worth of "write cards like this"."""

    guidance: str
    """A paragraph, in the imperative, spliced into the generation prompt."""

    traps: tuple[str, ...] = ()
    """The specific errors students (and models) make in this unit. Shown to
    the fact checker as a checklist, not to the writer — telling a model
    "don't say X" is a reliable way to make it say X."""


# Keyed by topic code, indexed by unit number - 1, so the tuple's length must
# match that subject's `units` list in lpu.py. tests/test_unit_guidance.py
# enforces that; a unit list that grows without guidance is fine (None), a
# guidance list longer than the unit list is a bug.
_UNITS: dict[str, tuple[UnitGuidance, ...]] = {}


def guidance_for(topic_code: str, unit_number: int) -> UnitGuidance | None:
    """`unit_number` is 1-based, as shown to the student."""
    units = _UNITS.get((topic_code or "").strip().upper())
    if not units or not 1 <= unit_number <= len(units):
        return None
    return units[unit_number - 1]


def guidance_text(topic_code: str, unit_number: int) -> str:
    """The block to splice into a generation prompt, or "" when unresearched.

    Returns a leading blank line with the text so the prompt reads correctly
    either way — an empty slot leaves no gap, a filled one is its own
    paragraph.
    """
    g = guidance_for(topic_code, unit_number)
    return f"\n{g.guidance}\n" if g else ""


def traps_text(topic_code: str, unit_number: int) -> str:
    """The fact checker's per-unit checklist, or "" when unresearched."""
    g = guidance_for(topic_code, unit_number)
    if g is None or not g.traps:
        return ""
    listed = "\n".join(f"- {t}" for t in g.traps)
    return ("\nMistakes that are common in this unit specifically. Check every "
            "card against this list; a card that makes one of these is "
            '"wrong":\n' + listed + "\n")
