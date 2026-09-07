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
from recall.usage import check_daily_budget, record_spend

router = APIRouter(tags=["knowledge"])


class KnowledgeGenerateIn(BaseModel):
    unit: int = Field(ge=1, description="1-based unit number from the syllabus")
    count: int = Field(default=DEFAULT_CARDS_PER_UNIT, ge=1, le=MAX_CARDS_PER_CALL)


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
