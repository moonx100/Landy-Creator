"""Integration test: OTP verify rate limiting / lockout (LC-4).

Exercises the real /api/auth/login + /api/auth/verify endpoints against a
real Postgres so the rolling-window count in otp_verify_attempts is exercised
end to end, not mocked.

Run with:
    DATABASE_URL=... python -m pytest tests/test_otp_rate_limit.py -v
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from landy.database import engine

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping DB integration tests",
)


def _run(sql: str, params: dict | None = None):
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        return conn.execute(sa.text(sql), params or {})


@pytest.fixture(autouse=True)
def _clean_ip_bucket():
    """TestClient reports the client IP as the literal string "testclient",
    shared across every test in this module (and across separate pytest
    invocations against the same database). Since the rate limiter now
    correctly persists failed attempts outside the request transaction,
    leftover IP-scoped rows from a previous test — or a previous full-suite
    run within the rolling window — would otherwise trip the IP-level
    lockout for a test that never itself made anywhere near 15 failed
    attempts. Start and end each test with that bucket clean.
    """
    _run("DELETE FROM otp_verify_attempts WHERE ip_address = 'testclient'")
    yield
    _run("DELETE FROM otp_verify_attempts WHERE ip_address = 'testclient'")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEBUG_OTP", "true")
    from landy.config import settings
    settings.debug_otp = True
    from landy.main import app
    return TestClient(app)


@pytest.fixture
def test_user():
    uid = str(uuid.uuid4())
    email = f"otp-rl-{uid[:8]}@example.com"
    _run(
        "INSERT INTO users (id, email, display_name, is_active) "
        "VALUES (:id, :email, 'OTP RL Test', true)",
        {"id": uid, "email": email},
    )
    yield uid, email
    _run("DELETE FROM otp_verify_attempts WHERE identifier = :email", {"email": email})
    _run("DELETE FROM login_tokens WHERE user_id = :id", {"id": uid})
    _run("DELETE FROM sessions WHERE user_id = :id", {"id": uid})
    _run("DELETE FROM users WHERE id = :id", {"id": uid})


def _new_challenge(client: TestClient, email: str) -> str:
    resp = client.post("/api/auth/login", json={"email": email})
    assert resp.status_code == 200
    return resp.json()["challenge_id"]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_legitimate_first_attempt_succeeds(client, test_user):
    """A correct OTP on the first try must never be blocked by the limiter."""
    uid, email = test_user
    resp = client.post("/api/auth/login", json={"email": email})
    otp = resp.json()["debug_otp"]
    challenge_id = resp.json()["challenge_id"]

    verify = client.post(
        "/api/auth/verify", json={"challenge_id": challenge_id, "otp": otp}
    )
    assert verify.status_code == 200
    assert verify.json()["email"] == email


def test_brute_force_locks_out_identifier(client, test_user):
    """Repeated wrong OTPs against the same identifier hit the lockout."""
    uid, email = test_user
    challenge_id = _new_challenge(client, email)

    responses = []
    for _ in range(8):
        resp = client.post(
            "/api/auth/verify",
            json={"challenge_id": challenge_id, "otp": "000000"},
        )
        responses.append(resp.status_code)

    # First 5 are wrong-code 401s; once the identifier's failed-attempt count
    # reaches the threshold, subsequent calls must be 429 — never a silent
    # pass-through back to OTP comparison.
    assert responses.count(401) == 5
    assert responses[5:] == [429, 429, 429]

    # Even a correct OTP is now rejected — lockout fails closed, it doesn't
    # merely rate-limit wrong guesses while letting a lucky guess through.
    resp = client.post(
        "/api/auth/verify", json={"challenge_id": challenge_id, "otp": "111111"}
    )
    assert resp.status_code == 429


def test_lockout_message_does_not_confirm_identifier(client, test_user):
    """The 429 body must be identical whether or not the email exists."""
    _, email = test_user
    challenge_id = _new_challenge(client, email)
    for _ in range(6):
        client.post(
            "/api/auth/verify",
            json={"challenge_id": challenge_id, "otp": "000000"},
        )
    real_locked = client.post(
        "/api/auth/verify", json={"challenge_id": challenge_id, "otp": "000000"}
    )

    fake_challenge = str(uuid.uuid4())
    for _ in range(6):
        client.post(
            "/api/auth/verify",
            json={"challenge_id": fake_challenge, "otp": "000000"},
        )
    fake_locked = client.post(
        "/api/auth/verify", json={"challenge_id": fake_challenge, "otp": "000000"}
    )

    assert real_locked.status_code == fake_locked.status_code == 429
    assert real_locked.json()["detail"] == fake_locked.json()["detail"]


def test_lockout_expires_after_window(client, test_user):
    """Attempts older than the rolling window no longer count toward the limit."""
    uid, email = test_user
    challenge_id = _new_challenge(client, email)

    # Directly seed 5 failed attempts timestamped just outside the window,
    # rather than sleeping 15 real minutes in a test.
    for _ in range(5):
        _run(
            "INSERT INTO otp_verify_attempts (identifier, ip_address, success, created_at) "
            "VALUES (:identifier, 'testclient', false, :ts)",
            {
                "identifier": email.lower(),
                "ts": datetime.now(timezone.utc) - timedelta(minutes=16),
            },
        )

    resp = client.post(
        "/api/auth/login", json={"email": email}
    )
    challenge_id = resp.json()["challenge_id"]
    otp = resp.json()["debug_otp"]

    verify = client.post(
        "/api/auth/verify", json={"challenge_id": challenge_id, "otp": otp}
    )
    assert verify.status_code == 200


def test_ip_lockout_blocks_new_identifier_from_same_ip(client, test_user):
    """A flood of failures from one IP locks that IP even across different
    challenge_ids — the per-identifier bucket alone isn't enough."""
    uid, email = test_user

    responses = []
    for _ in range(17):
        fake_challenge = str(uuid.uuid4())
        resp = client.post(
            "/api/auth/verify",
            json={"challenge_id": fake_challenge, "otp": "000000"},
        )
        responses.append(resp.status_code)

    assert responses[-1] == 429
