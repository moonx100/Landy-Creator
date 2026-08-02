"""Pydantic models for the version diff API.

Used by GET /api/documents/{doc_id}/versions/{ver_id}/diff.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

import pydantic


class VersionDiffRow(pydantic.BaseModel):
    """One changed clause row from version_diffs."""
    id: UUID
    from_version: UUID
    to_version: UUID
    clause_ref: Optional[str]
    change_kind: str            # 'added' | 'removed' | 'modified'
    # None when the classification failed — the change is real but its legal
    # significance is unknown. Never coerce to 'immaterial' in a consumer.
    materiality: Optional[str]  # 'material' | 'immaterial' | None
    materiality_reason: Optional[str]
    # 'ok' | 'low_confidence' | 'failed' — the operational outcome of the
    # classification, separate from the semantic answer (LC-41).
    classification_status: str = "ok"
    classification_error: Optional[str] = None
    before_text: Optional[str]
    after_text: Optional[str]


class VersionDiffResponse(pydantic.BaseModel):
    """Full diff response — returned by GET /api/.../diff."""
    from_version_id: UUID
    to_version_id: UUID
    from_version_no: int
    to_version_no: int
    total_changes: int
    material_count: int
    immaterial_count: int
    # Changes whose classification failed. Computed by counting, never by
    # subtraction — total may exceed material + immaterial.
    unclassified_count: int = 0
    diffs: list[VersionDiffRow]  # material + unclassified first, then immaterial
    # Completed analysis job for to_version, if one exists.
    job_id: Optional[str] = None
    # How the diff was produced:
    #   'tracked_changes' — from <w:ins>/<w:del> marks in the DOCX
    #   'text_diff'       — from clause-level textual comparison between versions
    diff_source: str = "text_diff"
    # Parse status of the DOCX revision layer for to_version. 'failed' means
    # revisions could not be read and diff_source degraded to text_diff — the
    # UI must say so instead of presenting text_diff as a normal outcome.
    tc_parse_status: Optional[str] = None
    tc_parse_note: Optional[str] = None

    @pydantic.computed_field
    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0

    @pydantic.computed_field
    @property
    def review_complete(self) -> bool:
        """True only when every change was successfully classified and the
        revision layer was readable. The all-clear sentence ("tidak ada
        perubahan material") may only render when this is True (LC-41)."""
        return self.unclassified_count == 0 and self.tc_parse_status != "failed"
