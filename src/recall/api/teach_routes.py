"""Teaching routes. Thin over recall.teach.explain — logic lives in the service."""

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from recall.config import load_config
from recall.db import connect
from recall.llm.client import DeepSeekClient, LlmResponse
from recall.teach.explain import explain_card

USER_ID = 1  # single user for now; every query already filters by it

router = APIRouter()


class ExplainIn(BaseModel):
    card_id: int


def get_conn():
    # Deliberately a second copy of the app's dependency rather than an import
    # from recall.api.app: the app imports this router, so importing back would
    # be a cycle. Same env var, same default, so both point at one database.
    conn = connect(os.environ.get("RECALL_DB", "recall.db"))
    try:
        yield conn
    finally:
        conn.close()


class DeferredClient:
    """Builds the real client on first use.

    A cached explanation must cost nothing, and that includes not constructing an
    HTTP client and not requiring an API key to exist, on a request that will
    never leave the process.
    """

    def __init__(self) -> None:
        self._inner: DeepSeekClient | None = None

    def complete_json(self, system: str, user: str) -> LlmResponse:
        if self._inner is None:
            try:
                cfg = load_config()
            except RuntimeError as exc:
                # Deferring the client means this route, unlike the upload
                # routes, cannot fail the missing key at dependency time. Say
                # so plainly instead of letting it become a bare 500 with a
                # plain-text body, which the contract forbids.
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            self._inner = DeepSeekClient(cfg)
        return self._inner.complete_json(system, user)


def get_llm() -> tuple[object, str]:
    """(client, model name) for the explanation route. The model name mirrors
    config.load_config's default so it can be read without an API key."""
    return DeferredClient(), os.environ.get("RECALL_MODEL", "deepseek-chat")


@router.post("/api/teach/explain")
def explain(body: ExplainIn, conn=Depends(get_conn), llm=Depends(get_llm)):
    client, model = llm
    try:
        out = explain_card(conn, client, user_id=USER_ID, card_id=body.card_id,
                           model=model)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "explanation": out.explanation,
        "source_quote": out.source_quote,
        "page_ref": out.page_ref,
        "topic_code": out.topic_code,
        "cached": out.cached,
    }
