"""Restore FORCE RLS and add SYSTEM_WORKER bypass for the background worker.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-23

Problem:
  Migration 0004 removed FORCE ROW LEVEL SECURITY so the table owner
  (DATABASE_URL user) would bypass RLS in the worker. However, the API
  process connects as the same user, so API queries also bypassed RLS —
  any authenticated user could read other users' documents (IDOR).

Fix (two-part):
  1. Restore FORCE ROW LEVEL SECURITY on all 8 user-scoped tables so the
     table owner is again subject to RLS policies.
  2. Update each policy to recognise the literal token 'SYSTEM_WORKER'
     in app.current_user_id as an operator-level bypass, distinct from
     any real user UUID. The worker sets this token at the start of every
     transaction. The API layer never sets 'SYSTEM_WORKER' — it always
     sets the authenticated user's UUID from the validated session token —
     so a client cannot forge operator access through the API.

Security contract:
  - API requests: get_current_user dep sets app.current_user_id to the
    real user UUID → RLS policies filter to that user's rows only.
  - Worker process: sets app.current_user_id = 'SYSTEM_WORKER' at the
    start of each transaction → sees all rows across all users.
  - No DB role change is needed; both processes use DATABASE_URL.
"""
from alembic import op

revision = "0005"
down_revision = "0004"
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

# New policy SQL for each table.
# The SYSTEM_WORKER check comes first (fast constant equality) and
# short-circuits the UUID cast on the hot path.
_POLICY_SQL: dict[str, str] = {
    "documents": """
        CREATE POLICY user_isolation ON documents
            FOR ALL TO PUBLIC
            USING (
                current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
                OR user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
            )
    """,
    "document_versions": """
        CREATE POLICY user_isolation ON document_versions
            FOR ALL TO PUBLIC
            USING (
                current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
                OR document_id IN (
                    SELECT id FROM documents
                    WHERE user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
    """,
    "clauses": """
        CREATE POLICY user_isolation ON clauses
            FOR ALL TO PUBLIC
            USING (
                current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
                OR version_id IN (
                    SELECT dv.id
                    FROM   document_versions dv
                    JOIN   documents d ON d.id = dv.document_id
                    WHERE  d.user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
    """,
    "risk_flags": """
        CREATE POLICY user_isolation ON risk_flags
            FOR ALL TO PUBLIC
            USING (
                current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
                OR version_id IN (
                    SELECT dv.id
                    FROM   document_versions dv
                    JOIN   documents d ON d.id = dv.document_id
                    WHERE  d.user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
    """,
    "suggested_edits": """
        CREATE POLICY user_isolation ON suggested_edits
            FOR ALL TO PUBLIC
            USING (
                current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
                OR risk_flag_id IN (
                    SELECT rf.id
                    FROM   risk_flags rf
                    JOIN   document_versions dv ON dv.id = rf.version_id
                    JOIN   documents d ON d.id = dv.document_id
                    WHERE  d.user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
    """,
    "version_diffs": """
        CREATE POLICY user_isolation ON version_diffs
            FOR ALL TO PUBLIC
            USING (
                current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
                OR from_version IN (
                    SELECT dv.id
                    FROM   document_versions dv
                    JOIN   documents d ON d.id = dv.document_id
                    WHERE  d.user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
    """,
    "analysis_jobs": """
        CREATE POLICY user_isolation ON analysis_jobs
            FOR ALL TO PUBLIC
            USING (
                current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
                OR user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
            )
    """,
    "usage_events": """
        CREATE POLICY user_isolation ON usage_events
            FOR ALL TO PUBLIC
            USING (
                current_setting('app.current_user_id', true) = 'SYSTEM_WORKER'
                OR user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
            )
    """,
}


def upgrade() -> None:
    # 1. Drop old policies
    for tbl in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS user_isolation ON {tbl}")

    # 2. Recreate policies with SYSTEM_WORKER exception
    for tbl, sql in _POLICY_SQL.items():
        op.execute(sql)

    # 3. Restore FORCE ROW LEVEL SECURITY (undoes migration 0004)
    for tbl in _TABLES:
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Remove FORCE and revert to 0004 state (owner bypass, no SYSTEM_WORKER)
    for tbl in _TABLES:
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS user_isolation ON {tbl}")
