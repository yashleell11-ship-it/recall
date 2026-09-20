"""Yash Made Test routes. Thin over recall.mcq.service — logic lives there.

Three exception types, three statuses, and no fourth way of saying no:
`LookupError` -> 404 (including somebody else's attempt, which must be
indistinguishable from an id that never existed), `ValueError` -> 422,
`McqConflict` -> 409. Nothing here returns 200 with an error in the body.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from recall.api.deps import get_conn, get_current_user
from recall.mcq import service
from recall.mcq.service import McqConflict

router = APIRouter(tags=["mcq"])


class AttemptIn(BaseModel):
    subject_code: str
    #: Unit numbers as printed on the deck, 1-based. Order is irrelevant —
    #: the service canonicalises them, so [2,1] and [1,2] are one selection
    #: and therefore one leaderboard.
    units: list[int]
    #: 30, 60 or "full". Validated in the service rather than by a Literal so
    #: the 422 body says what the legal lengths are instead of listing a union.
    length: int | Literal["full"]


class AnswerIn(BaseModel):
    #: 1-based, into the attempt's own question list.
    position: int = Field(ge=1)
    #: 0-3 in the SHOWN option order — the only order the client has seen.
    chosen: int = Field(ge=0)


def _units_param(units: str) -> list[int]:
    """`units=1,2` from the query string. 422 on anything else."""
    try:
        return [int(part) for part in units.split(",") if part.strip()]
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"units must be comma-separated numbers, got {units!r}",
        ) from exc


def _length_param(length: str):
    return length if length == "full" else _int_or_422(length)


def _int_or_422(length: str) -> int:
    try:
        return int(length)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"length must be 30, 60 or 'full', got {length!r}",
        ) from exc


@router.get("/api/mcq/subjects")
def subjects(user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
    """The picker: every subject and unit in the registry, with live counts."""
    return service.list_subjects(conn)


@router.post("/api/mcq/attempts")
def create_attempt(body: AttemptIn, user_id: int = Depends(get_current_user),
                   conn=Depends(get_conn)):
    try:
        return service.create_attempt(conn, user_id, body.subject_code,
                                      body.units, body.length)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/mcq/attempts")
def list_attempts(user_id: int = Depends(get_current_user),
                  conn=Depends(get_conn)):
    return service.list_attempts(conn, user_id)


@router.get("/api/mcq/leaderboard")
def leaderboard(subject_code: str,
                units: str = Query(..., description="comma-separated, e.g. 1,2"),
                length: str = Query(..., description="30, 60 or full"),
                user_id: int = Depends(get_current_user),
                conn=Depends(get_conn)):
    try:
        return service.leaderboard(conn, subject_code, _units_param(units),
                                   _length_param(length))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/mcq/attempts/{attempt_id}")
def get_attempt(attempt_id: int, user_id: int = Depends(get_current_user),
                conn=Depends(get_conn)):
    try:
        return service.get_attempt(conn, user_id, attempt_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/mcq/attempts/{attempt_id}/answer")
def answer_attempt(attempt_id: int, body: AnswerIn,
                   user_id: int = Depends(get_current_user),
                   conn=Depends(get_conn)):
    """Record one answer and reveal it. A second answer to the same position is
    409, never an overwrite — the first click is the answer."""
    try:
        return service.answer_attempt(conn, user_id, attempt_id, body.position,
                                      body.chosen)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except McqConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/mcq/attempts/{attempt_id}/submit")
def submit_attempt(attempt_id: int, user_id: int = Depends(get_current_user),
                   conn=Depends(get_conn)):
    """Close and score. Submitting twice returns the stored result unchanged."""
    try:
        return service.submit_attempt(conn, user_id, attempt_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api/mcq/attempts/{attempt_id}")
def abandon_attempt(attempt_id: int, user_id: int = Depends(get_current_user),
                    conn=Depends(get_conn)):
    """Throw away an unfinished sitting. A submitted one is refused with 409 —
    that is a graded result, not clutter."""
    try:
        service.abandon_attempt(conn, user_id, attempt_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except McqConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}
