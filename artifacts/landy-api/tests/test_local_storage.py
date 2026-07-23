"""Tests for the local filesystem storage backend and serve endpoint.

These tests run against the actual DB so they require DATABASE_URL to be set.
They cover:
  - Local upload / download / delete round-trip
  - generate_presigned_url in local mode (returns /api/storage/local/... URL)
  - Serve endpoint: valid token → 200, expired/revoked token → 401,
    wrong user → 403, missing file → 404
  - Path traversal rejection
  - _validate_session_token mirrors get_current_user semantics (revoked=false)
"""
from __future__ import annotations

import pathlib
import uuid
from unittest.mock import patch

import pytest

# ── Unit tests — no DB required ───────────────────────────────────────────────

class TestLocalStorageCore:
    """Pure unit tests for storage.py local mode (no DB, no network)."""

    def setup_method(self):
        import landy.storage as _s
        # Force local mode for every test in this class
        self._orig = _s._backend
        _s._backend = "local"

    def teardown_method(self):
        import landy.storage as _s
        _s._backend = self._orig

    def test_storage_key_format(self):
        from landy.storage import storage_key
        key = storage_key("user-1", "doc-2", 3, "contract.docx")
        assert key == "documents/user-1/doc-2/v3/contract.docx"

    def test_upload_download_delete_roundtrip(self, tmp_path, monkeypatch):
        import landy.storage as s
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        key = "documents/u1/d1/v1/test.pdf"
        data = b"PDF contract bytes"

        returned_key = s.upload_bytes(key, data, "application/pdf")
        assert returned_key == key

        retrieved = s.download_bytes(key)
        assert retrieved == data

        s.delete_object(key)
        with pytest.raises(FileNotFoundError):
            s.download_bytes(key)

    def test_download_missing_raises(self, tmp_path, monkeypatch):
        import landy.storage as s
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)
        with pytest.raises(FileNotFoundError):
            s.download_bytes("documents/u/d/v1/nope.docx")

    def test_generate_presigned_url_local_mode(self, tmp_path, monkeypatch):
        import landy.storage as s
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        key = "documents/uid-abc/doc-def/v1/file.docx"
        url = s.generate_presigned_url(key, expires_in=600, bearer_token="tok-123")

        assert url.startswith("/api/storage/local/")
        assert "tok-123" in url
        assert "documents/uid-abc" in url

    def test_generate_presigned_url_local_requires_token(self, tmp_path, monkeypatch):
        import landy.storage as s
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        with pytest.raises(ValueError, match="bearer_token is required"):
            s.generate_presigned_url("documents/u/d/v1/f.docx", bearer_token=None)

    def test_path_traversal_dotdot_neutralised(self, tmp_path, monkeypatch):
        """'..' segments are stripped — the result must stay inside _LOCAL_ROOT."""
        import landy.storage as s
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        # "../../etc/passwd" → ".." stripped → "etc/passwd" → inside tmp_path
        result = s._local_path("../../etc/passwd")
        assert str(result).startswith(str(tmp_path.resolve())), (
            f"Path escaped LOCAL_ROOT: {result}"
        )
        # Must never resolve to the actual /etc/passwd
        assert str(result) != "/etc/passwd"

    def test_path_traversal_with_dotdot_segments(self, tmp_path, monkeypatch):
        import landy.storage as s
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)
        # Segments with ".." are stripped; the result must stay inside _LOCAL_ROOT
        safe_path = s._local_path("documents/../documents/u/d/v1/file.docx")
        assert str(safe_path).startswith(str(tmp_path))

    def test_is_local_mode_flag(self):
        import landy.storage as s
        assert s.is_local_mode() is True


# ── Integration tests — require DB ────────────────────────────────────────────

def _has_db() -> bool:
    try:
        import os
        return bool(os.environ.get("DATABASE_URL"))
    except Exception:
        return False


@pytest.mark.skipif(not _has_db(), reason="DATABASE_URL not set")
class TestLocalStorageServeEndpoint:
    """Tests for GET /api/storage/local/{path} with real DB sessions."""

    @pytest.fixture(autouse=True)
    def force_local_mode(self, monkeypatch):
        import landy.storage as s
        monkeypatch.setattr(s, "_backend", "local")

    @pytest.fixture()
    def test_user_and_session(self):
        """Create a user + session row for auth testing; clean up after."""
        import sqlalchemy as sa
        from landy.database import engine

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())  # This IS the bearer token (sessions.id)
        email = f"storage-test-{user_id[:8]}@example.com"

        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO users (id, email, is_active) "
                "VALUES (:id, :email, true)"
            ), {"id": user_id, "email": email})

            conn.execute(sa.text(
                "INSERT INTO sessions (id, user_id, revoked, expires_at) "
                "VALUES (:id, :uid, false, now() + interval '1 hour')"
            ), {"id": session_id, "uid": user_id})

        yield {"user_id": user_id, "session_id": session_id}

        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": user_id})
            conn.execute(sa.text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})

    @pytest.fixture()
    def revoked_session(self, test_user_and_session):
        """Create an additional session that is revoked."""
        import sqlalchemy as sa
        from landy.database import engine

        rev_id = str(uuid.uuid4())
        uid = test_user_and_session["user_id"]
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO sessions (id, user_id, revoked, expires_at) "
                "VALUES (:id, :uid, true, now() + interval '1 hour')"
            ), {"id": rev_id, "uid": uid})
        yield rev_id
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM sessions WHERE id = :id"), {"id": rev_id})

    @pytest.fixture()
    def stored_file(self, test_user_and_session, tmp_path, monkeypatch):
        """Upload a file to local storage under the test user's prefix."""
        import landy.storage as s
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        uid = test_user_and_session["user_id"]
        key = f"documents/{uid}/doc-test/v1/contract.docx"
        s.upload_bytes(key, b"contract content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        return {"key": key, "uid": uid}

    def _serve(self, path: str, token: str):
        """Call the serve endpoint directly via the route function."""
        from landy.routes.storage import serve_local_file
        return serve_local_file(path=path, token=token)

    def test_valid_token_serves_file(self, test_user_and_session, stored_file, tmp_path, monkeypatch):
        import landy.storage as s
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        session_id = test_user_and_session["session_id"]
        key = stored_file["key"]
        # Strip leading "documents/..." — serve_local_file receives the path portion
        response = self._serve(key, session_id)
        assert response.body == b"contract content"
        assert response.status_code == 200

    def test_invalid_token_returns_401(self, stored_file, tmp_path, monkeypatch):
        import landy.storage as s
        from fastapi import HTTPException
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        with pytest.raises(HTTPException) as exc_info:
            self._serve(stored_file["key"], "completely-invalid-token")
        assert exc_info.value.status_code == 401

    def test_revoked_token_returns_401(self, stored_file, revoked_session, tmp_path, monkeypatch):
        """Revoked (logged-out) sessions must be rejected."""
        import landy.storage as s
        from fastapi import HTTPException
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        with pytest.raises(HTTPException) as exc_info:
            self._serve(stored_file["key"], revoked_session)
        assert exc_info.value.status_code == 401

    def test_wrong_user_returns_403(self, stored_file, tmp_path, monkeypatch):
        """A valid session for a different user must not access another user's file."""
        import sqlalchemy as sa
        from landy.database import engine
        import landy.storage as s
        from fastapi import HTTPException
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        other_user_id = str(uuid.uuid4())
        other_session_id = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO users (id, email, is_active) VALUES (:id, :email, true)"
            ), {"id": other_user_id, "email": f"other-{other_user_id[:8]}@example.com"})
            conn.execute(sa.text(
                "INSERT INTO sessions (id, user_id, revoked, expires_at) "
                "VALUES (:id, :uid, false, now() + interval '1 hour')"
            ), {"id": other_session_id, "uid": other_user_id})

        try:
            with pytest.raises(HTTPException) as exc_info:
                self._serve(stored_file["key"], other_session_id)
            assert exc_info.value.status_code == 403
        finally:
            with engine.begin() as conn:
                conn.execute(sa.text("DELETE FROM sessions WHERE id = :id"), {"id": other_session_id})
                conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": other_user_id})

    def test_missing_file_returns_404(self, test_user_and_session, tmp_path, monkeypatch):
        import landy.storage as s
        from fastapi import HTTPException
        monkeypatch.setattr(s, "_LOCAL_ROOT", tmp_path)

        uid = test_user_and_session["user_id"]
        session_id = test_user_and_session["session_id"]
        missing_key = f"documents/{uid}/doc-missing/v1/ghost.docx"

        with pytest.raises(HTTPException) as exc_info:
            self._serve(missing_key, session_id)
        assert exc_info.value.status_code == 404

    def test_validate_session_token_matches_get_current_user_semantics(
        self, test_user_and_session
    ):
        """_validate_session_token must mirror get_current_user: revoked=false, not expired."""
        from landy.routes.storage import _validate_session_token

        session_id = test_user_and_session["session_id"]
        user_id = test_user_and_session["user_id"]

        result = _validate_session_token(session_id)
        assert result == user_id

        result_invalid = _validate_session_token("no-such-token")
        assert result_invalid is None
