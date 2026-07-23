"""Pydantic models for export endpoints (Task 4).

POST /api/documents/{doc_id}/versions/{ver_id}/export/docx
POST /api/documents/{doc_id}/versions/{ver_id}/export/email-draft
PATCH /api/suggested-edits/{edit_id}
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

import pydantic


class PatchSuggestedEditRequest(pydantic.BaseModel):
    """Body for PATCH /api/suggested-edits/{id}."""
    accepted: Optional[bool]  # True=accept, False=reject, None=undecided


class SuggestedEditPatchResponse(pydantic.BaseModel):
    """Updated suggested edit row."""
    id: UUID
    risk_flag_id: UUID
    clause_id: Optional[UUID]
    original_text: str
    revised_text: str
    comment: Optional[str]
    accepted: Optional[bool]


class DocxExportResponse(pydantic.BaseModel):
    """Response for DOCX export — presigned download URL."""
    url: str
    expires_in_seconds: int = 600
    edit_count: int          # number of tracked changes included
    comment_only_count: int  # edits surfaced as comments (original text not found)
    warning: Optional[str]   # non-null if MinIO unavailable or other non-fatal issue


class EmailDraftResponse(pydantic.BaseModel):
    """Response for email draft generation."""
    draft: str          # full email body, plain text, Bahasa Indonesia
    flag_count: int     # number of flags covered in the draft
