"""Tests for the debug_otp production guard in landy.config.Settings.

debug_otp must default to False and the app must refuse to construct
Settings when ENVIRONMENT=production and DEBUG_OTP=true — see
.claude/rules (Step 0, privacy-path P0).
"""
from __future__ import annotations

import pytest

from landy.config import Settings


def _settings(**overrides) -> Settings:
    base = {"database_url": "postgresql://u:p@localhost:5432/db"}
    base.update(overrides)
    return Settings(**base)


def test_debug_otp_defaults_false():
    assert _settings().debug_otp is False


def test_debug_otp_allowed_in_development():
    s = _settings(environment="development", debug_otp=True)
    assert s.debug_otp is True


def test_debug_otp_allowed_in_beta():
    s = _settings(environment="beta", debug_otp=True)
    assert s.debug_otp is True


def test_debug_otp_forbidden_in_production():
    with pytest.raises(RuntimeError, match="debug_otp"):
        _settings(environment="production", debug_otp=True)


def test_production_without_debug_otp_boots_fine():
    s = _settings(environment="production", debug_otp=False)
    assert s.debug_otp is False
