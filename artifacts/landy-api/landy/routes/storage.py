"""Local storage serve endpoint.

GET /api/storage/local/{path:path}?token={bearer_token}

Used only when the local filesystem storage backend is active (dev/beta without
MinIO). In production, all downloads go through S3 presigned URLs — this route
is never called.

Security:
  - Token validated against the sessions table (same mechanism as all other
    authenticated routes, but via query param so the browser can follow the URL
    directly after window.open()).
  - Ownership check: the storage key path begins with
    "documents/{user_id}/..." — the authenticated user_id must match the
    user_id embedded in the key.
  - Path traversal prevention is enforced by storage._local_path().
"""
from __future__ import annotations

import mimetypes
from typing import Optional
from urllib.parse import unquote

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

import landy.storage as storage
from landy.database import engine
from landy.logging_setup import logger

router = APIRouter()


def _validate_session_token(token: str) -> Optional[str]:
    """Return user_id (str) if token is valid and not revoked, else None.

    Mirrors get_current_user semantics exactly:
      - sessions.id is the bearer token value
      - revoked = false (logged-out sessions are rejected)
      - expires_at > now()
      - user must be active
    """
    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                "SELECT s.user_id "
                "FROM sessions s "
                "JOIN users u ON u.id = s.user_id "
                "WHERE s.id         = :token "
                "  AND s.revoked    = false "
                "  AND s.expires_at > now() "
                "  AND u.is_active  = true"
            ),
            {"token": token},
        ).fetchone()
    return str(row.user_id) if row else None


@router.get("/storage/local/{path:path}")
def serve_local_file(
    path: str,
    token: str = Query(..., description="Bearer token from the session"),
) -> Response:
    """Serve a file from local dev storage, authenticated via query-param token.

    Only active in local storage mode. Returns 503 if called when S3 is active
    (should never happen — generate_presigned_url won't produce local URLs in
    that case).
    """
    if not storage.is_local_mode():
        raise HTTPException(
            status_code=503,
            detail="Local storage serve endpoint is only available in dev mode.",
        )

    # ── Authenticate ──────────────────────────────────────────────────────────
    user_id = _validate_session_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Token tidak valid atau sudah kadaluarsa.")

    # ── Ownership check ───────────────────────────────────────────────────────
    # Key format: documents/{user_id}/{doc_id}/v{n}/{filename}
    decoded_path = unquote(path).lstrip("/")
    parts = decoded_path.split("/")
    if len(parts) < 4 or parts[0] != "documents":
        raise HTTPException(status_code=400, detail="Storage key tidak valid.")

    key_user_id = parts[1]
    if key_user_id != user_id:
        logger.warning(
            "local_storage_ownership_mismatch",
            key_user_id=key_user_id,
            session_user_id=user_id,
        )
        raise HTTPException(status_code=403, detail="Akses ditolak.")

    # ── Read file ─────────────────────────────────────────────────────────────
    key = decoded_path
    try:
        data = storage.download_bytes(key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File tidak ditemukan di penyimpanan lokal.")
    except Exception as exc:
        logger.error("local_storage_serve_failed", key=key, error=str(exc))
        raise HTTPException(status_code=500, detail="Gagal membaca file dari penyimpanan lokal.")

    # ── Determine content type ────────────────────────────────────────────────
    filename = parts[-1] if parts else "download"
    content_type, _ = mimetypes.guess_type(filename)
    content_type = content_type or "application/octet-stream"

    logger.info("local_storage_served", key=key, user_id=user_id, bytes=len(data))

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )
