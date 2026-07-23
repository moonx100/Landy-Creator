"""S3-compatible object storage module.

All blob I/O goes through this module. Configure via env vars:
  S3_ENDPOINT_URL  — MinIO in dev; IDCloudHost IS3 / Biznet Gio NEO in prod
  S3_ACCESS_KEY    — access key
  S3_SECRET_KEY    — secret key
  S3_BUCKET_CLASS_B — bucket for user-uploaded contracts (Class B personal data)

Class A (statute corpus) uses a different bucket, added when that feature lands.

Key format: documents/{user_id}/{doc_id}/v{n}/{filename}
Never store a public URL in the DB — only storage_key. Generate presigned
URLs on-demand with a 10-minute TTL for authenticated downloads.
"""
import io
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from landy.config import settings
from landy.logging_setup import logger


def _client() -> "boto3.client":
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=60,
            retries={"max_attempts": 3},
        ),
        # MinIO ignores this; AWS requires it; set to a neutral value
        region_name="us-east-1",
    )


def bootstrap_bucket() -> None:
    """Create the Class-B bucket if absent; enable SSE-S3.

    Called at API startup. Failures are logged as warnings — the API remains
    healthy but uploads will fail with a clear error until storage is reachable.
    """
    bucket = settings.s3_bucket_class_b
    client = _client()
    try:
        client.head_bucket(Bucket=bucket)
        logger.info("storage_bucket_exists", bucket=bucket)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            client.create_bucket(Bucket=bucket)
            logger.info("storage_bucket_created", bucket=bucket)
        else:
            raise

    # Enable server-side encryption (AES-256).
    # MinIO supports this; Indonesian cloud providers that are AWS-compatible do too.
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
        # Some S3-compatible providers don't implement SSE configuration API
        # but still encrypt at rest. Log and continue.
        logger.warning("storage_sse_config_skipped", bucket=bucket,
                       note="Provider may handle SSE transparently")


def upload_bytes(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload bytes to the Class-B bucket. Returns the storage key."""
    client = _client()
    client.put_object(
        Bucket=settings.s3_bucket_class_b,
        Key=key,
        Body=data,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )
    logger.info("storage_upload", key=key, bytes=len(data))
    return key


def download_bytes(key: str) -> bytes:
    """Download and return raw bytes for a storage key."""
    client = _client()
    response = client.get_object(Bucket=settings.s3_bucket_class_b, Key=key)
    return response["Body"].read()


def delete_object(key: str) -> None:
    """Permanently delete a blob. Called by the retention cleanup job."""
    client = _client()
    client.delete_object(Bucket=settings.s3_bucket_class_b, Key=key)
    logger.info("storage_delete", key=key)


def generate_presigned_url(key: str, expires_in: int = 600) -> str:
    """Generate a time-limited GET URL (default 10 min). Never store this in the DB."""
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_class_b, "Key": key},
        ExpiresIn=expires_in,
    )


def storage_key(user_id: str, document_id: str, version_no: int, filename: str) -> str:
    """Canonical storage key for a document version blob."""
    return f"documents/{user_id}/{document_id}/v{version_no}/{filename}"
