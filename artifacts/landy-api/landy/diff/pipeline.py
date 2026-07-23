"""Version diff orchestration pipeline.

Entry point: `run_diff(from_version_id, to_version_id, job_id, user_id, set_stage_fn)`

Called from the worker when version_no > 1, after clause segmentation.
Fetches clauses for both versions, computes the diff, classifies materiality
via LLM, and persists `version_diffs` rows.

Failure handling:
  - Missing prior-version clauses: logs a warning, writes no rows (non-fatal).
  - LLM materiality failures: handled in materiality.py; rows are still
    persisted with "Klasifikasi tidak tersedia" reasons.
  - Any unexpected exception: caught in worker.py; never crashes the job.

Security: every DB operation sets SYSTEM_WORKER RLS token so the worker can
read across all users' rows.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

import sqlalchemy as sa

from landy.database import engine
from landy.diff.compute import DiffEntry, compute_clause_diff
from landy.diff.materiality import classify_materiality
from landy.logging_setup import logger

if TYPE_CHECKING:
    from landy.tracked_changes import TrackedChangesResult


# ── DB helpers ────────────────────────────────────────────────────────────────

def _fetch_version_clauses(version_id: str) -> list[dict]:
    """Return clauses for a version ordered by ordinal. Empty list if none."""
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        rows = conn.execute(
            sa.text(
                "SELECT id, ordinal, heading_path, text "
                "FROM clauses WHERE version_id = :vid ORDER BY ordinal ASC"
            ),
            {"vid": version_id},
        ).fetchall()
    return [
        {
            "id": str(r.id),
            "ordinal": r.ordinal,
            "heading_path": r.heading_path,
            "text": r.text,
        }
        for r in rows
    ]


def _fetch_prior_version_id(to_version_id: str) -> Optional[str]:
    """Return the immediately preceding version_id for the same document.

    Looks up the document from to_version_id, finds the version with
    version_no = to_version.version_no - 1.

    Returns None if no prior version exists.
    """
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        row = conn.execute(
            sa.text(
                "SELECT dv_prev.id AS prior_id "
                "FROM document_versions dv "
                "JOIN document_versions dv_prev "
                "  ON dv_prev.document_id = dv.document_id "
                "  AND dv_prev.version_no = dv.version_no - 1 "
                "WHERE dv.id = :vid"
            ),
            {"vid": to_version_id},
        ).fetchone()
    return str(row.prior_id) if row else None


def _delete_existing_diff(from_version_id: str, to_version_id: str) -> None:
    """Delete any existing diff rows for this pair (idempotent re-run)."""
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        conn.execute(
            sa.text(
                "DELETE FROM version_diffs "
                "WHERE from_version = :fv AND to_version = :tv"
            ),
            {"fv": from_version_id, "tv": to_version_id},
        )


def _persist_diff_rows(
    from_version_id: str,
    to_version_id: str,
    entries_with_materiality: list[tuple],  # (DiffEntry, materiality, reason)
) -> int:
    """Persist version_diffs rows. Returns row count written."""
    if not entries_with_materiality:
        return 0

    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        for entry, materiality, reason in entries_with_materiality:
            conn.execute(
                sa.text(
                    "INSERT INTO version_diffs "
                    "(from_version, to_version, clause_ref, change_kind, "
                    " materiality, materiality_reason, before_text, after_text) "
                    "VALUES (:fv, :tv, :ref, :kind, :mat, :reason, :before, :after)"
                ),
                {
                    "fv": from_version_id,
                    "tv": to_version_id,
                    "ref": entry.clause_ref,
                    "kind": entry.change_kind,
                    "mat": materiality,
                    "reason": reason,
                    "before": entry.before_text,
                    "after": entry.after_text,
                },
            )
    return len(entries_with_materiality)


# ── Public entry point ────────────────────────────────────────────────────────

def _tc_to_diff_entries(tc_changes: list) -> list[DiffEntry]:
    """Convert TrackedChange objects to DiffEntry objects.

    Each paragraph with tracked changes becomes one DiffEntry.  The
    materiality pipeline treats them identically to text-diff entries.
    """
    entries: list[DiffEntry] = []
    for tc in tc_changes:
        orig = tc.original_text.strip()
        rev = tc.revised_text.strip()
        if orig and rev:
            kind = "modified"
        elif rev:
            kind = "added"
        else:
            kind = "removed"
        entries.append(DiffEntry(
            change_kind=kind,
            clause_ref=tc.clause_ref,
            before_text=orig or None,
            after_text=rev or None,
        ))
    return entries


def run_diff(
    to_version_id: str,
    job_id: str,
    user_id: str,
    set_stage_fn: Callable[[str], None],
    tracked_changes: "Optional[TrackedChangesResult]" = None,
) -> int:
    """Compute and persist a version diff with LLM materiality classification.

    Args:
        to_version_id:   The new version being uploaded.
        job_id:          UUID of the current analysis_jobs row (for usage_events).
        user_id:         UUID of the owning user (for usage_events).
        set_stage_fn:    Callback to update the job's stage label in the worker.
        tracked_changes: Optional parsed tracked-change result from the DOCX.
                         When present and has_changes=True, TC pairs are used
                         directly as diff entries (skipping clause-level textual
                         diff) to produce more precise before/after text.

    Returns:
        Number of diff rows written (0 if no prior version or no changes).

    This function is intentionally non-raising — all errors are logged.
    The caller (worker) catches any propagated exception and logs it.
    """
    set_stage_fn("Mencari versi sebelumnya")
    from_version_id = _fetch_prior_version_id(to_version_id)
    if not from_version_id:
        logger.info(
            "version_diff_no_prior",
            to_version_id=to_version_id,
            note="No prior version found; skipping diff",
        )
        return 0

    # ── Decide diff strategy ──────────────────────────────────────────────────
    use_tracked_changes = bool(tracked_changes and tracked_changes.has_changes)

    if use_tracked_changes:
        # Tracked changes found: convert to DiffEntry objects directly.
        # We still need new_clauses for the materiality call's clause context,
        # but we do NOT need to compute a textual diff.
        set_stage_fn(
            f"Menggunakan Track Changes sebagai sumber diff "
            f"({len(tracked_changes.changes)} paragraf)"  # type: ignore[union-attr]
        )
        entries = _tc_to_diff_entries(tracked_changes.changes)  # type: ignore[union-attr]

        if not entries:
            logger.info(
                "version_diff_tc_empty_after_conversion",
                to_version_id=to_version_id,
            )
            return 0
    else:
        # No tracked changes: load clauses from both versions and text-diff them.
        set_stage_fn("Memuat klausul dari versi sebelumnya")
        old_clauses = _fetch_version_clauses(from_version_id)
        new_clauses = _fetch_version_clauses(to_version_id)

        if not old_clauses:
            logger.warning(
                "version_diff_no_prior_clauses",
                from_version_id=from_version_id,
                to_version_id=to_version_id,
                note="Prior version has no clauses (extraction may have failed); skipping diff",
            )
            return 0

        if not new_clauses:
            logger.warning(
                "version_diff_no_new_clauses",
                to_version_id=to_version_id,
                note="New version has no clauses (extraction may have failed); skipping diff",
            )
            return 0

        set_stage_fn("Menghitung perbedaan antar versi")
        entries = compute_clause_diff(old_clauses, new_clauses)

    if not entries:
        logger.info(
            "version_diff_no_changes",
            from_version_id=from_version_id,
            to_version_id=to_version_id,
        )
        return 0

    logger.info(
        "version_diff_computed",
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        changes=len(entries),
        source="tracked_changes" if use_tracked_changes else "text_diff",
    )

    set_stage_fn(f"Mengklasifikasi materialitas {len(entries)} perubahan klausul")
    materiality_results = classify_materiality(entries, job_id, user_id)

    # Pair each entry with its (materiality, reason)
    entries_with_materiality = [
        (entry, mat, reason)
        for entry, (mat, reason) in zip(entries, materiality_results)
    ]

    # Idempotent: delete any prior diff rows for this pair before reinserting
    _delete_existing_diff(from_version_id, to_version_id)
    rows_written = _persist_diff_rows(from_version_id, to_version_id, entries_with_materiality)

    material_count = sum(1 for _, mat, _ in entries_with_materiality if mat == "material")
    logger.info(
        "version_diff_persisted",
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        rows_written=rows_written,
        material=material_count,
        immaterial=rows_written - material_count,
    )
    return rows_written
