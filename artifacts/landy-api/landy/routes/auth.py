"""Auth endpoints.

POST /api/auth/redeem  — redeem an invite code, create user, return session token
POST /api/auth/login   — step 1: send 6-digit OTP challenge; returns challenge_id
POST /api/auth/verify  — step 2: validate OTP + challenge_id, issue session token
GET  /api/auth/me      — current user profile + quota (requires Bearer token)
POST /api/auth/logout  — revoke the current session token (only this token, not all)

Login is a two-step OTP flow:
  1. Client POSTs email to /login → server generates OTP, stores sha256(OTP) in
     login_tokens, returns challenge_id.
     In dev/beta (settings.debug_otp=True), the plaintext OTP is also returned
     so testers can complete the flow without an email provider.
     In production, the email provider (Task #3) will send the OTP.
  2. Client POSTs challenge_id + 6-digit OTP to /verify → server checks hash,
     marks token used, issues a session.

Session tokens are random URL-safe strings stored in the sessions table.
No JWT — the DB is the source of truth so revocation is instant.
"""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Tuple, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from landy.config import settings
from landy.database import engine
from landy.deps.db import get_raw_conn
from landy.deps.auth import get_current_user
from landy.logging_setup import logger
from landy.models.auth import (
    RedeemInviteRequest,
    LoginRequest,
    LoginChallengeResponse,
    VerifyOTPRequest,
    LogoutResponse,
    SessionResponse,
    UserProfile,
)

router = APIRouter()

_OTP_TTL_MINUTES = 15

# OTP verify rate limiting (LC-4). Rolling window: lockout expires as old
# attempt rows age out of the window, so no separate lockout-state write is
# needed. Counts only failed attempts — a burst of correct verifications
# (e.g. a double-submit) must never lock a legitimate user out.
_OTP_RATE_LIMIT_WINDOW_MINUTES = 15
_OTP_MAX_FAILED_ATTEMPTS_PER_IDENTIFIER = 5
_OTP_MAX_FAILED_ATTEMPTS_PER_IP = 15
_RATE_LIMITED = HTTPException(
    status_code=429,
    detail="Terlalu banyak percobaan. Coba lagi dalam beberapa menit.",
)


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _create_session(conn: sa.engine.Connection, user_id: str) -> tuple[str, datetime]:
    """Insert a new session row and return (token, expires_at)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
    conn.execute(
        sa.text(
            "INSERT INTO sessions (id, user_id, expires_at, revoked) "
            "VALUES (:token, :user_id, :expires_at, false)"
        ),
        {"token": token, "user_id": user_id, "expires_at": expires_at},
    )
    return token, expires_at


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _recent_failed_attempts(
    conn: sa.engine.Connection, column: str, value: str
) -> int:
    """Count failed otp_verify_attempts rows for `column` = `value` within the
    rate-limit window. `column` is a fixed literal from this module, never
    request input — safe to interpolate into the query text.
    """
    row = conn.execute(
        sa.text(
            f"SELECT COUNT(*) AS n FROM otp_verify_attempts "
            f"WHERE {column} = :value AND success = false "
            f"AND created_at > now() - make_interval(mins => :window_minutes)"
        ),
        {"value": value, "window_minutes": _OTP_RATE_LIMIT_WINDOW_MINUTES},
    ).fetchone()
    return row.n


def _record_otp_attempt(
    conn: sa.engine.Connection, identifier: str, ip_address: str, success: bool
) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO otp_verify_attempts (identifier, ip_address, success) "
            "VALUES (:identifier, :ip_address, :success)"
        ),
        {"identifier": identifier, "ip_address": ip_address, "success": success},
    )


def _record_failed_attempt_committed(identifier: str, ip_address: str) -> None:
    """Persist a failed OTP attempt in its own transaction.

    `get_raw_conn` wraps the whole request in `engine.begin()`, which rolls
    back on any exception — and every failed-verify path raises one. Writing
    the attempt row through the request's own connection would therefore be
    rolled back along with it, silently erasing the rate limiter's own
    bookkeeping on every single failure. This uses an independent connection
    so the failed attempt survives regardless of what the request transaction
    does next.
    """
    with engine.begin() as record_conn:
        record_conn.execute(
            sa.text(
                "INSERT INTO otp_verify_attempts (identifier, ip_address, success) "
                "VALUES (:identifier, :ip_address, false)"
            ),
            {"identifier": identifier, "ip_address": ip_address},
        )


@router.post("/redeem", response_model=SessionResponse)
def redeem_invite(
    body: RedeemInviteRequest,
    conn: sa.engine.Connection = Depends(get_raw_conn),
) -> SessionResponse:
    """Redeem an invite code and create a new user account."""
    invite = conn.execute(
        sa.text(
            "SELECT code, email FROM invites "
            "WHERE code = :code AND redeemed_at IS NULL"
        ),
        {"code": body.invite_code},
    ).fetchone()

    if not invite:
        raise HTTPException(
            status_code=400,
            detail="Kode undangan tidak valid atau sudah digunakan.",
        )

    if invite.email and invite.email.lower() != body.email.lower():
        raise HTTPException(
            status_code=400,
            detail="Email tidak sesuai dengan kode undangan ini.",
        )

    existing = conn.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": body.email.lower()},
    ).fetchone()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Email sudah terdaftar. Silakan masuk.",
        )

    user = conn.execute(
        sa.text(
            "INSERT INTO users (email, display_name, analyses_quota) "
            "VALUES (:email, :display_name, :quota) "
            "RETURNING id, email, display_name, created_at"
        ),
        {
            "email": body.email.lower(),
            "display_name": body.display_name,
            "quota": settings.default_analyses_quota,
        },
    ).fetchone()

    conn.execute(
        sa.text(
            "UPDATE invites SET redeemed_at = now(), redeemed_by = :user_id "
            "WHERE code = :code"
        ),
        {"user_id": str(user.id), "code": body.invite_code},
    )

    token, expires_at = _create_session(conn, str(user.id))
    logger.info("invite_redeemed", email=body.email)

    return SessionResponse(
        token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        expires_at=expires_at,
    )


@router.post("/login", response_model=LoginChallengeResponse)
def login(
    body: LoginRequest,
    conn: sa.engine.Connection = Depends(get_raw_conn),
) -> LoginChallengeResponse:
    """Step 1 of login: generate a 6-digit OTP and return a challenge_id.

    The OTP is stored as sha256(otp) in login_tokens and expires in 15 minutes.
    In dev/beta mode (debug_otp=True), the plaintext OTP is included in the
    response so testers can proceed without an email provider.
    In production, the email provider (wired in Task #3) sends the OTP.
    """
    user = conn.execute(
        sa.text(
            "SELECT id, email, is_active FROM users WHERE email = :email"
        ),
        {"email": body.email.lower()},
    ).fetchone()

    # Return same response whether user exists or not to prevent enumeration.
    # If user not found or inactive, we still return 200 but never create a
    # login_token — the /verify step will always fail for unknown challenge_ids.
    if not user or not user.is_active:
        logger.info("login_noop", reason="user_not_found_or_inactive", email=body.email)
        # Return a fake challenge_id so the client flow continues identically.
        import uuid
        return LoginChallengeResponse(
            challenge_id=uuid.uuid4(),
            message="Kode OTP telah dikirim ke email Anda.",
            debug_otp=None,  # intentionally blank — no valid OTP exists
        )

    otp = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = _hash_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_OTP_TTL_MINUTES)

    row = conn.execute(
        sa.text(
            "INSERT INTO login_tokens (user_id, otp_hash, expires_at) "
            "VALUES (:user_id, :otp_hash, :expires_at) "
            "RETURNING id"
        ),
        {"user_id": str(user.id), "otp_hash": otp_hash, "expires_at": expires_at},
    ).fetchone()

    logger.info("otp_issued", user_id=str(user.id), debug=settings.debug_otp)

    # TODO Task #3: send OTP via email provider when debug_otp is False
    if not settings.debug_otp:
        logger.info("otp_email_todo", note="Email provider not yet configured — Task #3")

    return LoginChallengeResponse(
        challenge_id=row.id,
        message="Kode OTP telah dikirim ke email Anda.",
        debug_otp=otp if settings.debug_otp else None,
    )


@router.post("/verify", response_model=SessionResponse)
def verify_otp(
    body: VerifyOTPRequest,
    request: Request,
    conn: sa.engine.Connection = Depends(get_raw_conn),
) -> SessionResponse:
    """Step 2 of login: validate the OTP and issue a session token.

    Rate-limited per identifier (the email tied to the challenge) and per
    client IP (LC-4) — both checked before the OTP comparison is attempted,
    so a locked-out caller never gets a hash comparison to time against.
    On success: marks the login_token as used and creates a new session.
    On failure: raises 401 (same message for wrong OTP or expired/used token).
    """
    ip = _client_ip(request)
    _invalid = HTTPException(
        status_code=401,
        detail="Kode OTP tidak valid atau sudah kadaluarsa.",
    )

    # Look up the challenge by id alone (not yet comparing the OTP hash) so
    # we know which identifier bucket to rate-limit against. A challenge_id
    # that doesn't resolve to a real, still-valid token is bucketed by the
    # challenge_id itself — never by "does this email exist", which would
    # turn the rate limiter into an account-enumeration oracle.
    challenge_row = conn.execute(
        sa.text(
            "SELECT lt.id, lt.user_id, lt.otp_hash, lt.expires_at, lt.used, "
            "       u.email, u.display_name, u.is_active "
            "FROM login_tokens lt "
            "JOIN users u ON u.id = lt.user_id "
            "WHERE lt.id = :challenge_id"
        ),
        {"challenge_id": str(body.challenge_id)},
    ).fetchone()

    identifier = (
        challenge_row.email.lower()
        if challenge_row
        else f"challenge:{body.challenge_id}"
    )

    if _recent_failed_attempts(conn, "ip_address", ip) >= _OTP_MAX_FAILED_ATTEMPTS_PER_IP:
        logger.warning("otp_rate_limited", scope="ip", ip=ip)
        raise _RATE_LIMITED
    if (
        _recent_failed_attempts(conn, "identifier", identifier)
        >= _OTP_MAX_FAILED_ATTEMPTS_PER_IDENTIFIER
    ):
        logger.warning("otp_rate_limited", scope="identifier", ip=ip)
        raise _RATE_LIMITED

    def _fail() -> None:
        _record_failed_attempt_committed(identifier, ip)
        raise _invalid

    if not challenge_row:
        _fail()
    if challenge_row.used:
        _fail()
    if challenge_row.expires_at < datetime.now(timezone.utc):
        _fail()
    if not secrets.compare_digest(challenge_row.otp_hash, _hash_otp(body.otp)):
        _fail()
    if not challenge_row.is_active:
        _fail()

    # Mark token used (one-time)
    conn.execute(
        sa.text("UPDATE login_tokens SET used = true WHERE id = :id"),
        {"id": str(challenge_row.id)},
    )
    _record_otp_attempt(conn, identifier, ip, success=True)

    session_token, expires_at = _create_session(conn, str(challenge_row.user_id))
    logger.info("user_verified", user_id=str(challenge_row.user_id))

    return SessionResponse(
        token=session_token,
        user_id=challenge_row.user_id,
        email=challenge_row.email,
        display_name=challenge_row.display_name,
        expires_at=expires_at,
    )


@router.get("/me", response_model=UserProfile)
def get_me(
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> UserProfile:
    """Return the current user's profile and quota status."""
    conn, user = auth
    return UserProfile(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
        analyses_used=user.analyses_used,
        analyses_quota=user.analyses_quota,
        quota_period_start=user.quota_period_start,
        is_active=user.is_active,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> LogoutResponse:
    """Revoke only the current session token (not all sessions for the user).

    The token is read directly from the Authorization header so we can
    target exactly the presented session — no global logout side effects.
    """
    _, user = auth
    # get_current_user already validated this header; strip prefix
    bearer = request.headers.get("Authorization", "")
    token = bearer.removeprefix("Bearer ").strip()

    from landy.database import engine
    with engine.begin() as raw_conn:
        raw_conn.execute(
            sa.text(
                "UPDATE sessions SET revoked = true "
                "WHERE id = :token AND revoked = false"
            ),
            {"token": token},
        )

    logger.info("user_logout", user_id=str(user.user_id))
    return LogoutResponse()
