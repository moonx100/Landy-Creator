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
    # DOCX-only — PDFs have no standardised revision-mark format.
    # Non-fatal: any failure is logged and the pipeline continues unaffected.
    _tc_result = None
    if result.source_format == "docx" and result.extraction_ok:
        _set_stage(job_id, "Membaca track changes dan komentar dari DOCX")
        try:
            from landy.tracked_changes import parse_tracked_changes
            from landy.doc_comments import parse_comments

            _tc_result = parse_tracked_changes(file_bytes)
            _comments_result = parse_comments(file_bytes)

            # Persist has_tracked_changes flag on the version row
            with engine.begin() as conn:
                conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
                conn.execute(
                    sa.text(
                        "UPDATE document_versions "
                        "SET has_tracked_changes = :htc WHERE id = :vid"
                    ),
                    {"htc": _tc_result.has_changes, "vid": version_id},
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
                tc_count=len(_tc_result.changes),
                comments_count=len(_comments_result.comments),
            )
        except Exception as exc:
            logger.error(
                "docx_tc_comments_error",
                version_id=version_id,
                error=str(exc),
            )
            _tc_result = None  # fall back to text-level diff

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
            if domains_ok == 0:
                # All domains failed — hard failure
                _mark_failed(job_id, err_summary)
                logger.error(
                    "analysis_all_domains_failed",
                    job_id=job_id,
                    version_id=version_id,
                    domain_errors=domain_errors,
                )
                return
            else:
                # Partial failure — job completes but records which domains failed
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
