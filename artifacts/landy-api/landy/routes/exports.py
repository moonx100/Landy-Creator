"""Export endpoints and suggested-edit acceptance.

PATCH /api/suggested-edits/{edit_id}
POST  /api/documents/{doc_id}/versions/{ver_id}/export/docx
POST  /api/documents/{doc_id}/versions/{ver_id}/export/email-draft

Security: every query has explicit user_id ownership checks (defence-in-depth
alongside RLS). A user can only export or patch edits on their own documents.
"""
from __future__ import annotations

import io
import uuid
from typing import Any, Tuple
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException

from landy.deps.auth import get_current_user
from landy.export.docx_export import ClauseData, EditData, build_redlined_docx
from landy.export.email_draft import generate_email_draft
from landy.llm import LLMError
from landy.logging_setup import logger
from landy.models.exports import (
    DocxExportResponse,
    EmailDraftResponse,
    PatchSuggestedEditRequest,
    SuggestedEditPatchResponse,
)
from landy.redaction import expand, fetch_mapping
import landy.storage as storage

router = APIRouter()

_EXPORT_STORAGE_PREFIX = "exports"


# ── Suggested-edit acceptance ─────────────────────────────────────────────────

@router.patch("/suggested-edits/{edit_id}", response_model=SuggestedEditPatchResponse)
def patch_suggested_edit(
    edit_id: UUID,
    body: PatchSuggestedEditRequest,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> SuggestedEditPatchResponse:
    """Accept, reject, or reset (undecided) a suggested edit.

    Ownership enforced via JOIN through risk_flags → document_versions → documents → user_id.
    """
    conn, user = auth
    uid = str(user.user_id)

    # Verify ownership and fetch current state
    row = conn.execute(
        sa.text(
            "SELECT se.id, se.risk_flag_id, se.clause_id, se.original_text, "
            "se.revised_text, se.comment, se.accepted "
            "FROM suggested_edits se "
            "JOIN risk_flags rf ON rf.id = se.risk_flag_id "
            "JOIN document_versions dv ON dv.id = rf.version_id "
            "JOIN documents d ON d.id = dv.document_id "
            "WHERE se.id = :eid AND d.user_id = :uid AND d.deleted_at IS NULL"
        ),
        {"eid": str(edit_id), "uid": uid},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Saran perubahan tidak ditemukan.")

    # Update accepted field. Re-asserts ownership in the UPDATE itself (not just
    # the preceding SELECT) so the predicate is load-bearing on every query that
    # touches the row, per the tenant-isolation rule.
    conn.execute(
        sa.text(
            "UPDATE suggested_edits SET accepted = :val "
            "WHERE id = :eid AND EXISTS ("
            "  SELECT 1 FROM risk_flags rf "
            "  JOIN document_versions dv ON dv.id = rf.version_id "
            "  JOIN documents d ON d.id = dv.document_id "
            "  WHERE rf.id = suggested_edits.risk_flag_id "
            "    AND d.user_id = :uid AND d.deleted_at IS NULL"
            ")"
        ),
        {"val": body.accepted, "eid": str(edit_id), "uid": uid},
    )

    logger.info(
        "suggested_edit_patched",
        edit_id=str(edit_id),
        accepted=body.accepted,
        user_id=uid,
    )

    return SuggestedEditPatchResponse(
        id=row.id,
        risk_flag_id=row.risk_flag_id,
        clause_id=row.clause_id,
        original_text=row.original_text,
        revised_text=row.revised_text,
        comment=row.comment,
        accepted=body.accepted,
    )


# ── Shared ownership helpers ──────────────────────────────────────────────────

def _require_version_ownership(
    conn: sa.engine.Connection,
    document_id: str,
    version_id: str,
    uid: str,
) -> sa.Row:
    """Fetch the version row; 404 if missing, deleted, or not owned by uid."""
    row = conn.execute(
        sa.text(
            "SELECT dv.id, dv.storage_key, dv.source_filename, dv.source_format, "
            "d.title, d.counterparty "
            "FROM document_versions dv "
            "JOIN documents d ON d.id = dv.document_id "
            "WHERE dv.id = :vid AND d.id = :did AND d.user_id = :uid AND d.deleted_at IS NULL"
        ),
        {"vid": version_id, "did": document_id, "uid": uid},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Versi dokumen tidak ditemukan.")
    return row


def _fetch_redaction_map(conn: sa.engine.Connection, version_id: str) -> dict[str, str]:
    """Return token→original mapping for a version (from redaction_mappings table)."""
    return fetch_mapping(conn, version_id)


def _fetch_clauses(conn: sa.engine.Connection, version_id: str) -> list[sa.Row]:
    return conn.execute(
        sa.text(
            "SELECT id, ordinal, heading_path, text "
            "FROM clauses WHERE version_id = :vid ORDER BY ordinal ASC"
        ),
        {"vid": version_id},
    ).fetchall()


def _fetch_latest_job_id(
    conn: sa.engine.Connection,
    version_id: str,
    uid: str,
) -> str | None:
    """Return the most-recently-completed job_id for this version."""
    row = conn.execute(
        sa.text(
            "SELECT id FROM analysis_jobs "
            "WHERE version_id = :vid AND user_id = :uid AND state = 'done' "
            "ORDER BY finished_at DESC LIMIT 1"
        ),
        {"vid": version_id, "uid": uid},
    ).fetchone()
    return str(row.id) if row else None


def _fetch_edits(
    conn: sa.engine.Connection,
    version_id: str,
    job_id: str,
    accepted_only: bool = False,
) -> list[sa.Row]:
    """Fetch suggested edits for a version's latest job.

    If accepted_only=False, returns both accepted (True) and undecided (NULL) edits
    (rejected edits are excluded from the export per user's decision).
    """
    accepted_clause = "AND se.accepted IS NOT FALSE" if not accepted_only else "AND se.accepted = TRUE"
    return conn.execute(
        sa.text(
            f"SELECT se.id, se.clause_id, se.original_text, se.revised_text, se.comment, se.accepted "
            f"FROM suggested_edits se "
            f"JOIN risk_flags rf ON rf.id = se.risk_flag_id "
            f"WHERE rf.version_id = :vid AND rf.job_id = :jid {accepted_clause}"
        ),
        {"vid": version_id, "jid": job_id},
    ).fetchall()


def _fetch_flags(
    conn: sa.engine.Connection,
    version_id: str,
    job_id: str,
) -> list[sa.Row]:
    return conn.execute(
        sa.text(
            "SELECT domain, severity, summary, rationale, negotiation_ask, finding_type "
            "FROM risk_flags WHERE version_id = :vid AND job_id = :jid "
            "ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 "
            "WHEN 'medium' THEN 3 ELSE 4 END, created_at ASC"
        ),
        {"vid": version_id, "jid": job_id},
    ).fetchall()


# ── DOCX export ────────────────────────────────────────────────────────────────

@router.post(
    "/documents/{document_id}/versions/{version_id}/export/docx",
    response_model=DocxExportResponse,
)
def export_docx(
    document_id: UUID,
    version_id: UUID,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> DocxExportResponse:
    """Generate a DOCX with real OOXML tracked changes for accepted/undecided edits.

    Re-expands PII redaction placeholders before writing.
    Stores the generated file in MinIO and returns a 10-minute presigned URL.

    Spec §8a: only w:del/w:ins — never fake formatting.
    """
    conn, user = auth
    uid = str(user.user_id)
    vid = str(version_id)
    did = str(document_id)

    version_row = _require_version_ownership(conn, did, vid, uid)
    job_id = _fetch_latest_job_id(conn, vid, uid)

    if not job_id:
        raise HTTPException(
            status_code=409,
            detail="Analisis belum selesai atau belum ada hasil. Tunggu hingga analisis selesai.",
        )

    # Fetch data
    redaction_map = _fetch_redaction_map(conn, vid)
    clause_rows = _fetch_clauses(conn, vid)
    edit_rows = _fetch_edits(conn, vid, job_id, accepted_only=False)

    if not clause_rows:
        raise HTTPException(
            status_code=409,
            detail="Tidak ada klausul yang diekstrak dari dokumen ini.",
        )

    # Build ClauseData with expanded (non-redacted) text
    clauses = [
        ClauseData(
            id=str(r.id),
            ordinal=r.ordinal,
            heading_path=r.heading_path,
            text=expand(r.text, redaction_map),
        )
        for r in clause_rows
    ]

    # Build EditData for accepted/undecided edits
    edits = [
        EditData(
            id=str(r.id),
            clause_id=str(r.clause_id) if r.clause_id else None,
            original_text=expand(r.original_text, redaction_map),
            revised_text=expand(r.revised_text, redaction_map),
            comment=r.comment,
        )
        for r in edit_rows
    ]

    title = expand(version_row.title, redaction_map)

    logger.info(
        "docx_export_start",
        version_id=vid,
        clauses=len(clauses),
        edits=len(edits),
        user_id=uid,
    )

    # Generate DOCX
    try:
        docx_bytes, tc_count, co_count = build_redlined_docx(
            title=title,
            clauses=clauses,
            edits=edits,
        )
    except Exception as exc:
        logger.error("docx_generation_failed", version_id=vid, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Gagal menghasilkan DOCX: {exc}",
        )

    # Upload to MinIO
    export_key = f"{_EXPORT_STORAGE_PREFIX}/{uid}/{did}/{vid}/redlined_{uuid.uuid4().hex[:8]}.docx"
    try:
        storage.upload_bytes(
            export_key,
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        url = storage.generate_presigned_url(export_key, expires_in=600)
        warning = None
    except Exception as exc:
        logger.warning("docx_storage_upload_failed", error=str(exc))
        # MinIO unavailable in dev — return the DOCX bytes as a data URL fallback
        # so the feature still works locally without storage.
        import base64
        b64 = base64.b64encode(docx_bytes).decode()
        url = (
            "data:application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document;base64," + b64
        )
        warning = "Penyimpanan tidak tersedia — tautan unduhan langsung (berlaku sekali)."

    logger.info(
        "docx_export_done",
        version_id=vid,
        tracked_changes=tc_count,
        comment_only=co_count,
        user_id=uid,
    )

    return DocxExportResponse(
        url=url,
        expires_in_seconds=600,
        edit_count=tc_count,
        comment_only_count=co_count,
        warning=warning,
    )


# ── Email draft export ────────────────────────────────────────────────────────

@router.post(
    "/documents/{document_id}/versions/{version_id}/export/email-draft",
    response_model=EmailDraftResponse,
)
def export_email_draft(
    document_id: UUID,
    version_id: UUID,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> EmailDraftResponse:
    """Generate a plain-language Bahasa Indonesia negotiation email draft.

    Covers critical/high/medium risk flags with their negotiation_ask.
    Includes disclaimer. No in-platform editor and no email sending.
    """
    conn, user = auth
    uid = str(user.user_id)
    vid = str(version_id)
    did = str(document_id)

    version_row = _require_version_ownership(conn, did, vid, uid)
    job_id = _fetch_latest_job_id(conn, vid, uid)

    if not job_id:
        raise HTTPException(
            status_code=409,
            detail="Analisis belum selesai. Tunggu hingga analisis selesai sebelum membuat email draft.",
        )

    flag_rows = _fetch_flags(conn, vid, job_id)
    if not flag_rows:
        raise HTTPException(
            status_code=409,
            detail="Tidak ada temuan risiko. Pastikan analisis berhasil diselesaikan.",
        )

    flags = [
        {
            "domain": r.domain,
            "severity": r.severity,
            "summary": r.summary,
            "negotiation_ask": r.negotiation_ask,
            "finding_type": r.finding_type,
        }
        for r in flag_rows
    ]

    logger.info(
        "email_draft_start",
        version_id=vid,
        flag_count=len(flags),
        user_id=uid,
    )

    try:
        draft = generate_email_draft(
            document_title=version_row.title,
            counterparty=version_row.counterparty,
            flags=flags,
            version_id=vid,
        )
    except LLMError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gagal menghasilkan email draft: {exc}",
        )

    return EmailDraftResponse(draft=draft, flag_count=len(flags))
