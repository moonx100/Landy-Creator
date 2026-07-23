"""Document endpoints.

POST   /api/documents                             create document record
GET    /api/documents                             list user's documents (with latest version + job)
GET    /api/documents/{id}                        single document
DELETE /api/documents/{id}                        soft-delete
POST   /api/documents/{id}/versions              upload file → store blob → enqueue job
GET    /api/documents/{id}/versions              list versions for a document
GET    /api/documents/{id}/versions/{vid}/download  generate presigned download URL

Security: two independent layers of isolation
  1. Row-level security (FORCE): policies filter to the current user's rows
     via app.current_user_id set by the get_current_user dependency.
  2. Explicit WHERE user_id = :uid predicates in every query that touches
     user-owned rows. Correctness does not depend solely on RLS semantics.

The upload path (POST .../versions):
  1. Validate file type and size (max 20 MB)
  2. Compute SHA-256 for deduplication and integrity audit trail
  3. Upload to MinIO (private bucket, AES-256 server-side encryption)
  4. Create document_version with extraction_ok=False (worker updates it)
  5. Create analysis_job with state='queued'
  6. Consume one quota unit
"""
import hashlib
from typing import Optional, Tuple, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from landy.deps.auth import get_current_user
from landy.deps.quota import consume_quota, require_quota
from landy.logging_setup import logger
from landy.models.documents import (
    AnalysisJobResponse,
    CreateDocumentRequest,
    DocumentListItem,
    DocumentResponse,
    PresignedDownloadResponse,
    VersionResponse,
    VersionUploadResponse,
)
import landy.storage as storage

router = APIRouter()

_ALLOWED_EXTENSIONS = {"docx", "pdf", "jpg", "jpeg", "png", "webp"}
_ALLOWED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


def _file_ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _source_format_from_ext(ext: str) -> str:
    return {
        "docx": "docx",
        "pdf": "pdf_text",  # worker will correct to pdf_image if needed
        "jpg": "image",
        "jpeg": "image",
        "png": "image",
        "webp": "image",
    }.get(ext, "docx")


def _require_document(
    conn: sa.engine.Connection,
    document_id: str,
    user_id: str,
) -> sa.Row:
    """Fetch document; raise 404 if missing, soft-deleted, or belonging to
    another user. The explicit user_id predicate guards correctness independent
    of RLS — never rely on RLS alone for access control decisions."""
    doc = conn.execute(
        sa.text(
            "SELECT id, user_id, title, counterparty, created_at, deleted_at "
            "FROM documents "
            "WHERE id = :id AND user_id = :uid AND deleted_at IS NULL"
        ),
        {"id": document_id, "uid": user_id},
    ).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan.")
    return doc


def _row_to_version(row: sa.Row) -> VersionResponse:
    return VersionResponse(
        id=row.id,
        document_id=row.document_id,
        version_no=row.version_no,
        source_filename=row.source_filename,
        source_format=row.source_format,
        sha256=row.sha256,
        extraction_ok=row.extraction_ok,
        extraction_note=row.extraction_note,
        detected_language=row.detected_language,
        uploaded_at=row.uploaded_at,
    )


# ── Create document ────────────────────────────────────────────────────────────

@router.post("", response_model=DocumentResponse, status_code=201)
def create_document(
    body: CreateDocumentRequest,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> DocumentResponse:
    """Create a new document record (no file upload here — use .../versions)."""
    conn, user = auth
    doc = conn.execute(
        sa.text(
            "INSERT INTO documents (user_id, title, counterparty) "
            "VALUES (:uid, :title, :counterparty) "
            "RETURNING id, user_id, title, counterparty, created_at, deleted_at"
        ),
        {
            "uid": str(user.user_id),
            "title": body.title,
            "counterparty": body.counterparty,
        },
    ).fetchone()
    logger.info("document_created", doc_id=str(doc.id), user_id=str(user.user_id))
    return DocumentResponse(
        id=doc.id,
        user_id=doc.user_id,
        title=doc.title,
        counterparty=doc.counterparty,
        created_at=doc.created_at,
        deleted_at=doc.deleted_at,
    )


# ── List documents ─────────────────────────────────────────────────────────────

@router.get("", response_model=list[DocumentListItem])
def list_documents(
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> list[DocumentListItem]:
    """Return all non-deleted documents for the current user, newest first.

    Explicit user_id predicate ensures isolation independent of RLS.
    """
    conn, user = auth
    uid = str(user.user_id)

    docs = conn.execute(
        sa.text(
            "SELECT id, title, counterparty, created_at "
            "FROM documents "
            "WHERE user_id = :uid AND deleted_at IS NULL "
            "ORDER BY created_at DESC"
        ),
        {"uid": uid},
    ).fetchall()

    result: list[DocumentListItem] = []
    for doc in docs:
        vc = conn.execute(
            sa.text(
                "SELECT COUNT(*) as cnt FROM document_versions WHERE document_id = :did"
            ),
            {"did": str(doc.id)},
        ).fetchone()

        lv_row = conn.execute(
            sa.text(
                "SELECT id, document_id, version_no, source_filename, source_format, "
                "storage_key, sha256, extraction_ok, extraction_note, "
                "detected_language, uploaded_at "
                "FROM document_versions WHERE document_id = :did "
                "ORDER BY version_no DESC LIMIT 1"
            ),
            {"did": str(doc.id)},
        ).fetchone()

        latest_version = _row_to_version(lv_row) if lv_row else None

        latest_job = None
        if lv_row:
            lj_row = conn.execute(
                sa.text(
                    "SELECT id, version_id, user_id, state, stage, error_message, "
                    "created_at, finished_at "
                    "FROM analysis_jobs "
                    "WHERE version_id = :vid AND user_id = :uid "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"vid": str(lv_row.id), "uid": uid},
            ).fetchone()
            if lj_row:
                latest_job = AnalysisJobResponse(
                    job_id=lj_row.id,
                    version_id=lj_row.version_id,
                    user_id=lj_row.user_id,
                    state=lj_row.state,
                    stage=lj_row.stage,
                    error_message=lj_row.error_message,
                    created_at=lj_row.created_at,
                    finished_at=lj_row.finished_at,
                )

        result.append(DocumentListItem(
            id=doc.id,
            title=doc.title,
            counterparty=doc.counterparty,
            created_at=doc.created_at,
            version_count=vc.cnt if vc else 0,
            latest_version=latest_version,
            latest_job=latest_job,
        ))

    return result


# ── Get single document ────────────────────────────────────────────────────────

@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: UUID,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> DocumentResponse:
    conn, user = auth
    doc = _require_document(conn, str(document_id), str(user.user_id))
    return DocumentResponse(
        id=doc.id,
        user_id=doc.user_id,
        title=doc.title,
        counterparty=doc.counterparty,
        created_at=doc.created_at,
        deleted_at=doc.deleted_at,
    )


# ── Soft-delete document ───────────────────────────────────────────────────────

@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: UUID,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> None:
    """Soft-delete: sets deleted_at. A scheduled cleanup job hard-deletes blobs
    after RETENTION_DAYS (default 30). Explicit user_id = :uid in the UPDATE
    ensures a user can never soft-delete another user's document."""
    conn, user = auth
    uid = str(user.user_id)
    _require_document(conn, str(document_id), uid)  # 404 guard
    conn.execute(
        sa.text(
            "UPDATE documents SET deleted_at = now() "
            "WHERE id = :id AND user_id = :uid"
        ),
        {"id": str(document_id), "uid": uid},
    )
    logger.info("document_soft_deleted", doc_id=str(document_id), user_id=uid)


# ── Upload a new version ───────────────────────────────────────────────────────

@router.post("/{document_id}/versions", response_model=VersionUploadResponse, status_code=201)
def upload_version(
    document_id: UUID,
    file: UploadFile = File(...),
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
    _quota: None = Depends(require_quota),
) -> VersionUploadResponse:
    """Upload a contract file, store it in MinIO, and enqueue an analysis job.

    Accepts: DOCX, PDF, JPG, JPEG, PNG, WEBP (max 20 MB).
    Returns immediately with version info and job_id for polling.
    """
    conn, user = auth
    uid = str(user.user_id)
    _require_document(conn, str(document_id), uid)

    # ── Validate file ──────────────────────────────────────────────────────────
    filename = file.filename or "upload"
    ext = _file_ext(filename)
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Format file '{ext}' tidak didukung. "
                "Gunakan: DOCX, PDF, JPG, JPEG, PNG, atau WEBP."
            ),
        )

    file_bytes = file.file.read()
    if len(file_bytes) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Ukuran file melebihi batas 20 MB.",
        )

    # ── SHA-256 ────────────────────────────────────────────────────────────────
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    # ── Determine next version number ──────────────────────────────────────────
    max_v = conn.execute(
        sa.text(
            "SELECT COALESCE(MAX(version_no), 0) AS max_v "
            "FROM document_versions WHERE document_id = :did"
        ),
        {"did": str(document_id)},
    ).fetchone()
    version_no = (max_v.max_v if max_v else 0) + 1

    # ── Upload to MinIO ────────────────────────────────────────────────────────
    key = storage.storage_key(uid, str(document_id), version_no, filename)
    content_type_map = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    try:
        storage.upload_bytes(
            key, file_bytes, content_type_map.get(ext, "application/octet-stream")
        )
    except Exception as exc:
        logger.error("storage_upload_failed", key=key, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Gagal menyimpan file. Layanan penyimpanan tidak tersedia sementara.",
        )

    # ── Create document_version ────────────────────────────────────────────────
    version = conn.execute(
        sa.text(
            "INSERT INTO document_versions "
            "(document_id, version_no, source_filename, source_format, "
            " storage_key, sha256, extraction_ok) "
            "VALUES (:doc_id, :vno, :fname, :fmt, :key, :sha, false) "
            "RETURNING id, document_id, version_no, source_filename, source_format, "
            "storage_key, sha256, extraction_ok, extraction_note, detected_language, uploaded_at"
        ),
        {
            "doc_id": str(document_id),
            "vno": version_no,
            "fname": filename,
            "fmt": _source_format_from_ext(ext),
            "key": key,
            "sha": sha256,
        },
    ).fetchone()

    # ── Enqueue analysis job ───────────────────────────────────────────────────
    job = conn.execute(
        sa.text(
            "INSERT INTO analysis_jobs (user_id, version_id, state, stage) "
            "VALUES (:uid, :vid, 'queued', 'Menunggu antrian analisis') "
            "RETURNING id, version_id, user_id, state, stage, error_message, created_at, finished_at"
        ),
        {"uid": uid, "vid": str(version.id)},
    ).fetchone()

    # ── Consume one quota unit ─────────────────────────────────────────────────
    consume_quota(conn, uid)

    logger.info(
        "version_uploaded",
        doc_id=str(document_id),
        version_id=str(version.id),
        job_id=str(job.id),
        user_id=uid,
        version_no=version_no,
    )

    return VersionUploadResponse(
        version=_row_to_version(version),
        job_id=job.id,
        job_state=job.state,
    )


# ── List versions ──────────────────────────────────────────────────────────────

@router.get("/{document_id}/versions", response_model=list[VersionResponse])
def list_versions(
    document_id: UUID,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> list[VersionResponse]:
    conn, user = auth
    _require_document(conn, str(document_id), str(user.user_id))
    rows = conn.execute(
        sa.text(
            "SELECT id, document_id, version_no, source_filename, source_format, "
            "storage_key, sha256, extraction_ok, extraction_note, detected_language, uploaded_at "
            "FROM document_versions WHERE document_id = :did ORDER BY version_no DESC"
        ),
        {"did": str(document_id)},
    ).fetchall()
    return [_row_to_version(r) for r in rows]


# ── Presigned download URL ─────────────────────────────────────────────────────

@router.get(
    "/{document_id}/versions/{version_id}/download",
    response_model=PresignedDownloadResponse,
)
def download_version(
    document_id: UUID,
    version_id: UUID,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> PresignedDownloadResponse:
    """Generate a 10-minute presigned URL for direct download. Never stores or
    returns a permanent URL — all access is time-limited and authenticated.

    Double ownership check: _require_document guards the document, then the
    version JOIN guards the specific version belongs to that document."""
    conn, user = auth
    uid = str(user.user_id)
    _require_document(conn, str(document_id), uid)

    version_row = conn.execute(
        sa.text(
            "SELECT dv.storage_key "
            "FROM document_versions dv "
            "JOIN documents d ON d.id = dv.document_id "
            "WHERE dv.id = :vid AND dv.document_id = :did AND d.user_id = :uid"
        ),
        {"vid": str(version_id), "did": str(document_id), "uid": uid},
    ).fetchone()
    if not version_row:
        raise HTTPException(status_code=404, detail="Versi dokumen tidak ditemukan.")

    try:
        url = storage.generate_presigned_url(version_row.storage_key, expires_in=600)
    except Exception as exc:
        logger.error("presigned_url_failed", key=version_row.storage_key, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Gagal membuat tautan unduhan. Coba lagi beberapa saat.",
        )

    return PresignedDownloadResponse(url=url, expires_in_seconds=600)
