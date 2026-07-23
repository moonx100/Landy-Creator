"""Add index on version_diffs(to_version) for fast diff lookups.

The version_diffs table and its RLS policy already exist (migration 0001).
This migration adds only the index needed for the
GET /api/documents/{doc_id}/versions/{ver_id}/diff endpoint.

Revision ID: 0007
Revises: 0006_risk_flags_job_id
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_version_diffs_to_version "
        "ON version_diffs (to_version)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_version_diffs_from_version "
        "ON version_diffs (from_version)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_version_diffs_to_version")
    op.execute("DROP INDEX IF EXISTS idx_version_diffs_from_version")
