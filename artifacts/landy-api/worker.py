"""LANDY Creator background worker.

This process polls analysis_jobs for queued work, runs the document pipeline,
and writes results back to the DB. It runs as a separate OS process alongside
the FastAPI app (docker-compose: same image, different CMD).

Pipeline stages per job:
  1. Memuat dokumen dari penyimpanan   — download blob from MinIO
  2. Mengekstrak teks dari dokumen     — text extraction (DOCX / PDF / OCR)
  3. Mendeteksi bahasa dokumen         — language detection
  4. Mensegmentasi klausul kontrak     — clause segmentation
  5. Menyunting informasi pribadi      — PII redaction, save mapping to DB
  (6. Analisis AI                      — LLM analysis, wired in Task #3)

RLS / isolation contract:
  Every transaction in the worker begins with:
      SET LOCAL app.current_user_id = 'SYSTEM_WORKER'
  This satisfies the RLS policy check `current_setting(...) = 'SYSTEM_WORKER'`
  that was added in migration 0005. The worker therefore sees all rows across
  all users. The API never sets 'SYSTEM_WORKER' — it always sets the
  authenticated user's UUID from a validated session token — so a client
  cannot forge operator access through the API.

Error handling:
  - MinIO download fails → job state = 'failed', error_message populated
  - Extraction fails     → extraction_ok = False in document_versions; job = 'done'
                           (failure is a user-visible result, not a system crash)
  - Unexpected exception → job state = 'failed', error_message populated

On startup, any job stuck in state='running' from a previous crashed worker
is reset to 'queued' so it gets retried.

Retention cleanup runs every 6 hours: hard-deletes blobs + rows for documents
soft-deleted more than RETENTION_DAYS ago.
"""
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta

import sqlalchemy as sa
from apscheduler.schedulers.background import BackgroundScheduler

from landy.config import settings
from landy.database import engine
from landy.extraction import extract
from landy.logging_setup import configure_logging, logger
from landy.redaction import persist_mapping, redact
from landy.segmentation import segment
import landy.storage as storage

configure_logging()

_POLL_INTERVAL_SECONDS = 5
_RETENTION_CLEANUP_HOURS = 6
_WORKER_TOKEN = "SYSTEM_WORKER"


def _worker_conn():
    """Context manager for a worker transaction with RLS bypass token set."""
    return engine.begin()


def _exec_worker(sql: str, params: dict | None = None):
    """Execute SQL in a single worker transaction with SYSTEM_WORKER RLS token."""
    with engine.begin() as conn:
        conn.execute(
            sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'")
        )
        result = conn.execute(sa.text(sql), params or {})
        return result


# ── Job lifecycle helpers ─────────────────────────────────────────────────────

def _set_stage(job_id: str, stage: str) -> None:
    _exec_worker(
        "UPDATE analysis_jobs SET stage = :stage WHERE id = :id",
        {"stage": stage, "id": job_id},
    )


def _mark_done(job_id: str) -> None:
    _exec_worker(
        "UPDATE analysis_jobs SET state = 'done', stage = 'Selesai', "
        "finished_at = now() WHERE id = :id",
        {"id": job_id},
    )


def _mark_failed(job_id: str, error_message: str) -> None:
    logger.error("job_failed", job_id=job_id, error=error_message)
    _exec_worker(
        "UPDATE analysis_jobs SET state = 'failed', "
        "error_message = :err, finished_at = now() WHERE id = :id",
        {"err": error_message[:2000], "id": job_id},
    )


def _refund_quota(job_id: str, user_id: str) -> bool:
    """Return the job's quota unit to the user (MV decision 2026-08-02).

    Idempotent: the quota_refunded flag on the job is flipped first, in the
    same guarded UPDATE pattern as LC-15, so a re-run can never refund twice.
    Returns True when a refund was actually applied.
    """
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        claimed = conn.execute(
            sa.text(
                "UPDATE analysis_jobs SET quota_refunded = TRUE "
                "WHERE id = :jid AND quota_refunded = FALSE "
                "RETURNING id"
            ),
            {"jid": job_id},
        ).fetchone()
        if not claimed:
            return False
        conn.execute(
            sa.text(
                "UPDATE users SET analyses_used = GREATEST(analyses_used - 1, 0) "
                "WHERE id = :uid"
            ),
            {"uid": user_id},
        )
    logger.info("quota_refunded", job_id=job_id, user_id=user_id)
    return True


# ── Pipeline stages ───────────────────────────────────────────────────────────

def _process_job(job_id: str, version_id: str, user_id: str) -> None:
    """Run the full pipeline for one analysis job."""

    # ── 1. Download blob ──────────────────────────────────────────────────────
    _set_stage(job_id, "Memuat dokumen dari penyimpanan")
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        version_row = conn.execute(
            sa.text(
                "SELECT storage_key, source_filename, source_format "
                "FROM document_versions WHERE id = :vid"
            ),
            {"vid": version_id},
        ).fetchone()

    if not version_row:
        _mark_failed(job_id, f"Versi dokumen {version_id} tidak ditemukan di database.")
        return

    try:
        file_bytes = storage.download_bytes(version_row.storage_key)
    except Exception as exc:
        _mark_failed(job_id, f"Gagal mengunduh dokumen dari penyimpanan: {exc}")
        return

    # ── 2. Extract text ────────────────────────────────────────────────────────
    _set_stage(job_id, "Mengekstrak teks dari dokumen")
    result = extract(file_bytes, version_row.source_filename)

    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        conn.execute(
            sa.text(
                "UPDATE document_versions SET "
                "extraction_ok = :ok, "
                "extraction_note = :note, "
                "source_format = :fmt "
                "WHERE id = :vid"
            ),
            {
                "ok": result.extraction_ok,
                "note": result.extraction_note,
                "fmt": result.source_format,
                "vid": version_id,
            },
        )

    if not result.extraction_ok:
        # Extraction failure surfaces to the user but does not crash the job.
        _mark_done(job_id)
        logger.warning(
            "extraction_failed",
            job_id=job_id,
            version_id=version_id,
            note=result.extraction_note,
        )
        return

    # ── 3. Detect language ────────────────────────────────────────────────────
    _set_stage(job_id, "Mendeteksi bahasa dokumen")
    detected_language = _detect_language(result.text)
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        conn.execute(
            sa.text(
                "UPDATE document_versions SET detected_language = :lang WHERE id = :vid"
            ),
            {"lang": detected_language, "vid": version_id},
        )

    # ── 4. Segment clauses ────────────────────────────────────────────────────
    _set_stage(job_id, "Mensegmentasi klausul kontrak")
    clauses = segment(result.text)
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        for clause in clauses:
            conn.execute(
                sa.text(
                    "INSERT INTO clauses "
                    "(version_id, ordinal, heading_path, text, char_start, char_end) "
                    "VALUES (:vid, :ord, :hp, :text, :cs, :ce) "
                    "ON CONFLICT (version_id, ordinal) DO UPDATE "
                    "SET heading_path = EXCLUDED.heading_path, "
                    "text = EXCLUDED.text, char_start = EXCLUDED.char_start, "
                    "char_end = EXCLUDED.char_end"
                ),
                {
                    "vid": version_id,
                    "ord": clause.ordinal,
                    "hp": clause.heading_path,
                    "text": clause.text,
                    "cs": clause.char_start,
                    "ce": clause.char_end,
                },
            )

    logger.info("clauses_saved", version_id=version_id, count=len(clauses))

    # ── 2.5. Parse DOCX tracked changes + comment bubbles ────────────────────
    # DOCX-only — PDFs have no standardised revision-mark format (their
    # tc/comments parse statuses stay NULL = not applicable).
    # Non-fatal for the job, but never silent: a parse failure is persisted as
    # tc_parse_status/comments_parse_status = 'failed' so the UI can say
    # "revisi/komentar tidak dapat dibaca" instead of claiming a clean document.
    _tc_result = None
    if result.source_format == "docx" and result.extraction_ok:
        _set_stage(job_id, "Membaca track changes dan komentar dari DOCX")
        from landy.tracked_changes import parse_tracked_changes
        from landy.doc_comments import parse_comments

        _tc_result = parse_tracked_changes(file_bytes)
        _comments_result = parse_comments(file_bytes)

        try:
            # Persist tracked-changes flag + both parse statuses on the version
            with engine.begin() as conn:
                conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
                conn.execute(
                    sa.text(
                        "UPDATE document_versions SET "
                        "has_tracked_changes = :htc, "
                        "tc_parse_status = :tcs, "
                        "tc_parse_note = :tcn, "
                        "comments_parse_status = :cps, "
                        "comments_parse_note = :cpn "
                        "WHERE id = :vid"
                    ),
                    {
                        "htc": _tc_result.has_changes,
                        "tcs": "ok" if _tc_result.parse_ok else "failed",
                        "tcn": _tc_result.parse_note,
                        "cps": "ok" if _comments_result.parse_ok else "failed",
                        "cpn": _comments_result.parse_note,
                        "vid": version_id,
                    },
                )

            # Persist extracted comment bubbles (idempotent via DELETE+INSERT)
            if _comments_result.comments:
                with engine.begin() as conn:
                    conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
                    # Delete any prior comments for this version (idempotent re-run)
                    conn.execute(
                        sa.text("DELETE FROM document_comments WHERE version_id = :vid"),
                        {"vid": version_id},
                    )
                    for c in _comments_result.comments:
                        conn.execute(
                            sa.text(
                                "INSERT INTO document_comments "
                                "(version_id, author, comment_date, anchor_text, body, ordinal) "
                                "VALUES (:vid, :auth, :cdate, :anchor, :body, :ord)"
                            ),
                            {
                                "vid": version_id,
                                "auth": (c.author or "")[:255] or None,
                                "cdate": (c.date or "")[:64] or None,
                                "anchor": c.anchor_text[:2000] if c.anchor_text else None,
                                "body": c.body[:4000],
                                "ord": int(c.comment_id) if c.comment_id.isdigit() else 0,
                            },
                        )

            logger.info(
                "docx_tc_comments_parsed",
                version_id=version_id,
                has_tc=_tc_result.has_changes,
                tc_parse_status="ok" if _tc_result.parse_ok else "failed",
                tc_count=len(_tc_result.changes),
                comments_parse_status="ok" if _comments_result.parse_ok else "failed",
                comments_count=len(_comments_result.comments),
            )
        except Exception as exc:
            # DB persistence failed (the parsers themselves never raise).
            # Record the failure on the version row so the downgrade to
            # text-diff is visible, then continue without tracked changes.
            logger.error(
                "docx_tc_comments_error",
                version_id=version_id,
                error=str(exc),
            )
            _tc_result = None
            try:
                with engine.begin() as conn:
                    conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
                    conn.execute(
                        sa.text(
                            "UPDATE document_versions SET "
                            "tc_parse_status = 'failed', "
                            "tc_parse_note = :note, "
                            "comments_parse_status = 'failed', "
                            "comments_parse_note = :note "
                            "WHERE id = :vid"
                        ),
                        {
                            "note": f"Gagal menyimpan hasil pembacaan revisi/komentar: {exc}",
                            "vid": version_id,
                        },
                    )
            except Exception as exc2:
                # Even the status write failed — surface loudly in logs; the
                # job-level error path is the only remaining honest channel.
                logger.error(
                    "docx_tc_comments_status_write_failed",
                    version_id=version_id,
                    error=str(exc2),
                )

        # A failed revision-layer parse must not feed downstream consumers a
        # confident "no changes" object.
        if _tc_result is not None and not _tc_result.parse_ok:
            _tc_result = None

    # ── 4.5. Version diff (if version_no > 1) ────────────────────────────────
    # Runs after segmentation so both versions have clauses; uses non-redacted
    # text so the user sees the real diff. Non-fatal: errors are logged and the
    # job continues.
    if version_row:  # always true here; guard for type narrowing
        with engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
            vno_row = conn.execute(
                sa.text("SELECT version_no FROM document_versions WHERE id = :vid"),
                {"vid": version_id},
            ).fetchone()

        if vno_row and vno_row.version_no > 1:
            try:
                from landy.diff.pipeline import run_diff
                diff_rows = run_diff(
                    to_version_id=version_id,
                    job_id=job_id,
                    user_id=user_id,
                    set_stage_fn=lambda s: _set_stage(job_id, s),
                    tracked_changes=_tc_result,
                )
                logger.info("version_diff_done", job_id=job_id, rows=diff_rows)
            except Exception as exc:
                logger.error(
                    "version_diff_error",
                    job_id=job_id,
                    version_id=version_id,
                    error=str(exc),
                )
                # Non-fatal — continue with the rest of the pipeline

    # ── 5. Redact PII ─────────────────────────────────────────────────────────
    _set_stage(job_id, "Menyunting informasi pribadi")
    redaction_result = redact(result.text)
    if redaction_result.mapping:
        with engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
            persist_mapping(conn, version_id, redaction_result.mapping)
        logger.info(
            "redaction_saved",
            version_id=version_id,
            tokens=len(redaction_result.mapping),
        )

    # ── 6. LLM analysis ───────────────────────────────────────────────────────
    _set_stage(job_id, "Memulai analisis AI")
    try:
        from landy.analysis.pipeline import run_analysis  # imported here to keep startup fast
        from landy.llm import LLMError

        domains_ok, domain_errors = run_analysis(
            version_id=version_id,
            job_id=job_id,
            user_id=user_id,
            set_stage_fn=lambda stage: _set_stage(job_id, stage),
        )

        if domain_errors:
            n_total = domains_ok + len(domain_errors)
            err_summary = (
                f"Analisis selesai: {domains_ok}/{n_total} domain berhasil, "
                f"{len(domain_errors)} domain gagal:\n" +
                "\n".join(domain_errors[:10])
            )
            # MV decision 2026-08-02: a majority-failed analysis is not a
            # result. >50% failed → honest 'failed' job + quota refund. The
            # successful domain runs stay persisted so a retry only re-runs
            # the failed checks.
            if len(domain_errors) * 2 > n_total:
                refunded = _refund_quota(job_id, user_id)
                fail_msg = (
                    f"Analisis gagal: {len(domain_errors)} dari {n_total} "
                    f"pemeriksaan tidak dapat diselesaikan. "
                    + (
                        "Kuota analisis Anda telah dikembalikan. "
                        if refunded
                        else ""
                    )
                    + "Silakan coba lagi — pemeriksaan yang sudah berhasil "
                    "tidak akan diulang. Jika masalah berlanjut, unggah ulang "
                    "dokumen dan pastikan formatnya .docx dan terstruktur."
                )
                _mark_failed(job_id, fail_msg)
                logger.error(
                    "analysis_majority_failed",
                    job_id=job_id,
                    version_id=version_id,
                    domains_ok=domains_ok,
                    domains_failed=len(domain_errors),
                    quota_refunded=refunded,
                )
                return
            else:
                # Partial failure below the threshold — job completes; the
                # failed domains stay visible via analysis_domain_runs and
                # error_message, and the UI blocks the all-clear claim.
                _exec_worker(
                    "UPDATE analysis_jobs SET error_message = :err WHERE id = :id",
                    {"err": err_summary[:2000], "id": job_id},
                )
                logger.warning(
                    "analysis_partial_failure",
                    job_id=job_id,
                    domains_ok=domains_ok,
                    domains_failed=len(domain_errors),
                )

    except LLMError as exc:
        # LLM misconfigured (no API key, wrong provider) — hard failure
        _mark_failed(job_id, f"Konfigurasi LLM tidak valid: {exc}")
        logger.error("analysis_llm_config_error", job_id=job_id, error=str(exc))
        return

    _mark_done(job_id)
    logger.info(
        "job_done",
        job_id=job_id,
        version_id=version_id,
        clauses=len(clauses),
        redacted_tokens=len(redaction_result.mapping),
    )


def _detect_language(text: str) -> str:
    """Return 'id', 'en', or 'mixed'. Defaults to 'id' if detection fails."""
    try:
        from langdetect import detect, DetectorFactory, LangDetectException  # type: ignore[import]
        DetectorFactory.seed = 0
        lang = detect(text[:3000])
        if lang == "id":
            return "id"
        elif lang == "en":
            return "en"
        else:
            return "mixed"
    except Exception:
        return "id"  # default for Indonesian creator contracts


# ── Main poll loop ────────────────────────────────────────────────────────────

def _claim_one_job() -> dict | None:
    """Atomically claim one queued job with SYSTEM_WORKER RLS bypass."""
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        row = conn.execute(
            sa.text(
                "UPDATE analysis_jobs SET state = 'running', "
                "stage = 'Memulai analisis' "
                "WHERE id = ( "
                "    SELECT id FROM analysis_jobs "
                "    WHERE state = 'queued' "
                "    ORDER BY created_at ASC "
                "    FOR UPDATE SKIP LOCKED "
                "    LIMIT 1 "
                ") "
                "RETURNING id, version_id, user_id"
            )
        ).fetchone()
        if not row:
            return None
        return {"id": str(row.id), "version_id": str(row.version_id), "user_id": str(row.user_id)}


def _recover_stuck_jobs() -> None:
    """On startup, reset any 'running' jobs to 'queued'."""
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        result = conn.execute(
            sa.text(
                "UPDATE analysis_jobs SET state = 'queued', "
                "stage = 'Menunggu antrian analisis (restart)' "
                "WHERE state = 'running' "
                "RETURNING id"
            )
        )
        recovered = result.rowcount
        if recovered:
            logger.info("worker_recovered_stuck_jobs", count=recovered)


# ── Retention cleanup ─────────────────────────────────────────────────────────

def _cleanup_deleted_documents() -> None:
    """Hard-delete blobs + rows for documents soft-deleted > RETENTION_DAYS ago."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    logger.info("retention_cleanup_start", cutoff=cutoff.isoformat())

    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        keys = conn.execute(
            sa.text(
                "SELECT dv.storage_key "
                "FROM document_versions dv "
                "JOIN documents d ON d.id = dv.document_id "
                "WHERE d.deleted_at IS NOT NULL AND d.deleted_at < :cutoff"
            ),
            {"cutoff": cutoff},
        ).fetchall()

        for row in keys:
            try:
                storage.delete_object(row.storage_key)
            except Exception as exc:
                logger.error(
                    "retention_blob_delete_failed",
                    key=row.storage_key,
                    error=str(exc),
                )

    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        result = conn.execute(
            sa.text(
                "DELETE FROM documents "
                "WHERE deleted_at IS NOT NULL AND deleted_at < :cutoff"
            ),
            {"cutoff": cutoff},
        )
        logger.info("retention_cleanup_done", documents_deleted=result.rowcount)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("landy_worker_start", poll_interval=_POLL_INTERVAL_SECONDS)

    # Fail fast if no LLM provider is configured — every job this worker
    # claims ends in an LLM analysis call, so an unconfigured provider is a
    # boot-time error, not a per-job failure discovered later.
    from landy.llm import assert_llm_configured
    assert_llm_configured()

    # Bootstrap storage backend — auto-selects local filesystem if S3 is
    # unreachable (same logic as the API server). Must run before any job is
    # processed so download_bytes() uses the correct backend.
    try:
        storage.bootstrap_bucket()
    except Exception as exc:
        logger.error("worker_storage_bootstrap_failed", error=str(exc))

    _recover_stuck_jobs()

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _cleanup_deleted_documents,
        "interval",
        hours=_RETENTION_CLEANUP_HOURS,
        id="retention_cleanup",
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    scheduler.start()

    try:
        while True:
            job = _claim_one_job()
            if job:
                logger.info(
                    "job_claimed",
                    job_id=job["id"],
                    version_id=job["version_id"],
                )
                try:
                    _process_job(job["id"], job["version_id"], job["user_id"])
                except Exception as exc:
                    _mark_failed(
                        job["id"],
                        f"Kesalahan tak terduga: {traceback.format_exc()[-1000:]}",
                    )
            else:
                time.sleep(_POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("landy_worker_stop", reason="keyboard_interrupt")
        scheduler.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
