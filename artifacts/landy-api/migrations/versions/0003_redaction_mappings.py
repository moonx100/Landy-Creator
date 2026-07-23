"""Add redaction_mappings table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-23

Stores the reversible PII redaction map per document version so that:
- The worker can redact before any LLM call (keeps PII on-premises)
- The export step (Task 4) can re-expand tokens back to originals in the DOCX

Token format examples: [NIK_1], [NPWP_1], [EMAIL_1], [PHONE_1], [BANK_1], [ADDR_1]
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE redaction_mappings (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            version_id  UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            token       TEXT NOT NULL,
            original    TEXT NOT NULL,
            UNIQUE (version_id, token)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_redaction_mappings_version ON redaction_mappings (version_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS redaction_mappings CASCADE")
