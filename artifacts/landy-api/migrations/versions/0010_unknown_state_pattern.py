"""Unified "unknown state" schema pattern (LC-41).

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-02

Design decided by MV 2026-08-02 (Build Action Items LC-41): every
classification or parse step gets a representable operational outcome,
jointly constrained so a failure can never be stored as a benign value.

Changes:
  - version_diffs: materiality becomes nullable; classification_status
    ('ok'|'low_confidence'|'failed') + classification_error added; joint
    CHECK makes "failed but valued" and "ok but NULL" unrepresentable.
    'low_confidence' is reserved now (emitted later, gated on the eval set)
    so enabling it needs no second migration.
  - document_versions: tc_parse_status / tc_parse_note and
    comments_parse_status / comments_parse_note. NULL status = not
    applicable (e.g. PDF); 'failed' = the revision/comments layer could not
    be read, which is distinct from "no revisions"/"no comments".
  - analysis_jobs: summary_status ('ok'|'failed') — a failed document
    summary is recorded, never replaced by a raw text slice.
  - analysis_domain_runs: one row per domain attempt per job, so "no risk
    flags" is only derivable from a full set of 'ok' runs. Failure mode for
    risk flags is "no row at all", hence the status lives one level up.
  - usage_events: status ('ok'|'failed') + failure_stage — failed LLM calls
    are metered (NULL tokens, honest status) instead of invisible.
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── version_diffs: nullable materiality + classification status ──────────
    op.execute(
        "ALTER TABLE version_diffs DROP CONSTRAINT version_diffs_materiality_check"
    )
    op.execute(
        "ALTER TABLE version_diffs ALTER COLUMN materiality DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE version_diffs "
        "ADD COLUMN classification_status TEXT NOT NULL DEFAULT 'ok' "
        "CHECK (classification_status IN ('ok','low_confidence','failed'))"
    )
    op.execute(
        "ALTER TABLE version_diffs ADD COLUMN classification_error TEXT"
    )
    # Joint constraint: the invalid states are unrepresentable —
    #   * failed  → materiality must be NULL (no value may be fabricated)
    #   * ok / low_confidence → materiality must be present and valid
    op.execute(
        """
        ALTER TABLE version_diffs ADD CONSTRAINT version_diffs_materiality_state
        CHECK (
            (classification_status = 'failed' AND materiality IS NULL)
            OR (classification_status IN ('ok','low_confidence')
                AND materiality IN ('material','immaterial'))
        )
        """
    )

    # ── document_versions: parse status for the DOCX revision/comments layer ──
    op.execute(
        "ALTER TABLE document_versions "
        "ADD COLUMN tc_parse_status TEXT "
        "CHECK (tc_parse_status IN ('ok','failed'))"
    )
    op.execute("ALTER TABLE document_versions ADD COLUMN tc_parse_note TEXT")
    op.execute(
        "ALTER TABLE document_versions "
        "ADD COLUMN comments_parse_status TEXT "
        "CHECK (comments_parse_status IN ('ok','failed'))"
    )
    op.execute("ALTER TABLE document_versions ADD COLUMN comments_parse_note TEXT")

    # ── analysis_jobs: summary outcome ────────────────────────────────────────
    op.execute(
        "ALTER TABLE analysis_jobs "
        "ADD COLUMN summary_status TEXT "
        "CHECK (summary_status IN ('ok','failed'))"
    )

    # A job that crossed the majority-failure threshold refunds its quota
    # unit; the flag makes the refund visible and idempotent.
    op.execute(
        "ALTER TABLE analysis_jobs "
        "ADD COLUMN quota_refunded BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # ── analysis_domain_runs: one row per domain attempt ─────────────────────
    op.execute(
        """
        CREATE TABLE analysis_domain_runs (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            job_id      UUID NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
            domain_key  TEXT NOT NULL,
            status      TEXT NOT NULL CHECK (status IN ('ok','failed')),
            error       TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (job_id, domain_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_analysis_domain_runs_job ON analysis_domain_runs (job_id)"
    )
    op.execute("ALTER TABLE analysis_domain_runs ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY analysis_domain_runs_isolation ON analysis_domain_runs
        USING (
            current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
            OR job_id IN (
                SELECT j.id FROM analysis_jobs j
                WHERE j.user_id = current_setting('app.current_user_id', true)::UUID
            )
        )
        """
    )

    # ── usage_events: failed calls become meterable ──────────────────────────
    op.execute(
        "ALTER TABLE usage_events "
        "ADD COLUMN status TEXT NOT NULL DEFAULT 'ok' "
        "CHECK (status IN ('ok','failed'))"
    )
    op.execute("ALTER TABLE usage_events ADD COLUMN failure_stage TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE usage_events DROP COLUMN IF EXISTS failure_stage")
    op.execute("ALTER TABLE usage_events DROP COLUMN IF EXISTS status")

    op.execute("DROP TABLE IF EXISTS analysis_domain_runs")

    op.execute("ALTER TABLE analysis_jobs DROP COLUMN IF EXISTS quota_refunded")
    op.execute("ALTER TABLE analysis_jobs DROP COLUMN IF EXISTS summary_status")

    op.execute("ALTER TABLE document_versions DROP COLUMN IF EXISTS comments_parse_note")
    op.execute("ALTER TABLE document_versions DROP COLUMN IF EXISTS comments_parse_status")
    op.execute("ALTER TABLE document_versions DROP COLUMN IF EXISTS tc_parse_note")
    op.execute("ALTER TABLE document_versions DROP COLUMN IF EXISTS tc_parse_status")

    op.execute(
        "ALTER TABLE version_diffs DROP CONSTRAINT IF EXISTS version_diffs_materiality_state"
    )
    op.execute("ALTER TABLE version_diffs DROP COLUMN IF EXISTS classification_error")
    op.execute("ALTER TABLE version_diffs DROP COLUMN IF EXISTS classification_status")
    # Rows persisted with NULL materiality under 0010 cannot satisfy the old
    # NOT NULL + two-value CHECK. Downgrade removes them explicitly — they
    # represent failed classifications, which the old schema cannot express.
    op.execute("DELETE FROM version_diffs WHERE materiality IS NULL")
    op.execute("ALTER TABLE version_diffs ALTER COLUMN materiality SET NOT NULL")
    op.execute(
        "ALTER TABLE version_diffs ADD CONSTRAINT version_diffs_materiality_check "
        "CHECK (materiality IN ('material','immaterial'))"
    )
