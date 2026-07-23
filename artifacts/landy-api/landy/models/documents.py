"""Pydantic models for document and analysis endpoints.

Every request/response crossing an API boundary must be a typed Pydantic model.
No untyped dicts, no Any, except where explicitly annotated.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

import pydantic


# ── Requests ──────────────────────────────────────────────────────────────────

class CreateDocumentRequest(pydantic.BaseModel):
    title: str = pydantic.Field(..., min_length=1, max_length=255)
    counterparty: Optional[str] = pydantic.Field(None, max_length=255)


class CreateAnalysisRequest(pydantic.BaseModel):
    version_id: UUID


# ── Version responses ─────────────────────────────────────────────────────────

class VersionResponse(pydantic.BaseModel):
    """Single document version row."""
    id: UUID
    document_id: UUID
    version_no: int
    source_filename: str
    source_format: str
    sha256: str
    extraction_ok: bool
    extraction_note: Optional[str]
    detected_language: Optional[str]
    uploaded_at: datetime

    @pydantic.computed_field
    @property
    def accuracy_warning(self) -> Optional[str]:
        """Derived: non-None for OCR-only source formats."""
        if self.source_format == "pdf_image":
            return (
                "Dokumen ini adalah PDF berbasis gambar. "
                "Akurasi ekstraksi teks dapat bervariasi — verifikasi klausul penting secara manual."
            )
        if self.source_format == "image":
            return (
                "Dokumen diunggah sebagai gambar. "
                "Akurasi ekstraksi teks dapat bervariasi — verifikasi klausul penting secara manual."
            )
        return None


# ── Job responses ─────────────────────────────────────────────────────────────

class AnalysisJobResponse(pydantic.BaseModel):
    """Analysis job status — polled by the frontend every ~3 seconds."""
    job_id: UUID
    version_id: UUID
    user_id: UUID
    state: str        # queued | running | done | failed
    stage: Optional[str]          # human-readable progress label
    error_message: Optional[str]  # populated on failure; never swallowed
    created_at: datetime
    finished_at: Optional[datetime]


# ── Document responses ────────────────────────────────────────────────────────

class DocumentResponse(pydantic.BaseModel):
    id: UUID
    user_id: UUID
    title: str
    counterparty: Optional[str]
    created_at: datetime
    deleted_at: Optional[datetime]


class VersionUploadResponse(pydantic.BaseModel):
    """Returned by POST /api/documents/{id}/versions."""
    version: VersionResponse
    job_id: UUID
    job_state: str


class DocumentListItem(pydantic.BaseModel):
    """One row in the document list — includes latest version + job summary."""
    id: UUID
    title: str
    counterparty: Optional[str]
    created_at: datetime
    version_count: int
    latest_version: Optional[VersionResponse]
    latest_job: Optional[AnalysisJobResponse]


class PresignedDownloadResponse(pydantic.BaseModel):
    url: str
    expires_in_seconds: int = 600
