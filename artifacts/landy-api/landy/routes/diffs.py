"""Version diff API endpoint.

GET /api/documents/{doc_id}/versions/{ver_id}/diff
  Returns the stored version diff between ver_id and its immediately
  preceding version. Returns 404 if no diff exists (version 1, or
  diff not yet computed, or no changes detected).

Security:
  - Ownership check: document must belong to the authenticated user.
  - Explicit WHERE user_id = :uid on every join (belt-and-suspenders
    alongside the RLS policy).
"""
from __future__ import annotations

from typing import Any, Tuple
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException

from landy.deps.auth import get_current_user
from landy.logging_setup import logger
from landy.models.diffs import VersionDiffResponse, VersionDiffRow

router = APIRouter()


@router.get(
    "/{document_id}/versions/{version_id}/diff",
    response_model=VersionDiffResponse,
)
def get_version_diff(
    document_id: UUID,
    version_id: UUID,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> VersionDiffResponse:
    """Return the diff between the specified version and its predecessor.

    Returns 404 when:
    - The document does not belong to the authenticated user.
    - The version does not exist.
    - The version is version_no = 1 (no prior version to diff against).
    - The diff has not been computed yet (worker has not run, or no changes).
    """
    conn, user = auth
    uid = str(user.user_id)
    doc_id = str(document_id)
    ver_id = str(version_id)

    # ── Ownership + version check ─────────────────────────────────────────────
    ver_row = conn.execute(
        sa.text(
            "SELECT dv.id, dv.version_no "
            "FROM document_versions dv "
            "JOIN documents d ON d.id = dv.document_id "
            "WHERE dv.id = :vid AND d.id = :did AND d.user_id = :uid "
            "  AND d.deleted_at IS NULL"
        ),
        {"vid": ver_id, "did": doc_id, "uid": uid},
    ).fetchone()

    if not ver_row:
        raise HTTPException(
            status_code=404,
            detail="Versi dokumen tidak ditemukan.",
        )

    if ver_row.version_no == 1:
        raise HTTPException(
            status_code=404,
            detail="Ini adalah versi pertama — tidak ada versi sebelumnya untuk dibandingkan.",
        )

    # ── Fetch prior version info ──────────────────────────────────────────────
    prior_row = conn.execute(
        sa.text(
            "SELECT dv.id, dv.version_no "
            "FROM document_versions dv "
            "WHERE dv.document_id = :did "
            "  AND dv.version_no = :prev_no"
        ),
        {"did": doc_id, "prev_no": ver_row.version_no - 1},
    ).fetchone()

    if not prior_row:
        raise HTTPException(
            status_code=404,
            detail="Versi sebelumnya tidak ditemukan.",
        )

    # ── Fetch diff rows ───────────────────────────────────────────────────────
    diff_rows = conn.execute(
        sa.text(
            "SELECT id, from_version, to_version, clause_ref, change_kind, "
            "  materiality, materiality_reason, "
            "  classification_status, classification_error, "
            "  before_text, after_text "
            "FROM version_diffs "
            "WHERE from_version = :fv AND to_version = :tv "
            # Material and unclassified changes first (co-equal weight, per
            # MV: an unclassified change deserves the same attention as a
            # material one), then immaterial; within each group by clause_ref
            "ORDER BY "
            "  CASE WHEN materiality = 'material' "
            "       OR classification_status = 'failed' THEN 1 ELSE 2 END ASC, "
            "  clause_ref ASC NULLS LAST"
        ),
        {"fv": str(prior_row.id), "tv": ver_id},
    ).fetchall()

    # ── Fetch tracked-changes state for the to_version ────────────────────────
    tc_row = conn.execute(
        sa.text(
            "SELECT has_tracked_changes, tc_parse_status, tc_parse_note "
            "FROM document_versions WHERE id = :vid"
        ),
        {"vid": ver_id},
    ).fetchone()
    diff_source = (
        "tracked_changes"
        if tc_row and tc_row.has_tracked_changes and tc_row.tc_parse_status != "failed"
        else "text_diff"
    )

    if not diff_rows:
        # Split the conflated 404: "not computed yet" and "computed, nothing
        # changed" are different facts and get different messages.
        done_job = conn.execute(
            sa.text(
                "SELECT id FROM analysis_jobs "
                "WHERE version_id = :vid AND user_id = :uid AND state = 'done' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"vid": ver_id, "uid": uid},
        ).fetchone()
        if done_job:
            detail = "Tidak ada perubahan yang terdeteksi antara kedua versi."
            if tc_row and tc_row.tc_parse_status == "failed":
                detail = (
                    "Lapisan revisi (track changes) tidak dapat dibaca dari "
                    "berkas ini, dan tidak ada perubahan teks yang terdeteksi. "
                    "Pastikan dokumen yang di-upload dalam format .docx dan terstruktur."
                )
        else:
            detail = "Diff belum tersedia — tunggu analisis selesai."
        raise HTTPException(status_code=404, detail=detail)

    diffs = [
        VersionDiffRow(
            id=r.id,
            from_version=r.from_version,
            to_version=r.to_version,
            clause_ref=r.clause_ref,
            change_kind=r.change_kind,
            materiality=r.materiality,
            materiality_reason=r.materiality_reason,
            classification_status=r.classification_status,
            classification_error=r.classification_error,
            before_text=r.before_text,
            after_text=r.after_text,
        )
        for r in diff_rows
    ]

    # Counts by counting — never subtraction (LC-41)
    material_count = sum(1 for d in diffs if d.materiality == "material")
    immaterial_count = sum(1 for d in diffs if d.materiality == "immaterial")
    unclassified_count = sum(1 for d in diffs if d.classification_status == "failed")

    # ── Resolve the analysis job for the "to" version ─────────────────────────
    job_row = conn.execute(
        sa.text(
            "SELECT id FROM analysis_jobs "
            "WHERE version_id = :ver_id AND user_id = :uid AND state = 'done' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"ver_id": ver_id, "uid": uid},
    ).fetchone()
    job_id = str(job_row.id) if job_row else None

    logger.info(
        "version_diff_fetched",
        doc_id=doc_id,
        version_id=ver_id,
        total=len(diffs),
        material=material_count,
        unclassified=unclassified_count,
        user_id=uid,
    )

    return VersionDiffResponse(
        from_version_id=prior_row.id,
        to_version_id=ver_id,
        from_version_no=prior_row.version_no,
        to_version_no=ver_row.version_no,
        total_changes=len(diffs),
        material_count=material_count,
        immaterial_count=immaterial_count,
        unclassified_count=unclassified_count,
        diffs=diffs,
        job_id=job_id,
        diff_source=diff_source,
        tc_parse_status=tc_row.tc_parse_status if tc_row else None,
        tc_parse_note=tc_row.tc_parse_note if tc_row else None,
    )
