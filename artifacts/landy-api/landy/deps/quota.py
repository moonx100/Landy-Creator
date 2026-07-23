"""Quota enforcement dependency.

require_quota:
  Reads the current user's analyses_used / analyses_quota / quota_period_start.
  If the current period has rolled over (current date is past the period_start
  by >= 1 month), resets analyses_used to 0 and advances quota_period_start.
  Raises HTTP 429 if analyses_used >= analyses_quota after any reset.

Usage in route handlers:

    @router.post("/analyses")
    def create_analysis(
        auth: Tuple[Connection, Any] = Depends(get_current_user),
        _quota: None = Depends(require_quota),
    ):
        ...

Note: require_quota does NOT itself consume a quota slot. The route handler
must call consume_quota(conn, user_id) after successfully enqueuing the job,
to increment analyses_used atomically.
"""
from datetime import date
from typing import Tuple, Any

import sqlalchemy as sa
from fastapi import Depends, HTTPException

from landy.deps.auth import get_current_user


def require_quota(
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> None:
    """Raise 429 if the user has exhausted their analysis quota for this period."""
    conn, user = auth

    today = date.today()
    period_start: date = user.quota_period_start

    # Check if we've rolled into a new monthly period
    rolled_over = (today.year > period_start.year) or (
        today.year == period_start.year and today.month > period_start.month
    )

    if rolled_over:
        # Reset counter and advance period_start to today
        conn.execute(
            sa.text(
                "UPDATE users SET analyses_used = 0, quota_period_start = :today "
                "WHERE id = :uid"
            ),
            {"today": today, "uid": str(user.user_id)},
        )
        # After reset, the user has 0 used — always allow
        return

    if user.analyses_used >= user.analyses_quota:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Kuota analisis bulan ini telah habis "
                f"({user.analyses_used}/{user.analyses_quota}). "
                "Kuota akan diperbarui pada awal bulan berikutnya."
            ),
        )


def consume_quota(conn: sa.engine.Connection, user_id: str) -> None:
    """Atomically increment analyses_used by 1.

    Call this AFTER successfully enqueuing an analysis job — not before.
    """
    conn.execute(
        sa.text(
            "UPDATE users SET analyses_used = analyses_used + 1 WHERE id = :uid"
        ),
        {"uid": user_id},
    )
