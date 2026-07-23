"""Add job_id column to risk_flags for per-run result scoping.

Without this column, re-triggering analysis on the same version accumulates
flags from multiple runs. Adding job_id lets the results endpoint return
exactly the findings from one run and keeps historical runs intact.

ON DELETE CASCADE: when a job is deleted (cascaded from user delete),
its risk_flags are deleted too.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "risk_flags",
        sa.Column(
            "job_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
            nullable=True,   # nullable so existing rows don't break
        ),
    )
    op.create_index("ix_risk_flags_job_id", "risk_flags", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_flags_job_id", "risk_flags")
    op.drop_column("risk_flags", "job_id")
