"""Test mode routes. Thin over recall.testmode.service — logic lives there.

The connection dependency is defined here rather than imported from
recall.api.app: app.py includes this router, so importing back from it would be
a circular import. The two are deliberately identical.
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from recall.db import connect
from recall.testmode import service

USER_ID = 1  # single user for now; every query already filters by it

router = APIRouter(tags=["tests"])


def get_conn():
    conn = connect(os.environ.get("RECALL_DB", "recall.db"))
    try:
        yield conn
    finally:
        conn.close()


class TestCreateIn(BaseModel):
    kind: str
    topic_code: str | None = None


class AnswerIn(BaseModel):
    ordinal: int = Field(ge=1)
    verdict: str
    seconds: int = Field(default=0, ge=0)


@router.post("/api/tests")
def create_test(body: TestCreateIn, conn=Depends(get_conn)):
    try:
        return service.create_test(conn, USER_ID, body.kind, body.topic_code)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/tests")
def list_tests(conn=Depends(get_conn)):
    return service.list_tests(conn, USER_ID)


@router.get("/api/tests/{test_id}")
def get_test(test_id: int, conn=Depends(get_conn)):
    try:
        return service.get_test(conn, USER_ID, test_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/tests/{test_id}/answer")
def record_answer(test_id: int, body: AnswerIn, conn=Depends(get_conn)):
    try:
        return service.record_answer(conn, USER_ID, test_id, body.ordinal,
                                     body.verdict, body.seconds)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/tests/{test_id}/submit")
def submit_test(test_id: int, conn=Depends(get_conn)):
    try:
        return service.submit_test(conn, USER_ID, test_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
