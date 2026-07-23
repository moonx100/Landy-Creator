"""Object storage module — S3-compatible (production) or local filesystem (dev).

At startup, `bootstrap_bucket()` probes the S3 endpoint. If it is reachable,
S3 mode is used for the rest of the process lifetime. If not (MinIO not running,
no credentials configured, etc.), the module transparently falls back to a local
filesystem backend stored at ~/.landy-dev-storage/.

Calling code (routes, worker) never needs to know which backend is active — the
public API (upload_bytes, download_bytes, delete_object, generate_presigned_url,
storage_key, is_local_mode) is identical in both modes.

Production deployment: always set S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY
to real values. S3 mode will be selected automatically.

Class B bucket — user-uploaded contracts (Indonesian Peraturan PDP class B
personal data). Objects are encrypted at rest (AES-256 SSE where supported).
"""
from __future__ import annotations

import pathlib
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from landy.config import settings
from landy.logging_setup import logger

# ── Backend state ─────────────────────────────────────────────────────────────
# Set by bootstrap_bucket() at startup. Never mutate elsewhere.
_backend: str = "s3"  # "s3" | "local"
_LOCAL_ROOT = pathlib.Path.home() / ".landy-dev-storage"


def is_local_mode() -> bool:
    """True when the local filesystem backend is active."""
    return _backend == "local"


# ── S3 client ─────────────────────────────────────────────────────────────────

def _client() -> "boto3.client":
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(
            signature_version="s3v4",
            connect_timeout=3,
            read_timeout=60,
            retries={"max_attempts": 2},
        ),
        region_name="us-east-1",
    )


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def bootstrap_bucket() -> None:
    """Probe S3; create bucket if needed; fall back to local storage on failure.

    Called once at API startup (and by the worker). Failures switch the process
    to local-filesystem mode — uploads remain functional without MinIO.
    """
    global _backend

    bucket = settings.s3_bucket_class_b
    client = _client()

    try:
        client.head_bucket(Bucket=bucket)
        logger.info("storage_s3_ok", bucket=bucket)
        _backend = "s3"

    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            try:
                client.create_bucket(Bucket=bucket)
                logger.info("storage_bucket_created", bucket=bucket)
                _backend = "s3"
            except Exception as create_exc:
                logger.warning(
                    "storage_s3_unreachable",
                    error=str(create_exc),
                    note="Switching to local filesystem storage",
                )
                _backend = "local"
        else:
            logger.warning(
                "storage_s3_unreachable",
                error=str(exc),
                note="Switching to local filesystem storage",
            )
            _backend = "local"

    except (EndpointConnectionError, Exception) as exc:
        logger.warning(
            "storage_s3_unreachable",
            error=str(exc),
            note="Switching to local filesystem storage",
        )
        _backend = "local"

    if _backend == "s3":
        # Enable server-side encryption (best-effort — some providers ignore this)
        try:
            client.put_bucket_encryption(
                Bucket=bucket,
                ServerSideEncryptionConfiguration={
                    "Rules": [
                        {
                            "ApplyServerSideEncryptionByDefault": {
                                "SSEAlgorithm": "AES256"
                            }
                        }
                    ]
                },
            )
        except ClientError:
            logger.warning(
                "storage_sse_config_skipped",
                bucket=bucket,
                note="Provider may handle SSE transparently",
            )
    else:
        _LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        logger.info(
            "storage_local_mode_active",
            path=str(_LOCAL_ROOT),
            note="Dev only — not encrypted. Set S3 env vars for production.",
        )


# ── Local filesystem helpers ──────────────────────────────────────────────────

def _local_path(key: str) -> pathlib.Path:
    """Resolve a storage key to an absolute local filesystem path.

    Guards against path traversal: the resolved path must remain inside
    _LOCAL_ROOT. Raises ValueError if it escapes.
    """
    # Normalise: strip leading slashes, collapse ".." segments
    parts = [p for p in key.replace("\\", "/").split("/") if p and p != ".."]
    candidate = _LOCAL_ROOT.joinpath(*parts).resolve()
    if not str(candidate).startswith(str(_LOCAL_ROOT.resolve())):
        raise ValueError(f"Path traversal attempt rejected: {key!r}")
    return candidate


# ── Public storage API ────────────────────────────────────────────────────────

def upload_bytes(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload bytes. Returns the storage key."""
    if _backend == "local":
        path = _local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("storage_local_upload", key=key, bytes=len(data))
        return key

    client = _client()
    client.put_object(
        Bucket=settings.s3_bucket_class_b,
        Key=key,
        Body=data,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )
    logger.info("storage_s3_upload", key=key, bytes=len(data))
    return key


def download_bytes(key: str) -> bytes:
    """Download and return raw bytes for a storage key."""
    if _backend == "local":
        path = _local_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Local storage object not found: {key}")
        data = path.read_bytes()
        logger.info("storage_local_download", key=key, bytes=len(data))
        return data

    client = _client()
    response = client.get_object(Bucket=settings.s3_bucket_class_b, Key=key)
    return response["Body"].read()


def delete_object(key: str) -> None:
    """Permanently delete a blob. Called by the retention cleanup job."""
    if _backend == "local":
        path = _local_path(key)
        if path.exists():
            path.unlink()
        logger.info("storage_local_delete", key=key)
        return

    client = _client()
    client.delete_object(Bucket=settings.s3_bucket_class_b, Key=key)
    logger.info("storage_s3_delete", key=key)


def generate_presigned_url(
    key: str,
    expires_in: int = 600,
    bearer_token: Optional[str] = None,
) -> str:
    """Generate a time-limited download URL.

    S3 mode: returns a standard presigned GET URL (no auth header needed).
    Local mode: returns an API path /api/storage/local/{key}?token={bearer}
      so the browser can fetch the file without needing to set a header.

    Args:
        key: Storage key (from storage_key()).
        expires_in: TTL in seconds (used for S3; ignored in local mode).
        bearer_token: The caller's session token — required in local mode
            so the serve endpoint can authenticate the download.
    """
    if _backend == "local":
        if not bearer_token:
            raise ValueError(
                "bearer_token is required for local-mode presigned URLs"
            )
        from urllib.parse import quote
        safe_key = quote(key, safe="/")
        return f"/api/storage/local/{safe_key}?token={bearer_token}"

    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_class_b, "Key": key},
        ExpiresIn=expires_in,
    )


def storage_key(user_id: str, document_id: str, version_no: int, filename: str) -> str:
    """Canonical storage key for a document version blob."""
    return f"documents/{user_id}/{document_id}/v{version_no}/{filename}"
