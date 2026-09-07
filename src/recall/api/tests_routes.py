"""Test mode routes. Thin over recall.testmode.service — logic lives there."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from recall.api.deps import get_conn, get_current_user
from recall.testmode import service

router = APIRouter(tags=["tests"])


class TestCreateIn(BaseModel):
    kind: str
    topic_code: str | None = None


class AnswerIn(BaseModel):
    ordinal: int = Field(ge=1)
    verdict: str
    seconds: int = Field(default=0, ge=0)


@router.post("/api/tests")
def create_test(body: TestCreateIn, user_id: int = Depends(get_current_user),
                conn=Depends(get_conn)):
    try:
        return service.create_test(conn, user_id, body.kind, body.topic_code)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/tests")
def list_tests(user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
    return service.list_tests(conn, user_id)


@router.get("/api/tests/{test_id}")
def get_test(test_id: int, user_id: int = Depends(get_current_user),
            conn=Depends(get_conn)):
    try:
        return service.get_test(conn, user_id, test_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/tests/{test_id}/answer")
def record_answer(test_id: int, body: AnswerIn,
                  user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
    try:
        return service.record_answer(conn, user_id, test_id, body.ordinal,
                                     body.verdict, body.seconds)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/tests/{test_id}/submit")
def submit_test(test_id: int, user_id: int = Depends(get_current_user),
                conn=Depends(get_conn)):
    try:
        return service.submit_test(conn, user_id, test_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
