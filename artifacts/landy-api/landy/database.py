"""Database engine.

The engine is created once at module import time and shared across the process.
Connection pooling is handled by SQLAlchemy's QueuePool.

RLS context is set per-request in landy/deps/auth.py — see that module for the
pattern. This module only owns the engine; deps own connection lifecycle.
"""
import sqlalchemy as sa
from sqlalchemy.pool import QueuePool

from landy.config import settings

engine = sa.create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"options": "-c client_encoding=UTF8"},
)
