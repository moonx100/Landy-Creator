"""Admin CLI for operator tasks.

Usage:
    python -m landy.admin seed-invites --count 10
    python -m landy.admin seed-invites --count 1 --email creator@example.com
    python -m landy.admin list-invites
    python -m landy.admin deactivate-user --email user@example.com

This CLI reads DATABASE_URL from the environment — never calls the HTTP API.
It requires ADMIN_SECRET to be set as a safeguard against accidental runs.
"""
import os
import secrets
import sys
from datetime import datetime, timezone

import click
import sqlalchemy as sa

from landy.config import settings
from landy.database import engine
from landy.logging_setup import configure_logging, logger

configure_logging()

_ADMIN_GUARD_CHECKED = False


def _require_admin_secret() -> None:
    """Abort unless ADMIN_SECRET env var matches settings."""
    provided = os.environ.get("ADMIN_SECRET", "")
    if provided != settings.admin_secret or not provided:
        click.echo(
            "ERROR: ADMIN_SECRET env var is missing or incorrect. "
            "Set it to the value in .env before running admin commands.",
            err=True,
        )
        sys.exit(1)


@click.group()
def cli() -> None:
    """LANDY Creator operator CLI — run from the project root with DATABASE_URL set."""
    _require_admin_secret()


@cli.command("seed-invites")
@click.option("--count", "-n", default=1, show_default=True, help="Number of invite codes to generate.")
@click.option("--email", default=None, help="Optional: restrict invite to a specific email address.")
def seed_invites(count: int, email: str | None) -> None:
    """Generate one or more invite codes and insert them into the invites table."""
    codes = [secrets.token_urlsafe(12) for _ in range(count)]

    with engine.begin() as conn:
        for code in codes:
            conn.execute(
                sa.text(
                    "INSERT INTO invites (code, email) VALUES (:code, :email)"
                ),
                {"code": code, "email": email.lower() if email else None},
            )

    click.echo(f"Created {count} invite code(s):")
    for code in codes:
        suffix = f"  (restricted to {email})" if email else ""
        click.echo(f"  {code}{suffix}")

    logger.info("admin_seed_invites", count=count, email_restricted=email is not None)


@cli.command("list-invites")
@click.option("--unused-only", is_flag=True, default=False, help="Only show unused codes.")
def list_invites(unused_only: bool) -> None:
    """List invite codes from the database."""
    with engine.begin() as conn:
        query = "SELECT code, email, created_at, redeemed_at FROM invites"
        if unused_only:
            query += " WHERE redeemed_at IS NULL"
        query += " ORDER BY created_at DESC"
        rows = conn.execute(sa.text(query)).fetchall()

    if not rows:
        click.echo("No invite codes found.")
        return

    for row in rows:
        status = "USED" if row.redeemed_at else "available"
        email_str = f"  email={row.email}" if row.email else ""
        click.echo(f"{row.code}  [{status}]{email_str}")


@cli.command("deactivate-user")
@click.option("--email", required=True, help="Email of the user to deactivate.")
def deactivate_user(email: str) -> None:
    """Set is_active=false for a user. Does not delete their data."""
    with engine.begin() as conn:
        result = conn.execute(
            sa.text(
                "UPDATE users SET is_active = false "
                "WHERE email = :email RETURNING id, email"
            ),
            {"email": email.lower()},
        ).fetchone()

    if not result:
        click.echo(f"No user found with email {email}.", err=True)
        sys.exit(1)

    click.echo(f"Deactivated user {result.email} (id={result.id})")
    logger.info("admin_deactivate_user", email=email)


if __name__ == "__main__":
    cli()
