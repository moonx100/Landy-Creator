"""Add document_comments table and has_tracked_changes column.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-23

Changes:
  - document_versions: add has_tracked_changes BOOLEAN NOT NULL DEFAULT FALSE
  - document_comments: new table storing comment bubbles extracted from DOCX files
  - RLS policy on document_comments: ownership via version_id → documents.user_id
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── has_tracked_changes on document_versions ──────────────────────────────
    op.execute(
        "ALTER TABLE document_versions "
        "ADD COLUMN has_tracked_changes BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # ── document_comments table ───────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE document_comments (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            version_id   UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            author       TEXT,
            comment_date TEXT,
            anchor_text  TEXT,
            body         TEXT NOT NULL,
            ordinal      INT  NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        "CREATE INDEX idx_document_comments_version "
        "ON document_comments (version_id)"
    )

    # ── Row-level security ────────────────────────────────────────────────────
    # The SYSTEM_WORKER bypass lets the background worker insert/read all rows.
    # API requests are scoped to the owning user via the version → document chain.
    op.execute("ALTER TABLE document_comments ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY document_comments_isolation ON document_comments
        USING (
            current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
            OR version_id IN (
                SELECT dv.id
                FROM document_versions dv
                JOIN documents d ON d.id = dv.document_id
                WHERE d.user_id = current_setting('app.current_user_id', true)::UUID
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_comments")
    op.execute(
        "ALTER TABLE document_versions "
        "DROP COLUMN IF EXISTS has_tracked_changes"
    )
