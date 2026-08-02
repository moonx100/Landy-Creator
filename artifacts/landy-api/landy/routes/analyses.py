"""Analysis job endpoints.

POST /api/analyses                    — enqueue a new analysis job for a version
GET  /api/analyses/{job_id}           — poll job state, stage, and error_message
GET  /api/analyses/{job_id}/results   — fetch full risk_flags + suggested_edits

The upload endpoint (POST /api/documents/{id}/versions) auto-enqueues a job.
POST /api/analyses is used to re-trigger analysis on a version whose job failed,
or to trigger analysis manually if the upload step was done separately.
Both consume one quota unit.

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
from landy.models.documents import (
    AnalysisJobResponse,
    AnalysisResultsResponse,
    CitationResponse,
    CreateAnalysisRequest,
    DocCommentResponse,
    RiskFlagResponse,
    SuggestedEditResponse,
)

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
        raise HTTPException(status_code=404, detail="Versi dokumen tidak ditemukan.")

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
        raise HTTPException(status_code=404, detail="Pekerjaan analisis tidak ditemukan.")

    return _job_row_to_response(row)


@router.get("/{job_id}/results", response_model=AnalysisResultsResponse)
def get_analysis_results(
    job_id: UUID,
    auth: Tuple[sa.engine.Connection, Any] = Depends(get_current_user),
) -> AnalysisResultsResponse:
    """Return the full set of risk_flags (with suggested_edits and citations)
    for a completed analysis job.

    Available as soon as the job state is 'done' (or 'failed' — returns
    whatever partial results were persisted before the failure).

    Explicit user_id ensures no cross-user data leakage.
    """
    conn, user = auth
    uid = str(user.user_id)

    # Fetch the job + parent document_id (ownership check via user_id = :uid)
    job_row = conn.execute(
        sa.text(
            "SELECT aj.id, aj.version_id, aj.user_id, aj.state, aj.stage, "
            "aj.error_message, aj.created_at, aj.finished_at, dv.document_id "
            "FROM analysis_jobs aj "
            "JOIN document_versions dv ON dv.id = aj.version_id "
            "WHERE aj.id = :jid AND aj.user_id = :uid"
        ),
        {"jid": str(job_id), "uid": uid},
    ).fetchone()

    if not job_row:
        raise HTTPException(status_code=404, detail="Pekerjaan analisis tidak ditemukan.")

    # Fetch all risk_flags for exactly this job run, ordered by severity then created_at.
    # Scoping by job_id (not version_id) means reruns on the same version never pollute
    # each other's results — each job sees only its own findings.
    _SEVERITY_ORDER = "CASE rf.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END"
    flag_rows = conn.execute(
        sa.text(
            f"SELECT rf.id, rf.clause_id, rf.domain, rf.severity, rf.finding_type, "
            f"rf.summary, rf.rationale, rf.negotiation_ask, rf.created_at "
            f"FROM risk_flags rf "
            f"WHERE rf.job_id = :jid "
            f"ORDER BY {_SEVERITY_ORDER}, rf.created_at ASC"
        ),
        {"jid": str(job_id)},
    ).fetchall()

    # Build flag responses with nested suggested_edits and citations
    flags: list[RiskFlagResponse] = []
    for f in flag_rows:
        flag_id = str(f.id)

        # Suggested edits for this flag
        edit_rows = conn.execute(
            sa.text(
                "SELECT id, clause_id, original_text, revised_text, comment, accepted "
                "FROM suggested_edits WHERE risk_flag_id = :fid ORDER BY id"
            ),
            {"fid": flag_id},
        ).fetchall()

        edits = [
            SuggestedEditResponse(
                id=e.id,
                clause_id=e.clause_id,
                original_text=e.original_text,
                revised_text=e.revised_text,
                comment=e.comment,
                accepted=e.accepted,
            )
            for e in edit_rows
        ]

        # Citation placeholders for this flag
        cite_rows = conn.execute(
            sa.text(
                "SELECT id, provision_id, citation_text, basis "
                "FROM citations WHERE risk_flag_id = :fid ORDER BY id"
            ),
            {"fid": flag_id},
        ).fetchall()

        citations = [
            CitationResponse(
                id=c.id,
                provision_id=c.provision_id,
                citation_text=c.citation_text,
                basis=c.basis,
            )
            for c in cite_rows
        ]

        flags.append(
            RiskFlagResponse(
                id=f.id,
                clause_id=f.clause_id,
                domain=f.domain,
                severity=f.severity,
                finding_type=f.finding_type,
                summary=f.summary,
                rationale=f.rationale,
                negotiation_ask=f.negotiation_ask,
                created_at=f.created_at,
                suggested_edits=edits,
                citations=citations,
            )
        )

    # Fetch document comments for the version (empty for PDFs / no-comment docs)
    version_id_str = str(job_row.version_id)
    comment_rows = conn.execute(
        sa.text(
            "SELECT id, author, comment_date, anchor_text, body, ordinal "
            "FROM document_comments "
            "WHERE version_id = :vid "
            "ORDER BY ordinal ASC"
        ),
        {"vid": version_id_str},
    ).fetchall()

    doc_comments = [
        DocCommentResponse(
            id=c.id,
            author=c.author,
            comment_date=c.comment_date,
            anchor_text=c.anchor_text,
            body=c.body,
            ordinal=c.ordinal,
        )
        for c in comment_rows
    ]

    # Fetch has_tracked_changes + revision/comments parse status for the version
    tc_row = conn.execute(
        sa.text(
            "SELECT has_tracked_changes, tc_parse_status, tc_parse_note, "
            "comments_parse_status, comments_parse_note "
            "FROM document_versions WHERE id = :vid"
        ),
        {"vid": version_id_str},
    ).fetchone()
    has_tracked_changes = bool(tc_row and tc_row.has_tracked_changes)

    # Job-level completeness: summary outcome, quota refund, per-domain runs
    job_meta = conn.execute(
        sa.text(
            "SELECT summary_status, quota_refunded FROM analysis_jobs "
            "WHERE id = :jid AND user_id = :uid"
        ),
        {"jid": str(job_id), "uid": uid},
    ).fetchone()

    run_rows = conn.execute(
        sa.text(
            "SELECT adr.domain_key, adr.status FROM analysis_domain_runs adr "
            "JOIN analysis_jobs aj ON aj.id = adr.job_id "
            "WHERE adr.job_id = :jid AND aj.user_id = :uid"
        ),
        {"jid": str(job_id), "uid": uid},
    ).fetchall()
    failed_domains = sorted(r.domain_key for r in run_rows if r.status == "failed")

    return AnalysisResultsResponse(
        job_id=job_row.id,
        version_id=job_row.version_id,
        document_id=job_row.document_id,
        state=job_row.state,
        stage=job_row.stage,
        error_message=job_row.error_message,
        risk_flags=flags,
        document_comments=doc_comments,
        has_tracked_changes=has_tracked_changes,
        tc_parse_status=tc_row.tc_parse_status if tc_row else None,
        tc_parse_note=tc_row.tc_parse_note if tc_row else None,
        comments_parse_status=tc_row.comments_parse_status if tc_row else None,
        comments_parse_note=tc_row.comments_parse_note if tc_row else None,
        summary_status=job_meta.summary_status if job_meta else None,
        domains_total=len(run_rows),
        domains_failed=len(failed_domains),
        failed_domains=failed_domains,
        quota_refunded=bool(job_meta and job_meta.quota_refunded),
    )
