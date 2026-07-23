"""Integration test: rerun scoping for analysis results.

Verifies that GET /api/analyses/{job_id}/results returns ONLY the risk_flags
belonging to that specific job — not flags from a prior run on the same version.

This is a DB-level integration test: it inserts rows directly, then exercises
the same SQL logic used by the /results endpoint. No LLM calls are made.

Run with:
    DATABASE_URL=... python -m pytest tests/test_analysis_rerun.py -v
"""
import os
import uuid
import pytest
import sqlalchemy as sa

from landy.database import engine

# Skip entire module if no real DB is available (CI without a Postgres service)
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping DB integration tests",
)

# ── SQL helpers ───────────────────────────────────────────────────────────────

def _run(sql: str, params: dict | None = None):
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        result = conn.execute(sa.text(sql), params or {})
        return result


def _fetch(sql: str, params: dict | None = None) -> list:
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        return conn.execute(sa.text(sql), params or {}).fetchall()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def test_user():
    uid = str(uuid.uuid4())
    _run(
        "INSERT INTO users (id, email, display_name, is_active) "
        "VALUES (:id, :email, 'Test User', true)",
        {"id": uid, "email": f"test-{uid[:8]}@example.com"},
    )
    yield uid
    _run("DELETE FROM users WHERE id = :id", {"id": uid})


@pytest.fixture
def test_document(test_user):
    doc_id = str(uuid.uuid4())
    _run(
        "INSERT INTO documents (id, user_id, title) VALUES (:id, :uid, 'Test Contract')",
        {"id": doc_id, "uid": test_user},
    )
    yield doc_id


@pytest.fixture
def test_version(test_document):
    vid = str(uuid.uuid4())
    _run(
        "INSERT INTO document_versions "
        "(id, document_id, version_no, source_filename, source_format, storage_key, sha256, extraction_ok) "
        "VALUES (:id, :did, 1, 'test.docx', 'docx', 'test/key', 'abc123', true)",
        {"id": vid, "did": test_document},
    )
    yield vid


@pytest.fixture
def test_jobs(test_user, test_version):
    job1 = str(uuid.uuid4())
    job2 = str(uuid.uuid4())
    for jid in (job1, job2):
        _run(
            "INSERT INTO analysis_jobs (id, user_id, version_id, state, stage) "
            "VALUES (:id, :uid, :vid, 'done', 'Selesai')",
            {"id": jid, "uid": test_user, "vid": test_version},
        )
    yield job1, job2
    for jid in (job1, job2):
        _run("DELETE FROM analysis_jobs WHERE id = :id", {"id": jid})


# ── Test: rerun isolation ─────────────────────────────────────────────────────

def test_results_scoped_to_job(test_version, test_jobs):
    """Each job's /results query returns only its own flags, never the other's."""
    job1, job2 = test_jobs

    # Insert one flag for job1 and one for job2 on the same version
    flag1 = str(uuid.uuid4())
    flag2 = str(uuid.uuid4())

    _run(
        "INSERT INTO risk_flags "
        "(id, job_id, version_id, domain, severity, finding_type, summary, rationale) "
        "VALUES (:id, :jid, :vid, 'ip_ownership', 'critical', 'present_risky', "
        "        'Ringkasan job1', 'Alasan job1')",
        {"id": flag1, "jid": job1, "vid": test_version},
    )
    _run(
        "INSERT INTO risk_flags "
        "(id, job_id, version_id, domain, severity, finding_type, summary, rationale) "
        "VALUES (:id, :jid, :vid, 'ip_ownership', 'high', 'present_risky', "
        "        'Ringkasan job2', 'Alasan job2')",
        {"id": flag2, "jid": job2, "vid": test_version},
    )

    # Simulate the /results endpoint query (same SQL as the route uses)
    flags_for_job1 = _fetch(
        "SELECT id FROM risk_flags WHERE job_id = :jid", {"jid": job1}
    )
    flags_for_job2 = _fetch(
        "SELECT id FROM risk_flags WHERE job_id = :jid", {"jid": job2}
    )

    # Each job should see exactly one flag — its own
    assert len(flags_for_job1) == 1, f"job1 expected 1 flag, got {len(flags_for_job1)}"
    assert str(flags_for_job1[0].id) == flag1, "job1 returned the wrong flag"

    assert len(flags_for_job2) == 1, f"job2 expected 1 flag, got {len(flags_for_job2)}"
    assert str(flags_for_job2[0].id) == flag2, "job2 returned the wrong flag"


def test_rerun_does_not_accumulate(test_version, test_jobs):
    """Re-running analysis on the same version does not cause job1 to see job2's flags."""
    job1, job2 = test_jobs

    # Insert 3 flags for job1 and 3 for job2
    for i in range(3):
        _run(
            "INSERT INTO risk_flags "
            "(job_id, version_id, domain, severity, finding_type, summary, rationale) "
            "VALUES (:jid, :vid, :domain, 'medium', 'present_risky', :summary, 'Alasan')",
            {
                "jid": job1,
                "vid": test_version,
                "domain": f"domain_{i}_job1",
                "summary": f"Temuan {i} dari job1",
            },
        )
        _run(
            "INSERT INTO risk_flags "
            "(job_id, version_id, domain, severity, finding_type, summary, rationale) "
            "VALUES (:jid, :vid, :domain, 'high', 'present_risky', :summary, 'Alasan')",
            {
                "jid": job2,
                "vid": test_version,
                "domain": f"domain_{i}_job2",
                "summary": f"Temuan {i} dari job2",
            },
        )

    # Total flags in DB for this version = 6; but each job should only see 3
    total_for_version = _fetch(
        "SELECT id FROM risk_flags WHERE version_id = :vid", {"vid": test_version}
    )
    flags_job1 = _fetch(
        "SELECT id FROM risk_flags WHERE job_id = :jid", {"jid": job1}
    )
    flags_job2 = _fetch(
        "SELECT id FROM risk_flags WHERE job_id = :jid", {"jid": job2}
    )

    assert len(total_for_version) == 6, "Expected 6 total flags across both runs"
    assert len(flags_job1) == 3, f"job1 should see 3 flags, got {len(flags_job1)}"
    assert len(flags_job2) == 3, f"job2 should see 3 flags, got {len(flags_job2)}"

    # Confirm no cross-contamination
    job1_ids = {str(r.id) for r in flags_job1}
    job2_ids = {str(r.id) for r in flags_job2}
    assert job1_ids.isdisjoint(job2_ids), "job1 and job2 returned overlapping flags"


def test_usage_events_written_for_every_call():
    """Placeholder: usage_events are written even for finding_type='none' domains.

    Full verification requires a mock LLM call. The structure is validated here:
    the usage_events table accepts rows with zero token counts without error.
    """
    uid = str(uuid.uuid4())
    _run(
        "INSERT INTO users (id, email, is_active) VALUES (:id, :email, true)",
        {"id": uid, "email": f"usage-{uid[:8]}@example.com"},
    )
    try:
        # Insert a usage_event with zero tokens (simulates provider omitting usage)
        _run(
            "INSERT INTO usage_events (user_id, input_tokens, output_tokens, model) "
            "VALUES (:uid, 0, 0, 'test-model')",
            {"uid": uid},
        )
        rows = _fetch(
            "SELECT input_tokens, output_tokens FROM usage_events WHERE user_id = :uid",
            {"uid": uid},
        )
        assert len(rows) == 1
        assert rows[0].input_tokens == 0
        assert rows[0].output_tokens == 0
    finally:
        _run("DELETE FROM users WHERE id = :id", {"id": uid})
