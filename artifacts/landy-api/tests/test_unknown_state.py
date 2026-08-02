"""Forced-failure acceptance tests for the unified unknown-state pattern (LC-41).

The governance greps verify shapes; these tests verify semantics the greps
cannot see — that a forced failure lands in the honest state and never in a
benign value:

- A malformed DOCX must yield parse_ok=False, never a clean "no revisions" /
  "no comments" result (LC-32 / LC-33).
- An unparseable or out-of-vocabulary materiality answer must yield
  status='failed' with materiality=None, never 'immaterial' (LC-9 / LC-41).
- An out-of-vocabulary finding_type / severity must raise (→ domain run
  'failed'), never coerce to 'none' / 'info' (LC-34 / LC-30).
- A failed summary call must return (None, 'failed'), never a raw text slice
  (LC-35).

Run with:
    python -m pytest tests/test_unknown_state.py -v
"""
from __future__ import annotations

import io
import os
import zipfile

# These are pure-function tests; no DB is touched. Settings still requires a
# DATABASE_URL at import time, so provide a dummy for collection.
os.environ.setdefault(
    "DATABASE_URL", "postgresql://landy:landy@localhost:5432/landy_test_dummy"
)

import pytest

from landy.doc_comments import parse_comments
from landy.tracked_changes import parse_tracked_changes
from landy.diff.materiality import MaterialityResult, _parse_batch_response
from landy.analysis.pipeline import _build_summary, _parse_domain_result, ClauseRow


_W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(document_xml: bytes | None, comments_xml: bytes | None = None) -> bytes:
    """Build a minimal in-memory DOCX (ZIP) with the given parts."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if document_xml is not None:
            zf.writestr("word/document.xml", document_xml)
        if comments_xml is not None:
            zf.writestr("word/comments.xml", comments_xml)
    return buf.getvalue()


_CLEAN_DOC = (
    f'<?xml version="1.0"?><w:document {_W_NS}><w:body>'
    f"<w:p><w:r><w:t>Pasal 1. Teks biasa.</w:t></w:r></w:p>"
    f"</w:body></w:document>"
).encode()


# ── LC-32: tracked changes — failure is never "no revisions" ──────────────────

class TestTrackedChangesUnknownState:
    def test_clean_docx_no_revisions_is_ok(self):
        r = parse_tracked_changes(_docx(_CLEAN_DOC))
        assert r.parse_ok is True
        assert r.has_changes is False
        assert r.parse_note is None

    def test_not_a_zip_is_parse_failure(self):
        r = parse_tracked_changes(b"this is not a zip file")
        assert r.parse_ok is False
        assert r.parse_note
        assert r.has_changes is False and r.changes == []

    def test_missing_document_xml_is_parse_failure(self):
        r = parse_tracked_changes(_docx(None, comments_xml=b"<x/>"))
        assert r.parse_ok is False
        assert "document.xml" in (r.parse_note or "")

    def test_malformed_xml_is_parse_failure(self):
        r = parse_tracked_changes(_docx(b"<w:document><unclosed"))
        assert r.parse_ok is False
        assert r.parse_note

    def test_failure_and_empty_are_distinguishable(self):
        """The core LC-32 property: corrupt file != clean file."""
        clean = parse_tracked_changes(_docx(_CLEAN_DOC))
        corrupt = parse_tracked_changes(b"garbage")
        assert clean.parse_ok != corrupt.parse_ok


# ── LC-33: comments — failure is never "no comments" ──────────────────────────

class TestCommentsUnknownState:
    def test_no_comments_part_is_ok_empty(self):
        r = parse_comments(_docx(_CLEAN_DOC))
        assert r.parse_ok is True
        assert r.comments == []

    def test_not_a_zip_is_parse_failure(self):
        r = parse_comments(b"not a zip")
        assert r.parse_ok is False
        assert r.parse_note

    def test_malformed_comments_xml_is_parse_failure(self):
        r = parse_comments(_docx(_CLEAN_DOC, comments_xml=b"<w:comments><broken"))
        assert r.parse_ok is False
        assert r.comments == []

    def test_anchor_failure_degrades_with_note_not_failure(self):
        comments = (
            f'<?xml version="1.0"?><w:comments {_W_NS}>'
            f'<w:comment w:id="1" w:author="Reviewer">'
            f"<w:p><w:r><w:t>Tolong ubah pasal ini.</w:t></w:r></w:p>"
            f"</w:comment></w:comments>"
        ).encode()
        r = parse_comments(_docx(b"<w:document><unclosed", comments_xml=comments))
        assert r.parse_ok is True  # comments themselves parsed
        assert len(r.comments) == 1
        assert r.parse_note  # anchor degradation surfaced


# ── LC-9 / LC-41: materiality — failure is never 'immaterial' ─────────────────

class TestMaterialityUnknownState:
    def test_valid_response_is_ok(self):
        content = (
            '{"changes": [{"index": 1, "materiality": "material", '
            '"materiality_reason": "Mengubah cakupan hak"}]}'
        )
        [r] = _parse_batch_response(content, 1)
        assert r.status == "ok" and r.materiality == "material"

    def test_out_of_vocabulary_answer_is_failed_not_immaterial(self):
        content = '{"changes": [{"index": 1, "materiality": "borderline"}]}'
        [r] = _parse_batch_response(content, 1)
        assert r.status == "failed"
        assert r.materiality is None

    def test_missing_answer_is_failed(self):
        content = '{"changes": [{"index": 1}]}'
        [r] = _parse_batch_response(content, 1)
        assert r.status == "failed" and r.materiality is None

    def test_short_response_pads_with_failed_not_immaterial(self):
        content = (
            '{"changes": [{"index": 1, "materiality": "immaterial", '
            '"materiality_reason": "Redaksional"}]}'
        )
        results = _parse_batch_response(content, 3)
        assert len(results) == 3
        assert results[0].status == "ok"
        assert all(r.status == "failed" and r.materiality is None for r in results[1:])

    def test_garbage_response_is_all_failed(self):
        results = _parse_batch_response("bukan JSON sama sekali", 2)
        assert all(r.status == "failed" and r.materiality is None for r in results)

    def test_no_result_ever_pairs_failed_with_a_value(self):
        """The DB CHECK invariant, asserted at the source: failed ⇔ NULL."""
        for content in [
            "garbage",
            '{"changes": []}',
            '{"changes": [{"materiality": "material", "materiality_reason": "x"}]}',
            '{"changes": [{"materiality": "unknown_value"}]}',
        ]:
            for r in _parse_batch_response(content, 2):
                assert (r.status == "failed") == (r.materiality is None)


# ── LC-34 / LC-30: finding_type & severity — never coerced ────────────────────

class _FakeCompletion:
    input_tokens = 10
    output_tokens = 5
    model = "test-model"


class TestDomainResultNoCoercion:
    def _raw(self, **overrides):
        raw = {
            "finding_type": "present_risky",
            "severity": "high",
            "summary": "Temuan uji",
            "rationale": "Alasan uji",
        }
        raw.update(overrides)
        return raw

    def test_valid_result_parses(self):
        r = _parse_domain_result(self._raw(), _FakeCompletion())
        assert r.finding_type == "present_risky" and r.severity == "high"

    def test_invalid_finding_type_raises_not_none(self):
        with pytest.raises(ValueError):
            _parse_domain_result(self._raw(finding_type="weird"), _FakeCompletion())

    def test_missing_finding_type_raises(self):
        raw = self._raw()
        del raw["finding_type"]
        with pytest.raises(ValueError):
            _parse_domain_result(raw, _FakeCompletion())

    def test_invalid_severity_raises_not_info(self):
        with pytest.raises(ValueError):
            _parse_domain_result(self._raw(severity="catastrophic"), _FakeCompletion())


# ── LC-35: summary — failure is never a raw text slice ────────────────────────

class TestSummaryUnknownState:
    def test_failed_summary_returns_none_failed(self, monkeypatch):
        class _FailingClient:
            def chat_complete(self, *a, **kw):
                raise RuntimeError("provider down")

        monkeypatch.setattr(
            "landy.analysis.pipeline.get_llm_client", lambda: _FailingClient()
        )
        clauses = [ClauseRow(id="c1", ordinal=1, heading_path=None, text="Pasal 1. Uji.")]
        summary, status = _build_summary(clauses, {})
        assert status == "failed"
        assert summary is None  # never sample_text[:500]

    def test_empty_document_is_ok_with_honest_text(self):
        summary, status = _build_summary([], {})
        assert status == "ok"
        assert summary and "tidak memiliki klausul" in summary
