"""Resize statute_provisions.embedding from vector(768) to vector(1024).

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-02

The adopted dense embedding model is BGE-M3 (1024-dim); vector(768) was
mGTE's size — the schema was written against the model that was rejected
(Research — RAG decision register; Build Action Items LC-39).

The corpus is empty in v1 (`statutes` / `statute_provisions` carry 0 rows by
design), so this ALTER is free now. Once a corpus is seeded, the same change
would require a full re-embed and re-import — which is why this ships as its
own standalone migration ahead of any ingest work.
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard against silent data loss if this ever runs against a seeded
    # corpus: a USING cast between vector sizes is not meaningful, so the
    # column must be empty. Fail loudly rather than convert.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM statute_provisions WHERE embedding IS NOT NULL) THEN
                RAISE EXCEPTION
                    'statute_provisions.embedding contains data; resizing 768->1024 requires a re-embed, not an ALTER';
            END IF;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE statute_provisions "
        "ALTER COLUMN embedding TYPE vector(1024) USING NULL"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM statute_provisions WHERE embedding IS NOT NULL) THEN
                RAISE EXCEPTION
                    'statute_provisions.embedding contains data; downgrade requires a re-embed, not an ALTER';
            END IF;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE statute_provisions "
        "ALTER COLUMN embedding TYPE vector(768) USING NULL"
    )
