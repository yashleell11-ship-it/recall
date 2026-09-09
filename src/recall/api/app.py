"""HTTP API. Thin routes over recall.api.scheduling — logic lives in the service."""

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from recall.api import auth_routes, knowledge_routes, learn_routes, scheduling
from recall.api import teach_routes, tests_routes, upload_routes
from recall.api.deps import get_conn, get_current_user
from recall.db import connect, init_db
from recall.llm.client import LlmUnavailable
from recall.study import plan


class ReviewIn(BaseModel):
    card_id: int
    grade: int = Field(ge=1, le=4)


class DecideIn(BaseModel):
    ids: list[int]
    action: str


class SettingsIn(BaseModel):
    new_cards_per_day: int | None = Field(default=None, ge=0, le=500)
    daily_review_cap: int | None = Field(default=None, ge=1, le=2000)
    desired_retention: float | None = Field(default=None, ge=0.70, le=0.99)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Bring the schema up to date on boot.

    schema.sql is CREATE TABLE IF NOT EXISTS throughout, so this adds tables that
    a newer release introduced and never touches existing data. Without it, a
    database created before a feature landed 500s on that feature's first request
    — which is exactly what happened when test mode and explanations shipped.
    """
    try:
        conn = connect(os.environ.get("RECALL_DB", "recall.db"))
        init_db(conn)
        conn.close()
    except Exception as exc:  # noqa: BLE001 - never let this stop the server booting
        print(f"warning: could not ensure schema on startup: {exc}")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Recall", version="0.1.0", lifespan=_lifespan)
    # allow_credentials=True is needed for the session cookie to survive local
    # dev's cross-port setup (frontend :3210, backend :8077 — different
    # origins). Production serves both under one hostname through the shared
    # Caddy edge, so this is a no-op there. Starlette reflects the actual
    # matched origin when allow_origin_regex is set (never "*"), which is
    # required for allow_credentials to be legal at all — keep the regex
    # narrow to loopback for exactly that reason.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(LlmUnavailable)
    def _llm_unavailable(request: Request, exc: LlmUnavailable) -> JSONResponse:
        """One handler for every paid route.

        Without it, an upstream refusal — a rejected key, an exhausted
        balance, a rate limit — escapes as an unhandled 500. Starlette's
        server-error path runs OUTSIDE CORSMiddleware, so the browser never
        even sees the status: it sees a CORS failure and the client reports
        "could not reach the API", which is the one thing that definitely did
        not happen. Handled here, it comes back as a 502 with the actual
        reason, through the middleware, with the headers on it.
        """
        return JSONResponse(status_code=502, content={"detail": exc.detail})

    @app.get("/api/topics")
    def topics(user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
        return scheduling.topic_summary(conn, user_id)

    @app.get("/api/queue")
    def queue(topic: str | None = None, limit: int | None = None,
              user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
        return scheduling.build_queue(conn, user_id, topic_code=topic, limit=limit)

    @app.post("/api/review")
    def review(body: ReviewIn, user_id: int = Depends(get_current_user),
              conn=Depends(get_conn)):
        try:
            out = scheduling.record_review(conn, user_id, body.card_id, body.grade)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "card_id": out.card_id,
            "interval_days": round(out.interval_days, 3),
            "due_at": out.due_at,
            "stability": round(out.stability, 4),
            "difficulty": round(out.difficulty, 4),
        }

    @app.get("/api/pending")
    def pending(limit: int = 50, offset: int = 0, topic: str | None = None,
                user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
        clause = " AND t.code = ?" if topic else ""
        args: tuple = (topic,) if topic else ()
        rows = conn.execute(
            "SELECT c.id, c.kind, c.question, c.answer, c.cloze_text, c.origin,"
            " c.detail, t.code AS topic_code, ch.page_ref,"
            " s.filename AS source_filename"
            " FROM cards c JOIN topics t ON t.id = c.topic_id"
            " JOIN chunks ch ON ch.id = c.chunk_id"
            " JOIN sources s ON s.id = ch.source_id"
            f" WHERE c.state = 'pending' AND t.user_id = ?{clause}"
            " ORDER BY c.id LIMIT ? OFFSET ?",
            (user_id, *args, limit, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM cards c JOIN topics t ON t.id = c.topic_id"
            f" WHERE c.state = 'pending' AND t.user_id = ?{clause}", (user_id, *args)
        ).fetchone()["n"]
        return {"cards": [dict(r) for r in rows], "total": total}

    @app.post("/api/pending/decide")
    def decide(body: DecideIn, user_id: int = Depends(get_current_user),
              conn=Depends(get_conn)):
        if body.action not in ("approve", "reject"):
            raise HTTPException(status_code=422,
                                detail="action must be 'approve' or 'reject'")
        if not body.ids:
            return {"updated": 0}
        state = "active" if body.action == "approve" else "rejected"
        reason = None if body.action == "approve" else "rejected by hand"
        placeholders = ",".join("?" for _ in body.ids)
        # Scoped through topics.user_id: with more than one user's cards ever
        # sharing this table, an id list alone is not proof of ownership —
        # without this join, one user's approve/reject call could reach into
        # another user's pending queue by id.
        cur = conn.execute(
            "UPDATE cards SET state = ?, reject_reason = ?"
            f" WHERE state = 'pending' AND id IN ({placeholders})"
            " AND topic_id IN (SELECT id FROM topics WHERE user_id = ?)",
            (state, reason, *body.ids, user_id),
        )
        conn.commit()
        return {"updated": cur.rowcount}

    @app.post("/api/cards/{card_id}/suspend")
    def suspend_card(card_id: int, user_id: int = Depends(get_current_user),
                     conn=Depends(get_conn)):
        """Bin a card mid-review.

        This is the counterweight to cards being auto-approved: judgement moves
        from "triage thirty cards before you know whether any of them are good"
        to "drop the one card you just discovered is bad, at the moment you
        discover it". Suspended cards leave the queue and every paper, but are
        not deleted — the row stays, so the reviews already recorded against it
        still mean something to the scheduler fit.
        """
        cur = conn.execute(
            "UPDATE cards SET state = 'suspended'"
            " WHERE id = ? AND state IN ('active','pending')"
            " AND topic_id IN (SELECT id FROM topics WHERE user_id = ?)",
            (card_id, user_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"no card {card_id}")
        return {"ok": True, "card_id": card_id, "state": "suspended"}

    @app.get("/api/settings")
    def read_settings(user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
        return scheduling.get_settings(conn, user_id)

    @app.put("/api/settings")
    def write_settings(body: SettingsIn, user_id: int = Depends(get_current_user),
                       conn=Depends(get_conn)):
        return scheduling.update_settings(conn, user_id, body.model_dump())

    @app.get("/api/stats")
    def stats(user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
        return scheduling.stats(conn, user_id)

    @app.get("/api/study-plan")
    def study_plan(user_id: int = Depends(get_current_user),
                   conn=Depends(get_conn)):
        """What to do next, per subject. Reads only — no paid call, ever, on a
        GET: the web client prefetches these on route intent, so a paid GET
        would spend money on a hover."""
        return plan.study_plan(conn, user_id)

    @app.get("/api/sources")
    def sources(user_id: int = Depends(get_current_user), conn=Depends(get_conn)):
        rows = conn.execute(
            "SELECT s.id, s.filename, t.code AS topic_code, s.added_at,"
            " COALESCE(g.cards_accepted, 0) AS accepted,"
            " COALESCE(g.cards_rejected, 0) AS rejected,"
            " COALESCE(g.cost_estimate, 0.0) AS cost_estimate"
            " FROM sources s JOIN topics t ON t.id = s.topic_id"
            " LEFT JOIN gen_runs g ON g.source_id = s.id"
            " WHERE s.user_id = ? ORDER BY s.added_at DESC", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # Routers own their full /api paths, so they mount without a prefix.
    app.include_router(auth_routes.router)
    app.include_router(knowledge_routes.router)
    app.include_router(tests_routes.router)
    app.include_router(teach_routes.router)
    app.include_router(learn_routes.router)
    app.include_router(upload_routes.router)

    return app


app = create_app()


def bootstrap(db_path: str) -> None:
    """Create the database if it does not exist yet."""
    conn = connect(db_path)
    init_db(conn)
    conn.close()
