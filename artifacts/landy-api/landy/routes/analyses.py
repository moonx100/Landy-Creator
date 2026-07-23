"""Analysis job endpoints.

POST /api/analyses         — enqueue a new analysis job for an existing version
GET  /api/analyses/{job_id} — poll job state, stage, and error

The upload endpoint (POST /api/documents/{id}/versions) auto-enqueues a job.
POST /api/analyses is used to re-trigger analysis on a version whose job failed,
or to trigger analysis manually if the upload step was done separately.

Both endpoints consume one quota unit (upload + re-trigger each cost 1).

Security: every query includes explicit user_id = :uid predicates so that
correctness is not solely dependent on RLS policy semantics.
"""
from typing import Tuple, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException

from landy.deps.auth import get_current_user
from landy.deps.quota import consume_quota, require_quota
from landy.logging_setup import logger
from landy.models.documents import AnalysisJobResponse, CreateAnalysisRequest

router = APIRouter()


def _job_row_to_response(row: sa.Row) -> AnalysisJobResponse:
    return AnalysisJobResponse(
        job_id=row.id,
        version_id=row.version_id,
        user_id=row.user_id,
        state=row.state,
        stage=row.stage,
        error_message=row.error_message,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )


@router.post("", response_model=AnalysisJobResponse, status_code=201)
def create_analysis(
    body: CreateAnalysisRequest,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
    _quota: None = Depends(require_quota),
) -> AnalysisJobResponse:
    """Enqueue a new analysis job for an existing document version.

    Use this to re-trigger analysis after a failure, or to trigger manually.
    Explicit user_id join ensures we never enqueue for another user's version.
    """
    conn, user = auth
    uid = str(user.user_id)

    # Verify the version exists and belongs to this user via explicit JOIN.
    # RLS also enforces this, but we add an explicit predicate for defence-in-depth.
    version_row = conn.execute(
        sa.text(
            "SELECT dv.id "
            "FROM document_versions dv "
            "JOIN documents d ON d.id = dv.document_id "
            "WHERE dv.id = :vid AND d.user_id = :uid AND d.deleted_at IS NULL"
        ),
        {"vid": str(body.version_id), "uid": uid},
    ).fetchone()

    if not version_row:
        raise HTTPException(
            status_code=404,
            detail="Versi dokumen tidak ditemukan.",
        )

    job = conn.execute(
        sa.text(
            "INSERT INTO analysis_jobs (user_id, version_id, state, stage) "
            "VALUES (:uid, :vid, 'queued', 'Menunggu antrian analisis') "
            "RETURNING id, version_id, user_id, state, stage, error_message, created_at, finished_at"
        ),
        {"uid": uid, "vid": str(body.version_id)},
    ).fetchone()

    consume_quota(conn, uid)

    logger.info(
        "analysis_enqueued",
        job_id=str(job.id),
        version_id=str(body.version_id),
        user_id=uid,
    )

    return _job_row_to_response(job)


@router.get("/{job_id}", response_model=AnalysisJobResponse)
def get_analysis(
    job_id: UUID,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> AnalysisJobResponse:
    """Return the current state of an analysis job.

    The frontend polls this every ~3 seconds and renders `stage` as progress.
    Returns 404 if the job doesn't exist or belongs to another user.
    Explicit user_id = :uid ensures isolation beyond RLS.
    """
    conn, user = auth
    uid = str(user.user_id)

    row = conn.execute(
        sa.text(
            "SELECT aj.id, aj.version_id, aj.user_id, aj.state, aj.stage, "
            "aj.error_message, aj.created_at, aj.finished_at "
            "FROM analysis_jobs aj "
            "WHERE aj.id = :jid AND aj.user_id = :uid"
        ),
        {"jid": str(job_id), "uid": uid},
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Pekerjaan analisis tidak ditemukan.",
        )

    return _job_row_to_response(row)
