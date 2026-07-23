"""Add login_tokens table for OTP-based auth challenge.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-23

The login flow is a two-step challenge:
  1. POST /api/auth/login  → generates a 6-digit OTP, stores sha256 hash here, returns challenge
  2. POST /api/auth/verify → validates OTP, deletes row, issues a session token

Tokens expire in 15 minutes and can only be used once.
No RLS on this table — tokens are identified by id+user_id, not the
current_user_id setting (which is only set after authentication is complete).
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE login_tokens (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            otp_hash    TEXT NOT NULL,
            expires_at  TIMESTAMPTZ NOT NULL,
            used        BOOLEAN NOT NULL DEFAULT false,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_login_tokens_user_id ON login_tokens (user_id)")
    op.execute(
        "CREATE INDEX idx_login_tokens_lookup ON login_tokens (id, used, expires_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS login_tokens CASCADE")
