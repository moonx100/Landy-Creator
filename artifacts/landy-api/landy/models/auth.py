"""Pydantic models for auth endpoints.

Every request and response crossing an API boundary must be a typed Pydantic model.
No untyped dicts, no Any except where explicitly documented.
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from uuid import UUID
import pydantic


class RedeemInviteRequest(pydantic.BaseModel):
    invite_code: str = pydantic.Field(..., min_length=1, max_length=64)
    email: pydantic.EmailStr
    display_name: Optional[str] = pydantic.Field(None, max_length=120)


class LoginRequest(pydantic.BaseModel):
    email: pydantic.EmailStr


class LoginChallengeResponse(pydantic.BaseModel):
    """Returned by POST /api/auth/login when OTP has been issued.

    challenge_id must be passed back to POST /api/auth/verify.
    debug_otp is only populated when settings.debug_otp is True (dev/beta).
    In production, the OTP is sent via email (Task #3 wires the email provider).
    """
    challenge_id: UUID
    message: str = "Kode OTP telah dikirim ke email Anda."
    debug_otp: Optional[str] = None  # only set in dev/beta mode


class VerifyOTPRequest(pydantic.BaseModel):
    challenge_id: UUID
    otp: str = pydantic.Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class SessionResponse(pydantic.BaseModel):
    """Returned after successful redeem or verify."""
    token: str
    user_id: UUID
    email: str
    display_name: Optional[str]
    expires_at: datetime


class UserProfile(pydantic.BaseModel):
    """Returned by GET /api/auth/me."""
    user_id: UUID
    email: str
    display_name: Optional[str]
    created_at: datetime
    analyses_used: int
    analyses_quota: int
    quota_period_start: date
    is_active: bool


class LogoutResponse(pydantic.BaseModel):
    detail: str = "Berhasil keluar"
