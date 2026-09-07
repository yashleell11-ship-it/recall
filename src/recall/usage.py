"""Per-user daily spend on the paid API.

`RECALL_MAX_COST_USD` caps a single generation run. That was enough when one
person owned the instance; with open registration it is not, because nothing
stopped a user from starting run after run. This adds the missing dimension:
what one account may spend in a day, across every run it starts.

Deliberately a floor, not a ceiling: the check runs BEFORE a call, and the
call's own cost is only known after it returns, so a user can end a day
slightly over. The cap exists to stop a runaway, not to bill anyone exactly.
"""

import os
from datetime import datetime, timezone

DEFAULT_DAILY_CAP_USD = 1.0


def daily_cap_usd() -> float:
    return float(os.environ.get("RECALL_MAX_COST_USD_PER_USER_PER_DAY",
                                str(DEFAULT_DAILY_CAP_USD)))


def _today() -> str:
    return datetime.now(timezone.utc).isoformat()[:10]


def spent_today(conn, user_id: int) -> float:
    row = conn.execute(
        "SELECT cost_usd FROM usage_daily WHERE user_id = ? AND day = ?",
        (user_id, _today()),
    ).fetchone()
    return float(row["cost_usd"]) if row else 0.0


def record_spend(conn, user_id: int, cost_usd: float) -> None:
    if cost_usd <= 0:
        return
    conn.execute(
        "INSERT INTO usage_daily (user_id, day, cost_usd) VALUES (?,?,?)"
        " ON CONFLICT(user_id, day) DO UPDATE SET cost_usd = cost_usd + excluded.cost_usd",
        (user_id, _today(), cost_usd),
    )
    conn.commit()


def check_daily_budget(conn, user_id: int) -> None:
    """Raise HTTPException(429) when this account has already spent its day.

    Kept as one named call at the top of each generation entry point rather
    than inlined into the chunk loops — the loops are shared with other work
    and this has no business being tangled into them.
    """
    from fastapi import HTTPException

    cap = daily_cap_usd()
    spent = spent_today(conn, user_id)
    if spent >= cap:
        raise HTTPException(
            status_code=429,
            detail=(f"Daily generation limit reached (${spent:.2f} of ${cap:.2f}). "
                    "It resets at midnight UTC."),
        )
