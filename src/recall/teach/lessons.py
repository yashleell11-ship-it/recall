"""Writing, checking and storing a lesson for one syllabus unit.

Offline by design. A lesson takes one to two minutes to write and costs money,
and the per-user daily cap is $1.00 with no resume path, so this is reached
from `recall lessons`, never from an HTTP request the student is waiting on.
The request path reads rows.

What is checked, in the order it is checked, cheapest first:

1. **Structure** — the shape the prompt asked for, in Python. A lesson missing
   its worked examples is not a lesson.
2. **Notation** — `recall.notation.check_notation`. Free, deterministic, and
   the one rule the owner stated in his own words.
3. **Re-derivation** — one fresh call per worked example, given only the
   question, compared in Python. This is the only check here with real teeth
   against a confidently wrong derivation, and it is honest about its reach:
   it catches wrong ANSWERS. Nothing cheap catches bad teaching.

A lesson that fails 1 or 2 is repaired once and re-checked; a lesson that
fails 3 is stored `status='suspect'` with the mismatch written into `notes`,
because a wrong worked example is exactly the thing a human should look at
rather than have silently deleted.
"""

import json
import re
from dataclasses import dataclass, field

from recall.api.scheduling import iso, utc_now
from recall.generate.knowledge import _synthetic_source_id, _unit_chunk_id
from recall.generate.unit_guidance import guidance_for
from recall.config import Config
from recall.notation import check_notation
from recall.teach.corpus import unit_passages
from recall.pipeline import _cost
from recall.teach.lesson_prompts import (
    DEFAULT_SHAPE,
    PASSAGES_PREFACE,
    EXAMPLES_PREFACE,
    GUIDANCE_PREFACE,
    LESSON_SYSTEM,
    LESSON_USER,
    REDERIVE_SYSTEM,
    REDERIVE_USER,
    SHAPE_BY_FORMAT,
)

#: A grounded lesson is long: five sections, two derivations shown line by
#: line, and a check. DeepSeek's default output cap is 4096 tokens, and
#: MTH165 unit 2 hit it twice — the json came back cut off mid-string, which
#: reads as "the model wrote nonsense" and is actually "we did not let it
#: finish". Sixteen tenths of a cent to learn that, twice.
_LESSON_MAX_TOKENS = 8000

#: How many worked examples a lesson must carry. Two, for the reason
#: unit_guidance gives about its own calibration pair: one cannot show a range,
#: and three starts to read as a problem set rather than a lesson.
_WORKED = 2
_MIN_SECTIONS, _MAX_SECTIONS = 3, 5
_MIN_CHECK = 2


@dataclass
class LessonResult:
    body: dict | None
    status: str                      #: 'draft' | 'suspect' | 'rejected'
    notes: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    lesson_id: int | None = None


def _loads(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _normalise_quote(text: str) -> str:
    """Whitespace and case only.

    Exactly `teach/explain.py`'s rule, and for its reason: a quote differing by
    a line break is still a real citation, one differing by a word is a
    paraphrase, and paraphrase is what this check exists to catch.
    """
    return re.sub(r"\s+", " ", text or "").strip().lower()


#: Text that is furniture rather than teaching. A page chunk spans several
#: pages, so a scraped site's navigation bar and its real content land in the
#: same passage and no passage-level filter separates them. What can be checked
#: is the QUOTE — the span that actually reaches the student.
_FURNITURE = (
    "reveal answer", "hide answer", "correct answer:", "try again",
    "ctrl+k", "view all updates", "mark all read", "you're offline",
    "exam center", "offline library", "request material", "loading…",
    "click here", "download pdf", "table of contents",
)

#: A citation shorter than this is not carrying a definition or a condition.
#: Six, not eight: the first grounded run was refused partly over
#: "det(A − λI) = 0", which is a real thing to cite even though it is not a
#: sentence.
_MIN_QUOTE_WORDS = 6

#: How much of a lesson must be anchored in the course material before the
#: lesson may be called grounded. Not all of it: a section that walks through
#: arithmetic is teaching a method, not a claim, and demanding a citation for
#: it only teaches the model to manufacture one.
_GROUNDED_SHARE = 0.5


def _quote_is_furniture(quote: str) -> str | None:
    """Why this quote is not worth citing, or None if it is fine."""
    low = " ".join((quote or "").split()).lower()
    if len(low.split()) < _MIN_QUOTE_WORDS:
        return f"is only {len(low.split())} words — too short to state anything"
    for marker in _FURNITURE:
        if marker in low:
            return (f"contains {marker!r}, which is page furniture from a "
                    "scraped site, not course material")
    return None


def check_grounding(body: dict, passages: list[dict]) -> list[str]:
    """Every section's quote must appear VERBATIM in the supplied passages.

    This is the only gate in the lesson pipeline with a floor under it. The
    re-derivation check asked a model to judge a model and was wrong every time
    it spoke; this asks Python whether a span of characters occurs in a
    document, and fluency cannot argue with the answer.

    Returns [] when no passages were supplied — an ungrounded lesson is not a
    failed one, it is a different and weaker thing, and the caller records
    which it is.
    """
    if not passages:
        return []
    haystack = " \u2016 ".join(_normalise_quote(p["text"]) for p in passages)
    out: list[str] = []
    for i, section in enumerate(body.get("sections") or [], 1):
        if not isinstance(section, dict):
            continue
        quote = str(section.get("quote") or "").strip()
        if not quote:
            # Not an error. A section may honestly have nothing to cite, and
            # demanding a citation for every one only teaches the model to
            # manufacture them — which is the failure this gate exists to
            # catch, arrived at from the other side. Whether ENOUGH of the
            # lesson is anchored is judged by grounded_share, once.
            continue
        elif _normalise_quote(quote) not in haystack:
            out.append(f"section {i} ({section.get('heading', '')!r}) quotes "
                       f"{quote[:70]!r}, which does not appear in the course "
                       "material — that is a paraphrase, not a citation")
        elif (why := _quote_is_furniture(quote)) is not None:
            # Verbatim and useless. The gate proves a span was copied, not that
            # it was worth copying, and a citation backed by a navigation bar
            # is a claim backed by nothing.
            out.append(f"section {i} ({section.get('heading', '')!r}) quotes "
                       f"{quote[:60]!r}, which {why}")
    return out


def drop_bad_citations(body: dict, passages: list[dict]) -> list[str]:
    """Remove every quote that cannot be verified, in place. Returns what went.

    Rejecting a whole lesson over a citation detail is the wrong trade: it
    throws away good teaching, costs a full generation, and — after three runs
    of it — was refusing lessons over `det(A − λI) = 0` being five words long.

    Dropping the quote certifies nothing, which is the only property that
    actually matters here. The section simply becomes uncited, and
    `grounded_share` decides whether enough of the lesson is left anchored for
    it to be called grounded at all. What is never allowed is a citation that
    is shown to the student and is not real.
    """
    gone: list[str] = []
    for i, section in enumerate(body.get("sections") or [], 1):
        if not isinstance(section, dict) or not str(section.get("quote") or "").strip():
            continue
        problem = check_grounding({"sections": [section]}, passages)
        if problem:
            gone.append(problem[0].replace("section 1", f"section {i}", 1))
            section.pop("quote", None)
            section.pop("source", None)
    return gone


def grounded_share(body: dict, passages: list[dict]) -> float:
    """What fraction of the lesson's sections carry a verified citation."""
    if not passages:
        return 0.0
    sections = [s for s in (body.get("sections") or []) if isinstance(s, dict)]
    if not sections:
        return 0.0
    haystack = " \u2016 ".join(_normalise_quote(p["text"]) for p in passages)
    good = sum(1 for s in sections
               if str(s.get("quote") or "").strip()
               and _normalise_quote(str(s["quote"])) in haystack
               and _quote_is_furniture(str(s["quote"])) is None)
    return good / len(sections)


def check_structure(body: dict) -> list[str]:
    """The shape the prompt asked for, verified rather than assumed."""
    out: list[str] = []
    if not isinstance(body.get("why"), str) or not body["why"].strip():
        out.append("no 'why': the lesson never says what the unit is for")

    sections = body.get("sections")
    if not isinstance(sections, list) or not (
            _MIN_SECTIONS <= len(sections) <= _MAX_SECTIONS):
        out.append(f"needs {_MIN_SECTIONS}-{_MAX_SECTIONS} sections, "
                   f"got {len(sections) if isinstance(sections, list) else 0}")
    else:
        for i, s in enumerate(sections, 1):
            if not isinstance(s, dict) or not str(s.get("body", "")).strip():
                out.append(f"section {i} has no body")
            elif len(str(s["body"]).split()) < 40:
                out.append(f"section {i} is {len(str(s['body']).split())} words"
                           " — a heading with a sentence under it is not teaching")

    worked = body.get("worked")
    if not isinstance(worked, list) or len(worked) != _WORKED:
        out.append(f"needs exactly {_WORKED} worked examples, "
                   f"got {len(worked) if isinstance(worked, list) else 0}")
    else:
        for i, w in enumerate(worked, 1):
            if not isinstance(w, dict):
                out.append(f"worked example {i} is malformed")
                continue
            steps = w.get("steps")
            if not isinstance(steps, list) or len(steps) < 2:
                out.append(f"worked example {i} has no derivation — the steps "
                           "are the whole point")
            if not str(w.get("answer", "")).strip():
                out.append(f"worked example {i} never reaches an answer")
            if not str(w.get("question", "")).strip():
                out.append(f"worked example {i} has no question")

    check = body.get("check")
    if not isinstance(check, list) or len(check) < _MIN_CHECK:
        out.append(f"needs at least {_MIN_CHECK} check questions")
    return out


def lesson_text(body: dict) -> str:
    """Every word a student would read, for the notation check."""
    parts = [str(body.get("why", ""))]
    for s in body.get("sections") or []:
        if isinstance(s, dict):
            parts += [str(s.get("heading", "")), str(s.get("body", ""))]
    for w in body.get("worked") or []:
        if isinstance(w, dict):
            parts += [str(w.get("question", "")), str(w.get("answer", ""))]
            parts += [str(x) for x in (w.get("steps") or [])]
    for c in body.get("check") or []:
        if isinstance(c, dict):
            parts += [str(c.get("question", "")), str(c.get("answer", "")),
                      str(c.get("why", ""))]
    return "\n".join(parts)


_NUM = re.compile(r"-?\d+(?:\.\d+)?")

#: Typographic forms of the same mathematics. The lesson is REQUIRED by the
#: notation law to write − (U+2212); the re-derivation call, which is told to
#: answer as compactly as possible, writes the ASCII hyphen. Comparing them
#: raw made the two rules fight each other, and the first run flagged
#: e^(−1/6) against e^(-1/6) as a contradiction.
_SAME_CHAR = str.maketrans({
    "\u2212": "-", "\u2013": "-", "\u2014": "-", "\u00d7": "*",
    "\u00f7": "/", "\u2044": "/", "\u2261": "=", "\u2245": "=",
    "\u2248": "=", "\u00a0": " ",
})

#: An answer with no digits and more than this many words is prose, and this
#: comparator has no business judging it.
_PROSE_WORDS = 6

#: How many independent cold solves must AGREE WITH EACH OTHER before their
#: disagreement with the lesson counts against the lesson. Two, because the
#: first run proved one is not enough: a single solve contradicted two
#: worked examples that were, on checking, both correct.
_REDERIVE_VOTES = 2


def _chars(text: str) -> str:
    """Same characters for the same mathematics, spacing untouched."""
    return (text or "").translate(_SAME_CHAR).strip().lower()


def _demote(status: str) -> str:
    """Everything this check can say is "not confirmed", never "wrong".

    Six lessons were written and the re-derivation flagged five worked
    examples. Every one that was then checked by hand — numpy for a rank and a
    3×3 inverse, a numerical derivative for an astroid's d²y/dx² — found the
    LESSON correct and the check mistaken, including twice where both cold
    solves agreed with each other and were both wrong in the same way.

    That is a structural result, not bad luck. The lesson is written with
    researched guidance and two calibrated worked examples in front of it; the
    re-solve gets a bare question and one attempt. The checker is weaker than
    the thing it checks, so it cannot convict, and a status that says "suspect"
    on this evidence is a queue of non-problems — which is how a check gets
    switched off, taking the useful part with it.

    So it annotates. Real correctness gating needs a source to check AGAINST,
    which is what the licensed corpus is for: `verify/judges.check_grounded`
    verifies a verbatim quote in Python, and that one cannot be talked out of.
    """
    return "unverified" if status == "draft" else status


def _refused(answer: str) -> bool:
    """Did the solver decline the question rather than answer it?"""
    return "cannotsolve" in re.sub(r"[\s_-]+", "", (answer or "").lower())


def _canon(text: str) -> str:
    """As above, with separators removed, for the containment test."""
    return re.sub(r"[\s,;$]+", "", _chars(text))


def is_adjudicable(claimed: str) -> bool:
    """Can string comparison honestly settle this answer?

    Only where the answer is determinate — a number, an expression, a matrix.
    On a design-thinking paper the answer is a sentence, and two correct
    sentences share almost no characters: the first run compared "They skipped
    Define…" against "Define; a point of view statement" and called the lesson
    suspect, when the two say the same thing.

    A check that cannot adjudicate must say so. Guessing in either direction is
    worse than the honest answer, because a review queue full of non-problems
    is how a check gets switched off, and a green tick nobody earned is how a
    wrong derivation reaches a student.
    """
    a = (claimed or "").strip()
    if not a:
        return False
    return bool(_NUM.search(a)) or len(a.split()) <= _PROSE_WORDS


def answers_agree(claimed: str, fresh: str) -> bool:
    """Do two answers to the same question say the same thing?

    Deliberately generous about form and strict about value: "x = 2" and "2"
    agree, "λ = 3, 5" and "3 and 5" agree, and − and - are the same sign.
    Only called when `is_adjudicable(claimed)`.
    """
    a, b = _canon(claimed), _canon(fresh)
    if not a or not b:
        return False
    if "cannotsolve" in b:
        return False
    if a == b or a in b or b in a:
        return True
    # Fall back to the numbers: same multiset of values, same answer. Signs
    # included — an inverse matrix with every sign flipped is a different
    # matrix, and that is a real defect this caught on the first run.
    #
    # Read off the SPACED text, not the squashed one: squashing turns the
    # comma in "3, 5" into nothing and the two roots into the single number
    # thirty-five.
    na = _NUM.findall(_chars(claimed).replace("^", " "))
    nb = _NUM.findall(_chars(fresh).replace("^", " "))
    if na and sorted(float(x) for x in na) == sorted(float(x) for x in nb):
        return True
    return False


def _rederive(client, cfg: Config, *, topic_code: str, full_name: str,
              unit_name: str, question: str) -> tuple[str, float]:
    resp = client.complete_json(
        REDERIVE_SYSTEM,
        REDERIVE_USER.format(topic_code=topic_code, full_name=full_name,
                             unit_name=unit_name, question=question))
    data = _loads(resp.content) or {}
    return (str(data.get("answer", "")),
            _cost(cfg, resp.prompt_tokens, resp.completion_tokens))


def write_lesson(conn, client, cfg: Config, *, user_id: int, topic_id: int,
                 topic_code: str, meta: dict, unit_number: int,
                 rederive: bool = True, ground: bool = True,
                 passage_limit: int = 8, embed=None,
                 _passages: list[dict] | None = None) -> LessonResult:
    """Write, check and store one lesson. `unit_number` is 1-based."""
    units = meta.get("units") or []
    if not 1 <= unit_number <= len(units):
        raise ValueError(
            f"{topic_code} has {len(units)} units; there is no unit {unit_number}")
    unit_name = units[unit_number - 1]
    full_name = meta.get("full_name") or topic_code
    shape = SHAPE_BY_FORMAT.get(meta.get("exam_format") or "", DEFAULT_SHAPE)

    guidance = guidance_for(topic_code, unit_number)
    guidance_block = (GUIDANCE_PREFACE.format(guidance=guidance.guidance)
                      if guidance and guidance.guidance else "")
    examples_block = ""
    if guidance and guidance.examples:
        shown = "\n\n".join(
            f"Q: {e.question}\nA: {e.answer}\nWorking: {e.detail}"
            for e in guidance.examples)
        examples_block = EXAMPLES_PREFACE.format(examples=shown)

    # Course material for this unit, if any has been loaded. What it buys is
    # the one check with a floor under it: a quote Python can find, or cannot.
    passages: list[dict] = list(_passages or [])
    if ground and not passages:
        # One query per thing the unit has to teach, not one for the unit.
        # The researched guidance names them — "Rolle's theorem and the Mean
        # Value Theorem", "L'Hospital's rule", "the Maclaurin formulas" — so
        # they are already written down and need no model call to discover.
        queries = [f"{unit_name}. {full_name}."]
        if guidance and guidance.guidance:
            queries += [part.strip()
                        for part in re.split(r"(?<=[.;])\s+", guidance.guidance)
                        if len(part.split()) >= 5]
        if guidance:
            queries += [e.question for e in guidance.examples if e.question]
        passages = unit_passages(conn, user_id=user_id, topic_id=topic_id,
                                 unit_name=unit_name, query=queries,
                                 limit=passage_limit, embed=embed)
    passages_block = ""
    if passages:
        shown = "\n\n".join(
            f"[{i}] {p['filename']} {p['page_ref']}\n{p['text']}"
            for i, p in enumerate(passages, 1))
        passages_block = PASSAGES_PREFACE.format(passages=shown)

    user = LESSON_USER.format(
        topic_code=topic_code, full_name=full_name, unit_number=unit_number,
        unit_count=len(units), unit_name=unit_name,
        all_units="; ".join(f"{i + 1}. {u}" for i, u in enumerate(units)),
        shape=shape, guidance=guidance_block,
        examples=examples_block + passages_block)

    cost = 0.0
    body: dict | None = None
    complaints: list[str] = []
    citation_notes: list[str] = []
    for attempt in (1, 2):
        prompt = user if attempt == 1 else (
            user + "\n\nYour previous attempt was rejected for these reasons. "
            "Fix every one and write the lesson again:\n- "
            + "\n- ".join(complaints))
        resp = client.complete_json(LESSON_SYSTEM, prompt,
                                    max_tokens=_LESSON_MAX_TOKENS)
        cost += _cost(cfg, resp.prompt_tokens, resp.completion_tokens)
        candidate = _loads(resp.content)
        if candidate is None:
            # Say WHICH failure it was. "not valid json" sent me looking at the
            # prompt when the reply had simply been truncated at the cap.
            cut_off = getattr(resp, "finish_reason", "stop") == "length"
            complaints = [
                "the reply was cut off at the token cap, so the json is "
                f"incomplete ({resp.completion_tokens} tokens) — the lesson is "
                "too long for the limit, not malformed"
                if cut_off else
                f"the reply was not valid json ({resp.completion_tokens} tokens)"
            ]
            continue
        # Citation problems are worth one repair — the model can usually pick a
        # better sentence when told which one failed — but they are not worth a
        # second full generation. On the last attempt they are dropped instead.
        fatal = check_structure(candidate) + check_notation(lesson_text(candidate))
        complaints = fatal + check_grounding(candidate, passages)
        body = candidate
        if not complaints:
            break
        if attempt == 2 and not fatal:
            dropped = drop_bad_citations(candidate, passages)
            complaints = []
            citation_notes.extend(dropped)
            break

    if body is None or complaints:
        return LessonResult(body, "rejected", complaints, cost)

    status, notes, check_cost = verify_worked(
        client, cfg, body, topic_code=topic_code, full_name=full_name,
        unit_name=unit_name) if rederive else ("draft", [], 0.0)
    cost += check_cost

    # Grounding outranks everything the re-derivation can say. Every section
    # quoted the course material and Python found every quote — that is a real
    # warranty, and it must not be talked down to "unverified" by a solver that
    # was wrong every time it spoke on the first six lessons.
    notes.extend(citation_notes)
    share = grounded_share(body, passages)
    if passages and share >= _GROUNDED_SHARE:
        status = "grounded"
        pct = round(100 * share)
        notes.insert(0, f"grounded: {pct}% of sections carry a quote found "
                        f"verbatim in {len(passages)} passages of course "
                        "material")
    elif passages:
        notes.insert(0, f"only {round(100 * share)}% of sections are anchored "
                        "in the course material — the citations that are there "
                        "were verified, but most of this is the model's own "
                        "knowledge")
    else:
        notes.append("no course material loaded for this unit — written from "
                     "the model's own knowledge, with nothing to check it "
                     "against")

    source_id = _synthetic_source_id(conn, user_id, topic_id)
    chunk_id = _unit_chunk_id(conn, source_id, unit_number - 1, unit_name)
    cur = conn.execute(
        "INSERT INTO lessons (chunk_id, topic_id, body_json, status, notes,"
        " model, cost_usd, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (chunk_id, topic_id, json.dumps(body, ensure_ascii=False), status,
         "\n".join(notes) or None, cfg.model, cost, iso(utc_now())))
    conn.commit()
    return LessonResult(body, status, notes, cost, int(cur.lastrowid))


def verify_worked(client, cfg: Config, body: dict, *, topic_code: str,
                  full_name: str, unit_name: str) -> tuple[str, list[str], float]:
    """Re-solve every worked example and judge the lesson on the result.

    Split out of `write_lesson` so that re-checking a stored lesson runs the
    SAME check rather than a second copy of it — a second opinion about what
    "verified" means, computed differently in a second place, is the drift this
    codebase keeps paying for.
    """
    notes: list[str] = []
    status = "draft"
    cost = 0.0
    unchecked = 0
    for i, w in enumerate(body["worked"], 1):
        claimed = str(w["answer"])
        if not is_adjudicable(claimed):
            # Not a failure and not a pass. Said out loud, because a lesson
            # nobody could check is a different thing from one that passed.
            unchecked += 1
            notes.append(
                f"worked example {i}: answer is prose, so re-solving it "
                "cannot confirm or contradict it — read this one yourself")
            continue
        # Two independent solves, not one. The first real run flagged both
        # of a lesson's worked examples; checked against numpy, the LESSON
        # was right both times and the single cold solve was wrong — once
        # by an arithmetic slip (k = 5 for k = 4) and once by dropping the
        # sign of det A, returning the exact negative of the true inverse.
        #
        # That is the shape of the problem: the checker is weaker than the
        # thing it checks. The lesson is written with researched guidance
        # and two calibrated examples in front of it; the re-solve gets a
        # bare question. So one disagreement is evidence about the SOLVER,
        # and only two solvers agreeing with each other and disagreeing
        # with the lesson is evidence about the lesson.
        votes = []
        for _ in range(_REDERIVE_VOTES):
            fresh, c = _rederive(client, cfg, topic_code=topic_code,
                                 full_name=full_name, unit_name=unit_name,
                                 question=str(w["question"]))
            cost += c
            votes.append(fresh)
            if answers_agree(claimed, fresh):
                break          # confirmed; a second opinion buys nothing
        else:
            if all(_refused(v) for v in votes):
                # Both solvers declined rather than answering differently:
                # agreement about the QUESTION, not disagreement about the
                # answer. Worth a note; not a verdict, for the reason below.
                status = _demote(status)
                notes.append(
                    f"worked example {i}: two fresh attempts both refused the "
                    "question as stated, so it is probably missing something a "
                    "solver needs — check the question, not the answer")
            elif answers_agree(votes[0], votes[1]):
                status = _demote(status)
                notes.append(
                    f"worked example {i}: the lesson answers "
                    f"{claimed[:80]!r}; solved fresh twice it came out "
                    f"{votes[0][:60]!r} and {votes[1][:60]!r}. Two solvers "
                    "agreeing is worth your eyes, not a conviction — on the "
                    "first run two agreeing solvers were both wrong")
            else:
                status = _demote(status)
                notes.append(
                    f"worked example {i}: two fresh attempts disagreed with "
                    f"each other ({votes[0][:40]!r} vs {votes[1][:40]!r}), "
                    "so this says the question is hard to solve cold, not "
                    "that the lesson is wrong — read this one yourself")
    if unchecked:
        status = _demote(status)
    return status, notes, cost


def recheck_lesson(conn, client, cfg: Config, *, user_id: int, lesson_id: int,
                   topic_code: str, full_name: str) -> LessonResult:
    """Re-run verification on a STORED lesson, leaving its text alone.

    The check improved after the first three lessons were written, and their
    stored verdicts were left saying the opposite of the truth: two worked
    examples marked `suspect` were confirmed correct against numpy, while the
    single cold solve that accused them was the thing in error.

    Rewriting the lesson to fix its label would have thrown away prose the
    owner was already reading in order to correct a judgement about it. So this
    re-judges instead: same body, same id, new status.

    Ownership arrives through `sources.user_id` — chunks carry no owner.
    """
    row = conn.execute(
        "SELECT l.id, l.body_json, ch.text AS unit"
        " FROM lessons l"
        " JOIN chunks ch ON ch.id = l.chunk_id"
        " JOIN sources s ON s.id = ch.source_id"
        " WHERE l.id = ? AND s.user_id = ?", (lesson_id, user_id)).fetchone()
    if row is None:
        raise LookupError(f"no lesson {lesson_id}")

    body = json.loads(row["body_json"])
    status, notes, cost = verify_worked(
        client, cfg, body, topic_code=topic_code, full_name=full_name,
        unit_name=row["unit"])
    conn.execute(
        "UPDATE lessons SET status = ?, notes = ?, cost_usd = cost_usd + ?"
        " WHERE id = ?",
        (status, "\n".join(notes) or None, cost, lesson_id))
    conn.commit()
    return LessonResult(body, status, notes, cost, lesson_id)


def latest_lesson(conn, user_id: int, topic_id: int, unit_name: str) -> dict | None:
    """The most recent lesson for one unit, or None.

    Joins `sources` and filters `s.user_id` — chunks carry no owner, so this is
    the only thing keeping one account's lessons out of another's.
    """
    from recall.generate.knowledge import knowledge_sha, unit_key

    row = conn.execute(
        "SELECT l.id, l.body_json, l.status, l.notes, l.created_at, ch.text AS unit"
        " FROM lessons l"
        " JOIN chunks ch ON ch.id = l.chunk_id"
        " JOIN sources s ON s.id = ch.source_id"
        " WHERE s.user_id = ? AND s.sha256 = ? AND l.topic_id = ?"
        " ORDER BY l.id DESC", (user_id, knowledge_sha(topic_id), topic_id)
    ).fetchall()
    for r in row:
        if unit_key(r["unit"]) == unit_key(unit_name):
            return {"id": r["id"], "body": json.loads(r["body_json"]),
                    "status": r["status"], "notes": r["notes"],
                    "created_at": r["created_at"], "unit": r["unit"]}
    return None


__all__ = ["LessonResult", "answers_agree", "check_grounding",
           "grounded_share",
           "check_structure",
           "is_adjudicable", "latest_lesson", "recheck_lesson",
           "verify_worked",
           "lesson_text", "write_lesson"]
