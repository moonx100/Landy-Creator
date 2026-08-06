"""Regression test for LC-25: PATCH /suggested-edits/{edit_id} tenant isolation.

The route's UPDATE previously carried no user_id/ownership predicate of its
own — only the preceding ownership SELECT was scoped. Not exploitable in the
route as written (the SELECT already 404s on a foreign edit_id before the
UPDATE runs), but it broke the "every query is scoped, including the mutating
one" invariant every other route in landy-api follows. This test exercises the
UPDATE's own SQL directly with a foreign user_id, so a future edit that drops
the ownership SELECT (or reorders it) cannot silently update another tenant's
row.

Run with:
    DATABASE_URL=... python -m pytest tests/test_suggested_edit_isolation.py -v
"""
import os
import uuid

import pytest
import sqlalchemy as sa

from landy.database import engine

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping DB integration tests",
)

# Same UPDATE the route issues (landy/routes/exports.py::patch_suggested_edit).
_UPDATE_SQL = (
    "UPDATE suggested_edits SET accepted = :val "
    "WHERE id = :eid AND EXISTS ("
    "  SELECT 1 FROM risk_flags rf "
    "  JOIN document_versions dv ON dv.id = rf.version_id "
    "  JOIN documents d ON d.id = dv.document_id "
    "  WHERE rf.id = suggested_edits.risk_flag_id "
    "    AND d.user_id = :uid AND d.deleted_at IS NULL"
    ")"
)


def _run(sql: str, params: dict | None = None):
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        return conn.execute(sa.text(sql), params or {})


def _fetch_one(sql: str, params: dict | None = None):
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        return conn.execute(sa.text(sql), params or {}).fetchone()


@pytest.fixture
def owner_and_edit():
    """A suggested_edit belonging to `owner_uid`, plus an unrelated `other_uid`."""
    owner_uid = str(uuid.uuid4())
    other_uid = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    flag_id = str(uuid.uuid4())
    edit_id = str(uuid.uuid4())

    _run("INSERT INTO users (id, email, is_active) VALUES (:id, :email, true)",
         {"id": owner_uid, "email": f"owner-{owner_uid[:8]}@example.com"})
    _run("INSERT INTO users (id, email, is_active) VALUES (:id, :email, true)",
         {"id": other_uid, "email": f"other-{other_uid[:8]}@example.com"})
    _run("INSERT INTO documents (id, user_id, title) VALUES (:id, :uid, 'Test Contract')",
         {"id": doc_id, "uid": owner_uid})
    _run(
        "INSERT INTO document_versions "
        "(id, document_id, version_no, source_filename, source_format, storage_key, sha256, extraction_ok) "
        "VALUES (:id, :did, 1, 'test.docx', 'docx', 'test/key', 'abc123', true)",
        {"id": version_id, "did": doc_id},
    )
    _run(
        "INSERT INTO analysis_jobs (id, user_id, version_id, state, stage) "
        "VALUES (:id, :uid, :vid, 'done', 'Selesai')",
        {"id": job_id, "uid": owner_uid, "vid": version_id},
    )
    _run(
        "INSERT INTO risk_flags "
        "(id, job_id, version_id, domain, severity, finding_type, summary, rationale) "
        "VALUES (:id, :jid, :vid, 'ip_ownership', 'high', 'present_risky', 'S', 'R')",
        {"id": flag_id, "jid": job_id, "vid": version_id},
    )
    _run(
        "INSERT INTO suggested_edits "
        "(id, risk_flag_id, clause_id, original_text, revised_text, accepted) "
        "VALUES (:id, :fid, NULL, 'orig', 'revised', NULL)",
        {"id": edit_id, "fid": flag_id},
    )

    yield {"owner_uid": owner_uid, "other_uid": other_uid, "edit_id": edit_id}

    _run("DELETE FROM users WHERE id IN (:o, :a)", {"o": owner_uid, "a": other_uid})


def test_foreign_user_cannot_update_edit(owner_and_edit):
    edit_id = owner_and_edit["edit_id"]
    other_uid = owner_and_edit["other_uid"]

    _run(_UPDATE_SQL, {"val": True, "eid": edit_id, "uid": other_uid})

    row = _fetch_one(
        "SELECT accepted FROM suggested_edits WHERE id = :id", {"id": edit_id}
    )
    assert row.accepted is None, "a foreign user_id must not be able to update the row"


def test_owner_can_update_edit(owner_and_edit):
    edit_id = owner_and_edit["edit_id"]
    owner_uid = owner_and_edit["owner_uid"]

    _run(_UPDATE_SQL, {"val": True, "eid": edit_id, "uid": owner_uid})

    row = _fetch_one(
        "SELECT accepted FROM suggested_edits WHERE id = :id", {"id": edit_id}
    )
    assert row.accepted is True
