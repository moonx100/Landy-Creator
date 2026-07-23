"""Authenticated request dependency.

get_current_user:
  1. Extracts the Bearer token from the Authorization header.
  2. Validates it against the sessions table (not expired, not revoked).
  3. Checks the user is_active.
  4. Sets SET LOCAL app.current_user_id = '<uuid>' for Postgres RLS policies.
  5. Yields (conn, user_row) for the route handler.

The connection stays open and in-transaction for the lifetime of the request.
RLS policies on all protected tables read current_setting('app.current_user_id', true).
"""
from typing import Generator, Optional, Tuple, Any

import sqlalchemy as sa
from fastapi import Header, HTTPException

from landy.database import engine


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Generator[Tuple[sa.engine.Connection, Any], None, None]:
    """FastAPI dependency: authenticate + set RLS context.

    Yields (conn, user_row). Route handlers destructure as:
        conn, user = auth
    """
    token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip() or None

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Token autentikasi diperlukan.",
        )

    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                """
                SELECT
                    s.user_id,
                    u.email,
                    u.display_name,
                    u.is_active,
                    u.analyses_used,
                    u.analyses_quota,
                    u.quota_period_start,
                    u.created_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.id         = :token
                  AND s.revoked    = false
                  AND s.expires_at > now()
                """
            ),
            {"token": token},
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=401,
                detail="Sesi tidak valid atau sudah berakhir. Silakan masuk kembali.",
            )

        if not row.is_active:
            raise HTTPException(
                status_code=403,
                detail="Akun tidak aktif. Hubungi administrator.",
            )

        # Set RLS context for this transaction.
        # All subsequent queries on `conn` will be filtered by Postgres RLS policies
        # that read current_setting('app.current_user_id', true).
        conn.execute(
            sa.text("SET LOCAL app.current_user_id = :uid"),
            {"uid": str(row.user_id)},
        )

        yield conn, row
