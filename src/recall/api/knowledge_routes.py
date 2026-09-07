"""Generate cards for a syllabus unit with nothing uploaded.

The paid counterpart to /api/sources/{id}/generate, for the case where there
is no source at all. Same shape of response, so the client's existing
GenerateResponse type covers both.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from recall.api.deps import get_conn, get_current_user
from recall.api.upload_routes import get_config, get_embed, get_llm_client
from recall.config import Config
from recall.generate.knowledge import (
    DEFAULT_CARDS_PER_UNIT,
    MAX_CARDS_PER_CALL,
    generate_for_unit,
    topic_units,
)
from recall.testmode import service
from recall.testmode.paper import ensure_coverage
from recall.testmode.service import KINDS
from recall.usage import check_daily_budget, record_spend

router = APIRouter(tags=["knowledge"])


class KnowledgeGenerateIn(BaseModel):
    unit: int = Field(ge=1, description="1-based unit number from the syllabus")
    count: int = Field(default=DEFAULT_CARDS_PER_UNIT, ge=1, le=MAX_CARDS_PER_CALL)


class PaperIn(BaseModel):
    kind: str = Field(description="class30 | mte40 | endterm100 | fullday")


@router.post("/api/topics/{topic_code}/paper")
def sit_a_paper(topic_code: str, body: PaperIn,
                user_id: int = Depends(get_current_user),
                conn=Depends(get_conn), cfg: Config = Depends(get_config),
                client=Depends(get_llm_client), embed=Depends(get_embed)):
    """Sit a real paper for this subject, generating what the deck is missing.

    The difference from POST /api/tests is what happens when the deck cannot
    cover the paper. That endpoint assembles from what exists and hands back
    an empty paper if that is nothing. This one works out which units the
    paper draws from, fills the gaps, and then assembles — so "no questions"
    stops being a possible outcome on a subject you have simply not uploaded
    anything for yet.
    """
    if body.kind not in KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"kind must be one of {', '.join(KINDS)}")

    row = conn.execute(
        "SELECT id, label, meta FROM topics WHERE user_id = ? AND code = ?",
        (user_id, topic_code),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no topic {topic_code!r}")

    units = topic_units(row["meta"])
    if not units:
        raise HTTPException(
            status_code=422,
            detail=f"{topic_code} has no syllabus units on record, so a paper "
                   "cannot be planned. Upload a source and generate from it.")

    meta = json.loads(row["meta"])
    # The same refusal create_test makes, made before any money is spent
    # rather than after: a paper the university will never set is practice
    # for nothing.
    if body.kind == "mte40" and meta.get("mte_exists") is False:
        raise HTTPException(
            status_code=422,
            detail=f"{topic_code} has no MTE at LPU "
                   f"({meta.get('ca_policy', 'CA/ETE only')})")

    check_daily_budget(conn, user_id)
    coverage = ensure_coverage(
        conn, cfg, client, user_id=user_id, topic_id=row["id"],
        topic_code=topic_code,
        full_name=meta.get("full_name") or row["label"],
        exam_format=meta.get("exam_format") or "written",
        units=units, kind=body.kind, embed=embed,
    )
    record_spend(conn, user_id, coverage.cost_usd)

    try:
        paper = service.create_test(conn, user_id, body.kind, topic_code)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    paper["generated"] = {
        "cards": coverage.generated,
        "rejected": coverage.rejected,
        "cost_usd": round(coverage.cost_usd, 6),
        "units": [i + 1 for i in coverage.units_touched],
        "deck_already_covered_it": coverage.already_covered,
    }
    return paper


@router.post("/api/topics/{topic_code}/generate")
def generate_from_knowledge(topic_code: str, body: KnowledgeGenerateIn,
                            user_id: int = Depends(get_current_user),
                            conn=Depends(get_conn),
                            cfg: Config = Depends(get_config),
                            client=Depends(get_llm_client),
                            embed=Depends(get_embed)):
    row = conn.execute(
        "SELECT id, label, meta FROM topics WHERE user_id = ? AND code = ?",
        (user_id, topic_code),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no topic {topic_code!r}")

    units = topic_units(row["meta"])
    if not units:
        raise HTTPException(
            status_code=422,
            detail=f"{topic_code} has no syllabus units on record, so there is "
                   "nothing to generate from. Upload a source instead.",
        )
    if body.unit > len(units):
        raise HTTPException(
            status_code=422,
            detail=f"{topic_code} has {len(units)} units; there is no unit {body.unit}",
        )

    check_daily_budget(conn, user_id)

    meta = json.loads(row["meta"])
    result = generate_for_unit(
        conn, cfg, client, user_id=user_id, topic_id=row["id"],
        topic_code=topic_code,
        full_name=meta.get("full_name") or row["label"],
        exam_format=meta.get("exam_format") or "written",
        unit_index=body.unit - 1, unit_name=units[body.unit - 1],
        n=body.count, embed=embed,
    )
    record_spend(conn, user_id, result.cost_usd)
    return {"accepted": result.accepted, "rejected": result.rejected,
            "cost_usd": round(result.cost_usd, 6),
            "stopped_early": result.stopped_early}
