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


# ── Analysis results ──────────────────────────────────────────────────────────
# Used by GET /api/analyses/{job_id}/results

class CitationResponse(pydantic.BaseModel):
    """Citation placeholder row (corpus empty in v1; provision_id always null)."""
    id: UUID
    provision_id: Optional[UUID]  # always NULL in v1 — corpus not yet populated
    citation_text: Optional[str]  # always NULL in v1
    basis: Optional[str]          # 'statutory' | 'doctrinal'


class SuggestedEditResponse(pydantic.BaseModel):
    """A proposed redline edit for a risk flag."""
    id: UUID
    clause_id: Optional[UUID]     # the clause the edit applies to (may be null)
    original_text: str
    revised_text: str
    comment: Optional[str]        # becomes a Word comment alongside the change
    accepted: Optional[bool]      # None = undecided; True/False = user's choice before export


class RiskFlagResponse(pydantic.BaseModel):
    """One risk finding from the 18-domain taxonomy analysis."""
    id: UUID
    clause_id: Optional[UUID]     # null for absence / document-level findings
    domain: str                   # taxonomy key, e.g. 'ip_ownership'
    severity: str                 # critical | high | medium | info
    finding_type: str             # present_risky | absent | ambiguous
    summary: str                  # one-line Bahasa Indonesia summary
    rationale: str                # why this matters to the creator
    negotiation_ask: Optional[str]  # what to request instead
    created_at: datetime
    suggested_edits: list[SuggestedEditResponse]
    citations: list[CitationResponse]


class AnalysisResultsResponse(pydantic.BaseModel):
    """Full analysis results for one job — returned by GET /api/analyses/{job_id}/results."""
    job_id: UUID
    version_id: UUID
    state: str
    stage: Optional[str]
    error_message: Optional[str]
    risk_flags: list[RiskFlagResponse]

    @pydantic.computed_field
    @property
    def flag_counts(self) -> dict[str, int]:
        """Quick summary: count of flags per severity level."""
        counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "info": 0}
        for flag in self.risk_flags:
            if flag.severity in counts:
                counts[flag.severity] += 1
        return counts
