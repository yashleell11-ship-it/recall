"""HTTP API. Thin routes over recall.api.scheduling — logic lives in the service."""

import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from recall.api import scheduling
from recall.api import teach_routes, tests_routes, upload_routes
from recall.db import connect, init_db

USER_ID = 1  # single user for now; every query already filters by it


def get_conn():
    conn = connect(os.environ.get("RECALL_DB", "recall.db"))
    try:
        yield conn
    finally:
        conn.close()


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


def create_app() -> FastAPI:
    app = FastAPI(title="Recall", version="0.1.0")
    # Private single-user app served over loopback: any localhost port is the
    # dev server, and pinning one port only breaks when that port is taken.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/topics")
    def topics(conn=Depends(get_conn)):
        return scheduling.topic_summary(conn, USER_ID)

    @app.get("/api/queue")
    def queue(topic: str | None = None, limit: int | None = None,
              conn=Depends(get_conn)):
        return scheduling.build_queue(conn, USER_ID, topic_code=topic, limit=limit)

    @app.post("/api/review")
    def review(body: ReviewIn, conn=Depends(get_conn)):
        try:
            out = scheduling.record_review(conn, USER_ID, body.card_id, body.grade)
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
                conn=Depends(get_conn)):
        clause = " AND t.code = ?" if topic else ""
        args: tuple = (topic,) if topic else ()
        rows = conn.execute(
            "SELECT c.id, c.kind, c.question, c.answer, c.cloze_text,"
            " t.code AS topic_code, ch.page_ref, s.filename AS source_filename"
            " FROM cards c JOIN topics t ON t.id = c.topic_id"
            " JOIN chunks ch ON ch.id = c.chunk_id"
            " JOIN sources s ON s.id = ch.source_id"
            f" WHERE c.state = 'pending'{clause}"
            " ORDER BY c.id LIMIT ? OFFSET ?",
            (*args, limit, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM cards c JOIN topics t ON t.id = c.topic_id"
            f" WHERE c.state = 'pending'{clause}", args
        ).fetchone()["n"]
        return {"cards": [dict(r) for r in rows], "total": total}

    @app.post("/api/pending/decide")
    def decide(body: DecideIn, conn=Depends(get_conn)):
        if body.action not in ("approve", "reject"):
            raise HTTPException(status_code=422,
                                detail="action must be 'approve' or 'reject'")
        if not body.ids:
            return {"updated": 0}
        state = "active" if body.action == "approve" else "rejected"
        reason = None if body.action == "approve" else "rejected by hand"
        placeholders = ",".join("?" for _ in body.ids)
        cur = conn.execute(
            f"UPDATE cards SET state = ?, reject_reason = ?"
            f" WHERE state = 'pending' AND id IN ({placeholders})",
            (state, reason, *body.ids),
        )
        conn.commit()
        return {"updated": cur.rowcount}

    @app.get("/api/settings")
    def read_settings(conn=Depends(get_conn)):
        return scheduling.get_settings(conn, USER_ID)

    @app.put("/api/settings")
    def write_settings(body: SettingsIn, conn=Depends(get_conn)):
        return scheduling.update_settings(conn, USER_ID, body.model_dump())

    @app.get("/api/stats")
    def stats(conn=Depends(get_conn)):
        return scheduling.stats(conn, USER_ID)

    @app.get("/api/sources")
    def sources(conn=Depends(get_conn)):
        rows = conn.execute(
            "SELECT s.id, s.filename, t.code AS topic_code, s.added_at,"
            " COALESCE(g.cards_accepted, 0) AS accepted,"
            " COALESCE(g.cards_rejected, 0) AS rejected,"
            " COALESCE(g.cost_estimate, 0.0) AS cost_estimate"
            " FROM sources s JOIN topics t ON t.id = s.topic_id"
            " LEFT JOIN gen_runs g ON g.source_id = s.id"
            " WHERE s.user_id = ? ORDER BY s.added_at DESC", (USER_ID,)
        ).fetchall()
        return [dict(r) for r in rows]

    # Routers own their full /api paths, so they mount without a prefix.
    app.include_router(tests_routes.router)
    app.include_router(teach_routes.router)
    app.include_router(upload_routes.router)

    return app


app = create_app()


def bootstrap(db_path: str) -> None:
    """Create the database if it does not exist yet."""
    conn = connect(db_path)
    init_db(conn)
    conn.close()
