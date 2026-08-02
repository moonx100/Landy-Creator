"""OTP verify attempt log — rate limiting / lockout (LC-4).

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-03

An invite-only beta with unlimited OTP verification attempts is
brute-forceable: a 6-digit OTP is 1,000,000 combinations, well within
reach of a scripted attacker inside the 15-minute token TTL.

This adds an append-only attempt log. Rate limiting is a rolling-window
count over this table (COUNT WHERE created_at > now() - window), not a
separate lockout-state column — the lockout expires naturally as old rows
age out of the window, and the counter store is the database, so it
survives a worker/API restart (Replit environment has no Redis).

`identifier` is the normalized email tied to the challenge when the
challenge_id resolves to a real user, or `challenge:<challenge_id>` when it
does not (unknown/expired/foreign challenge_id) — this buckets guessing
against a nonexistent or already-consumed challenge without ever branching
on "does this email exist", which would leak account existence.
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE otp_verify_attempts (
            id          BIGSERIAL PRIMARY KEY,
            identifier  TEXT NOT NULL,
            ip_address  TEXT NOT NULL,
            success     BOOLEAN NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Both lookups are "recent rows for X" — created_at trailing in the
    # index lets Postgres range-scan the window instead of sorting.
    op.execute(
        "CREATE INDEX idx_otp_attempts_identifier ON otp_verify_attempts "
        "(identifier, created_at)"
    )
    op.execute(
        "CREATE INDEX idx_otp_attempts_ip ON otp_verify_attempts "
        "(ip_address, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS otp_verify_attempts CASCADE")
