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
    materiality: str            # 'material' | 'immaterial'
    materiality_reason: Optional[str]
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
    diffs: list[VersionDiffRow]  # material changes first, then immaterial
    # Completed analysis job for to_version, if one exists.
    job_id: Optional[str] = None

    @pydantic.computed_field
    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0
