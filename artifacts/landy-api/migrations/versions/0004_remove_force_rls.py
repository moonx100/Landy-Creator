"""Remove FORCE ROW LEVEL SECURITY so the worker (running as table owner) can bypass RLS.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-23

Why: FORCE ROW LEVEL SECURITY subjects even the table owner to RLS policies.
The background worker process connects as the same DATABASE_URL user that
created the tables (i.e., the owner). Without this fix the worker cannot
claim queued jobs or write extraction results because app.current_user_id
is not set in the worker context.

With RLS enabled (but NOT forced), the rules are:
- All API requests (via get_current_user dep that sets app.current_user_id)
  are still subject to per-user RLS policies — no change in user-facing isolation.
- The table owner (DATABASE_URL user = worker) bypasses RLS silently,
  allowing it to see all rows across all users.

This is correct for a monolithic worker process owned by the operator.
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TABLES = [
    "documents",
    "document_versions",
    "clauses",
    "risk_flags",
    "suggested_edits",
    "version_diffs",
    "analysis_jobs",
    "usage_events",
]


def upgrade() -> None:
    for tbl in _TABLES:
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for tbl in _TABLES:
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
