"""Unauthenticated database connection dependency.

Use ONLY for endpoints that run before a user session exists:
  - GET /api/healthz
  - POST /api/auth/redeem
  - POST /api/auth/login
  - Admin CLI scripts

All other endpoints must use get_current_user from landy.deps.auth, which sets
the RLS context on the connection.
"""
from typing import Generator

import sqlalchemy as sa

from landy.database import engine


def get_raw_conn() -> Generator[sa.engine.Connection, None, None]:
    """Yield a plain DB connection with no RLS context.

    The connection is wrapped in a transaction (engine.begin()) so SET LOCAL
    would scope correctly if needed. But no user context is set here.
    """
    with engine.begin() as conn:
        yield conn
